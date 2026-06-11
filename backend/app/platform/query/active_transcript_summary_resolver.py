"""Active-transcript summary read projection (ADR-46-E).

A READ-ONLY wrapper around the transcript-domain eligibility predicate. It resolves "what summaries
does the active transcript currently surface?" for the lecturer active-summary preview (the browser
gate polls this in 4.6d; the student HTTP surface is 4.7). It makes NO write/activation decision and
NO authorization decision — both live elsewhere (activation in ``transcripts/domain``; authz at the
endpoint). Keeping the projection here honours the standing rule that ``platform/query`` holds read
models only, while the business predicate stays owned by the domain.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.transcripts.summary_eligibility import is_summary_eligible
from app.platform.db.models import GeneratedLectureSummary, Transcript
from app.platform.query.summary_read import get_latest_transcript_summaries


@dataclass(frozen=True)
class ActiveSummaryView:
    brief: GeneratedLectureSummary | None
    detailed: GeneratedLectureSummary | None
    brief_eligible: bool
    detailed_eligible: bool


class ActiveTranscriptSummaryResolver:
    """Resolves the latest brief/detailed summaries for an active transcript with eligibility flags.

    Wraps the SAME ``is_summary_eligible`` predicate the activation write-side uses (single source of
    truth) but never participates in the activation decision. A row that exists but fails the predicate
    (e.g. left over from a superseded transcript identity, or a checksum mismatch) is returned with its
    ``*_eligible`` flag False rather than silently combining v1 identity with v2 content.
    """

    async def resolve(
        self,
        db: AsyncSession,
        *,
        active_transcript: Transcript,
    ) -> ActiveSummaryView:
        brief, detailed = await get_latest_transcript_summaries(
            db, transcript_id=active_transcript.id
        )
        return ActiveSummaryView(
            brief=brief,
            detailed=detailed,
            brief_eligible=(
                brief is not None
                and is_summary_eligible(brief, active_transcript=active_transcript)
            ),
            detailed_eligible=(
                detailed is not None
                and is_summary_eligible(detailed, active_transcript=active_transcript)
            ),
        )
