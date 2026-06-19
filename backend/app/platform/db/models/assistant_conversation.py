from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
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


class AssistantConversation(Base):
    """A student's assistant conversation (Stage 8.1).

    Shaped as a LIST of conversations (8.4-ready): each carries a ``conversation_kind`` and an OPTIONAL
    ``attached_section_id`` (the lecture/lab it belongs to). For 8.1 the lecture entry point creates a
    ``lecture_default`` conversation attached to the section the student is reading; the partial-unique
    index guarantees at most one ACTIVE (non-soft-deleted) such conversation per (student, section), so
    two tabs pressing "Start chat" cannot create duplicates. ``manual``/``floating_widget``/``workspace``
    (8.4) carry no such constraint, so multiple conversations per lecture remain possible later with no
    migration.

    Stage 8.4 adds the conversation-management lifecycle (migration 0040): ``deleted_at`` (soft-delete
    tombstone — excluded from the list + the one-active index, so reopen creates a fresh row),
    ``title_source`` (``auto`` until a manual rename flips it to ``manual``; an auto-title never
    overwrites a manual one — and titles are NEVER AI-generated, rule 15), and ``last_activity_at``
    (orders the list newest-first; bumped on user-message creation + successful assistant completion).
    """

    __tablename__ = "assistant_conversations"
    __table_args__ = (
        CheckConstraint(
            "conversation_kind IN ('lecture_default', 'manual', 'floating_widget', 'workspace')",
            name="ck_assistant_conversations_kind",
        ),
        CheckConstraint(
            "title_source IN ('auto', 'manual')",
            name="ck_assistant_conversations_title_source",
        ),
        Index("ix_assistant_conversations_student", "student_id"),
        # Race-safe single lecture_default per (student, section); scoped to the kind AND excluding
        # soft-deleted rows (8.4) so delete-then-reopen creates a fresh conversation (invariant A).
        Index(
            "uq_assistant_conversations_one_lecture_default",
            "student_id",
            "attached_section_id",
            unique=True,
            postgresql_where=text("conversation_kind = 'lecture_default' AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_kind: Mapped[str] = mapped_column(Text, nullable=False)
    attached_section_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="CASCADE"),
    )
    title: Mapped[str | None] = mapped_column(Text)
    # 8.4: 'auto' (title derived-on-read from the lecture) until a manual rename flips it to 'manual';
    # an auto-title never overwrites a manual one. Titles are NEVER AI-generated (rule 15).
    title_source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'auto'"),
    )
    # 8.4: soft-delete tombstone — excluded from the list + the one-active index; reopen → 404.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 8.4: orders the conversation list newest-first; bumped on user-message creation and successful
    # assistant completion only (read paths COALESCE it with updated_at).
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
