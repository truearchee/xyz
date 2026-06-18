"""MistakeRecord pooled-model upsert identity (Stage 6a).

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-17

Adds ``mistake_records.source_pool_question_id`` (FK → pool_questions, SET NULL) and the partial-unique
``(student_id, source_quiz_definition_id, source_pool_question_id) WHERE source_pool_question_id IS NOT
NULL``. This is the ON-CONFLICT upsert identity: under question reuse, re-missing the SAME pool question
in the SAME QuizDefinition (different attempts → different source_question_id) updates ONE record rather
than duplicating it, so "stays in the bank / flips at 2" stays coherent. Pre-retrofit and mistake_review
misses leave the column NULL and fall back to the Stage 5 ``uq_mistake_records_attempt_question`` identity
(both constraints coexist). Additive; quiz domain only. Guards existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


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


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
                """
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    if not _column_exists("mistake_records", "source_pool_question_id"):
        op.add_column(
            "mistake_records",
            sa.Column(
                "source_pool_question_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
    if not _constraint_exists("fk_mistake_records_source_pool_question_id"):
        op.create_foreign_key(
            "fk_mistake_records_source_pool_question_id",
            "mistake_records",
            "pool_questions",
            ["source_pool_question_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _index_exists("uq_mistake_records_pool_identity"):
        op.create_index(
            "uq_mistake_records_pool_identity",
            "mistake_records",
            ["student_id", "source_quiz_definition_id", "source_pool_question_id"],
            unique=True,
            postgresql_where=sa.text("source_pool_question_id IS NOT NULL"),
        )


def downgrade() -> None:
    if _index_exists("uq_mistake_records_pool_identity"):
        op.drop_index("uq_mistake_records_pool_identity", table_name="mistake_records")
    if _constraint_exists("fk_mistake_records_source_pool_question_id"):
        op.drop_constraint(
            "fk_mistake_records_source_pool_question_id",
            "mistake_records",
            type_="foreignkey",
        )
    if _column_exists("mistake_records", "source_pool_question_id"):
        op.drop_column("mistake_records", "source_pool_question_id")
