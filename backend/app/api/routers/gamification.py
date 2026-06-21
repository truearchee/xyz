from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.gamification import service
from app.domains.gamification.schemas import GamificationRead
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session


router = APIRouter(tags=["gamification"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]

_NO_STORE = "private, no-store"


@router.get(
    "/student/gamification",
    response_model=GamificationRead,
    operation_id="getStudentGamification",
)
async def get_student_gamification(
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> GamificationRead:
    # Student-level (the streak is unified across all the caller's modules). No student_id param —
    # the student is always the authenticated caller; the service gates role (403 for lecturer/admin)
    # and never grants a badge or sets a streak from the client.
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_student_gamification(db, current_user=current_user)
