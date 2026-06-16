from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class AnswerOption(Base):
    """One option of a multiple-choice question (Stage 5 lock 7).

    ``is_correct`` is the truth; correctness is always identified by this row's identity, never by a
    display letter (the client shuffles ``display_order``). "Exactly one correct per question" is
    enforced by the generation pipeline + OutputValidator (5b), not by a DB constraint. ``is_correct``
    is NEVER serialized in a student-facing DTO before the question is answered.
    """

    __tablename__ = "answer_options"
    __table_args__ = (
        Index(
            "ix_answer_options_question_order",
            "quiz_question_id",
            "display_order",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    quiz_question_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa_text("now()"),
    )
