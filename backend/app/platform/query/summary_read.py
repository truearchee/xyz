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

from app.platform.db.models import GeneratedLectureSummary


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
