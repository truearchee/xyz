"""Conversation save-source read model (Stage 8.5) — resolve + verify an assistant-chat glossary save.

Read model ONLY (rule 8): the glossary domain reads assistant state through here instead of importing the
assistant domain. Returns the minimal facts a glossary save needs, or ``None`` for every condition the
assistant pins to a 404 (not-owned / missing / soft-deleted / unbound conversation; message not in the
conversation; bound section no longer visible). It encapsulates exactly the ownership + visibility checks
whose failure is the 404; the glossary service decides role / status / text-match (its own 4xx vocabulary).

Mirrors assistant ``service._resolve_owned_conversation`` semantics as a pure read, and reuses
``student_summary_read.get_visible_student_section`` for the published + assigned (Stage 4.7) gate, which
also yields the ``course_module_id`` the save uses as the subject (server-derived, never client-trusted).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import AssistantConversation, AssistantMessage
from app.platform.query.student_summary_read import get_visible_student_section


@dataclass(frozen=True)
class ResolvedConversationSource:
    section_id: UUID
    course_module_id: UUID
    message_role: str
    message_status: str
    message_content: str | None


async def get_conversation_save_source(
    db: AsyncSession,
    *,
    student_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
) -> ResolvedConversationSource | None:
    """Resolve a conversation save source, or ``None`` (caller → pinned 404) for not-owned / missing /
    soft-deleted / unbound conversation, message-not-in-conversation, or a no-longer-visible section."""
    conv = await db.get(AssistantConversation, conversation_id)
    if conv is None or conv.student_id != student_id or conv.deleted_at is not None:
        return None
    if conv.attached_section_id is None:
        return None  # unbound — no resolvable subject (8.5 D4); rejected here regardless of the UI
    visible = await get_visible_student_section(
        db, student_id=student_id, section_id=conv.attached_section_id
    )
    if visible is None:
        return None  # unpublished / unassigned / inactive membership / lost access
    msg = await db.get(AssistantMessage, message_id)
    if msg is None or msg.conversation_id != conv.id:
        return None  # message-not-in-conversation is indistinguishable from missing → 404, no probing
    return ResolvedConversationSource(
        section_id=conv.attached_section_id,
        course_module_id=visible.course_module_id,
        message_role=msg.role,
        message_status=msg.status,
        message_content=msg.content,
    )
