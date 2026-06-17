from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class StudentAnswer(Base):
    """A student's answer to one question of one attempt (Stage 5 data model).

    ``is_correct`` is denormalized at write time (computed server-side from the submitted option's
    identity) to avoid joining ``answer_options`` on every read. ``UNIQUE(quiz_attempt_id,
    quiz_question_id)`` is the DB-enforced answer idempotency guard: a double-tap / two-tab resubmit
    raises ``IntegrityError`` and the endpoint returns the ORIGINAL feedback, so ``correct_count`` can
    never be inflated by a second row.
    """

    __tablename__ = "student_answers"
    __table_args__ = (
        UniqueConstraint(
            "quiz_attempt_id",
            "quiz_question_id",
            name="uq_student_answers_attempt_question",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    quiz_attempt_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    quiz_question_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_answer_option_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("answer_options.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
