"""Stage 11.6 grade-forecast advice cache and grade_forecast_advice AI feature.

Revision ID: 0059
Revises: 0058
Create Date: 2026-06-21

Adds the student grade-forecast advice cache (one row per student/module). The advice EXPLAINS the
Stage 9 deterministic forecast; the deterministic template renders immediately and a lazy/cached AI
phrasing layer swaps in when ready. Also widens the shared AIRequestLog feature CHECK to include the
new lazy advice generation (`grade_forecast_advice`).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

FEATURE_CHECK = "ck_ai_request_logs_feature"
FEATURE_VALUES_NEW = (
    "('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool', "
    "'glossary_definition', 'assistant', 'recommendation_copy', 'grade_forecast_advice')"
)
FEATURE_VALUES_OLD = (
    "('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool', "
    "'glossary_definition', 'assistant', 'recommendation_copy')"
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
        "student_forecast_advice",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("source_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_state", sa.Text(), nullable=False),
        sa.Column("deterministic_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_status", sa.Text(), nullable=False, server_default=sa.text("'not_requested'")),
        sa.Column("ai_text", sa.Text(), nullable=True),
        sa.Column("ai_failure_message_sanitized", sa.Text(), nullable=True),
        sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ai_model_id", sa.Text(), nullable=True),
        sa.Column("ai_prompt_version", sa.Text(), nullable=True),
        sa.Column("ai_input_hash", sa.Text(), nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_forecast_advice"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_forecast_advice_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_student_forecast_advice_module_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ai_request_log_id"],
            ["ai_request_logs.id"],
            name="fk_student_forecast_advice_ai_request_log_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "student_id",
            "module_id",
            name="uq_student_forecast_advice_student_module",
        ),
        sa.CheckConstraint(
            "forecast_state IN ('final_no_remaining', 'achieved', 'impossible', "
            "'on_track', 'at_risk', 'requires_high_score')",
            name="ck_student_forecast_advice_forecast_state",
        ),
        sa.CheckConstraint(
            "ai_status IN ('not_requested', 'queued', 'succeeded', 'failed', 'template_fallback')",
            name="ck_student_forecast_advice_ai_status",
        ),
    )
    op.create_index(
        "ix_student_forecast_advice_ai_status",
        "student_forecast_advice",
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
    op.drop_index("ix_student_forecast_advice_ai_status", table_name="student_forecast_advice")
    op.drop_table("student_forecast_advice")
