"""Backfill stale (truncated / non-map-reduce) detailed summaries (Stage 4.5.1b, §0.1).

Stage 4.7 shipped on the Option-A truncation path, so every active lecture's detailed summary in the DB
today covers only the first portion (``truncated=true``, ``generation_strategy != 'map_reduce'``). This
command finds those and RE-ENQUEUES their detailed IngestionJob, which now runs map-reduce (full coverage);
the brief then re-forks from the regenerated detailed (the 4.5.1b DAG). After it runs, no active
transcript is left with a summary Stage 5 would read as full-coverage that is actually truncated.

Built in 4.5.1b, RUN in 4.5.1c (against the real Checkpoint A + the existing 4.7 data) — one of the three
named 4.5.1c prerequisites. Guarded: ``dry_run`` reports the selection without enqueuing; a per-run ``cap``
bounds the work; idempotent (a transcript already at map_reduce+¬truncated is never selected).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.transcripts.summary_eligibility import is_full_coverage_detailed
from app.domains.transcripts.summary_specs import DETAILED
from app.platform.db.models import GeneratedLectureSummary, Transcript

logger = logging.getLogger(__name__)

DEFAULT_BACKFILL_CAP = 100


@dataclass
class BackfillReport:
    dry_run: bool
    selected: list[UUID] = field(default_factory=list)  # active transcripts with a stale detailed
    enqueued: list[tuple[str, UUID]] = field(default_factory=list)  # (transcript_id, detailed_job_id)
    capped: bool = False


async def _select_stale_active_detailed(session: AsyncSession) -> list[UUID]:
    """Active transcripts whose LATEST detailed summary exists but is NOT full-coverage (truncated or
    not map_reduce). A transcript with no detailed summary is not 'stale' (it was never summarized)."""
    active_ids = set(
        (
            await session.execute(
                select(Transcript.id).where(Transcript.lifecycle_state == "active")
            )
        ).scalars().all()
    )
    if not active_ids:
        return []
    rows = (
        await session.execute(
            select(GeneratedLectureSummary)
            .where(
                GeneratedLectureSummary.summary_type == DETAILED.summary_type,
                GeneratedLectureSummary.transcript_id.in_(active_ids),
            )
            .order_by(GeneratedLectureSummary.generated_at.desc())
        )
    ).scalars().all()
    latest: dict[UUID, GeneratedLectureSummary] = {}
    for row in rows:
        latest.setdefault(row.transcript_id, row)  # first seen = latest (desc order)
    return [tid for tid, row in latest.items() if not is_full_coverage_detailed(row)]


async def backfill_stale_detailed_summaries(
    factory: async_sessionmaker[AsyncSession],
    *,
    dry_run: bool = True,
    cap: int | None = None,
) -> BackfillReport:
    """Re-enqueue the detailed job for every active transcript with a stale detailed summary (capped).

    ``dry_run=True`` (default) reports the selection and enqueues nothing — run it first to see the blast
    radius. ``dry_run=False`` resets+enqueues each detailed job (which regenerates via map-reduce; the brief
    re-forks). Idempotent: re-running after a successful pass selects nothing (the summaries are now
    full-coverage)."""
    # Local import keeps the backfill ⇄ summary_service/queues edges lazy (summary_service imports many).
    from app.domains.transcripts.summary_service import _ensure_summary_job
    from app.workers.queues import enqueue_summary_job

    effective_cap = DEFAULT_BACKFILL_CAP if cap is None else cap

    async with factory() as session:
        stale = await _select_stale_active_detailed(session)

    capped = len(stale) > effective_cap
    selected = stale[:effective_cap]
    report = BackfillReport(dry_run=dry_run, selected=list(selected), capped=capped)
    if dry_run:
        logger.info(
            "backfill dry-run",
            extra={"stale_count": len(stale), "selected": len(selected), "capped": capped},
        )
        return report

    for transcript_id in selected:
        async with factory() as session:
            async with session.begin():
                transcript = (
                    await session.execute(
                        select(Transcript).where(Transcript.id == transcript_id).with_for_update()
                    )
                ).scalar_one_or_none()
                if transcript is None or transcript.lifecycle_state != "active":
                    continue  # raced — skip
                job_id = await _ensure_summary_job(session, transcript=transcript, spec=DETAILED)
        if job_id is not None:
            enqueue_summary_job(DETAILED.job_type, job_id)
            report.enqueued.append((str(transcript_id), job_id))
    logger.info(
        "backfill enqueued detailed regenerations",
        extra={"enqueued": len(report.enqueued), "selected": len(selected)},
    )
    return report
