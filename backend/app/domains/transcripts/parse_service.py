from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid6 import uuid7

from app.domains.transcripts.chunk_service import create_chunk_job_for_parse_success
from app.domains.transcripts.fencing import can_commit_step
from app.domains.transcripts.parsers import ParsedSegment, route_and_parse
from app.domains.transcripts.parsers.timestamps import validate_range
from app.domains.transcripts.parsers.types import TranscriptParseError
from app.platform.db.models import (
    GeneratedLectureSummary,
    IngestionJob,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)
from app.platform.db.session import async_session
from app.platform.faults.pipeline_faults import maybe_fail_step
from app.platform.storage.base import (
    StorageObjectNotFoundError,
    StorageProvider,
    StorageProviderError,
    StorageUnavailableError,
)
from app.platform.storage.supabase import get_storage_provider
from app.workers.queues import enqueue_chunk_transcript, enqueue_summary_job


logger = logging.getLogger(__name__)

PARSE_JOB_TYPE = "parse"
PARSE_PROCESSOR_VERSION = "parse:v1"


@dataclass(frozen=True)
class ParseClaim:
    transcript_id: UUID
    storage_key: str
    mime_type: str
    idempotency_key: str
    claimed_attempt: int
    job_id: UUID


@dataclass(frozen=True)
class _ParsePersistResult:
    # After-commit work parse owns (matrix: parse re-enqueues chunk, brief, detailed — summaries fork
    # from parse, NOT embed, so an embed failure never blocks summaries; ADR-46-B).
    chunk_job_id: UUID | None
    summary_jobs: list[tuple[str, UUID]]


