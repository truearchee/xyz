"""Summary eligibility — predicate + write-side activation readiness (ADR-46-A §3.3, ADR-46-E).

This module OWNS the business decision of whether a stored summary may stand for the active
transcript. The predicate guards three things:

  - identity:    summary.transcript_id == active_transcript.id  (a same-bytes re-upload yields a
                 matching checksum against the WRONG record, so checksum alone is insufficient)
  - provenance:  summary.source_transcript_checksum == active_transcript.checksum
  - generated:   the row exists  (``GeneratedLectureSummary`` is a success-only table — there is no
                 ``status`` column; a row's existence IS "generated")

The read-side projection (``platform/query/ActiveTranscriptSummaryResolver``) wraps the SAME
predicate for reads only; it never makes the activation decision. ``activation`` consumes the
write-side ``get_activation_ready_summaries`` here, never the resolver.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.transcripts.summary_specs import (
    EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE,
    BRIEF,
    DETAILED,
)
from app.platform.db.models import GeneratedLectureSummary, Transcript
from app.platform.query.summary_read import get_latest_transcript_summaries


def is_summary_eligible(
    summary: GeneratedLectureSummary,
    *,
    active_transcript: Transcript,
) -> bool:
    """Whether ``summary`` (a row that exists ⇒ generated) is bound to ``active_transcript``."""
    return (
        summary.transcript_id == active_transcript.id
        and summary.source_transcript_checksum == active_transcript.checksum
    )


def is_full_coverage_detailed(summary: GeneratedLectureSummary | None) -> bool:
    """§0.1 quiz/glossary/assistant gating predicate (Stage 4.5.1b). A DETAILED summary may seed
    downstream generation ONLY when it covers the WHOLE lecture: produced by map-reduce AND not
    truncated. ``single_call`` (legacy/short) and ``truncated_fallback`` (the Option-A emergency path)
    are NOT full-coverage; a truncated map-reduce row (should not occur) is also rejected.

    Stage 5 (quiz), 7 (glossary), 8 (assistant) read THIS on the DETAILED summary — never the brief's
    label (a brief's ``derived_from_detailed`` strategy is informational provenance; quiz-eligibility is
    a property of the detailed it derived from). The brief carries no quiz authority. Downstream reads
    DB STATE, never the user-facing truncation label."""
    return (
        summary is not None
        and summary.summary_type == DETAILED.summary_type
        and summary.generation_strategy == "map_reduce"
        and not summary.truncated
    )


@dataclass(frozen=True)
class ActivationReadiness:
    brief_ready: bool
    detailed_ready: bool
    brief_row: GeneratedLectureSummary | None
    detailed_row: GeneratedLectureSummary | None

    @property
    def is_ready(self) -> bool:
        return self.brief_ready and self.detailed_ready


def _row_ready(
    row: GeneratedLectureSummary | None,
    *,
    active_transcript: Transcript,
    summary_type: str,
) -> bool:
    if row is None:
        return False
    if not is_summary_eligible(row, active_transcript=active_transcript):
        return False
    expected = EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE.get(summary_type)
    return expected is None or row.prompt_version in expected


async def get_activation_ready_summaries(
    db: AsyncSession,
    *,
    transcript: Transcript,
    require_detailed: bool,
) -> ActivationReadiness:
    """Write-side readiness for activation: EXACTLY ONE eligible brief (+ detailed when required).

    "Exactly one" is satisfied structurally — ``get_latest_transcript_summaries`` collapses to one
    latest row per type — and the predicate confirms that row is bound to ``transcript`` at the
    expected prompt version. ``require_detailed`` mirrors ``settings.ENABLE_DETAILED_SUMMARY`` at the
    call site; when detailed is gated off, ``overall_state`` never reaches ``summarized`` anyway, so
    activation stays a no-op.
    """
    brief, detailed = await get_latest_transcript_summaries(db, transcript_id=transcript.id)
    brief_ready = _row_ready(
        brief, active_transcript=transcript, summary_type=BRIEF.summary_type
    )
    detailed_ready = (
        _row_ready(detailed, active_transcript=transcript, summary_type=DETAILED.summary_type)
        if require_detailed
        else True
    )
    return ActivationReadiness(
        brief_ready=brief_ready,
        detailed_ready=detailed_ready,
        brief_row=brief,
        detailed_row=detailed,
    )
