"""StudentAnswer — one answer per question per attempt (DB-enforced idempotency).

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-16

Stage 5 (data model) — ``is_correct`` is denormalized at write (computed server-side from the submitted
option's identity). ``UNIQUE(quiz_attempt_id, quiz_question_id)`` is the DB-enforced answer idempotency
guard: a double-tap / two-tab resubmit raises IntegrityError and the endpoint returns the ORIGINAL
feedback, so correct_count can never be inflated. Guards existence-checked.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018"
down_revision = "0017"
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


def upgrade() -> None:
    if not _table_exists("student_answers"):
        op.create_table(
            "student_answers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quiz_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quiz_question_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("selected_answer_option_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("is_correct", sa.Boolean(), nullable=False),
            sa.Column(
                "answered_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_student_answers"),
            sa.ForeignKeyConstraint(
                ["quiz_attempt_id"],
                ["quiz_attempts.id"],
                name="fk_student_answers_quiz_attempt_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["quiz_question_id"],
                ["quiz_questions.id"],
                name="fk_student_answers_quiz_question_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["selected_answer_option_id"],
                ["answer_options.id"],
                name="fk_student_answers_selected_answer_option_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "quiz_attempt_id",
                "quiz_question_id",
                name="uq_student_answers_attempt_question",
            ),
        )


def downgrade() -> None:
    if _table_exists("student_answers"):
        op.drop_table("student_answers")
