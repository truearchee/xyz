"""Assessment-scope read model for the exam-prep assistant mode (Stage 8.6b).

Read model ONLY (rule 8): resolves a named ``AssessmentScope`` to its student-visible identity + the
eligible (published + assigned + READY-detailed-summary) sections of its covered weeks, by composing the
EXISTING ``platform/query`` primitives (``resolve_sections_by_weeks`` + ``resolve_section_eligibility``) —
the SAME building blocks ``domains/quiz/scope_service.resolve_exam_prep_scope`` uses. The assistant must
NOT import the quiz domain; this surface gives it the scope-scoped section set for grounding without that
coupling. Invents no policy; never mutates.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import AssessmentScope
from app.platform.query.section_eligibility_read import (
    resolve_section_eligibility,
    student_is_active_member,
)
from app.platform.query.section_week_resolver import resolve_sections_by_weeks


@dataclass(frozen=True)
class VisibleAssessmentScope:
    id: UUID
    name: str
    module_id: UUID
    covered_weeks: list[int]


@dataclass(frozen=True)
class ScopeSectionResolution:
    ready_section_ids: list[UUID]       # published + assigned + READY detailed summary (groundable)
    processing_section_ids: list[UUID]  # in scope but the detailed summary is still generating


async def get_visible_assessment_scope(
    db: AsyncSession, *, student_id: UUID, scope_id: UUID
) -> VisibleAssessmentScope | None:
    """One row iff the scope exists and the student is an active member of its (active) module; else None
    (caller → pinned 404). The student never sees another module's scope."""
    scope = await db.get(AssessmentScope, scope_id)
    if scope is None:
        return None
    if not await student_is_active_member(db, student_id=student_id, module_id=scope.module_id):
        return None
    return VisibleAssessmentScope(
        id=scope.id,
        name=scope.name,
        module_id=scope.module_id,
        covered_weeks=[int(w) for w in (scope.covered_weeks or [])],
    )


async def resolve_scope_ready_sections(
    db: AsyncSession,
    *,
    module_id: UUID,
    covered_weeks: list[int],
    student_id: UUID,
) -> ScopeSectionResolution:
    """The scope's covered weeks → eligible (published+assigned+READY) section ids + the still-generating
    ones (so the assistant can say grounding is partial). Wraps the 5.5 week resolver + the 6b eligibility
    read — no quiz-domain import."""
    candidates = await resolve_sections_by_weeks(
        db, module_id=module_id, covered_weeks=covered_weeks
    )
    elig = await resolve_section_eligibility(
        db, module_id=module_id, candidate_sections=candidates, student_id=student_id
    )
    return ScopeSectionResolution(
        ready_section_ids=elig.ready_ids, processing_section_ids=elig.processing_ids
    )
