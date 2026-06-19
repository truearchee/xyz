"""Student-reachable assistant DTOs (Stage 8.1).

These shapes are intentionally narrow: a student message carries no provenance, no system/hidden
prompt, and no model reasoning. The full technical provenance (model, promptVersion, tokens, chunk
refs) lives in AIRequestLog, never here (decision 10). ``groundingStatus``/``answerBasis`` are reserved
for 8.2 and are null in 8.1.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class AssistantAvailabilityResponse(CamelModel):
    """Whether the lecture assistant can be started for this section (decision 9).

    ``state`` ∈ {``ready``, ``processing``, ``unavailable``}. The UI shows "Start chat" only on
    ``ready`` and reuses the summary processing/unavailable treatment otherwise.
    """

    state: str


class ConversationRead(CamelModel):
    id: UUID
    conversation_kind: str
    attached_section_id: UUID | None
    title: str | None = None  # raw stored title (manual rename); null while title_source = 'auto'
    title_source: str = "auto"  # 'auto' | 'manual' — a manual rename is never overwritten (rule 15: no AI titles)
    last_activity_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationListItem(CamelModel):
    """One row of the Workspace conversation list (Stage 8.4). ``display_title`` is derived-on-read (the
    manual title when set, else the lecture/lab title) so old null-title rows render with no backfill;
    ``grounding_chip`` is the constant "Lecture grounded" in Option A (no ungrounded chat). Excludes
    soft-deleted AND access-revoked conversations (invariant C) — the list query is the 4.7 gate."""

    id: UUID
    display_title: str
    module_id: UUID
    module_title: str
    attached_section_id: UUID
    section_title: str
    section_type: str  # 'lecture' | 'lab'
    last_message_preview: str | None = None
    last_activity_at: datetime
    message_count: int
    grounding_chip: str


class RenameConversationRequest(CamelModel):
    title: str = Field(min_length=1, max_length=120)


class MessageRead(CamelModel):
    id: UUID
    role: str  # 'user' | 'assistant'
    status: str  # 'pending' | 'completed' | 'failed'
    content: str | None = None
    grounding_status: str | None = None  # 8.2
    answer_basis: str | None = None  # 8.2 "Where did this come from?" line
    retryable: bool = False
    failure_message: str | None = None  # sanitized; never a stack trace
    created_at: datetime


class SendMessageRequest(CamelModel):
    content: str = Field(min_length=1, max_length=4000)
    client_idempotency_key: str = Field(min_length=1, max_length=200)


class SendMessageResponse(CamelModel):
    """The user message (saved first) + the pending assistant reply the client polls for."""

    user_message: MessageRead
    assistant_message: MessageRead
