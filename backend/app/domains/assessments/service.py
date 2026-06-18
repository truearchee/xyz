"""AssessmentScope service (Stage 6b) — lecturer-defined exam-prep scopes.

Authorization reuses the shipped lecturer-on-module predicate verbatim: role gate (403) → active lecturer
membership on THIS module (403) → pinned 404 for a missing scope. Creating or editing a scope pre-warms its
in-scope eligible section pools (Decision #1) at background priority so no student waits on a known exam;
pre-warm is idempotent (it skips a section that already has a fresh pool).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.assessments.schemas import (
    CreateAssessmentScopeRequest,
    UpdateAssessmentScopeRequest,
)
from app.domains.quiz.scope_service import prewarm_scope_pools, resolve_exam_prep_scope
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import AssessmentScope
from app.platform.query.content_read import lecturer_has_active_module_membership

SCOPE_FORBIDDEN = "ASSESSMENT_SCOPE_FORBIDDEN"
SCOPE_NOT_FOUND = "ASSESSMENT_SCOPE_NOT_FOUND"


async def _require_lecturer_on_module(
    db: AsyncSession, *, current_user: CurrentUserContext, module_id: UUID
) -> None:
    """Role gate (403) before any lookup, then active lecturer membership on THIS module (403)."""
    if current_user.role != "lecturer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SCOPE_FORBIDDEN)
    if not await lecturer_has_active_module_membership(
        db, user_id=current_user.user_id, module_id=module_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SCOPE_FORBIDDEN)


def _normalize_weeks(weeks: list[int]) -> list[int]:
    cleaned = sorted(dict.fromkeys(int(w) for w in weeks))
    if not cleaned or any(w < 1 for w in cleaned):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="coveredWeeks must be a non-empty list of positive integers",
        )
    return cleaned


async def create_scope(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    payload: CreateAssessmentScopeRequest,
) -> AssessmentScope:
    await _require_lecturer_on_module(db, current_user=current_user, module_id=module_id)
    weeks = _normalize_weeks(payload.covered_weeks)
    scope = AssessmentScope(
        module_id=module_id,
        name=payload.name,
        covered_weeks=weeks,
        created_by_user_id=current_user.user_id,
        status="active",
    )
    db.add(scope)
    await db.commit()
    await db.refresh(scope)
    await _prewarm(db, scope)
    return scope


async def list_scopes(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[AssessmentScope], int]:
    await _require_lecturer_on_module(db, current_user=current_user, module_id=module_id)
    total = int(
        await db.scalar(
            select(func.count(AssessmentScope.id)).where(AssessmentScope.module_id == module_id)
        )
        or 0
    )
    items = (
        await db.scalars(
            select(AssessmentScope)
            .where(AssessmentScope.module_id == module_id)
            .order_by(AssessmentScope.created_at.desc(), AssessmentScope.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(items), total


async def get_scope(
    db: AsyncSession, *, current_user: CurrentUserContext, scope_id: UUID
) -> AssessmentScope:
    scope = await db.get(AssessmentScope, scope_id)
    if scope is None:
        # Role gate would 403 a non-lecturer; but a lecturer asking for a non-existent scope gets 404.
        if current_user.role != "lecturer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=SCOPE_FORBIDDEN)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SCOPE_NOT_FOUND)
    await _require_lecturer_on_module(db, current_user=current_user, module_id=scope.module_id)
    return scope


async def update_scope(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    scope_id: UUID,
    payload: UpdateAssessmentScopeRequest,
) -> AssessmentScope:
    scope = await get_scope(db, current_user=current_user, scope_id=scope_id)
    if payload.name is not None:
        scope.name = payload.name
    if payload.covered_weeks is not None:
        scope.covered_weeks = _normalize_weeks(payload.covered_weeks)
    await db.commit()
    await db.refresh(scope)
    # Re-warm: idempotent skip of already-fresh pools, so an edit that only adds weeks costs one pool each.
    await _prewarm(db, scope)
    return scope


async def _prewarm(db: AsyncSession, scope: AssessmentScope) -> None:
    """D1 pre-warm — generate the scope's in-scope eligible section pools now (lecturer view: no student
    publish/assignment filter), background priority, idempotent.

    LOAD-BEARING (F-6e): this is what keeps a *known* exam off the ~264s pool-generation first-wait —
    pools are warm by the time students open exam-prep. Live K2-Think-v2 pool generation is inherently
    multi-minute (~max_tokens/73 tok/s; see ADR-047 F-6e amendment + the 6d real-provider-smoke report),
    and reasoning_effort=low is NOT a safe shortcut yet (it halves output validity). Do NOT remove or
    weaken this pre-warm on AssessmentScope create/update without an equivalent mitigation: a regression
    here silently reintroduces the multi-minute wait on exams."""
    resolution = await resolve_exam_prep_scope(db, scope=scope, student_id=None)
    if not resolution.ready_section_ids:
        return
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    await prewarm_scope_pools(factory, section_ids=resolution.ready_section_ids)
