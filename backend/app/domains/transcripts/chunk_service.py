from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid6 import uuid7

from app.domains.transcripts.chunker import (
    CHUNKING_VERSION,
    NORMALIZATION_VERSION,
    ChunkableSegment,
    ChunkDraft,
    chunk_segments,
)
from app.domains.transcripts.embedding_service import (
    create_embed_job_for_chunk_success,
    mark_embed_enqueue_failed,
)
from app.platform.db.models import IngestionJob, Transcript, TranscriptChunk, TranscriptSegment
from app.platform.db.session import async_session
from app.platform.faults.pipeline_faults import maybe_fail_step
from app.workers.queues import enqueue_embed_transcript


logger = logging.getLogger(__name__)

CHUNK_JOB_TYPE = "chunk"
CHUNK_PROCESSOR_VERSION = CHUNKING_VERSION
PRECONDITION_PARSE_NOT_COMPLETED = "precondition_not_met_parse_not_completed"


class TranscriptChunkError(RuntimeError):
    pass


async def create_chunk_job_for_parse_success(
    session: AsyncSession,
    *,
    transcript: Transcript,
    parse_job: IngestionJob,
) -> UUID | None:
    if parse_job.processor_version is None:
        raise TranscriptChunkError("completed parse job is missing processor version")

    idempotency_key = _chunk_idempotency_key(
        transcript=transcript,
        parser_version=parse_job.processor_version,
    )
    await session.execute(
        insert(IngestionJob)
        .values(
            id=uuid7(),
            transcript_id=transcript.id,
            job_type=CHUNK_JOB_TYPE,
            status="queued",
            idempotency_key=idempotency_key,
            processor_version=CHUNK_PROCESSOR_VERSION,
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
    if job.status == "completed":
        return None
    return job.id


async def chunk_transcript_async(
    ingestion_job_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    try:
        async with factory() as session:
            embed_job_id = await _persist_chunks(session, ingestion_job_id=ingestion_job_id)
        if embed_job_id is not None:
            try:
                enqueue_embed_transcript(embed_job_id)
            except Exception as enqueue_exc:
                async with factory() as session:
                    async with session.begin():
                        await mark_embed_enqueue_failed(
                            session,
                            embed_job_id=embed_job_id,
                            exc=enqueue_exc,
                        )
    except Exception as exc:
        async with factory() as session:
            await _persist_failure(session, ingestion_job_id=ingestion_job_id, exc=exc)


async def _persist_chunks(
    session: AsyncSession,
    *,
    ingestion_job_id: UUID,
) -> UUID | None:
    async with session.begin():
        job = await _lock_chunk_job(session, ingestion_job_id=ingestion_job_id)
        if job is None:
            return None

        completed_job = await _completed_chunk_job_for_key(
            session,
            idempotency_key=job.idempotency_key,
            exclude_job_id=job.id,
        )
        if completed_job is not None:
            return None

        transcript = (
            await session.execute(
                select(Transcript)
                .where(Transcript.id == job.transcript_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if transcript is None:
            raise TranscriptChunkError("transcript not found")
        if transcript.lifecycle_state == "superseded":
            # Fenced before any mutation: do not chunk a superseded transcript (ADR-46-B §3.2).
            return None

        now = _now()
        job.status = "running"
        job.attempts += 1
        job.started_at = now
        job.completed_at = None
        job.updated_at = now
        job.error_message = None
        job.result_metadata = None

        parse_job = await _completed_parse_job(session, transcript_id=transcript.id)
        if parse_job is None:
            job.status = "failed"
            job.error_message = PRECONDITION_PARSE_NOT_COMPLETED
            job.updated_at = now
            return None

        maybe_fail_step("chunk")

        segments = (
            await session.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptSegment.sequence_number)
            )
        ).scalars().all()
        result = chunk_segments(
            [
                ChunkableSegment(
                    id=segment.id,
                    transcript_id=segment.transcript_id,
                    sequence_number=segment.sequence_number,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text,
                )
                for segment in segments
            ]
        )

        await session.execute(
            delete(TranscriptChunk).where(TranscriptChunk.transcript_id == transcript.id)
        )
        session.add_all(
            [
                _chunk_model(
                    transcript_id=transcript.id,
                    draft=draft,
                    segments=segments,
                    created_by_ingestion_job_id=job.id,
                )
                for draft in result.chunks
            ]
        )
        transcript.status = "completed"
        transcript.updated_at = now
        job.status = "completed"
        job.completed_at = now
        job.updated_at = now
        job.error_message = None
        job.result_metadata = {
            "chunk_count": len(result.chunks),
            "oversized_segment_count": result.oversized_segment_count,
        }
        return await create_embed_job_for_chunk_success(
            session,
            transcript=transcript,
            chunk_job=job,
        )


async def _persist_failure(
    session: AsyncSession,
    *,
    ingestion_job_id: UUID,
    exc: Exception,
) -> None:
    sanitized = _sanitize_error(exc)
    async with session.begin():
        job = (
            await session.execute(
                select(IngestionJob)
                .where(
                    IngestionJob.id == ingestion_job_id,
                    IngestionJob.job_type == CHUNK_JOB_TYPE,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if job is None or job.status == "completed":
            return

        transcript = (
            await session.execute(
                select(Transcript)
                .where(Transcript.id == job.transcript_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if transcript is not None and transcript.lifecycle_state == "superseded":
            # Fenced: do not fail a superseded transcript's pipeline (ADR-46-B §3.2).
            return
        now = _now()
        if transcript is not None:
            transcript.status = "failed"
            transcript.updated_at = now
        job.status = "failed"
        job.error_message = sanitized
        job.failure_category = "chunk_failed"
        job.updated_at = now
        logger.warning(
            "Chunk job failed",
            extra={
                "transcript_id": str(job.transcript_id),
                "job_id": str(job.id),
                "job_type": CHUNK_JOB_TYPE,
                "reason": sanitized,
            },
        )


async def _lock_chunk_job(
    session: AsyncSession,
    *,
    ingestion_job_id: UUID,
) -> IngestionJob | None:
    job = (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.id == ingestion_job_id,
                IngestionJob.job_type == CHUNK_JOB_TYPE,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None or job.status in {"completed", "running"}:
        return None
    return job


async def _completed_chunk_job_for_key(
    session: AsyncSession,
    *,
    idempotency_key: str,
    exclude_job_id: UUID,
) -> IngestionJob | None:
    return (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.idempotency_key == idempotency_key,
                IngestionJob.id != exclude_job_id,
                IngestionJob.job_type == CHUNK_JOB_TYPE,
                IngestionJob.status == "completed",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()


async def _completed_parse_job(
    session: AsyncSession,
    *,
    transcript_id: UUID,
) -> IngestionJob | None:
    return (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type == "parse",
                IngestionJob.status == "completed",
            )
            .order_by(IngestionJob.completed_at.desc().nullslast(), IngestionJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _chunk_model(
    *,
    transcript_id: UUID,
    draft: ChunkDraft,
    segments: list[TranscriptSegment],
    created_by_ingestion_job_id: UUID,
) -> TranscriptChunk:
    segment_transcripts = {
        segment.id: segment.transcript_id
        for segment in segments
        if segment.id in {draft.start_segment_id, draft.end_segment_id}
    }
    if segment_transcripts.get(draft.start_segment_id) != transcript_id:
        raise TranscriptChunkError("chunk start segment transcript mismatch")
    if segment_transcripts.get(draft.end_segment_id) != transcript_id:
        raise TranscriptChunkError("chunk end segment transcript mismatch")
    payload = asdict(draft)
    payload.pop("start_time")
    payload.pop("end_time")
    # Stamp the chunk-creating job. Embed later writes the vector and stamps
    # embedding_created_by_ingestion_job_id SEPARATELY — it must never overwrite this column.
    return TranscriptChunk(
        transcript_id=transcript_id,
        start_time=draft.start_time,
        end_time=draft.end_time,
        created_by_ingestion_job_id=created_by_ingestion_job_id,
        **payload,
    )


def _chunk_idempotency_key(
    *,
    transcript: Transcript,
    parser_version: str,
) -> str:
    return (
        f"{transcript.id}:chunk:{transcript.checksum}:"
        f"{parser_version}:{NORMALIZATION_VERSION}:{CHUNKING_VERSION}"
    )


def _sanitize_error(exc: Exception) -> str:
    if isinstance(exc, TranscriptChunkError):
        return str(exc)
    return "transcript chunk failed"


def _now() -> datetime:
    return datetime.now(UTC)
