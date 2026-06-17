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


class QuizQuestion(Base):
    """An ATTEMPT-SNAPSHOT question (Stage 5 lock 10).

    Never a pool: ``quiz_attempt_id`` is NOT NULL and questions belong to exactly one attempt. Stage 6
    question pools get a SEPARATE table — this table is never overloaded across two lifecycles. The
    Stage-6-ready nullable columns (``source_type``, ``source_mistake_record_id``, ``source_*``,
    ``model_name``, ``prompt_version``) are added NOW to avoid a hot-table migration; in Stage 5
    ``source_type`` is always ``new_generated`` and ``source_mistake_record_id`` is always null. The FK
    on ``source_mistake_record_id`` is created in migration 0019 (once ``mistake_records`` exists).
    """

    __tablename__ = "quiz_questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('multiple_choice')",
            name="ck_quiz_questions_question_type",
        ),
        CheckConstraint(
            "source_type IN ('new_generated', 'mistake_review')",
            name="ck_quiz_questions_source_type",
        ),
        Index(
            "ix_quiz_questions_attempt_order",
            "quiz_attempt_id",
            "display_order",
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
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'multiple_choice'"),
    )
    explanation: Mapped[str | None] = mapped_column(Text)

    # Stage-6-ready provenance/source columns (Stage 5: source_type='new_generated', rest null).
    source_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'new_generated'"),
    )
    # FK to mistake_records added in 0019 (table created after this one); bare UUID here.
    source_mistake_record_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    # Stage 6a: the durable PoolQuestion this attempt-question was sampled+snapshotted from. Set when
    # source_type='new_generated' under the pooled model; NULL for mistake_review and pre-retrofit
    # post-class rows (treated as "unseen" by exposure). FK to pool_questions added in 0023; bare UUID here.
    source_pool_question_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    source_module_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    source_section_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    source_summary_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    model_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
