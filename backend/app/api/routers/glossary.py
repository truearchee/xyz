"""Personal glossary HTTP surface (Stage 7a).

Every route is student-authed and personal-scoped (another student's resource → 404, never 403). Every
response carries ``Cache-Control: private, no-store`` (user-specific private data). Lists use the Stage 5
pagination envelope.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.glossary import practice_service, service
from app.domains.glossary.schemas import (
    FolderCreateRequest,
    FolderUpdateRequest,
    GlossaryEntryDetail,
    GlossaryEntryRead,
    GlossaryFolderRead,
    ManualEntryRequest,
    PracticeAnswerFeedback,
    PracticeAnswerRequest,
    PracticeAvailability,
    PracticeResult,
    PracticeSessionState,
    SaveHighlightRequest,
    SaveResponse,
    StartPracticeRequest,
    UpdateEntryRequest,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.platform.query.pagination import PaginatedResponse

router = APIRouter(tags=["glossary"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]

_NO_STORE = "private, no-store"


# ── save ──
@router.post(
    "/student/glossary/highlight",
    response_model=SaveResponse,
    operation_id="saveGlossaryHighlight",
)
async def save_highlight(
    payload: SaveHighlightRequest, response: Response, db: DbSession, current_user: CurrentUser
) -> SaveResponse:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.save_from_highlight(db, current_user=current_user, payload=payload)


@router.post(
    "/student/glossary/entries",
    response_model=SaveResponse,
    operation_id="createGlossaryEntry",
)
async def create_entry(
    payload: ManualEntryRequest, response: Response, db: DbSession, current_user: CurrentUser
) -> SaveResponse:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.save_manual(db, current_user=current_user, payload=payload)


# ── entries ──
@router.get(
    "/student/glossary/entries",
    response_model=PaginatedResponse[GlossaryEntryRead],
    operation_id="listGlossaryEntries",
)
async def list_entries(
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
    subject_id: Annotated[UUID | None, Query(alias="subjectId")] = None,
    folder_id: Annotated[UUID | None, Query(alias="folderId")] = None,
    entry_status: Annotated[str, Query(alias="status")] = "active",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[GlossaryEntryRead]:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.list_entries(
        db,
        current_user=current_user,
        subject_id=subject_id,
        folder_id=folder_id,
        entry_status=entry_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/student/glossary/entries/{entry_id}",
    response_model=GlossaryEntryDetail,
    operation_id="getGlossaryEntry",
)
async def get_entry(
    entry_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> GlossaryEntryDetail:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_entry(db, current_user=current_user, entry_id=entry_id)


@router.patch(
    "/student/glossary/entries/{entry_id}",
    response_model=GlossaryEntryRead,
    operation_id="updateGlossaryEntry",
)
async def update_entry(
    entry_id: UUID,
    payload: UpdateEntryRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> GlossaryEntryRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.update_entry(
        db, current_user=current_user, entry_id=entry_id, payload=payload
    )


@router.delete(
    "/student/glossary/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteGlossaryEntry",
)
async def delete_entry(
    entry_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> None:
    response.headers["Cache-Control"] = _NO_STORE
    await service.archive_entry(db, current_user=current_user, entry_id=entry_id)


# ── folders ──
@router.get(
    "/student/glossary/folders",
    response_model=list[GlossaryFolderRead],
    operation_id="listGlossaryFolders",
)
async def list_folders(
    response: Response, db: DbSession, current_user: CurrentUser
) -> list[GlossaryFolderRead]:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.list_folders(db, current_user=current_user)


@router.post(
    "/student/glossary/folders",
    response_model=GlossaryFolderRead,
    operation_id="createGlossaryFolder",
)
async def create_folder(
    payload: FolderCreateRequest, response: Response, db: DbSession, current_user: CurrentUser
) -> GlossaryFolderRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.create_folder(db, current_user=current_user, name=payload.name)


@router.patch(
    "/student/glossary/folders/{folder_id}",
    response_model=GlossaryFolderRead,
    operation_id="updateGlossaryFolder",
)
async def update_folder(
    folder_id: UUID,
    payload: FolderUpdateRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> GlossaryFolderRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.update_folder(
        db, current_user=current_user, folder_id=folder_id, name=payload.name
    )


@router.delete(
    "/student/glossary/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteGlossaryFolder",
)
async def delete_folder(
    folder_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> None:
    response.headers["Cache-Control"] = _NO_STORE
    await service.archive_folder(db, current_user=current_user, folder_id=folder_id)


# ── practice (7b/7c) ──
@router.get(
    "/student/glossary/practice/availability",
    response_model=PracticeAvailability,
    operation_id="getGlossaryPracticeAvailability",
)
async def practice_availability(
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
    mode: Annotated[str, Query()],
    scope: Annotated[str, Query()] = "all",
    subject_id: Annotated[UUID | None, Query(alias="subjectId")] = None,
) -> PracticeAvailability:
    response.headers["Cache-Control"] = _NO_STORE
    return await practice_service.get_practice_availability(
        db, current_user=current_user, scope=scope, subject_id=subject_id, mode=mode
    )


@router.post(
    "/student/glossary/practice/start",
    response_model=PracticeSessionState,
    operation_id="startGlossaryPractice",
)
async def practice_start(
    payload: StartPracticeRequest, response: Response, db: DbSession, current_user: CurrentUser
) -> PracticeSessionState:
    response.headers["Cache-Control"] = _NO_STORE
    return await practice_service.start_practice(db, current_user=current_user, payload=payload)


@router.get(
    "/student/glossary/practice/{session_id}",
    response_model=PracticeSessionState,
    operation_id="getGlossaryPracticeSession",
)
async def practice_session(
    session_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> PracticeSessionState:
    response.headers["Cache-Control"] = _NO_STORE
    return await practice_service.get_practice_session(
        db, current_user=current_user, session_id=session_id
    )


@router.post(
    "/student/glossary/practice/{session_id}/answer",
    response_model=PracticeAnswerFeedback,
    operation_id="answerGlossaryPractice",
)
async def practice_answer(
    session_id: UUID,
    payload: PracticeAnswerRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> PracticeAnswerFeedback:
    response.headers["Cache-Control"] = _NO_STORE
    return await practice_service.answer_practice(
        db, current_user=current_user, session_id=session_id, payload=payload
    )


@router.post(
    "/student/glossary/practice/{session_id}/complete",
    response_model=PracticeResult,
    operation_id="completeGlossaryPractice",
)
async def practice_complete(
    session_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> PracticeResult:
    response.headers["Cache-Control"] = _NO_STORE
    return await practice_service.complete_practice(
        db, current_user=current_user, session_id=session_id
    )
