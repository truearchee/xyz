"""QuizAttempt — per-student attempt + provenance + score (its own status tracker).

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-16

Stage 5 (locks 3 / 4 / 6a) — the attempt row is its own status tracker and recovery target (no
separate quiz-job table). INVARIANT 1: partial-unique one-active per (student, definition) WHERE status
IN ('generating','in_progress'). INVARIANT 2: UNIQUE (student, definition, attempt_number). Provenance
(summary id/hash, transcript checksum, model/prompt/backend, ai_request_log id, generation job id,
timings, failure category/message) lives on the attempt. Guards existence-checked.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :name
                """
            ),
            {"name": name},
        ).scalar()
    )


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"
            ),
            {"name": name},
        ).scalar()
    )


def upgrade() -> None:
    if not _table_exists("quiz_attempts"):
        op.create_table(
            "quiz_attempts",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quiz_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("total_questions", sa.Integer(), nullable=True),
            sa.Column("new_question_count", sa.Integer(), nullable=True),
            sa.Column("mistake_review_question_count", sa.Integer(), nullable=True),
            sa.Column("correct_count", sa.Integer(), nullable=True),
            sa.Column("incorrect_count", sa.Integer(), nullable=True),
            sa.Column("score_percentage", sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column("source_summary_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_summary_content_hash", sa.Text(), nullable=True),
            sa.Column("source_transcript_checksum", sa.Text(), nullable=True),
            sa.Column("model_name", sa.Text(), nullable=True),
            sa.Column("prompt_version", sa.Text(), nullable=True),
            sa.Column("backend_used", sa.Text(), nullable=True),
            sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("generation_job_id", sa.Text(), nullable=True),
            sa.Column("generation_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("generation_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_category", sa.Text(), nullable=True),
            sa.Column("failure_message_sanitized", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_quiz_attempts"),
            sa.ForeignKeyConstraint(
                ["quiz_definition_id"],
                ["quiz_definitions.id"],
                name="fk_quiz_attempts_quiz_definition_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_quiz_attempts_student_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_summary_id"],
                ["generated_lecture_summaries.id"],
                name="fk_quiz_attempts_source_summary_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["ai_request_log_id"],
                ["ai_request_logs.id"],
                name="fk_quiz_attempts_ai_request_log_id",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "status IN ('generating', 'in_progress', 'completed', 'failed')",
                name="ck_quiz_attempts_status",
            ),
            sa.CheckConstraint(
                "failure_category IS NULL OR failure_category IN "
                "('generation_timeout', 'provider_error', 'invalid_output', 'enqueue_failed', 'crashed')",
                name="ck_quiz_attempts_failure_category",
            ),
            sa.UniqueConstraint(
                "student_id",
                "quiz_definition_id",
                "attempt_number",
                name="uq_quiz_attempts_student_def_number",
            ),
        )
    if not _index_exists("uq_quiz_attempts_one_active"):
        op.create_index(
            "uq_quiz_attempts_one_active",
            "quiz_attempts",
            ["student_id", "quiz_definition_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('generating', 'in_progress')"),
        )
    if not _index_exists("ix_quiz_attempts_student_definition"):
        op.create_index(
            "ix_quiz_attempts_student_definition",
            "quiz_attempts",
            ["student_id", "quiz_definition_id"],
        )


def downgrade() -> None:
    if _index_exists("ix_quiz_attempts_student_definition"):
        op.drop_index("ix_quiz_attempts_student_definition", table_name="quiz_attempts")
    if _index_exists("uq_quiz_attempts_one_active"):
        op.drop_index("uq_quiz_attempts_one_active", table_name="quiz_attempts")
    if _table_exists("quiz_attempts"):
        op.drop_table("quiz_attempts")
