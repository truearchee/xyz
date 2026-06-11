from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from uuid6 import uuid7

from app.domains.transcripts.embedding_encoder import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_NORMALIZATION,
    EMBEDDING_VERSION,
    EmbeddingConfigurationError,
    EmbeddingEncoder,
    SentenceTransformersEmbeddingEncoder,
)
from app.domains.transcripts.activation import attempt_pending_activation
from app.domains.transcripts.fencing import can_commit_step
from app.platform.config import settings
from app.platform.db.models import IngestionJob, Transcript, TranscriptChunk
from app.platform.db.session import async_session
from app.platform.faults.pipeline_faults import maybe_fail_step


logger = logging.getLogger(__name__)

EMBED_JOB_TYPE = "embed"
EMBED_PROCESSOR_VERSION = EMBEDDING_VERSION
EMBED_ENQUEUE_FAILED = "transcript embedding enqueue failed"


class TranscriptEmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True)
class StaleChunk:
    id: UUID
    text: str
    input_hash: str


async def create_embed_job_for_chunk_success(
    session: AsyncSession,
    *,
    transcript: Transcript,
    chunk_job: IngestionJob,
) -> UUID | None:
    if chunk_job.processor_version is None:
        raise TranscriptEmbeddingError("completed chunk job is missing processor version")

    active_job = (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.transcript_id == transcript.id,
                IngestionJob.job_type == EMBED_JOB_TYPE,
                IngestionJob.status.in_(("queued", "running")),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if active_job is not None:
        return active_job.id

    idempotency_key = _embed_idempotency_key(
        transcript=transcript,
        chunk_processor_version=chunk_job.processor_version,
    )
    try:
        async with session.begin_nested():
            await session.execute(
                insert(IngestionJob)
                .values(
                    id=uuid7(),
                    transcript_id=transcript.id,
                    job_type=EMBED_JOB_TYPE,
                    status="queued",
                    idempotency_key=idempotency_key,
                    processor_version=EMBED_PROCESSOR_VERSION,
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
    except IntegrityError:
        # A concurrent chunk replacement can win the embed-only active-job index
        # with a different idempotency key. Re-read the active row below.
        pass
    active_job = (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.transcript_id == transcript.id,
                IngestionJob.job_type == EMBED_JOB_TYPE,
                IngestionJob.status.in_(("queued", "running")),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if active_job is not None:
        return active_job.id
    job = (
        await session.execute(
            select(IngestionJob)
            .where(IngestionJob.idempotency_key == idempotency_key)
            .with_for_update()
        )
    ).scalar_one()
    if job.status == "completed":
        return None
    if job.status == "failed":
        now = _now()
        job.status = "queued"
        job.error_message = None
        job.updated_at = now
    return job.id


async def embed_transcript_async(
    ingestion_job_id: UUID,
    *,
    encoder: EmbeddingEncoder | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    batch_size: int | None = None,
    model_revision: str | None = None,
    raise_on_failure: bool = False,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    revision = model_revision or settings.EMBEDDING_MODEL_REVISION
    active_encoder = encoder or SentenceTransformersEmbeddingEncoder(
        model_path=settings.EMBEDDING_MODEL_PATH,
        expected_revision=revision,
        device=settings.EMBEDDING_DEVICE,
    )
    size = batch_size or settings.EMBEDDING_BATCH_SIZE

    try:
        transcript_id = await _claim_embed_job(factory, ingestion_job_id=ingestion_job_id)
        if transcript_id is None:
            return
        maybe_fail_step("embed")
        while True:
            stale_chunks = await _next_stale_batch(
                factory,
                transcript_id=transcript_id,
                batch_size=size,
                model_revision=revision,
            )
            if not stale_chunks:
                break
            vectors = active_encoder.encode([chunk.text for chunk in stale_chunks])
            await _persist_embedding_batch(
                factory,
                ingestion_job_id=ingestion_job_id,
                stale_chunks=stale_chunks,
                vectors=vectors,
                model_revision=revision,
            )
        await _persist_success(
            factory,
            ingestion_job_id=ingestion_job_id,
            transcript_id=transcript_id,
            model_revision=revision,
        )
    except Exception as exc:
        await _persist_failure(factory, ingestion_job_id=ingestion_job_id, exc=exc)
        if raise_on_failure:
            raise TranscriptEmbeddingError(_sanitize_error(exc)) from None
        return
    # 4.6b (ADR-46-B): summaries fork from PARSE, not embed — embed no longer creates/enqueues them,
    # so an embed failure cannot block summaries. Embed still gates overall_state=='summarized' via the
    # projection (embed + brief + detailed all completed).
    # 4.6b-F2 (F-4.6b-2): embed is a pipeline LEAF that can finish last (it runs parallel to summaries),
    # so it too must attempt activation of a completed pending replacement — otherwise an embed-finishes-
    # last race leaves the pending stuck. Idempotent + best-effort; no-op until fully summarized.
    await attempt_pending_activation(factory, transcript_id=transcript_id)


async def mark_embed_enqueue_failed(
    session: AsyncSession,
    *,
    embed_job_id: UUID,
    exc: Exception,
) -> None:
    job = (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.id == embed_job_id,
                IngestionJob.job_type == EMBED_JOB_TYPE,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None or job.status == "completed":
        return
    now = _now()
    job.status = "failed"
    job.error_message = EMBED_ENQUEUE_FAILED
    job.updated_at = now
    transcript = (
        await session.execute(
            select(Transcript)
            .where(Transcript.id == job.transcript_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if transcript is not None:
        transcript.status = "failed"
        transcript.updated_at = now
    logger.warning(
        "Failed to enqueue transcript embed job",
        extra={
            "job_id": str(embed_job_id),
            "job_type": EMBED_JOB_TYPE,
            "reason": EMBED_ENQUEUE_FAILED,
            "exception_type": type(exc).__name__,
        },
    )


async def _claim_embed_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
) -> UUID | None:
    async with factory() as session:
        async with session.begin():
            job = await _lock_embed_job(session, ingestion_job_id=ingestion_job_id)
            if job is None:
                return None

            transcript = (
                await session.execute(
                    select(Transcript)
                    .where(Transcript.id == job.transcript_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if transcript is None:
                raise TranscriptEmbeddingError("transcript not found")
            if transcript.lifecycle_state == "superseded":
                # Fenced before any mutation: do not embed a superseded transcript (ADR-46-B §3.2).
                return None

            now = _now()
            job.status = "running"
            job.attempts += 1
            job.started_at = now
            job.completed_at = None
            job.updated_at = now
            job.error_message = None
            job.result_metadata = None
            transcript.status = "embedding"
            transcript.updated_at = now

            chunk_count = await _chunk_count(session, transcript_id=transcript.id)
            if chunk_count == 0:
                raise TranscriptEmbeddingError("no transcript chunks available")
            return transcript.id


async def _next_stale_batch(
    factory: async_sessionmaker[AsyncSession],
    *,
    transcript_id: UUID,
    batch_size: int,
    model_revision: str,
) -> list[StaleChunk]:
    async with factory() as session:
        async with session.begin():
            chunks = (
                await session.execute(
                    select(TranscriptChunk)
                    .where(TranscriptChunk.transcript_id == transcript_id)
                    .order_by(TranscriptChunk.chunk_index)
                    .with_for_update(skip_locked=True)
                )
            ).scalars().all()
            stale: list[StaleChunk] = []
            for chunk in chunks:
                _validate_chunk_for_embedding(chunk)
                expected_hash = expected_embedding_input_hash(
                    chunk_text=chunk.text,
                    model_revision=model_revision,
                    chunking_version=chunk.chunking_version,
                )
                if not _chunk_embedding_is_current(
                    chunk,
                    expected_hash=expected_hash,
                    model_revision=model_revision,
                ):
                    stale.append(
                        StaleChunk(
                            id=chunk.id,
                            text=chunk.text,
                            input_hash=expected_hash,
                        )
                    )
                if len(stale) == batch_size:
                    break
            return stale


async def _persist_embedding_batch(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    stale_chunks: list[StaleChunk],
    vectors: list[list[float]],
    model_revision: str,
) -> None:
    if len(vectors) != len(stale_chunks):
        raise TranscriptEmbeddingError("embedding encoder returned wrong batch size")
    stale_by_id = {chunk.id: chunk for chunk in stale_chunks}
    async with factory() as session:
        async with session.begin():
            # Fence each batch write: re-read the job + transcript FOR UPDATE and abort if the job is
            # no longer running or the transcript was superseded, so a stale embed never writes
            # vectors onto rows belonging to a newer attempt (ADR-46-B §3.2).
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == EMBED_JOB_TYPE,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            transcript = (
                await session.execute(
                    select(Transcript).where(Transcript.id == job.transcript_id).with_for_update()
                )
            ).scalar_one_or_none() if job is not None else None
            if job is None or not can_commit_step(job=job, transcript=transcript):
                return

            chunks = (
                await session.execute(
                    select(TranscriptChunk)
                    .where(TranscriptChunk.id.in_(list(stale_by_id)))
                    .with_for_update()
                )
            ).scalars().all()
            vector_by_id = {
                stale_chunks[index].id: vectors[index]
                for index in range(len(stale_chunks))
            }
            now = _now()
            for chunk in chunks:
                stale_chunk = stale_by_id[chunk.id]
                expected_hash = expected_embedding_input_hash(
                    chunk_text=chunk.text,
                    model_revision=model_revision,
                    chunking_version=chunk.chunking_version,
                )
                if _chunk_embedding_is_current(
                    chunk,
                    expected_hash=expected_hash,
                    model_revision=model_revision,
                ):
                    continue
                if expected_hash != stale_chunk.input_hash:
                    continue
                chunk.embedding = vector_by_id[chunk.id]
                chunk.embedding_model = EMBEDDING_MODEL
                chunk.embedding_model_revision = model_revision
                chunk.embedding_dimension = EMBEDDING_DIMENSION
                chunk.embedding_normalization = EMBEDDING_NORMALIZATION
                chunk.embedding_version = EMBEDDING_VERSION
                chunk.embedding_input_hash = expected_hash
                chunk.embedding_generated_at = now
                # Stamp ONLY the embedding-writer job; never touch created_by_ingestion_job_id
                # (that belongs to the chunk job, ADR-46-B §6).
                chunk.embedding_created_by_ingestion_job_id = ingestion_job_id
                chunk.updated_at = now


async def _persist_success(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    transcript_id: UUID,
    model_revision: str,
) -> None:
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == EMBED_JOB_TYPE,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            transcript = (
                await session.execute(
                    select(Transcript)
                    .where(Transcript.id == transcript_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or not can_commit_step(job=job, transcript=transcript):
                # Fenced: stale attempt or superseded transcript — write nothing (ADR-46-B §3.2).
                return

            chunk_count = await _chunk_count(session, transcript_id=transcript_id)
            embedded_chunk_count = await _current_embedding_count(
                session,
                transcript_id=transcript_id,
                model_revision=model_revision,
            )
            if chunk_count == 0:
                raise TranscriptEmbeddingError("no transcript chunks available")
            if embedded_chunk_count != chunk_count:
                raise TranscriptEmbeddingError("embedding job incomplete")

            now = _now()
            transcript.status = "completed"
            transcript.updated_at = now
            job.status = "completed"
            job.completed_at = now
            job.updated_at = now
            job.error_message = None
            job.failure_category = None
            job.result_metadata = {
                "chunk_count": chunk_count,
                "embedded_chunk_count": embedded_chunk_count,
                "embedding_model": EMBEDDING_MODEL,
                "embedding_model_revision": model_revision,
                "embedding_dimension": EMBEDDING_DIMENSION,
                "embedding_normalization": EMBEDDING_NORMALIZATION,
            }
            # 4.6b: summaries are NOT created here anymore — they fork from parse (ADR-46-B).


async def _persist_failure(
    factory: async_sessionmaker[AsyncSession],
    *,
    ingestion_job_id: UUID,
    exc: Exception,
) -> None:
    sanitized = _sanitize_error(exc)
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.id == ingestion_job_id,
                        IngestionJob.job_type == EMBED_JOB_TYPE,
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
            job.failure_category = "embedding_failed"
            job.updated_at = now
            logger.warning(
                "Embed job failed",
                extra={
                    "transcript_id": str(job.transcript_id),
                    "job_id": str(job.id),
                    "job_type": EMBED_JOB_TYPE,
                    "reason": sanitized,
                },
            )


async def _lock_embed_job(
    session: AsyncSession,
    *,
    ingestion_job_id: UUID,
) -> IngestionJob | None:
    job = (
        await session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.id == ingestion_job_id,
                IngestionJob.job_type == EMBED_JOB_TYPE,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None or job.status == "completed":
        return None
    return job


async def _chunk_count(session: AsyncSession, *, transcript_id: UUID) -> int:
    value = (
        await session.execute(
            select(func.count())
            .select_from(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == transcript_id)
        )
    ).scalar_one()
    return int(value)


async def _current_embedding_count(
    session: AsyncSession,
    *,
    transcript_id: UUID,
    model_revision: str,
) -> int:
    chunks = (
        await session.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == transcript_id)
            .order_by(TranscriptChunk.chunk_index)
        )
    ).scalars().all()
    count = 0
    for chunk in chunks:
        _validate_chunk_for_embedding(chunk)
        expected_hash = expected_embedding_input_hash(
            chunk_text=chunk.text,
            model_revision=model_revision,
            chunking_version=chunk.chunking_version,
        )
        if _chunk_embedding_is_current(
            chunk,
            expected_hash=expected_hash,
            model_revision=model_revision,
        ):
            count += 1
    return count


def expected_embedding_input_hash(
    *,
    chunk_text: str,
    model_revision: str,
    chunking_version: str,
    embedding_model: str = EMBEDDING_MODEL,
    embedding_normalization: str = EMBEDDING_NORMALIZATION,
) -> str:
    payload = embedding_hash_payload(
        chunk_text=chunk_text,
        model_revision=model_revision,
        chunking_version=chunking_version,
        embedding_model=embedding_model,
        embedding_normalization=embedding_normalization,
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def embedding_hash_payload(
    *,
    chunk_text: str,
    model_revision: str,
    chunking_version: str,
    embedding_model: str = EMBEDDING_MODEL,
    embedding_normalization: str = EMBEDDING_NORMALIZATION,
) -> dict[str, str]:
    return {
        "chunkText": chunk_text,
        "embeddingModel": embedding_model,
        "embeddingModelRevision": model_revision,
        "embeddingNormalization": embedding_normalization,
        "chunkerVersion": chunking_version,
    }


def _chunk_embedding_is_current(
    chunk: TranscriptChunk,
    *,
    expected_hash: str,
    model_revision: str,
) -> bool:
    return (
        chunk.embedding is not None
        and chunk.embedding_model == EMBEDDING_MODEL
        and chunk.embedding_model_revision == model_revision
        and chunk.embedding_dimension == EMBEDDING_DIMENSION
        and chunk.embedding_normalization == EMBEDDING_NORMALIZATION
        and chunk.embedding_version == EMBEDDING_VERSION
        and chunk.embedding_input_hash == expected_hash
    )


def _validate_chunk_for_embedding(chunk: TranscriptChunk) -> None:
    if not chunk.chunking_version:
        raise TranscriptEmbeddingError("transcript chunk is missing chunking version")
    if not chunk.text.strip():
        raise TranscriptEmbeddingError("transcript chunk text is empty")


def _embed_idempotency_key(
    *,
    transcript: Transcript,
    chunk_processor_version: str,
) -> str:
    return (
        f"{transcript.id}:embed:{transcript.checksum}:"
        f"{chunk_processor_version}:{EMBEDDING_MODEL}:"
        f"{settings.EMBEDDING_MODEL_REVISION}:{EMBEDDING_NORMALIZATION}:{EMBEDDING_VERSION}"
    )


def _sanitize_error(exc: Exception) -> str:
    if isinstance(exc, (TranscriptEmbeddingError, EmbeddingConfigurationError)):
        return str(exc)
    return "transcript embedding failed"


def _now() -> datetime:
    return datetime.now(UTC)
