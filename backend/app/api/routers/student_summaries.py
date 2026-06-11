"""Student-facing summary HTTP surface (Stage 4.7 §8.2).

Section-scoped entry ONLY (no by-summary-id / by-transcript-id route → IDOR closure, §8.5). Every
response carries ``Cache-Control: private, no-store`` (§8.4): user-specific + access-sensitive, so no
shared/browser/proxy cache may preserve a stale 200 after unpublish or membership removal. The role gate
(403 row R) fires inside the service before any resource lookup; a missing visible section is the pinned
404 (rows D/P/I).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.student_summaries.schemas import (
    StudentSectionListItem,
    StudentSectionRead,
    StudentSectionSummariesRead,
)
from app.domains.student_summaries.service import (
    get_student_section_detail,
    get_student_section_summaries,
    list_student_module_sections,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session

router = APIRouter(tags=["student-summaries"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]

_NO_STORE = "private, no-store"


@router.get(
    "/student/modules/{module_id}/sections",
    response_model=list[StudentSectionListItem],
    operation_id="getStudentModuleSections",
)
async def get_student_module_sections(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> list[StudentSectionListItem]:
    response.headers["Cache-Control"] = _NO_STORE
    return await list_student_module_sections(db, current_user=current_user, module_id=module_id)


@router.get(
    "/student/sections/{section_id}",
    response_model=StudentSectionRead,
    operation_id="getStudentSection",
)
async def get_student_section(
    section_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentSectionRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await get_student_section_detail(db, current_user=current_user, section_id=section_id)


@router.get(
    "/student/sections/{section_id}/summaries",
    response_model=StudentSectionSummariesRead,
    operation_id="getStudentSectionSummaries",
)
async def get_student_section_summaries_route(
    section_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentSectionSummariesRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await get_student_section_summaries(db, current_user=current_user, section_id=section_id)
