"""Quiz scope eligibility (Stage 6b) — which in-span sections a recap/exam-prep quiz may sample.

A section is QUIZ-ELIGIBLE iff it is a lecture/lab section (Slice 1) AND its detailed summary is READY
(Slice 2). assignment/supplementary sections are NEVER eligible and are excluded SILENTLY — never surfaced
as "processing". For STUDENTS, eligibility is further filtered to PUBLISHED sections in a module the student
is an active member of (Stage 3 / 4.7 visibility) — so a student can never be sampled an unpublished or
unassigned section's questions even if a pool exists from lecturer use.

D3 (all-or-wait): the span is available only when every eligible section is READY. ``processing_ids`` are
the lecture/lab sections in span whose detailed summary is still GENERATING (the ones that block + are worth
naming). A lecture/lab with NO usable summary (no transcript / failed → UNAVAILABLE) is NOT quiz-bearing:
it is dropped (it never blocks), so a recap does not hang forever on a section that will never have a quiz.
The canonical scope key is computed from ``ready_ids`` only (read after this filter).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.student_summaries.precedence import GENERATING, READY, derive_slot_state
from app.platform.db.models import CourseMembership, CourseModule
from app.platform.query.section_week_resolver import SectionWeekRow
from app.platform.query.student_summary_read import get_section_summary_inputs


@dataclass(frozen=True)
class EligibilityResult:
    ready_ids: list[UUID]        # sorted; the canonical scope (lecture/lab + READY detailed summary)
    processing_ids: list[UUID]   # lecture/lab in span whose detailed summary is GENERATING (D3 blocks)

    @property
    def all_ready(self) -> bool:
        """True iff there is at least one eligible section and none are still processing (D3 startable)."""
        return bool(self.ready_ids) and not self.processing_ids


async def student_is_active_member(db: AsyncSession, *, student_id: UUID, module_id: UUID) -> bool:
    """Active student membership in an active module — the 404-vs-409 discriminator for the recap/exam-prep
    start path (unassigned → pinned 404; assigned-but-nothing-ready → 409)."""
    row = (
        await db.execute(
            select(CourseMembership.id)
            .join(CourseModule, CourseMembership.module_id == CourseModule.id)
            .where(
                CourseMembership.user_id == student_id,
                CourseMembership.module_id == module_id,
                CourseMembership.role == "student",
                CourseMembership.status == "active",
                CourseModule.is_active.is_(True),
            )
        )
    ).first()
    return row is not None


async def resolve_section_eligibility(
    db: AsyncSession,
    *,
    module_id: UUID,
    candidate_sections: list[SectionWeekRow],
    student_id: UUID | None = None,
) -> EligibilityResult:
    """Partition the candidate lecture/lab sections (from the 5.5 resolver) into READY (in scope) and
    PROCESSING (block D3). ``student_id`` set → require published sections + active student membership
    (empty result if the student is not a member — the caller maps that to a pinned 404)."""
    if student_id is not None and not await student_is_active_member(
        db, student_id=student_id, module_id=module_id
    ):
        return EligibilityResult(ready_ids=[], processing_ids=[])

    ready: list[UUID] = []
    processing: list[UUID] = []
    for section in candidate_sections:
        if section.type not in ("lecture", "lab"):
            continue  # structurally ineligible → silent
        if student_id is not None and section.publish_status != "published":
            continue  # unpublished → invisible to the student (silent)
        inputs = await get_section_summary_inputs(db, section_id=section.id)
        detailed = derive_slot_state(
            section_type=section.type,
            summary_type="detailed_study",
            active_transcript=inputs.active_transcript,
            summary_row=inputs.detailed_row,
            summary_step_status=inputs.detailed_step_status,
            overall_state=inputs.overall_state,
            section_id=section.id,
        )
        if detailed.state == READY:
            ready.append(section.id)
        elif detailed.state == GENERATING:
            processing.append(section.id)
        # UNAVAILABLE / NOT_APPLICABLE → not quiz-bearing → dropped (never blocks).

    ready.sort(key=str)
    processing.sort(key=str)
    return EligibilityResult(ready_ids=ready, processing_ids=processing)
