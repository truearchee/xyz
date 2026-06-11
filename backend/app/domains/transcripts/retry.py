"""Retry resolution + apply over the true ingestion DAG (ADR-46-B §3.2).

Retry resumes at the EARLIEST failed step against the immutable transcript file, reusing valid upstream
output. The pipeline is a DAG, not a linear chain — after parse it forks:

    parse ──► chunk ──► embed          (retrieval branch)
    parse ──► brief                    (summary branch — uses normalized text, NOT chunks/embeddings)
    parse ──► detailed                 (summary branch)

So an embed failure must not block summaries, and a summary retry must not touch chunks/embeddings.
This module only resolves WHICH jobs to reset+re-enqueue; the per-step delete-and-regenerate and the
fencing happen in the worker when the re-enqueued job runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import IngestionJob, Transcript
from app.platform.query.transcript_status import TranscriptProcessingStatusRead
from app.workers.queues import (
    enqueue_chunk_transcript,
    enqueue_embed_transcript,
    enqueue_parse_transcript,
    enqueue_summary_job,
)


RETRIEVAL_CHAIN = ("parse", "chunk", "embed")
SUMMARY_STEPS = ("summary_brief", "summary_detailed")
# Projection step key → IngestionJob.job_type.
STEP_TO_JOB_TYPE: dict[str, str] = {
    "parse": "parse",
    "chunk": "chunk",
    "embed": "embed",
    "summary_brief": "generate_brief_summary",
    "summary_detailed": "generate_detailed_summary",
}


def resolve_retry_scope(projection: TranscriptProcessingStatusRead) -> list[str]:
    """The set of projection step keys to retry, respecting the DAG.

    - parse failed → just ``parse`` (its success cascade re-enqueues chunk + brief + detailed).
    - otherwise → the earliest failed retrieval step (chunk before embed), if any, PLUS each failed
      summary step (they are independent of the retrieval branch).
    """
    steps = projection.steps

    def failed(key: str) -> bool:
        step = steps.get(key)
        return step is not None and step.status == "failed"

    if failed("parse"):
        return ["parse"]

    scope: list[str] = []
    earliest_retrieval = next((s for s in ("chunk", "embed") if failed(s)), None)
    if earliest_retrieval is not None:
        scope.append(earliest_retrieval)
    scope.extend(s for s in SUMMARY_STEPS if failed(s))
    return scope


async def _latest_job_for_update(
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
            )
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()


async def apply_retry(
    session: AsyncSession,
    *,
    transcript: Transcript,
    scope: list[str],
) -> list[tuple[str, UUID]]:
    """Reset the failed jobs in ``scope`` to ``queued`` and return the (job_type, job_id) to enqueue.

    Runs in the caller's transaction. Locks the transcript + each job ``FOR UPDATE``; a job that is no
    longer ``failed`` (a concurrent retry already reset it) is skipped, so a double-retry enqueues once.
    The caller commits, THEN enqueues (enqueue-after-commit).
    """
    locked = (
        await session.execute(
            select(Transcript).where(Transcript.id == transcript.id).with_for_update()
        )
    ).scalar_one_or_none()
    if locked is None or locked.lifecycle_state == "superseded":
        return []

    now = datetime.now(UTC)
    to_enqueue: list[tuple[str, UUID]] = []
    for step in scope:
        job_type = STEP_TO_JOB_TYPE[step]
        job = await _latest_job_for_update(
            session, transcript_id=transcript.id, job_type=job_type
        )
        if job is None or job.status != "failed":
            continue
        job.status = "queued"
        job.error_message = None
        job.failure_category = None
        job.completed_at = None
        job.updated_at = now
        to_enqueue.append((job_type, job.id))
    return to_enqueue


def enqueue_retry_jobs(transcript_id: UUID, to_enqueue: list[tuple[str, UUID]]) -> None:
    """Dispatch the reset jobs onto their queues. Parse is keyed by transcript_id; the rest by job_id."""
    for job_type, job_id in to_enqueue:
        if job_type == "parse":
            enqueue_parse_transcript(transcript_id)
        elif job_type == "chunk":
            enqueue_chunk_transcript(job_id)
        elif job_type == "embed":
            enqueue_embed_transcript(job_id)
        else:
            enqueue_summary_job(job_type, job_id)
