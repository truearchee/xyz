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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class MistakeRecord(Base):
    """A recorded wrong answer (Stage 5 data model — full Slice 3 minimum).

    CREATED and POPULATED in Stage 5 (on an incorrect answer); nothing READS it for practice until
    Stage 6. The question/options are SNAPSHOTTED (JSONB) so the mistake renders even if the source
    question later changes. ``source_quiz_definition_id`` and ``module_id`` are denormalized (not
    join-only) so Stage 6's "my mistakes in this module/quiz" does not join through a snapshot table.
    ``retake_correct_count`` / ``show_in_retake_prefix`` exist now but the 2-correct flip is Stage 6.
    ``UNIQUE(source_quiz_attempt_id, source_question_id)`` keeps the snapshot idempotent per attempt.
    """

    __tablename__ = "mistake_records"
    __table_args__ = (
        UniqueConstraint(
            "source_quiz_attempt_id",
            "source_question_id",
            name="uq_mistake_records_attempt_question",
        ),
        Index(
            "ix_mistake_records_student_module",
            "student_id",
            "module_id",
        ),
        # Stage 6a — the pooled-model upsert identity. Under reuse, re-missing the SAME pool question in
        # the SAME QuizDefinition (across different attempts → different source_question_id) must update
        # ONE record, not duplicate it (so "stays in the bank / flips at 2" stays coherent). The
        # ON-CONFLICT upsert keys on this partial-unique; pre-retrofit / mistake_review rows have a NULL
        # source_pool_question_id and fall back to uq_mistake_records_attempt_question above.
        Index(
            "uq_mistake_records_pool_identity",
            "student_id",
            "source_quiz_definition_id",
            "source_pool_question_id",
            unique=True,
            postgresql_where=text("source_pool_question_id IS NOT NULL"),
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
    module_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("course_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    module_section_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("module_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_quiz_definition_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_quiz_attempt_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_question_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Stage 6a: the durable PoolQuestion the missed question was sampled from (the upsert identity, above).
    # NULL for pre-retrofit post-class / mistake_review misses. FK to pool_questions added in 0024; bare here.
    source_pool_question_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    question_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    answer_options_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    selected_wrong_answer: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    retake_correct_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    show_in_retake_prefix: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
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