async def parse_transcript_async(
    transcript_id: UUID,
    *,
    storage_provider: StorageProvider | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    storage = storage_provider or await get_storage_provider()

    async with factory() as session:
        claim = await _claim_parse_job(session, transcript_id=transcript_id)
    if claim is None:
        return

    try:
        maybe_fail_step("parse")
        raw_bytes = await storage.get_object(key=claim.storage_key)
        parsed_segments = route_and_parse(raw_bytes, mime_type=claim.mime_type)
        persisted_segments = _prepare_persisted_segments(parsed_segments)
        if not persisted_segments:
            raise TranscriptParseError("no parsable content")
        async with factory() as session:
            result = await _persist_success(
                session,
                claim=claim,
                segments=persisted_segments,
            )
        if result is not None:
            _enqueue_after_parse(claim, result)
    except Exception as exc:
        async with factory() as session:
            await _persist_failure(session, claim=claim, exc=exc)


def _enqueue_after_parse(claim: ParseClaim, result: _ParsePersistResult) -> None:
    if result.chunk_job_id is not None:
        try:
            enqueue_chunk_transcript(result.chunk_job_id)
        except Exception:
            logger.warning(
                "Failed to enqueue transcript chunk job",
                extra={
                    "transcript_id": str(claim.transcript_id),
                    "job_id": str(result.chunk_job_id),
                    "job_type": "chunk",
                },
            )
    for job_type, job_id in result.summary_jobs:
        try:
            enqueue_summary_job(job_type, job_id)
        except Exception:
            # §8 resilience gap: leave 'queued' for the sweeper; do NOT mark failed.
            logger.warning(
                "Failed to enqueue summary job after parse; left queued",
                extra={
                    "transcript_id": str(claim.transcript_id),
                    "ingestion_job_id": str(job_id),
                    "job_type": job_type,
                },
            )


async def _claim_parse_job(
    session: AsyncSession,
    *,
    transcript_id: UUID,
) -> ParseClaim | None:
    async with session.begin():
        transcript = (
            await session.execute(
                select(Transcript)
                .where(Transcript.id == transcript_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if transcript is None:
            logger.warning(
                "Parse job skipped because transcript was not found",
                extra={"transcript_id": str(transcript_id), "job_type": PARSE_JOB_TYPE},
            )
            return None

        idempotency_key = _idempotency_key(transcript)
        await session.execute(
            insert(IngestionJob)
            .values(
                id=uuid7(),
                transcript_id=transcript.id,
                job_type=PARSE_JOB_TYPE,
                status="queued",
                idempotency_key=idempotency_key,
                processor_version=PARSE_PROCESSOR_VERSION,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )

        job = (
            await session.execute(
                select(IngestionJob)
                .where(IngestionJob.idempotency_key == idempotency_key)
                .with_for_update()
            )
        ).scalar_one()

        if job.status in {"completed", "running"}:
            return None

        claimed_attempt = job.attempts + 1
        now = _now()
        job.status = "running"
        job.attempts = claimed_attempt
        job.started_at = now
        job.completed_at = None
        job.updated_at = now
        job.error_message = None
        transcript.status = "parsing"
        transcript.updated_at = now
        return ParseClaim(
            transcript_id=transcript.id,
            storage_key=transcript.storage_key,
            mime_type=transcript.mime_type,
            idempotency_key=idempotency_key,
            claimed_attempt=claimed_attempt,
            job_id=job.id,
        )


async def _persist_success(
    session: AsyncSession,
    *,
    claim: ParseClaim,
    segments: list[ParsedSegment],
) -> _ParsePersistResult | None:
    from app.domains.transcripts.summary_service import insert_summary_jobs

    async with session.begin():
        job = await _lock_owned_job(session, claim)
        if job is None:
            return None

        transcript = (
            await session.execute(
                select(Transcript)
                .where(Transcript.id == claim.transcript_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if not can_commit_step(job=job, transcript=transcript):
            # Fenced: stale attempt or superseded transcript — write/enqueue nothing (ADR-46-B §3.2).
            return None

        # Parse owns segments, but a re-parse invalidates ALL downstream output. Delete in FK order:
        # summaries → chunks → segments (chunks reference segment ids; deleting segments first would
        # trip the RESTRICT FK). On a first parse these are no-op deletes.
        await session.execute(
            delete(GeneratedLectureSummary).where(
                GeneratedLectureSummary.transcript_id == claim.transcript_id
            )
        )
        await session.execute(
            delete(TranscriptChunk).where(TranscriptChunk.transcript_id == claim.transcript_id)
        )
        await session.execute(
            delete(TranscriptSegment).where(TranscriptSegment.transcript_id == claim.transcript_id)
        )
        session.add_all(
            [
                TranscriptSegment(
                    transcript_id=claim.transcript_id,
                    sequence_number=sequence_number,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    speaker_name=segment.speaker_name,
                    text=segment.text,
                    created_by_ingestion_job_id=job.id,
                )
                for sequence_number, segment in enumerate(segments)
            ]
        )
        now = _now()
        job.status = "completed"
        job.completed_at = now
        job.updated_at = now
        job.error_message = None
        job.failure_category = None
        chunk_job_id = await create_chunk_job_for_parse_success(
            session,
            transcript=transcript,
            parse_job=job,
        )
        # Summaries fork from parse (normalized text from segments), independent of chunk/embed.
        summary_jobs = await insert_summary_jobs(session, transcript=transcript)
        return _ParsePersistResult(chunk_job_id=chunk_job_id, summary_jobs=summary_jobs)


async def _persist_failure(
    session: AsyncSession,
    *,
    claim: ParseClaim,
    exc: Exception,
) -> None:
    sanitized_message, failure_category = _classify_failure(exc)
    async with session.begin():
        job = await _lock_owned_job(session, claim)
        if job is None:
            return

        transcript = (
            await session.execute(
                select(Transcript)
                .where(Transcript.id == claim.transcript_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if transcript is None or transcript.lifecycle_state == "superseded":
            # Fenced: do not mark a superseded transcript's pipeline failed (ADR-46-B §3.2).
            return

        await session.execute(
            delete(TranscriptSegment).where(TranscriptSegment.transcript_id == claim.transcript_id)
        )
        now = _now()
        transcript.status = "failed"
        transcript.updated_at = now
        job.status = "failed"
        job.error_message = sanitized_message
        job.failure_category = failure_category
        job.updated_at = now
        logger.warning(
            "Parse job failed",
            extra={
                "transcript_id": str(claim.transcript_id),
                "job_id": str(claim.job_id),
                "job_type": PARSE_JOB_TYPE,
                "reason": sanitized_message,
                "failure_category": failure_category,
            },
        )


async def _lock_owned_job(
    session: AsyncSession,
    claim: ParseClaim,
) -> IngestionJob | None:
    job = (
        await session.execute(
            select(IngestionJob)
            .where(IngestionJob.idempotency_key == claim.idempotency_key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None or job.status != "running" or job.attempts != claim.claimed_attempt:
        return None
    return job


def _prepare_persisted_segments(segments: list[ParsedSegment]) -> list[ParsedSegment]:
    persisted: list[ParsedSegment] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        validate_range(segment.start_ms, segment.end_ms)
        persisted.append(
            ParsedSegment(
                text=text,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                speaker_name=segment.speaker_name.strip() if segment.speaker_name else None,
            )
        )
    return persisted


def _idempotency_key(transcript: Transcript) -> str:
    return f"{PARSE_JOB_TYPE}:{transcript.id}:{transcript.checksum}"


def _classify_failure(exc: Exception) -> tuple[str, str]:
    """Return (sanitized internal message, sanitized failure_category).

    A missing raw object is the terminal ``storage_missing`` condition (distinct on purpose — it is
    the same condition reconciliation reports and must not be buried under parse_failed). All other
    parse-time errors are content/format failures within an already-validated file type → ``parse_failed``
    (genuinely unsupported file types are rejected at upload with 422, before any parse job exists).
    StorageObjectNotFoundError / StorageUnavailableError subclass StorageProviderError — order matters.
    """
    if isinstance(exc, StorageObjectNotFoundError):
        return "storage object not found", "storage_missing"
    if isinstance(exc, StorageUnavailableError):
        return "storage provider unavailable", "parse_failed"
    if isinstance(exc, StorageProviderError):
        return "storage provider failed", "parse_failed"
    if isinstance(exc, TranscriptParseError):
        return str(exc), "parse_failed"
    return "transcript parse failed", "parse_failed"


def _now() -> datetime:
    return datetime.now(UTC)
