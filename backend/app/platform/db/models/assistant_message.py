from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class AssistantMessage(Base):
    """One turn in an assistant conversation (Stage 8.1).

    The user message is saved FIRST (``role='user'``, ``status='completed'``); the assistant reply is a
    separate row (``role='assistant'``) with an explicit lifecycle: ``pending → completed | failed``
    (8.1; 8.3 widens to add ``streaming/partial/cancelled``). An assistant row carries the standard AI
    provenance set + ``ai_request_log_id`` (rule 6). ``grounding_status`` is null in 8.1 and populated by
    the 8.2 retrieval path. ``client_idempotency_key`` on the user row + a partial-unique index make
    sending double-send-safe (decision 8); a retry re-activates the failed assistant row (or creates a
    new attempt) and NEVER duplicates the user message (decision 11).
    """

    __tablename__ = "assistant_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_assistant_messages_role",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_assistant_messages_status",
        ),
        CheckConstraint(
            "grounding_status IS NULL OR grounding_status IN "
            "('lecture_grounded', 'general_not_from_lecture', 'educational_redirect', "
            "'context_unavailable', 'access_denied')",
            name="ck_assistant_messages_grounding_status",
        ),
        CheckConstraint(
            "backend_used IS NULL OR backend_used IN ('cerebras', 'nvidia')",
            name="ck_assistant_messages_backend_used",
        ),
        Index(
            "ix_assistant_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
        # Double-send safety: one user message per (conversation, client idempotency key).
        Index(
            "uq_assistant_messages_user_idempotency",
            "conversation_id",
            "client_idempotency_key",
            unique=True,
            postgresql_where=text("role = 'user' AND client_idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The user message an assistant reply answers (self-ref); NULL on user rows.
    prompt_message_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("assistant_messages.id", ondelete="SET NULL"),
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    grounding_status: Mapped[str | None] = mapped_column(Text)
    # Provenance (assistant rows; rule 6) — populated when the turn completes.
    model_id: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    backend_used: Mapped[str | None] = mapped_column(Text)
    input_content_hash: Mapped[str | None] = mapped_column(Text)
    ai_request_log_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id", ondelete="SET NULL"),
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_category: Mapped[str | None] = mapped_column(Text)
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    client_idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
