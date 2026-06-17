"""AssessmentScope + multi-section QuizDefinition (Stage 6b).

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-17

Recap and exam-prep are MULTI-SECTION quizzes: the QuizDefinition stores SCOPE, not a single section. This
adds the lecturer-defined ``assessment_scopes`` (exam-prep) and makes ``quiz_definitions`` multi-section
capable — ``module_section_id`` becomes NULLABLE (post_class rows keep their value and their existing
partial-unique index, which filters ``WHERE quiz_mode='post_class'``; recap/exam_prep/mistakes_bank rows
store NULL and carry scope in ``source_scope`` + ``scope_key``). A new partial-unique index dedups the
shared definition per ``(module_id, quiz_mode, scope_key)`` for the new modes. Additive; quiz domain only.
Guards existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0025"
down_revision = "0024"
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


def _column_is_nullable(table: str, column: str) -> bool | None:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).scalar()
    if result is None:
        return None
    return result == "YES"


def upgrade() -> None:
    if not _table_exists("assessment_scopes"):
        op.create_table(
            "assessment_scopes",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("covered_weeks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "status",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'active'"),
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
            sa.PrimaryKeyConstraint("id", name="pk_assessment_scopes"),
            sa.ForeignKeyConstraint(
                ["module_id"],
                ["course_modules.id"],
                name="fk_assessment_scopes_module_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"],
                ["app_users.id"],
                name="fk_assessment_scopes_created_by_user_id",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "status IN ('active', 'locked')",
                name="ck_assessment_scopes_status",
            ),
        )
    if not _index_exists("ix_assessment_scopes_module"):
        op.create_index("ix_assessment_scopes_module", "assessment_scopes", ["module_id"])

    # quiz_definitions → multi-section capable.
    if _column_is_nullable("quiz_definitions", "module_section_id") is False:
        op.alter_column(
            "quiz_definitions",
            "module_section_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )
    if not _column_exists("quiz_definitions", "scope_key"):
        op.add_column("quiz_definitions", sa.Column("scope_key", sa.Text(), nullable=True))
    if not _column_exists("quiz_definitions", "assessment_scope_id"):
        op.add_column(
            "quiz_definitions",
            sa.Column("assessment_scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _constraint_exists("fk_quiz_definitions_assessment_scope_id"):
        op.create_foreign_key(
            "fk_quiz_definitions_assessment_scope_id",
            "quiz_definitions",
            "assessment_scopes",
            ["assessment_scope_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # Shared-definition dedup for the new multi-section modes (post_class keeps its own 0015 index).
    if not _index_exists("uq_quiz_definitions_scope"):
        op.create_index(
            "uq_quiz_definitions_scope",
            "quiz_definitions",
            ["module_id", "quiz_mode", "scope_key"],
            unique=True,
            postgresql_where=sa.text(
                "quiz_mode IN ('recap', 'exam_prep', 'mistakes_bank')"
            ),
        )


def downgrade() -> None:
    if _index_exists("uq_quiz_definitions_scope"):
        op.drop_index("uq_quiz_definitions_scope", table_name="quiz_definitions")
    if _constraint_exists("fk_quiz_definitions_assessment_scope_id"):
        op.drop_constraint(
            "fk_quiz_definitions_assessment_scope_id", "quiz_definitions", type_="foreignkey"
        )
    if _column_exists("quiz_definitions", "assessment_scope_id"):
        op.drop_column("quiz_definitions", "assessment_scope_id")
    if _column_exists("quiz_definitions", "scope_key"):
        op.drop_column("quiz_definitions", "scope_key")
    # Restore NOT NULL (safe on a fresh-DB round-trip — no multi-section rows exist at downgrade time).
    if _column_is_nullable("quiz_definitions", "module_section_id") is True:
        op.alter_column(
            "quiz_definitions",
            "module_section_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=False,
        )

    if _index_exists("ix_assessment_scopes_module"):
        op.drop_index("ix_assessment_scopes_module", table_name="assessment_scopes")
    if _table_exists("assessment_scopes"):
        op.drop_table("assessment_scopes")
