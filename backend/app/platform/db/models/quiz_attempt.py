from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.platform.db.models.base import Base


class QuizAttempt(Base):
    """A student's attempt at a quiz definition (Stage 5 lock 3).

    The attempt row is its OWN status tracker (``generating → in_progress | completed | failed`` — no
    ``abandoned``, D-ABANDON) and the recovery target — there is no separate quiz-job table. INVARIANT 1
    (partial-unique one-active per student+definition) makes resume-vs-restart unambiguous; INVARIANT 2
    (unique student+definition+attempt_number) keeps history integrity. Provenance lives HERE (lock 6a):
    this is the row you query to answer "why did this quiz look wrong?". ``score_percentage`` is computed
    from counts (``correct_count == total_questions`` for perfect), never float equality.
    """

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('generating', 'in_progress', 'completed', 'failed')",
            name="ck_quiz_attempts_status",
        ),
        CheckConstraint(
            "failure_category IS NULL OR failure_category IN "
            "('generation_timeout', 'provider_error', 'invalid_output', 'enqueue_failed', 'crashed')",
            name="ck_quiz_attempts_failure_category",
        ),
        UniqueConstraint(
            "student_id",
            "quiz_definition_id",
            "attempt_number",
            name="uq_quiz_attempts_student_def_number",
        ),
        Index(
            "uq_quiz_attempts_one_active",
            "student_id",
            "quiz_definition_id",
            unique=True,
            postgresql_where=text("status IN ('generating', 'in_progress')"),
        ),
        Index(
            "ix_quiz_attempts_student_definition",
            "student_id",
            "quiz_definition_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )
    quiz_definition_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("quiz_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    # Score fields (populated on completion).
    total_questions: Mapped[int | None] = mapped_column(Integer)
    new_question_count: Mapped[int | None] = mapped_column(Integer)
    mistake_review_question_count: Mapped[int | None] = mapped_column(Integer)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    incorrect_count: Mapped[int | None] = mapped_column(Integer)
    score_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # Provenance (lock 6a) — all nullable; stamped by the generation pipeline (5b).
    source_summary_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("generated_lecture_summaries.id", ondelete="SET NULL"),
    )
    source_summary_content_hash: Mapped[str | None] = mapped_column(Text)
    source_transcript_checksum: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    backend_used: Mapped[str | None] = mapped_column(Text)
    ai_request_log_id: Mapped[UUID | None] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("ai_request_logs.id", ondelete="SET NULL"),
    )
    # RQ job id ("quiz-generate-{attemptId}"); a string identity, not a DB row — no FK.
    generation_job_id: Mapped[str | None] = mapped_column(Text)
    generation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_category: Mapped[str | None] = mapped_column(Text)
    failure_message_sanitized: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
