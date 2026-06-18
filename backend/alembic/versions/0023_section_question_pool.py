"""Section question pool foundation (Stage 6a, Layer 1).

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-17

The durable, reusable per-section question store (capacity ADR): ``section_question_pools`` keyed
``(module_section_id, model, prompt_version)`` with two partial-unique indexes — one ``ready`` pool
(the live pool) and one ``generating`` pool (the herd lock, the 0007 ``ingestion_jobs`` pattern); and
``pool_questions`` (options canonical JSONB, shuffled at sampling). Adds the nullable
``quiz_questions.source_pool_question_id`` back-reference (the MVP exposure ledger) with its FK, and
widens the enumerated ``ai_request_logs.feature`` CHECK to gain ``'quiz_pool'`` (the 0020 precedent —
each consuming feature adds its value deliberately, never "anything"). Additive; quiz domain only.
Guards existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

FEATURE_CHECK = "ck_ai_request_logs_feature"
FEATURE_VALUES_NEW = "('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool')"
FEATURE_VALUES_OLD = "('summary_brief', 'summary_detailed', 'post_class_quiz')"


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


def upgrade() -> None:
    if not _table_exists("section_question_pools"):
        op.create_table(
            "section_question_pools",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("model", sa.Text(), nullable=False),
            sa.Column("prompt_version", sa.Text(), nullable=False),
            sa.Column("source_summary_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_summary_content_hash", sa.Text(), nullable=False),
            sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "status",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'generating'"),
            ),
            sa.Column("failure_category", sa.Text(), nullable=True),
            sa.Column("failure_message_sanitized", sa.Text(), nullable=True),
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
            sa.PrimaryKeyConstraint("id", name="pk_section_question_pools"),
            sa.ForeignKeyConstraint(
                ["module_section_id"],
                ["module_sections.id"],
                name="fk_section_question_pools_module_section_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_summary_id"],
                ["generated_lecture_summaries.id"],
                name="fk_section_question_pools_source_summary_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["ai_request_log_id"],
                ["ai_request_logs.id"],
                name="fk_section_question_pools_ai_request_log_id",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "status IN ('generating', 'ready', 'failed', 'superseded')",
                name="ck_section_question_pools_status",
            ),
            sa.CheckConstraint(
                "failure_category IS NULL OR failure_category IN "
                "('provider_error', 'invalid_output', 'crashed')",
                name="ck_section_question_pools_failure_category",
            ),
        )
    if not _index_exists("ix_section_question_pools_section"):
        op.create_index(
            "ix_section_question_pools_section",
            "section_question_pools",
            ["module_section_id"],
        )
    if not _index_exists("uq_section_question_pools_one_ready"):
        op.create_index(
            "uq_section_question_pools_one_ready",
            "section_question_pools",
            ["module_section_id", "model", "prompt_version"],
            unique=True,
            postgresql_where=sa.text("status = 'ready'"),
        )
    if not _index_exists("uq_section_question_pools_one_generating"):
        op.create_index(
            "uq_section_question_pools_one_generating",
            "section_question_pools",
            ["module_section_id", "model", "prompt_version"],
            unique=True,
            postgresql_where=sa.text("status = 'generating'"),
        )

    if not _table_exists("pool_questions"):
        op.create_table(
            "pool_questions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "section_question_pool_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_pool_questions"),
            sa.ForeignKeyConstraint(
                ["section_question_pool_id"],
                ["section_question_pools.id"],
                name="fk_pool_questions_section_question_pool_id",
                ondelete="CASCADE",
            ),
        )
    if not _index_exists("ix_pool_questions_pool"):
        op.create_index(
            "ix_pool_questions_pool",
            "pool_questions",
            ["section_question_pool_id"],
        )

    # quiz_questions.source_pool_question_id — the per-attempt → pool back-reference (exposure ledger).
    if not _column_exists("quiz_questions", "source_pool_question_id"):
        op.add_column(
            "quiz_questions",
            sa.Column(
                "source_pool_question_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )
    if not _constraint_exists("fk_quiz_questions_source_pool_question_id"):
        op.create_foreign_key(
            "fk_quiz_questions_source_pool_question_id",
            "quiz_questions",
            "pool_questions",
            ["source_pool_question_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Widen the enumerated feature CHECK to gain the pool-generation feature (0020 precedent).
    if _constraint_exists(FEATURE_CHECK):
        op.drop_constraint(FEATURE_CHECK, "ai_request_logs", type_="check")
    op.create_check_constraint(
        FEATURE_CHECK,
        "ai_request_logs",
        f"feature IN {FEATURE_VALUES_NEW}",
    )


def downgrade() -> None:
    if _constraint_exists(FEATURE_CHECK):
        op.drop_constraint(FEATURE_CHECK, "ai_request_logs", type_="check")
    op.create_check_constraint(
        FEATURE_CHECK,
        "ai_request_logs",
        f"feature IN {FEATURE_VALUES_OLD}",
    )

    if _constraint_exists("fk_quiz_questions_source_pool_question_id"):
        op.drop_constraint(
            "fk_quiz_questions_source_pool_question_id",
            "quiz_questions",
            type_="foreignkey",
        )
    if _column_exists("quiz_questions", "source_pool_question_id"):
        op.drop_column("quiz_questions", "source_pool_question_id")

    if _index_exists("ix_pool_questions_pool"):
        op.drop_index("ix_pool_questions_pool", table_name="pool_questions")
    if _table_exists("pool_questions"):
        op.drop_table("pool_questions")

    for index_name in (
        "uq_section_question_pools_one_generating",
        "uq_section_question_pools_one_ready",
        "ix_section_question_pools_section",
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name="section_question_pools")
    if _table_exists("section_question_pools"):
        op.drop_table("section_question_pools")
