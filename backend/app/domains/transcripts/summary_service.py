"""Summary generation job handlers (spec §6/§7/§8/§11).

After embeddings complete, two IngestionJob rows (``generate_brief_summary``,
``generate_detailed_summary``) are created in the embed transaction and enqueued onto the ``ai``
queue. Each handler loads the full normalized transcript, calls ``LLMGateway.complete`` (which owns
logging, limiting, validation), and on success stores a ``GeneratedLectureSummary`` whose provenance
is copied directly from the gateway's AIRequestLog row. On failure it writes no artifact and records
``IngestionJob.failure_category`` — the transcript itself is NOT failed (embeddings succeeded; the
projection represents per-step failure). This is the exact contract Stage 4.6's retry consumes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid6 import uuid7

from app.domains.transcripts.chunker import NORMALIZATION_VERSION, normalize_segment_text
from app.platform.db.models import (
    AIRequestLog,
    GeneratedLectureSummary,
    IngestionJob,
    ModuleSection,
    Transcript,
    TranscriptSegment,
)
from app.platform.db.session import async_session
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.prompt import PromptKey, SummaryFeature
from app.platform.llm.models.summary import (
    BRIEF_SCHEMA_VERSION,
    DETAILED_SCHEMA_VERSION,
    BriefSummary,
    DetailedSummary,
)

logger = logging.getLogger(__name__)

# Failures that warrant an RQ retry (rule 15: reserved for transient + bounded invalid_output).
RQ_RETRY_STATUSES = {"provider_transient", "invalid_output"}
_FAILURE_CATEGORIES = {"provider_transient", "rate_limited", "invalid_output", "invalid_input"}


class SummaryGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SummarySpec:
    job_type: str
    feature: SummaryFeature
    prompt_key: PromptKey
    output_schema: type[BriefSummary] | type[DetailedSummary]
    summary_type: str
    content_schema_version: str


BRIEF = SummarySpec(
    job_type="generate_brief_summary",
    feature="summary_brief",
    prompt_key=PromptKey("brief_summary", "v1"),
    output_schema=BriefSummary,
    summary_type="brief",
    content_schema_version=BRIEF_SCHEMA_VERSION,
)
DETAILED = SummarySpec(
    job_type="generate_detailed_summary",
    feature="summary_detailed",
    prompt_key=PromptKey("detailed_summary", "v1"),
    output_schema=DetailedSummary,
    summary_type="detailed_study",
    content_schema_version=DETAILED_SCHEMA_VERSION,
)
SUMMARY_SPECS: dict[str, SummarySpec] = {BRIEF.job_type: BRIEF, DETAILED.job_type: DETAILED}
SUMMARY_JOB_TYPES = tuple(SUMMARY_SPECS)


@dataclass(frozen=True)
class _SummaryContext:
    transcript_id: UUID
    module_section_id: UUID
    source_transcript_checksum: str
    section_type: str
    normalized_text: str
    input_hash: str
    attempts: int


def _now() -> datetime:
    return datetime.now(UTC)


def _summary_idempotency_key(transcript: Transcript, job_type: str) -> str:
    return f"{transcript.id}:{job_type}:{transcript.checksum}"


def _normalized_transcript(segments: list[TranscriptSegment]) -> str:
    parts = [normalize_segment_text(segment.text) for segment in segments]
    return " ".join(part for part in parts if part).strip()


def _summary_input_hash(normalized_text: str) -> str:
    payload = {"normalizationVersion": NORMALIZATION_VERSION, "text": normalized_text}
    canonical = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def insert_summary_jobs(
    session: AsyncSession,
    *,
    transcript: Transcript,
) -> list[tuple[str, UUID]]:
    """Create the two summary jobs (queued) within the caller's transaction (the embed txn).

    Returns the (job_type, job_id) pairs that should be enqueued. Idempotent: an already-active or
    completed job is not duplicated; a previously failed job is reset to queued.
    """
    to_enqueue: list[tuple[str, UUID]] = []
    for spec in SUMMARY_SPECS.values():
        job_id = await _ensure_summary_job(session, transcript=transcript, spec=spec)
        if job_id is not None:
            to_enqueue.append((spec.job_type, job_id))
    return to_enqueue


async def _ensure_summary_job(
    session: AsyncSession,
    *,
    transcript: Transcript,
    spec: SummarySpec,
) -> UUID | None:
    active = await _active_summary_job(session, transcript_id=transcript.id, job_type=spec.job_type)
    if active is not None:
        return active.id

    idempotency_key = _summary_idempotency_key(transcript, spec.job_type)
    try:
        async with session.begin_nested():
            await session.execute(
                pg_insert(IngestionJob)
                .values(
                    id=uuid7(),
                    transcript_id=transcript.id,
                    job_type=spec.job_type,
                    status="queued",
                    idempotency_key=idempotency_key,
                    processor_version=str(spec.prompt_key),
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
    except IntegrityError:
        # A concurrent writer won the one-active-summary index; re-read below.
        pass

    active = await _active_summary_job(session, transcript_id=transcript.id, job_type=spec.job_type)
    if active is not None:
        return active.id

    job = (
        await session.execute(
            select(IngestionJob)
            .where(IngestionJob.idempotency_key == idempotency_key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    if job.status == "completed":
        return None
    if job.status == "failed":
        now = _now()
        job.status = "queued"
        job.error_message = None
        job.failure_category = None
        job.updated_at = now
    return job.id


async def _active_summary_job(
    session: AsyncSession,
    *,
    transcript_id: UUID,
    job_type: str,
) -> IngestionJob | None:
    return (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type == job_type,
                IngestionJob.status.in_(("queued", "running")),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()


async def generate_brief_summary_async(
    ingestion_job_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    await _generate_summary_async(
        ingestion_job_id, spec=BRIEF, gateway=gateway, session_factory=session_factory
    )


async def generate_detailed_summary_async(
    ingestion_job_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    await _generate_summary_async(
        ingestion_job_id, spec=DETAILED, gateway=gateway, session_factory=session_factory
    )


async def _generate_summary_async(
    ingestion_job_id: UUID,
    *,
    spec: SummarySpec,
    gateway: LLMGateway | None,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim_summary_job(factory, ingestion_job_id=ingestion_job_id, spec=spec)
    if context is None:
        return

    try:
        result = await active_gateway.complete(
            prompt_key=spec.prompt_key,
            output_schema=spec.output_schema,
            context_refs=ContextRefs(
                ingestion_job_id=ingestion_job_id,
                transcript_text=context.normalized_text,
                input_content_hash=context.input_hash,
                section_type=context.section_type,
            ),
            priority="background",
            feature=spec.feature,
            attempt_number=context.attempts,
        )
    except GatewayError as exc:
        await _mark_summary_failed(
            factory,
            ingestion_job_id=ingestion_job_id,
            spec=spec,
            status=exc.status,
            error_message=_sanitize_error(exc),
        )
        if exc.status in RQ_RETRY_STATUSES:
            raise  # bounded RQ retry
        return
    except Exception as exc:  # pragma: no cover - defensive
        await _mark_summary_failed(
            factory,
            ingestion_job_id=ingestion_job_id,
            spec=spec,
            status="failed",
            error_message="summary generation failed",
        )
        raise SummaryGenerationError(str(exc)) from None

    await _persist_summary_success(
        factory, ingestion_job_id=ingestion_job_id, spec=spec, context=context, result=result
    )


async def _claim_summary_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    spec: SummarySpec,
) -> _SummaryContext | None:
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == spec.job_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or job.status == "completed":
                return None

            now = _now()
            job.status = "running"
            job.attempts += 1
            job.started_at = now
            job.completed_at = None
            job.updated_at = now
            job.error_message = None
            job.failure_category = None

            transcript = (
                await session.execute(
                    select(Transcript).where(Transcript.id == job.transcript_id)
                )
            ).scalar_one_or_none()
            if transcript is None:
                raise SummaryGenerationError("transcript not found")

            section = (
                await session.execute(
                    select(ModuleSection).where(
                        ModuleSection.id == transcript.module_section_id
                    )
                )
            ).scalar_one_or_none()
            if section is None:
                raise SummaryGenerationError("module section not found")

            segments = (
                await session.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.transcript_id == transcript.id)
                    .order_by(TranscriptSegment.sequence_number)
                )
            ).scalars().all()
            normalized = _normalized_transcript(list(segments))
            if not normalized:
                raise SummaryGenerationError("no transcript text available")

            return _SummaryContext(
                transcript_id=transcript.id,
                module_section_id=transcript.module_section_id,
                source_transcript_checksum=transcript.checksum,
                section_type=section.type,
                normalized_text=normalized,
                input_hash=_summary_input_hash(normalized),
                attempts=job.attempts,
            )


async def _persist_summary_success(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    spec: SummarySpec,
    context: _SummaryContext,
    result: dict,
) -> None:
    content_json = result["parsed"].model_dump(by_alias=True)
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == spec.job_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or job.status != "running":
                return

            log = await session.get(AIRequestLog, result["ai_request_log_id"])
            if log is None:  # pragma: no cover - defensive
                raise SummaryGenerationError("AIRequestLog row missing for generated summary")

            await session.execute(
                pg_insert(GeneratedLectureSummary)
                .values(
                    id=uuid7(),
                    transcript_id=context.transcript_id,
                    module_section_id=context.module_section_id,
                    summary_type=spec.summary_type,
                    content_json=content_json,
                    content_schema_version=spec.content_schema_version,
                    model_id=log.model_id,
                    prompt_version=log.prompt_version,
                    prompt_content_hash=log.prompt_content_hash,
                    backend_used=log.backend_used,
                    reasoning_level=log.reasoning_level,
                    source_transcript_checksum=context.source_transcript_checksum,
                    input_hash=context.input_hash,
                    ai_request_log_id=log.id,
                )
                .on_conflict_do_nothing(constraint="uq_gen_summaries_provenance")
            )

            now = _now()
            job.status = "completed"
            job.completed_at = now
            job.updated_at = now
            job.error_message = None
            job.failure_category = None
            job.result_metadata = {
                "summary_type": spec.summary_type,
                "ai_request_log_id": str(log.id),
                "backend_used": log.backend_used,
            }


async def _mark_summary_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    spec: SummarySpec,
    status: str,
    error_message: str,
) -> None:
    failure_category = status if status in _FAILURE_CATEGORIES else "failed"
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == spec.job_type,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or job.status == "completed":
                return
            now = _now()
            job.status = "failed"
            job.error_message = error_message
            job.failure_category = failure_category
            job.updated_at = now
            # The transcript is NOT failed — embeddings succeeded; per-step failure is shown
            # by the status projection (spec §7.4).
    logger.warning(
        "Summary job failed",
        extra={
            "ingestion_job_id": str(ingestion_job_id),
            "job_type": spec.job_type,
            "failure_category": failure_category,
        },
    )


def _sanitize_error(exc: GatewayError) -> str:
    code = f" ({exc.error_code})" if exc.error_code else ""
    return f"{exc.status}{code}"
