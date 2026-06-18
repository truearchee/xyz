from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class GlossaryPracticeSession(Base):
    """A glossary practice session (Stage 7b/7c) — the entity the ``glossary_practice_completed`` event
    keys off (``source_id = session id``).

    ``scope`` is 'course' (with ``subject_id``) or 'all' (``subject_id`` NULL = the student's whole deck).
    One active session per mode (partial-unique), mirroring ``quiz_attempts.uq_quiz_attempts_one_active``.
    Counts are populated on completion. NO AI runs during practice.
    """

    __tablename__ = "glossary_practice_sessions"
    __table_args__ = (
        CheckConstraint("scope IN ('course', 'all')", name="ck_glossary_practice_sessions_scope"),
        CheckConstraint(
            "mode IN ('flashcard', 'multiple_choice')",
            name="ck_glossary_practice_sessions_mode",
        ),
        CheckConstraint(
            "status IN ('in_progress', 'completed')",
            name="ck_glossary_practice_sessions_status",
        ),
        Index(
            "uq_glossary_practice_sessions_one_active",
            "student_id",
            "mode",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
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
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'in_progress'"),
    )
    total_count: Mapped[int | None] = mapped_column(Integer)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    not_known_count: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
