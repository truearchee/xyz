"""Read query for generated lecture summaries (Stage 4.5d).

Returns the latest brief and detailed `GeneratedLectureSummary` for a transcript. "Latest" matters
because a prompt-version bump or a re-generation creates a new provenance row (the
`uq_gen_summaries_provenance` unique constraint keys include prompt/version/input hashes), so a
transcript may accumulate more than one row per summary type over its lifetime.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import AIRequestLog, GeneratedLectureSummary


async def get_latest_transcript_summaries(
    db: AsyncSession,
    *,
    transcript_id: UUID,
) -> tuple[GeneratedLectureSummary | None, GeneratedLectureSummary | None]:
    """Return ``(brief, detailed)`` — the most recently generated row of each type, or None."""
    rows = (
        await db.execute(
            select(GeneratedLectureSummary)
            .where(
                GeneratedLectureSummary.transcript_id == transcript_id,
                GeneratedLectureSummary.summary_type.in_(("brief", "detailed_study")),
            )
            .order_by(GeneratedLectureSummary.generated_at.desc())
        )
    ).scalars().all()
    brief = next((row for row in rows if row.summary_type == "brief"), None)
    detailed = next((row for row in rows if row.summary_type == "detailed_study"), None)
    return brief, detailed


async def get_ai_request_log_chain(
    db: AsyncSession,
    *,
    ingestion_job_id: UUID,
) -> list[AIRequestLog]:
    """The correlated AIRequestLog chain for one orchestrating job, in time order (4.5.1b).

    A map-reduce detailed job emits one row per map unit + one (or, when tiered, several) reduce row(s),
    all sharing the detailed job's ``ingestion_job_id`` (the gateway logs against the ContextRefs job).
    This returns that chain so the 4.5.1c real-provider proof can count SUCCESSFUL rows (retry-robust),
    echo the per-phase model/backend, and confirm no 408s — the queryable provenance for the smoke.
    The brief's own job id yields its single ``brief_from_detailed`` row."""
    return list(
        (
            await db.execute(
                select(AIRequestLog)
                .where(AIRequestLog.ingestion_job_id == ingestion_job_id)
                .order_by(AIRequestLog.created_at, AIRequestLog.id)
            )
        ).scalars().all()
    )
