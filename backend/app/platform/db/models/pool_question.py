from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class PoolQuestion(Base):
    """A durable, validated question inside a SectionQuestionPool (Stage 6a, Layer 1).

    Options are stored canonically as JSONB (``[{"text", "isCorrect"}]``, exactly one correct) — the
    shuffle happens at SAMPLING time when the question is snapshotted into a per-attempt ``QuizQuestion`` /
    ``AnswerOption`` pair (correctness rides on option identity, never display letter). Validated by the
    OutputValidator (``_validate_quiz_pool``) before storage. A student has "seen" a PoolQuestion iff one
    of their attempts has a ``QuizQuestion`` row pointing back via ``source_pool_question_id`` — that
    back-reference is the MVP exposure ledger (recency bias + exhaustion-recycle read it).
    """

    __tablename__ = "pool_questions"
    __table_args__ = (
        Index(
            "ix_pool_questions_pool",
            "section_question_pool_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    section_question_pool_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("section_question_pools.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # Canonical options: [{"text": str, "isCorrect": bool}, ...] — exactly one true. Shuffled at sampling.
    options: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
