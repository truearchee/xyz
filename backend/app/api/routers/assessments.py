"""Lecturer AssessmentScope HTTP surface (Stage 6b).

Lecturer-on-that-module only (role 403 → membership 403 → pinned 404), reusing the shipped content
authorization. Creating/editing a scope pre-warms its section pools (Decision #1). The list uses the Stage 5
pagination envelope.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.assessments import service
from app.domains.assessments.schemas import (
    AssessmentScopeResponse,
    CreateAssessmentScopeRequest,
    UpdateAssessmentScopeRequest,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.platform.query.pagination import PaginatedResponse, PaginationMeta

router = APIRouter(tags=["assessments"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

_NO_STORE = "private, no-store"


@router.post(
    "/lecturer/modules/{module_id}/assessment-scopes",
    response_model=AssessmentScopeResponse,
    operation_id="createAssessmentScope",
)
async def create_assessment_scope(
    module_id: UUID,
    payload: CreateAssessmentScopeRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> AssessmentScopeResponse:
    response.headers["Cache-Control"] = _NO_STORE
    scope = await service.create_scope(
        db, current_user=current_user, module_id=module_id, payload=payload
    )
    return AssessmentScopeResponse.model_validate(scope)


@router.get(
    "/lecturer/modules/{module_id}/assessment-scopes",
    response_model=PaginatedResponse[AssessmentScopeResponse],
    operation_id="listAssessmentScopes",
)
async def list_assessment_scopes(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
    limit: Limit = 50,
    offset: Offset = 0,
) -> PaginatedResponse[AssessmentScopeResponse]:
    response.headers["Cache-Control"] = _NO_STORE
    items, total = await service.list_scopes(
        db, current_user=current_user, module_id=module_id, limit=limit, offset=offset
    )
    return PaginatedResponse(
        items=[AssessmentScopeResponse.model_validate(s) for s in items],
        pagination=PaginationMeta(limit=limit, offset=offset, total=total),
    )


@router.get(
    "/lecturer/assessment-scopes/{scope_id}",
    response_model=AssessmentScopeResponse,
    operation_id="getAssessmentScope",
)
async def get_assessment_scope(
    scope_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> AssessmentScopeResponse:
    response.headers["Cache-Control"] = _NO_STORE
    scope = await service.get_scope(db, current_user=current_user, scope_id=scope_id)
    return AssessmentScopeResponse.model_validate(scope)


@router.patch(
    "/lecturer/assessment-scopes/{scope_id}",
    response_model=AssessmentScopeResponse,
    operation_id="updateAssessmentScope",
)
async def update_assessment_scope(
    scope_id: UUID,
    payload: UpdateAssessmentScopeRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> AssessmentScopeResponse:
    response.headers["Cache-Control"] = _NO_STORE
    scope = await service.update_scope(
        db, current_user=current_user, scope_id=scope_id, payload=payload
    )
    return AssessmentScopeResponse.model_validate(scope)
