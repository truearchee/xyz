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


class GlossarySourceReference(Base):
    """Where a glossary entry came from (Stage 7a) — many per entry.

    On a confirmed duplicate save the system attaches a NEW source reference to the existing entry
    rather than creating a second entry (Slice 6). ``source_type='quiz'`` is allowed from 7a so the
    7d quiz-highlight integration needs no migration. ``source_type='conversation'`` (Stage 8.5) adds
    the assistant-chat origin — ``source_conversation_id`` + ``source_message_id`` point at the
    completed assistant reply the term was highlighted in. FKs are ``SET NULL`` so a deleted source
    does not destroy the entry's provenance trail. The partial-unique index makes the duplicate-save
    "attach the chat as another source" path IDEMPOTENT (same entry + same message never twice, 8.5 D3).
    """

    __tablename__ = "glossary_source_references"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('summary', 'manual', 'quiz', 'conversation')",
            name="ck_glossary_source_references_source_type",
        ),
        Index("ix_glossary_source_references_entry", "glossary_entry_id"),
        Index(
            "uq_glossary_source_references_conversation_message",
            "glossary_entry_id",
            "source_message_id",
            unique=True,
            postgresql_where=text(
                "source_type = 'conversation' AND source_message_id IS NOT NULL"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    glossary_entry_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("glossary_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    module_section_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="SET NULL"),
    )
    source_summary_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("generated_lecture_summaries.id", ondelete="SET NULL"),
    )
    # Set by the 7d quiz-highlight integration.
    source_quiz_attempt_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="SET NULL"),
    )
    # Set by the Stage 8.5 assistant save: the conversation + completed assistant message a term was
    # highlighted in. ``selected_text`` carries the server-verified, ≤500-char snippet (provenance only —
    # it is NOT fed to the definition prompt; chat saves get a subject-level definition, ADR-055).
    source_conversation_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("assistant_conversations.id", ondelete="SET NULL"),
    )
    source_message_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("assistant_messages.id", ondelete="SET NULL"),
    )
    selected_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
