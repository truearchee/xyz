"""Recap + exam-prep scope resolution (Stage 6b, Layer 2 scope side).

Recap and exam-prep are MULTI-SECTION quizzes assembled by the 6a engine. This module resolves a span to
its eligible (lecture/lab + READY detailed summary, published+assigned for students) section set, computes
the canonical ``scope_key``, and get-or-creates the SHARED QuizDefinition for that scope (identical scope ⇒
ONE definition across students). D3 all-or-wait gates on summary readiness — the span is available only when
no in-span eligible section is still GENERATING.

The scope_key grain: recap keys on the SORTED ELIGIBLE section ids (the scope IS the includable set, not the
requested week range — so a student never silently inherits a section that became unpublished/ineligible);
exam-prep keys on the AssessmentScope id (the lecturer owns the scope's identity).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.db.models import AssessmentScope, QuizDefinition
from app.platform.db.session import async_session
from app.platform.query.section_eligibility_read import (
    EligibilityResult,
    resolve_section_eligibility,
)
from app.platform.query.section_week_resolver import (
    resolve_sections_by_date_range,
    resolve_sections_by_weeks,
)

RECAP_MODE = "recap"
EXAM_PREP_MODE = "exam_prep"
MISTAKES_BANK_MODE = "mistakes_bank"

# Availability reason codes (only meaningful when not available).
REASON_PROCESSING = "processing"          # eligible lecture/lab summaries still generating (D3 wait)
REASON_NO_ELIGIBLE = "no_eligible_sections"  # nothing quiz-bearing in scope (for this student)


def canonical_scope_key(section_ids: list[UUID]) -> str:
    """sha256 of the sorted section ids — the recap dedup key (stable for a fixed eligible set)."""
    joined = ",".join(sorted(str(s) for s in section_ids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScopeResolution:
    available: bool
    reason_code: str | None
    ready_section_ids: list[UUID]
    processing_section_ids: list[UUID]
    scope_key: str | None  # set iff there is a non-empty ready set


def _to_resolution(elig: EligibilityResult, *, scope_key: str | None = None) -> ScopeResolution:
    if elig.processing_ids:
        return ScopeResolution(False, REASON_PROCESSING, elig.ready_ids, elig.processing_ids, None)
    if not elig.ready_ids:
        return ScopeResolution(False, REASON_NO_ELIGIBLE, [], [], None)
    key = scope_key if scope_key is not None else canonical_scope_key(elig.ready_ids)
    return ScopeResolution(True, None, elig.ready_ids, [], key)


async def resolve_recap_scope(
    db: AsyncSession,
    *,
    module_id: UUID,
    student_id: UUID | None,
    weeks: list[int] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ScopeResolution:
    """Resolve a recap span (weeks OR date range) to its eligible set + availability. ``student_id`` set →
    published+assigned filter (empty/404 if not a member)."""
    if weeks is not None:
        candidates = await resolve_sections_by_weeks(db, module_id=module_id, covered_weeks=weeks)
    elif start_date is not None and end_date is not None:
        candidates = await resolve_sections_by_date_range(
            db, module_id=module_id, start_date=start_date, end_date=end_date
        )
    else:
        raise ValueError("recap scope requires either weeks or a start_date/end_date range")
    elig = await resolve_section_eligibility(
        db, module_id=module_id, candidate_sections=candidates, student_id=student_id
    )
    return _to_resolution(elig)


async def resolve_exam_prep_scope(
    db: AsyncSession,
    *,
    scope: AssessmentScope,
    student_id: UUID | None,
) -> ScopeResolution:
    """Resolve an AssessmentScope's covered weeks to its eligible set + availability. The scope_key is the
    scope id (the lecturer-owned identity), NOT the section set."""
    candidates = await resolve_sections_by_weeks(
        db, module_id=scope.module_id, covered_weeks=[int(w) for w in (scope.covered_weeks or [])]
    )
    elig = await resolve_section_eligibility(
        db, module_id=scope.module_id, candidate_sections=candidates, student_id=student_id
    )
    return _to_resolution(elig, scope_key=str(scope.id))


async def get_or_create_pooled_definition(
    factory: async_sessionmaker[AsyncSession] | None,
    *,
    module_id: UUID,
    quiz_mode: str,
    scope_key: str,
    section_ids: list[UUID],
    assessment_scope_id: UUID | None = None,
) -> UUID:
    """Get-or-create the SHARED multi-section QuizDefinition for a scope (the 6a race pattern). Identical
    ``(module_id, quiz_mode, scope_key)`` ⇒ ONE definition across students."""
    f = factory or async_session
    source_scope: dict = {"quizMode": quiz_mode, "sectionIds": [str(s) for s in section_ids]}
    if assessment_scope_id is not None:
        source_scope["assessmentScopeId"] = str(assessment_scope_id)
    async with f() as session:
        async with session.begin():
            existing = await _existing_scoped_definition(
                session, module_id=module_id, quiz_mode=quiz_mode, scope_key=scope_key
            )
            if existing is not None:
                return existing.id
            definition = QuizDefinition(
                module_section_id=None,
                module_id=module_id,
                quiz_mode=quiz_mode,
                scope_key=scope_key,
                assessment_scope_id=assessment_scope_id,
                source_scope=source_scope,
            )
            session.add(definition)
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                existing = await _existing_scoped_definition(
                    session, module_id=module_id, quiz_mode=quiz_mode, scope_key=scope_key
                )
                if existing is not None:
                    return existing.id
                raise  # pragma: no cover - the unique violation implies a winner exists
            return definition.id


async def get_or_create_mistakes_bank_definition(
    factory: async_sessionmaker[AsyncSession] | None,
    *,
    module_id: UUID,
) -> UUID:
    """One shared mistakes-bank QuizDefinition per module (the bank contents stay per-student at
    assembly/read time; the definition is only the retake-able unit anchor)."""
    f = factory or async_session
    scope_key = str(module_id)
    async with f() as session:
        async with session.begin():
            existing = await _existing_scoped_definition(
                session, module_id=module_id, quiz_mode=MISTAKES_BANK_MODE, scope_key=scope_key
            )
            if existing is not None:
                return existing.id
            definition = QuizDefinition(
                module_section_id=None,
                module_id=module_id,
                quiz_mode=MISTAKES_BANK_MODE,
                scope_key=scope_key,
                assessment_scope_id=None,
                source_scope={"quizMode": MISTAKES_BANK_MODE, "moduleId": str(module_id)},
            )
            session.add(definition)
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                existing = await _existing_scoped_definition(
                    session, module_id=module_id, quiz_mode=MISTAKES_BANK_MODE, scope_key=scope_key
                )
                if existing is not None:
                    return existing.id
                raise  # pragma: no cover - the unique violation implies a winner exists
            return definition.id


async def _existing_scoped_definition(
    session: AsyncSession, *, module_id: UUID, quiz_mode: str, scope_key: str
) -> QuizDefinition | None:
    return (
        await session.execute(
            select(QuizDefinition).where(
                QuizDefinition.module_id == module_id,
                QuizDefinition.quiz_mode == quiz_mode,
                QuizDefinition.scope_key == scope_key,
            )
        )
    ).scalar_one_or_none()


async def prewarm_scope_pools(
    factory: async_sessionmaker[AsyncSession] | None, *, section_ids: list[UUID]
) -> None:
    """D1 exam-prep pre-warm: ensure a pool per in-scope eligible section (idempotent — skips a section that
    already has a fresh pool; generation runs at BACKGROUND priority inside the gateway, rule 15)."""
    from app.domains.quiz.pool_service import ensure_section_pool

    for section_id in section_ids:
        await ensure_section_pool(factory, section_id=section_id)
