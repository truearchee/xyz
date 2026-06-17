"""MistakeRecord (full Slice 3 minimum) + the deferred quiz_questions→mistake_records FK.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-16

Stage 5 (data model) — created and POPULATED here (on an incorrect answer); nothing READS it for
practice until Stage 6. Question/options are snapshotted (JSONB); ``source_quiz_definition_id`` and
``module_id`` are denormalized so Stage 6 scoped queries do not join through a snapshot table.
``UNIQUE(source_quiz_attempt_id, source_question_id)`` keeps the snapshot idempotent per attempt.
This migration ALSO adds the FK on ``quiz_questions.source_mistake_record_id`` (deferred from 0017,
which created that column before this table existed). Guards existence-checked.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0019"
down_revision = "0018"
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


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).scalar()
    )


def upgrade() -> None:
    if not _table_exists("mistake_records"):
        op.create_table(
            "mistake_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_quiz_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_quiz_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_question_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column(
                "answer_options_snapshot",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("selected_wrong_answer", sa.Text(), nullable=False),
            sa.Column("correct_answer", sa.Text(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column(
                "retake_correct_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "show_in_retake_prefix",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
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
            sa.PrimaryKeyConstraint("id", name="pk_mistake_records"),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_mistake_records_student_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["module_id"],
                ["course_modules.id"],
                name="fk_mistake_records_module_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["module_section_id"],
                ["module_sections.id"],
                name="fk_mistake_records_module_section_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_quiz_definition_id"],
                ["quiz_definitions.id"],
                name="fk_mistake_records_source_quiz_definition_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_quiz_attempt_id"],
                ["quiz_attempts.id"],
                name="fk_mistake_records_source_quiz_attempt_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_question_id"],
                ["quiz_questions.id"],
                name="fk_mistake_records_source_question_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "source_quiz_attempt_id",
                "source_question_id",
                name="uq_mistake_records_attempt_question",
            ),
        )
    if not _index_exists("ix_mistake_records_student_module"):
        op.create_index(
            "ix_mistake_records_student_module",
            "mistake_records",
            ["student_id", "module_id"],
        )
    # Deferred FK from 0017: now that mistake_records exists, wire the Stage-6 mistake-review link.
    if not _constraint_exists("fk_quiz_questions_source_mistake_record_id"):
        op.create_foreign_key(
            "fk_quiz_questions_source_mistake_record_id",
            "quiz_questions",
            "mistake_records",
            ["source_mistake_record_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if _constraint_exists("fk_quiz_questions_source_mistake_record_id"):
        op.drop_constraint(
            "fk_quiz_questions_source_mistake_record_id",
            "quiz_questions",
            type_="foreignkey",
        )
    if _index_exists("ix_mistake_records_student_module"):
        op.drop_index("ix_mistake_records_student_module", table_name="mistake_records")
    if _table_exists("mistake_records"):
        op.drop_table("mistake_records")
