"""Stage 11.2 student recommendations and recommendation-copy AI feature.

Revision ID: 0057
Revises: 0056
Create Date: 2026-06-20

Adds the deterministic recommendation state/cache table. Recommendations are created from
11.1 risk snapshots; visibility revalidates against current data at read time. Also widens the
shared AIRequestLog feature CHECK to include lazy recommendation copy generation.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

FEATURE_CHECK = "ck_ai_request_logs_feature"
FEATURE_VALUES_NEW = (
    "('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool', "
    "'glossary_definition', 'assistant', 'recommendation_copy')"
)
FEATURE_VALUES_OLD = (
    "('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool', "
    "'glossary_definition', 'assistant')"
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
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_risk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("target_label", sa.Text(), nullable=False),
        sa.Column("deterministic_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("source_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column("lecturer_state", sa.Text(), nullable=False, server_default=sa.text("'new'")),
        sa.Column("lecturer_acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lecturer_dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("student_state", sa.Text(), nullable=False, server_default=sa.text("'new'")),
        sa.Column("student_shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("student_dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lecturer_ai_text", sa.Text(), nullable=True),
        sa.Column("student_ai_text", sa.Text(), nullable=True),
        sa.Column("ai_status", sa.Text(), nullable=False, server_default=sa.text("'not_requested'")),
        sa.Column("ai_failure_message_sanitized", sa.Text(), nullable=True),
        sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ai_model_id", sa.Text(), nullable=True),
        sa.Column("ai_prompt_version", sa.Text(), nullable=True),
        sa.Column("ai_input_hash", sa.Text(), nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_recommendations"),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_recommendations_agent_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_risk_snapshot_id"],
            ["student_risk_snapshots.id"],
            name="fk_recommendations_student_risk_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_recommendations_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_recommendations_module_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ai_request_log_id"],
            ["ai_request_logs.id"],
            name="fk_recommendations_ai_request_log_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_recommendations_status"),
        sa.CheckConstraint(
            "close_reason IS NULL OR close_reason IN ('cleared', 'superseded')",
            name="ck_recommendations_close_reason",
        ),
        sa.CheckConstraint(
            "lecturer_state IN ('new', 'acted', 'dismissed')",
            name="ck_recommendations_lecturer_state",
        ),
        sa.CheckConstraint(
            "student_state IN ('new', 'shown', 'dismissed')",
            name="ck_recommendations_student_state",
        ),
        sa.CheckConstraint(
            "ai_status IN ('not_requested', 'queued', 'succeeded', 'failed', 'template_fallback')",
            name="ck_recommendations_ai_status",
        ),
    )
    op.create_index(
        "uq_recommendations_active_student_reason_target",
        "recommendations",
        ["student_id", "reason_code", "target_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_recommendations_module_student_status",
        "recommendations",
        ["module_id", "student_id", "status"],
    )
    op.create_index(
        "ix_recommendations_student_status",
        "recommendations",
        ["student_id", "status"],
    )
    op.create_index(
        "ix_recommendations_ai_status",
        "recommendations",
        ["ai_status", "updated_at"],
    )

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
    op.drop_index("ix_recommendations_ai_status", table_name="recommendations")
    op.drop_index("ix_recommendations_student_status", table_name="recommendations")
    op.drop_index("ix_recommendations_module_student_status", table_name="recommendations")
    op.drop_index("uq_recommendations_active_student_reason_target", table_name="recommendations")
    op.drop_table("recommendations")
