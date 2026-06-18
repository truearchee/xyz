from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.progress.schemas import (
    ProgressDashboardRead,
    ProgressModuleDetail,
    TargetGradeRequest,
)
from app.domains.progress import service
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session


router = APIRouter(tags=["progress"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]

_NO_STORE = "private, no-store"


@router.get(
    "/student/progress",
    response_model=ProgressDashboardRead,
    operation_id="getStudentProgressDashboard",
)
async def get_progress_dashboard(
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> ProgressDashboardRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_dashboard(db, current_user=current_user)


@router.get(
    "/student/modules/{module_id}/progress",
    response_model=ProgressModuleDetail,
    operation_id="getStudentModuleProgress",
)
async def get_module_progress(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> ProgressModuleDetail:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_module_progress(db, current_user=current_user, module_id=module_id)


@router.put(
    "/student/modules/{module_id}/target-grade",
    response_model=ProgressModuleDetail,
    operation_id="setStudentTargetGrade",
)
async def set_target_grade(
    module_id: UUID,
    payload: TargetGradeRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> ProgressModuleDetail:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.set_target_grade(
        db,
        current_user=current_user,
        module_id=module_id,
        payload=payload,
    )
