from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    IngestionJob,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)


STEP_KEYS = ("upload", "parse", "chunk", "embed")
JOB_STEP_KEYS = ("parse", "chunk", "embed")
SAFE_FAILURE_MESSAGES = {
    "upload": "Transcript upload failed.",
    "parse": "Transcript parsing failed.",
    "chunk": "Transcript chunking failed.",
    "embed": "Transcript embedding failed.",
}


@dataclass(frozen=True)
class TranscriptProcessingStepRead:
    status: str
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class TranscriptProcessingStatusRead:
    active_transcript_id: UUID
    transcript_status: str
    overall_state: str
    current_phase: str | None
    failed_step: str | None
    steps: dict[str, TranscriptProcessingStepRead]
    segment_count: int
    chunk_count: int
    embedded_chunk_count: int
    safe_failure_message: str | None
    updated_at: datetime


async def get_transcript_processing_status_read(
    db: AsyncSession,
    *,
    transcript: Transcript,
) -> TranscriptProcessingStatusRead:
    segment_count = await _count_rows(
        db,
        TranscriptSegment.transcript_id == transcript.id,
        model=TranscriptSegment,
    )
    chunk_count = await _count_rows(
        db,
        TranscriptChunk.transcript_id == transcript.id,
        model=TranscriptChunk,
    )
    embedded_chunk_count = await _count_rows(
        db,
        TranscriptChunk.transcript_id == transcript.id,
        TranscriptChunk.embedding.is_not(None),
        model=TranscriptChunk,
    )
    jobs = await _latest_jobs_by_type(db, transcript_id=transcript.id)
    steps = _steps(transcript=transcript, jobs=jobs)
    failed_step = _failed_step(transcript=transcript, jobs=jobs)
    safe_failure_message = _safe_failure_message(failed_step=failed_step, jobs=jobs)
    overall_state = _overall_state(
        transcript=transcript,
        steps=steps,
        segment_count=segment_count,
        chunk_count=chunk_count,
        embedded_chunk_count=embedded_chunk_count,
    )
    return TranscriptProcessingStatusRead(
        active_transcript_id=transcript.id,
        transcript_status=transcript.status,
        overall_state=overall_state,
        current_phase=_current_phase(overall_state),
        failed_step=failed_step,
        steps=steps,
        segment_count=segment_count,
        chunk_count=chunk_count,
        embedded_chunk_count=embedded_chunk_count,
        safe_failure_message=safe_failure_message,
        updated_at=_updated_at(transcript=transcript, jobs=jobs),
    )


async def _count_rows(db: AsyncSession, *where_clauses, model) -> int:
    value = (
        await db.execute(
            select(func.count())
            .select_from(model)
            .where(*where_clauses)
        )
    ).scalar_one()
    return int(value)


async def _latest_jobs_by_type(
    db: AsyncSession,
    *,
    transcript_id: UUID,
) -> dict[str, IngestionJob]:
    rows = (
        await db.execute(
            select(IngestionJob)
            .where(IngestionJob.transcript_id == transcript_id)
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
        )
    ).scalars().all()
    latest: dict[str, IngestionJob] = {}
    for job in rows:
        if job.job_type in JOB_STEP_KEYS and job.job_type not in latest:
            latest[job.job_type] = job
    return latest


def _steps(
    *,
    transcript: Transcript,
    jobs: dict[str, IngestionJob],
) -> dict[str, TranscriptProcessingStepRead]:
    steps = {
        "upload": TranscriptProcessingStepRead(
            status="completed",
            started_at=transcript.created_at,
            completed_at=transcript.created_at,
        )
    }
    for step_key in JOB_STEP_KEYS:
        job = jobs.get(step_key)
        steps[step_key] = TranscriptProcessingStepRead(
            status=job.status if job is not None else "not_started",
            started_at=job.started_at if job is not None else None,
            completed_at=job.completed_at if job is not None else None,
        )
    return steps


def _failed_step(
    *,
    transcript: Transcript,
    jobs: dict[str, IngestionJob],
) -> str | None:
    for step_key in ("embed", "chunk", "parse"):
        job = jobs.get(step_key)
        if job is not None and job.status == "failed":
            return step_key
    if transcript.status == "failed":
        return "upload"
    return None


def _safe_failure_message(
    *,
    failed_step: str | None,
    jobs: dict[str, IngestionJob],
) -> str | None:
    if failed_step is None:
        return None
    return SAFE_FAILURE_MESSAGES.get(failed_step, "Transcript processing failed.")


def _overall_state(
    *,
    transcript: Transcript,
    steps: dict[str, TranscriptProcessingStepRead],
    segment_count: int,
    chunk_count: int,
    embedded_chunk_count: int,
) -> str:
    if transcript.status == "failed" or any(
        step.status == "failed" for step in steps.values()
    ):
        return "failed"
    if (
        steps["embed"].status == "completed"
        and chunk_count > 0
        and embedded_chunk_count == chunk_count
    ):
        return "embedded"
    if steps["embed"].status in {"queued", "running"} or transcript.status == "embedding":
        return "embedding"
    if steps["chunk"].status == "completed" and chunk_count > 0:
        return "chunked"
    if steps["chunk"].status in {"queued", "running"} or transcript.status == "chunking":
        return "chunking"
    if steps["parse"].status == "completed" and segment_count > 0:
        return "parsed"
    if steps["parse"].status in {"queued", "running"} or transcript.status == "parsing":
        return "parsing"
    if transcript.status == "queued":
        return "queued"
    return "uploaded"


def _current_phase(overall_state: str) -> str | None:
    if overall_state in {"chunked", "embedded", "failed"}:
        return None
    if overall_state in {"chunking", "parsed"}:
        return "chunk"
    if overall_state in {"parsing"}:
        return "parse"
    if overall_state in {"embedding"}:
        return "embed"
    return "upload"


def _updated_at(
    *,
    transcript: Transcript,
    jobs: dict[str, IngestionJob],
) -> datetime:
    timestamps = [transcript.updated_at]
    timestamps.extend(job.updated_at for job in jobs.values())
    return max(timestamps)
