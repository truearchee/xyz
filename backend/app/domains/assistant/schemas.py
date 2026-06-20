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
    attached_module_id: UUID | None = None  # 8.6a: set for a homework_help conversation (module binding)
    attached_assessment_scope_id: UUID | None = None  # 8.6b: set for an exam_prep conversation
    title: str | None = None  # raw stored title (manual rename); null while title_source = 'auto'
    title_source: str = "auto"  # 'auto' | 'manual' — a manual rename is never overwritten (rule 15: no AI titles)
    last_activity_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# 8.6a — mode entry. Each mode is a conversation_kind; binding requirements differ per kind. The handler
# validates the kind→binding matrix (homework: module required, section optional). Creation is idempotent
# (resume-or-create on the natural key), so a double-clicked starter never makes a duplicate.
class CreateConversationRequest(CamelModel):
    conversation_kind: str  # 8.6a: only 'homework_help' is accepted; others → 422 (8.6b/8.6c add more)
    module_id: UUID | None = None
    section_id: UUID | None = None
    assessment_scope_id: UUID | None = None  # reserved for exam_prep (8.6b)


class ConversationListItem(CamelModel):
    """One row of the Workspace conversation list (Stage 8.4). ``display_title`` is derived-on-read (the
    manual title when set, else the lecture/lab title, else a mode-derived fallback) so old null-title rows
    render with no backfill; ``grounding_chip`` is "Lecture grounded" for the lecture chat and a mode label
    otherwise. Excludes soft-deleted AND access-revoked conversations (invariant C) — the list query is the
    4.7 gate. 8.6a: a module-bound homework conversation has NO section, so the section fields are nullable
    and ``module_id``/``module_title`` are always present."""

    id: UUID
    conversation_kind: str
    display_title: str
    module_id: UUID
    module_title: str
    attached_section_id: UUID | None = None
    section_title: str | None = None
    section_type: str | None = None  # 'lecture' | 'lab' | None (module-bound homework / exam-prep)
    # 8.6b: set for an exam_prep conversation (read-only scope context for the conversation surface).
    assessment_scope_id: UUID | None = None
    assessment_scope_name: str | None = None
    covered_weeks: list[int] | None = None
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
