"""QuizQuestion (attempt-snapshot) + AnswerOption.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-16

Stage 5 (locks 7 / 10) — questions are an ATTEMPT SNAPSHOT (quiz_attempt_id NOT NULL), never a pool;
Stage 6 pools get a separate table. Stage-6-ready nullable columns are added now to avoid a hot-table
migration (Stage 5: source_type='new_generated', source_mistake_record_id null — its FK is added in
0019 once mistake_records exists). AnswerOption.is_correct is the truth; correctness is by option
identity, never letter. Guards existence-checked.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017"
down_revision = "0016"
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
    if not _table_exists("quiz_questions"):
        op.create_table(
            "quiz_questions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quiz_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column(
                "question_type",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'multiple_choice'"),
            ),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column(
                "source_type",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'new_generated'"),
            ),
            sa.Column("source_mistake_record_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_module_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_section_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_summary_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("model_name", sa.Text(), nullable=True),
            sa.Column("prompt_version", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_quiz_questions"),
            sa.ForeignKeyConstraint(
                ["quiz_attempt_id"],
                ["quiz_attempts.id"],
                name="fk_quiz_questions_quiz_attempt_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "question_type IN ('multiple_choice')",
                name="ck_quiz_questions_question_type",
            ),
            sa.CheckConstraint(
                "source_type IN ('new_generated', 'mistake_review')",
                name="ck_quiz_questions_source_type",
            ),
        )
    if not _index_exists("ix_quiz_questions_attempt_order"):
        op.create_index(
            "ix_quiz_questions_attempt_order",
            "quiz_questions",
            ["quiz_attempt_id", "display_order"],
        )

    if not _table_exists("answer_options"):
        op.create_table(
            "answer_options",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quiz_question_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column("is_correct", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_answer_options"),
            sa.ForeignKeyConstraint(
                ["quiz_question_id"],
                ["quiz_questions.id"],
                name="fk_answer_options_quiz_question_id",
                ondelete="CASCADE",
            ),
        )
    if not _index_exists("ix_answer_options_question_order"):
        op.create_index(
            "ix_answer_options_question_order",
            "answer_options",
            ["quiz_question_id", "display_order"],
        )


def downgrade() -> None:
    if _index_exists("ix_answer_options_question_order"):
        op.drop_index("ix_answer_options_question_order", table_name="answer_options")
    if _table_exists("answer_options"):
        op.drop_table("answer_options")
    if _index_exists("ix_quiz_questions_attempt_order"):
        op.drop_index("ix_quiz_questions_attempt_order", table_name="quiz_questions")
    if _table_exists("quiz_questions"):
        op.drop_table("quiz_questions")
