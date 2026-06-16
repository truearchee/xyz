"""Stuck-row reaper (ADR-46-C).

Step-aware, RQ-registry-aware recovery for rows stuck by a worker crash or an enqueue-after-commit miss:
  - never-enqueued parse  → auto re-enqueue parse (idempotent)
  - queued downstream job not live in RQ → re-enqueue (subsumes the old reenqueue_summaries backfill)
  - running past its step threshold AND not live in RQ → mark failed + ``crashed`` (retryable), FENCED

Idempotent, singleton-locked, action-capped; writes a MaintenanceRun for every execution. Liveness is
RQ-registry + age (no heartbeat columns): embed/summary checked via stable RQ job_ids; parse/chunk by age.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domains.recovery.locks import maintenance_advisory_lock
from app.domains.recovery.maintenance_run_log import (
    create_maintenance_run,
    finalize_maintenance_run,
)
from app.domains.recovery.rq_liveness import is_job_live_in_rq
from app.platform.config import settings
from app.platform.db.models import AIRequestLog, IngestionJob, QuizAttempt, Transcript
from app.platform.db.session import async_session, engine as default_engine
from app.workers.queues import (
    enqueue_chunk_transcript,
    enqueue_embed_transcript,
    enqueue_parse_transcript,
    enqueue_summary_job,
)


logger = logging.getLogger(__name__)

_DOWNSTREAM_QUEUED_TYPES = ("chunk", "embed", "generate_brief_summary", "generate_detailed_summary")


def _threshold_seconds(job_type: str) -> int:
    if job_type == "parse":
        return settings.REAPER_THRESHOLD_PARSE_SECONDS
    if job_type == "chunk":
        return settings.REAPER_THRESHOLD_CHUNK_SECONDS
    if job_type == "embed":
        return settings.REAPER_THRESHOLD_EMBED_SECONDS
    return settings.REAPER_THRESHOLD_SUMMARY_SECONDS  # brief / detailed


def _reenqueue(job_type: str, *, transcript_id: UUID, job_id: UUID) -> None:
    if job_type == "chunk":
        enqueue_chunk_transcript(job_id)
    elif job_type == "embed":
        enqueue_embed_transcript(job_id)
    else:
        enqueue_summary_job(job_type, job_id)


async def run_stuck_row_reaper(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    engine: AsyncEngine | None = None,
    triggered_by_user_id: UUID | None = None,
    report_only: bool = False,
    rq_liveness=is_job_live_in_rq,
    now: datetime | None = None,
) -> dict | None:
    """Run the reaper under its singleton lock. Returns the summary dict, or None if the lock was held."""
    factory = session_factory or async_session
    eng = engine or default_engine
    if factory is None or eng is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    async with maintenance_advisory_lock(eng, "stuck_row_reaper") as acquired:
        if not acquired:
            return None  # another worker holds it → skip (not a run)
        return await _run_reaper(
            factory,
            triggered_by_user_id=triggered_by_user_id,
            report_only=report_only,
            rq_liveness=rq_liveness,
            now=now or datetime.now(UTC),
        )


async def _run_reaper(
    factory: async_sessionmaker[AsyncSession],
    *,
    triggered_by_user_id: UUID | None,
    report_only: bool,
    rq_liveness,
    now: datetime,
) -> dict:
    mode = "report_only" if report_only else "cleanup"
    run_id = await create_maintenance_run(
        factory,
        run_type="stuck_row_reaper",
        mode=mode,
        triggered_by_user_id=triggered_by_user_id,
    )
    counts = {"scanned": 0, "recovered": 0, "crashed": 0}
    budget = settings.REAPER_ACTION_CAP_PER_RUN
    try:
        budget = await _reap_never_enqueued_parse(factory, now, report_only, counts, budget)
        budget = await _reap_stuck_queued(factory, now, report_only, rq_liveness, counts, budget)
        budget = await _reap_crashed_running(factory, now, report_only, rq_liveness, counts, budget)
        budget = await _reap_lost_quiz_generation(
            factory, report_only, rq_liveness, counts, budget
        )
        await finalize_maintenance_run(factory, run_id, status="completed", summary=counts)
    except Exception as exc:  # pragma: no cover - defensive; never let recovery crash the caller
        logger.exception("stuck-row reaper failed")
        await finalize_maintenance_run(
            factory, run_id, status="failed", summary=counts, error_message=str(exc)[:500]
        )
    return {"run_id": str(run_id), **counts}


async def _reap_never_enqueued_parse(factory, now, report_only, counts, budget) -> int:
    """Transcripts uploaded/queued past the parse threshold with NO parse job at all → re-enqueue parse."""
    if budget <= 0:
        return budget
    threshold = now - timedelta(seconds=settings.REAPER_THRESHOLD_PARSE_SECONDS)
    async with factory() as session:
        transcripts = (
            await session.execute(
                select(Transcript)
                .where(
                    Transcript.lifecycle_state != "superseded",
                    Transcript.status.in_(("uploaded", "queued")),
                    Transcript.created_at < threshold,
                )
                .limit(budget)
            )
        ).scalars().all()
        to_enqueue: list[UUID] = []
        for transcript in transcripts:
            has_parse = (
                await session.execute(
                    select(IngestionJob.id)
                    .where(
                        IngestionJob.transcript_id == transcript.id,
                        IngestionJob.job_type == "parse",
                    )
                    .limit(1)
                )
            ).first()
            if has_parse is None:
                to_enqueue.append(transcript.id)
    for transcript_id in to_enqueue:
        if budget <= 0:
            break
        counts["scanned"] += 1
        if not report_only:
            enqueue_parse_transcript(transcript_id)
        counts["recovered"] += 1
        budget -= 1
    return budget


async def _reap_stuck_queued(factory, now, report_only, rq_liveness, counts, budget) -> int:
    """Downstream jobs stuck 'queued' past their step threshold and not live in RQ → re-enqueue."""
    if budget <= 0:
        return budget
    async with factory() as session:
        queued = (
            await session.execute(
                select(IngestionJob).where(
                    IngestionJob.status == "queued",
                    IngestionJob.job_type.in_(_DOWNSTREAM_QUEUED_TYPES),
                )
            )
        ).scalars().all()
        stale = [
            job
            for job in queued
            if job.created_at < now - timedelta(seconds=_threshold_seconds(job.job_type))
        ]
        # Drop jobs whose transcript was superseded.
        actionable: list[IngestionJob] = []
        for job in stale:
            transcript = await session.get(Transcript, job.transcript_id)
            if transcript is not None and transcript.lifecycle_state != "superseded":
                actionable.append(job)
    for job in actionable:
        if budget <= 0:
            break
        if rq_liveness(job.job_type, job.id) is True:
            continue  # genuinely queued in RQ — not stuck
        counts["scanned"] += 1
        if not report_only:
            _reenqueue(job.job_type, transcript_id=job.transcript_id, job_id=job.id)
        counts["recovered"] += 1
        budget -= 1
    return budget


async def _reap_crashed_running(factory, now, report_only, rq_liveness, counts, budget) -> int:
    """Jobs stuck 'running' past their step threshold and not live in RQ → mark failed + crashed (fenced)."""
    if budget <= 0:
        return budget
    async with factory() as session:
        running = (
            await session.execute(select(IngestionJob).where(IngestionJob.status == "running"))
        ).scalars().all()
    candidates = [
        job
        for job in running
        if job.started_at is not None
        and job.started_at < now - timedelta(seconds=_threshold_seconds(job.job_type))
    ]
    for job in candidates:
        if budget <= 0:
            break
        live = rq_liveness(job.job_type, job.id)
        if live is True:
            continue  # still running in RQ
        # Mark crashed only when confident it is NOT live: False (NoSuchJob) always; None (unknown) only
        # for parse/chunk, whose liveness is age-based by design (never crash an embed/summary on a
        # transient Redis error).
        confident_not_live = live is False or (live is None and job.job_type in ("parse", "chunk"))
        if not confident_not_live:
            continue
        counts["scanned"] += 1
        if report_only:
            counts["crashed"] += 1
            budget -= 1
            continue
        if await _mark_crashed_fenced(factory, job_id=job.id, job_type=job.job_type, now=now):
            counts["crashed"] += 1
            budget -= 1
    return budget


async def _reap_lost_quiz_generation(factory, report_only, rq_liveness, counts, budget) -> int:
    """QuizAttempt rows stuck in 'generating' whose RQ job is NOT live → mark failed + crashed (Stage
    5b lock 4). LIVENESS, NOT AGE: a job still queued/running behind a backed-up AI queue (the
    cohort-burst case Stage 5 deliberately absorbs) is ``live is True`` and must NOT be reaped; only a
    LOST job (``live is False`` — absent from every RQ registry) is. ``None`` (Redis hiccup) is never
    reaped — uncertainty principle. Marking crashed ALSO finalizes the linked AIRequestLog so the cost
    dashboard (rule 6) does not leak a dangling 'running' row."""
    if budget <= 0:
        return budget
    async with factory() as session:
        generating = (
            await session.execute(
                select(QuizAttempt).where(QuizAttempt.status == "generating")
            )
        ).scalars().all()
    for attempt in generating:
        if budget <= 0:
            break
        if rq_liveness("quiz_generate", attempt.id) is not False:
            continue  # live (True) or unknown (None) → do not reap (liveness, not age)
        counts["scanned"] += 1
        if report_only:
            counts["crashed"] += 1
            budget -= 1
            continue
        if await _mark_quiz_attempt_crashed_fenced(factory, attempt_id=attempt.id):
            counts["crashed"] += 1
            budget -= 1
    return budget


async def _mark_quiz_attempt_crashed_fenced(factory, *, attempt_id: UUID) -> bool:
    """Re-read the attempt FOR UPDATE and re-verify it is still 'generating' before failing (never
    races a job that just finished). Also finalizes the linked AIRequestLog (if the id was stamped)
    to a terminal status so a lost job leaves no dangling 'running' cost row."""
    async with factory() as session:
        async with session.begin():
            attempt = (
                await session.execute(
                    select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is None or attempt.status != "generating":
                return False  # raced (completed / failed) — fenced
            now = datetime.now(UTC)
            attempt.status = "failed"
            attempt.failure_category = "crashed"
            attempt.failure_message_sanitized = "worker crashed (reaped by stuck-row recovery)"
            attempt.generation_completed_at = now
            attempt.updated_at = now
            if attempt.ai_request_log_id is not None:
                log = await session.get(AIRequestLog, attempt.ai_request_log_id)
                if log is not None and log.status == "running":
                    log.status = "failed"
                    log.error_code = "abandoned_crashed"
    return True


async def _mark_crashed_fenced(factory, *, job_id: UUID, job_type: str, now: datetime) -> bool:
    """Re-read job + transcript FOR UPDATE and re-verify before failing — never races a job that just
    completed / was retried / whose transcript was superseded (ADR-46-B fencing)."""
    threshold = now - timedelta(seconds=_threshold_seconds(job_type))
    async with factory() as session:
        async with session.begin():
            job = (
                await session.execute(
                    select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
                )
            ).scalar_one_or_none()
            if job is None or job.status != "running":
                return False
            if job.started_at is None or job.started_at >= threshold:
                return False  # no longer stale (raced)
            transcript = (
                await session.execute(
                    select(Transcript).where(Transcript.id == job.transcript_id).with_for_update()
                )
            ).scalar_one_or_none()
            if transcript is None or transcript.lifecycle_state == "superseded":
                return False  # fenced
            job.status = "failed"
            job.failure_category = "crashed"
            job.error_message = "worker crashed (reaped by stuck-row recovery)"
            job.updated_at = now
            # Mirror the step's own failure behaviour: the retrieval steps fail the transcript; a
            # summary crash does not (summaries are per-step, the transcript itself isn't failed).
            if job.job_type in ("parse", "chunk", "embed"):
                transcript.status = "failed"
                transcript.updated_at = now
    return True
