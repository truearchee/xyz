"""QuizDefinition — thin per-section quiz anchor.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-16

Stage 5 (lock 2) — a thin anchor row materialized get-or-create on POST start only. No persisted
readiness status, no summary pointer (resolved live at Start, snapshotted on the attempt). The
partial-unique index enforces at most one ``post_class`` definition per section. ``quiz_mode`` carries
the full reserved vocabulary; only ``post_class`` is used in Stage 5. Guards existence-checked.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015"
down_revision = "0014"
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
    if not _table_exists("quiz_definitions"):
        op.create_table(
            "quiz_definitions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quiz_mode", sa.Text(), nullable=False),
            sa.Column(
                "question_policy",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("""'{"count": 10, "optionsPerQuestion": 4}'::jsonb"""),
            ),
            sa.Column("source_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            sa.PrimaryKeyConstraint("id", name="pk_quiz_definitions"),
            sa.ForeignKeyConstraint(
                ["module_section_id"],
                ["module_sections.id"],
                name="fk_quiz_definitions_module_section_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["module_id"],
                ["course_modules.id"],
                name="fk_quiz_definitions_module_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "quiz_mode IN ('post_class', 'recap', 'exam_prep', 'mistakes_bank')",
                name="ck_quiz_definitions_quiz_mode",
            ),
        )
    if not _index_exists("uq_quiz_definitions_post_class_section"):
        op.create_index(
            "uq_quiz_definitions_post_class_section",
            "quiz_definitions",
            ["module_section_id"],
            unique=True,
            postgresql_where=sa.text("quiz_mode = 'post_class'"),
        )


def downgrade() -> None:
    if _index_exists("uq_quiz_definitions_post_class_section"):
        op.drop_index(
            "uq_quiz_definitions_post_class_section",
            table_name="quiz_definitions",
        )
    if _table_exists("quiz_definitions"):
        op.drop_table("quiz_definitions")
