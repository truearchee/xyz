from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class GlossaryPracticeAnswer(Base):
    """One shown card / question per row (Stage 7b/7c).

    Leaner than the Slice-6 four-table quiz set: there is no AI-generated, shareable, snapshot-worthy
    question artifact, so a card/question maps 1:1 to an answer slot. For Multiple-Choice the option
    identities (prompt + 3 distractors) are snapshotted in ``distractor_entry_ids`` so a reload renders
    the identical question; correctness rides on option IDENTITY (``selected_entry_id ==
    correct_entry_id``), never display position. ``outcome='not_known'`` records "Don't know?".
    """

    __tablename__ = "glossary_practice_answers"
    __table_args__ = (
        UniqueConstraint(
            "practice_session_id",
            "display_order",
            name="uq_glossary_practice_answers_session_order",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('known', 'not_known')",
            name="ck_glossary_practice_answers_outcome",
        ),
        Index("ix_glossary_practice_answers_session", "practice_session_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    practice_session_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("glossary_practice_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    glossary_entry_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("glossary_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # MCQ option identities (bare UUIDs — snapshots keyed for rendering/grading, not lineage).
    selected_entry_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    correct_entry_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    distractor_entry_ids: Mapped[list | None] = mapped_column(JSONB)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    # Flashcard / "Don't know?" outcome.
    outcome: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
