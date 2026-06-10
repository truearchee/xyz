"""Dev-only backfill: enqueue brief + detailed summary jobs for embedded transcripts.

NOT the product retry path (that is Stage 4.6 lecturer retry). Finds transcripts whose embedding
completed and that lack summary artifacts, then creates + enqueues the two summary jobs through the
same idempotent path the embed step uses.

Run inside the backend container::

    docker compose exec backend python scripts/reenqueue_summaries.py
    docker compose exec backend python scripts/reenqueue_summaries.py --dry-run

Placed under ``backend/scripts/`` (not repo-root ``scripts/``) so it ships in the backend image —
the backend Docker build context is ``./backend``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.domains.transcripts.summary_service import (
    SUMMARY_JOB_TYPES,
    insert_summary_jobs,
)
from app.platform.db.models import GeneratedLectureSummary, IngestionJob, Transcript
from app.platform.db.session import async_session
from app.workers.queues import enqueue_summary_job

logger = logging.getLogger(__name__)


async def _embedded_transcripts_without_summaries(session) -> list[Transcript]:
    completed_embed = (
        select(IngestionJob.transcript_id)
        .where(IngestionJob.job_type == "embed", IngestionJob.status == "completed")
        .distinct()
    )
    have_summary = select(GeneratedLectureSummary.transcript_id).distinct()
    rows = (
        await session.execute(
            select(Transcript)
            .where(
                Transcript.id.in_(completed_embed),
                Transcript.id.not_in(have_summary),
            )
            .order_by(Transcript.created_at)
        )
    ).scalars().all()
    return list(rows)


async def main(dry_run: bool = False) -> None:
    logging.basicConfig(level=logging.INFO)
    if async_session is None:
        raise SystemExit("DATABASE_URL environment variable is required")

    async with async_session() as session:
        candidates = await _embedded_transcripts_without_summaries(session)

    logger.info("Found %d embedded transcript(s) without summaries", len(candidates))
    if dry_run:
        for transcript in candidates:
            logger.info("would enqueue %s for transcript %s", SUMMARY_JOB_TYPES, transcript.id)
        return

    enqueued = 0
    for transcript in candidates:
        async with async_session() as session:
            async with session.begin():
                jobs = await insert_summary_jobs(session, transcript=transcript)
        for job_type, job_id in jobs:
            enqueue_summary_job(job_type, job_id)
            enqueued += 1
    logger.info("Enqueued %d summary job(s)", enqueued)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list candidates, enqueue nothing")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
