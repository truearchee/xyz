from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.config import settings
from app.platform.db.models import (
    IngestionJob,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)


# Map an IngestionJob.job_type to the projection step key it drives.
JOB_TYPE_TO_STEP = {
    "parse": "parse",
    "chunk": "chunk",
    "embed": "embed",
    "generate_brief_summary": "summary_brief",
    "generate_detailed_summary": "summary_detailed",
}
JOB_STEP_KEYS = ("parse", "chunk", "embed", "summary_brief", "summary_detailed")
STEP_KEYS = ("upload",) + JOB_STEP_KEYS
SUMMARY_STEP_KEYS = ("summary_brief", "summary_detailed")
SAFE_FAILURE_MESSAGES = {
    "upload": "Transcript upload failed.",
    "parse": "Transcript parsing failed.",
    "chunk": "Transcript chunking failed.",
    "embed": "Transcript embedding failed.",
    "summary_brief": "Summary generation failed.",
    "summary_detailed": "Summary generation failed.",
}
# Category-based copy for summary failures (spec §7.5). Student-safe — never a stack trace or
# backend error body; provider config/auth detail is deliberately NOT leaked.
SUMMARY_FAILURE_MESSAGES_BY_CATEGORY = {
    "invalid_input": (
        "Transcript is too long for the summary model. Replace the transcript or contact support."
    ),
    "invalid_output": "Summary generation failed. Retry available.",
    "provider_transient": "Summary generation failed. Retry available.",
    "rate_limited": "Summary generation is busy and will retry automatically.",
    "provider_config_error": "Summary unavailable — configuration issue.",
    "provider_auth_error": "Summary unavailable — configuration issue.",
    "failed": "Summary generation failed.",
}


@dataclass(frozen=True)
class TranscriptProcessingStepRead:
    status: str
    started_at: datetime | None
    completed_at: datetime | None


# Internal IngestionJob.failure_category values that a lecturer retry cannot fix (re-running just
# fails the same way) — the fix is replace-the-transcript / contact-support, so retryable is False.
_NON_RETRYABLE_CATEGORIES = {
    "provider_config_error",
    "provider_auth_error",
    "invalid_input",
    "storage_missing",
    "unsupported_file",
}


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
    # Sanitized failure category surfaced to the lecturer (one of the 9 Stage 4.6 categories) +
    # whether a lecturer retry can help. The full internal reason stays on IngestionJob.error_message.
    failure_category: str | None
    retryable: bool
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
    failure_category = _sanitized_failure_category(failed_step=failed_step, jobs=jobs)
    retryable = _retryable(failed_step=failed_step, jobs=jobs)
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
        failure_category=failure_category,
        retryable=retryable,
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
        step = JOB_TYPE_TO_STEP.get(job.job_type)
        if step is not None and step not in latest:
            latest[step] = job
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
    for step_key in ("summary_detailed", "summary_brief", "embed", "chunk", "parse"):
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
    if failed_step in SUMMARY_STEP_KEYS:
        job = jobs.get(failed_step)
        category = job.failure_category if job is not None else None
        return SUMMARY_FAILURE_MESSAGES_BY_CATEGORY.get(
            category or "failed", SAFE_FAILURE_MESSAGES[failed_step]
        )
    return SAFE_FAILURE_MESSAGES.get(failed_step, "Transcript processing failed.")


def _sanitized_failure_category(
    *,
    failed_step: str | None,
    jobs: dict[str, IngestionJob],
) -> str | None:
    """Map (failed_step + the job's internal failure_category) to one of the 9 Stage 4.6 sanitized
    categories. The lecturer sees only this; the full internal reason stays on error_message."""
    if failed_step is None or failed_step == "upload":
        return None
    job = jobs.get(failed_step)
    internal = job.failure_category if job is not None else None
    if internal == "crashed":
        return "crashed"
    if failed_step == "parse":
        if internal in ("storage_missing", "unsupported_file"):
            return internal
        return "parse_failed"
    if failed_step == "chunk":
        return "chunk_failed"
    if failed_step == "embed":
        return "embedding_failed"
    if failed_step in SUMMARY_STEP_KEYS:
        if internal == "invalid_output":
            return "invalid_output"
        if internal in (
            "provider_transient",
            "rate_limited",
            "provider_config_error",
            "provider_auth_error",
        ):
            return "provider_error"
        return "summary_generation_failed"  # 'failed' / 'invalid_input' / None
    return None


def _retryable(
    *,
    failed_step: str | None,
    jobs: dict[str, IngestionJob],
) -> bool:
    """Whether a lecturer retry can target a failed step and plausibly help."""
    if failed_step is None or failed_step == "upload":
        return False
    job = jobs.get(failed_step)
    if job is None or job.status != "failed":
        return False
    return job.failure_category not in _NON_RETRYABLE_CATEGORIES


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
        brief = steps["summary_brief"].status
        detailed = steps["summary_detailed"].status
        if brief == "completed" and detailed == "completed":
            return "summarized"
        if "running" in (brief, detailed) or "queued" in (brief, detailed):
            return "summarizing"
        # 4.5b: detailed generation is gated off (§5), so no detailed job exists. With brief done and
        # detailed intentionally deferred to 4.5c, the transcript rests at 'summarizing' (not
        # 'embedded' — summarization has begun, and not 'summarized' — detailed is still pending).
        if brief == "completed" and not settings.ENABLE_DETAILED_SUMMARY:
            return "summarizing"
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
