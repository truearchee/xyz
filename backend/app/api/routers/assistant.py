"""Student assistant HTTP surface (Stage 8.1).

Section-scoped (availability + open-or-create), conversation-scoped (history + send), and
message-scoped (retry) routes ONLY — no by-row route that would enable IDOR. Every response carries
``Cache-Control: private, no-store`` (user-specific + access-sensitive: no cache may preserve a stale
200 after unpublish or membership removal). The role gate (403) and ownership/visibility gate (pinned
404) fire in the service before any work; non-student → 403; not-owner / lost-access → 404.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.assistant import service
from app.domains.assistant.schemas import (
    AssistantAvailabilityResponse,
    ConversationListItem,
    ConversationRead,
    MessageRead,
    RenameConversationRequest,
    SendMessageRequest,
    SendMessageResponse,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.platform.query.pagination import KeysetPage, PaginatedResponse, PaginationMeta

router = APIRouter(tags=["assistant"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

_NO_STORE = "private, no-store"


@router.get(
    "/student/sections/{section_id}/assistant/availability",
    response_model=AssistantAvailabilityResponse,
    operation_id="getStudentAssistantAvailability",
)
async def get_assistant_availability(
    section_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> AssistantAvailabilityResponse:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_availability(db, current_user=current_user, section_id=section_id)


@router.post(
    "/student/sections/{section_id}/assistant/conversation",
    response_model=ConversationRead,
    operation_id="openStudentAssistantConversation",
)
async def open_assistant_conversation(
    section_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> ConversationRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.open_or_create_conversation(
        db, current_user=current_user, section_id=section_id
    )


@router.get(
    "/student/assistant/conversations",
    response_model=PaginatedResponse[ConversationListItem],
    operation_id="listStudentAssistantConversations",
)
async def list_assistant_conversations(
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
    limit: Limit = 30,
    offset: Offset = 0,
) -> PaginatedResponse[ConversationListItem]:
    response.headers["Cache-Control"] = _NO_STORE
    items, total = await service.list_conversations(
        db, current_user=current_user, limit=limit, offset=offset
    )
    return PaginatedResponse(
        items=items,
        pagination=PaginationMeta(limit=limit, offset=offset, total=total),
    )


@router.get(
    "/student/assistant/conversations/{conversation_id}/messages",
    response_model=KeysetPage[MessageRead],
    operation_id="listStudentAssistantMessages",
)
async def list_assistant_messages(
    conversation_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
    limit: Limit = 30,
    before: Annotated[str | None, Query()] = None,
) -> KeysetPage[MessageRead]:
    response.headers["Cache-Control"] = _NO_STORE
    items, next_cursor, has_more = await service.list_messages(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        before=before,
        limit=limit,
    )
    return KeysetPage(items=items, next_cursor=next_cursor, has_more=has_more)


@router.post(
    "/student/assistant/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    operation_id="sendStudentAssistantMessage",
)
async def send_assistant_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> SendMessageResponse:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.send_message(
        db, current_user=current_user, conversation_id=conversation_id, payload=payload
    )


@router.post(
    "/student/assistant/messages/{message_id}/retry",
    response_model=MessageRead,
    operation_id="retryStudentAssistantMessage",
)
async def retry_assistant_message(
    message_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> MessageRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.retry_message(db, current_user=current_user, message_id=message_id)


@router.get(
    "/student/assistant/conversations/{conversation_id}",
    response_model=ConversationListItem,
    operation_id="getStudentAssistantConversation",
)
async def get_assistant_conversation(
    conversation_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> ConversationListItem:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_conversation_detail(
        db, current_user=current_user, conversation_id=conversation_id
    )


@router.patch(
    "/student/assistant/conversations/{conversation_id}",
    response_model=ConversationRead,
    operation_id="renameStudentAssistantConversation",
)
async def rename_assistant_conversation(
    conversation_id: UUID,
    payload: RenameConversationRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> ConversationRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.rename_conversation(
        db, current_user=current_user, conversation_id=conversation_id, title=payload.title
    )


@router.delete(
    "/student/assistant/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteStudentAssistantConversation",
)
async def delete_assistant_conversation(
    conversation_id: UUID, response: Response, db: DbSession, current_user: CurrentUser
) -> None:
    response.headers["Cache-Control"] = _NO_STORE
    await service.soft_delete_conversation(
        db, current_user=current_user, conversation_id=conversation_id
    )
