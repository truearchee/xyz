from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class GlossaryReviewState(Base):
    """Per-entry flashcard review state (Stage 7b) — a hardcoded-interval Leitner box.

    One row per glossary entry (created lazily on first practice). ``box`` indexes a hardcoded interval
    table (no adaptive SRS this stage). ``student_id`` / ``subject_id`` are denormalized so "due cards
    for this student / subject" is a single indexed scan without joining through the entry.
    """

    __tablename__ = "glossary_review_state"
    __table_args__ = (
        UniqueConstraint("glossary_entry_id", name="uq_glossary_review_state_entry"),
        Index("ix_glossary_review_state_due", "student_id", "subject_id", "due_at"),
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
    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    box: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_reviews: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    correct_streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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
