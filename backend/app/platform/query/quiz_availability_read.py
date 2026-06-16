"""Read-only post-class-quiz availability model (Stage 5 lock 2 / §HTTP contract).

A PURE READ: computes whether a post-class quiz is available for one (student, section) and creates NO
rows (the QuizDefinition is materialized only on POST start, in 5b). It reuses the 4.7 visibility scoped
query and the 4.7 detailed-summary readiness predicate, so quiz availability is NEVER more permissive
than summary visibility. The 403 student gate stays in the (future) endpoint via
``StudentSummaryAccessPolicy.require_student``; this model is DB-only and never raises HTTP.

Returns ``None`` when the section is not visible to the student — the caller maps that to the pinned
404 (never fetch-then-branch), exactly like the student-summary surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.student_summaries.precedence import (
    GENERATING,
    READY,
    derive_slot_state,
)
from app.platform.db.models import GeneratedLectureSummary
from app.platform.query.student_summary_read import (
    get_section_summary_inputs,
    get_visible_student_section,
)

# reasonCode values per the Stage 5 HTTP contract (only meaningful when available is False).
SUMMARY_PROCESSING = "summary_processing"
SUMMARY_UNAVAILABLE = "summary_unavailable"


@dataclass(frozen=True)
class QuizAvailabilityView:
    available: bool
    reason_code: str | None


async def get_quiz_availability(
    db: AsyncSession,
    *,
    student_id: UUID,
    section_id: UUID,
) -> QuizAvailabilityView | None:
    """Compute post-class quiz availability. ``None`` ⇒ section not visible (caller → pinned 404)."""
    visible = await get_visible_student_section(db, student_id=student_id, section_id=section_id)
    if visible is None:
        return None

    inputs = await get_section_summary_inputs(db, section_id=section_id)
    detailed = derive_slot_state(
        section_type=visible.type,
        summary_type="detailed_study",
        active_transcript=inputs.active_transcript,
        summary_row=inputs.detailed_row,
        summary_step_status=inputs.detailed_step_status,
        overall_state=inputs.overall_state,
        section_id=section_id,
    )

    if detailed.state == READY:
        return QuizAvailabilityView(available=True, reason_code=None)
    if detailed.state == GENERATING:
        return QuizAvailabilityView(available=False, reason_code=SUMMARY_PROCESSING)
    # UNAVAILABLE / NOT_APPLICABLE → visible section but no usable detailed summary to quiz on.
    return QuizAvailabilityView(available=False, reason_code=SUMMARY_UNAVAILABLE)


async def resolve_quiz_source_summary(
    db: AsyncSession,
    *,
    section_id: UUID,
    section_type: str,
) -> GeneratedLectureSummary | None:
    """The active ``detailed_study`` summary row IFF it is READY for this section, else None.

    The quiz start service snapshots this row's id/checksum onto the attempt (supersession-safe). Lives
    in platform/query so the quiz DOMAIN imports only platform read models — the readiness predicate
    (``derive_slot_state``) and the active-transcript resolution stay in one place, never duplicated.
    """
    inputs = await get_section_summary_inputs(db, section_id=section_id)
    detailed = derive_slot_state(
        section_type=section_type,
        summary_type="detailed_study",
        active_transcript=inputs.active_transcript,
        summary_row=inputs.detailed_row,
        summary_step_status=inputs.detailed_step_status,
        overall_state=inputs.overall_state,
        section_id=section_id,
    )
    if detailed.state == READY and inputs.detailed_row is not None:
        return inputs.detailed_row
    return None
