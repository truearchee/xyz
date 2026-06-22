"""Stage 11.4 deterministic workload planner.

Revision ID: 0058
Revises: 0057
Create Date: 2026-06-20

Adds student availability plus reproducible, read-only workload plans and items.
No AI, provider, assistant, gamification, or Stage 10 data is involved.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("study_days", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preferred_window", sa.Text(), nullable=False),
        sa.Column("max_study_minutes_per_day", sa.Integer(), nullable=False),
        sa.Column("availability_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_availability"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_availability_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_student_availability_module_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("student_id", "module_id", name="uq_student_availability_student_module"),
        sa.CheckConstraint(
            "preferred_window IN ('morning', 'afternoon', 'evening', 'no_preference')",
            name="ck_student_availability_preferred_window",
        ),
        sa.CheckConstraint(
            "max_study_minutes_per_day > 0",
            name="ck_student_availability_max_minutes_positive",
        ),
        sa.CheckConstraint(
            "availability_version > 0",
            name="ck_student_availability_version_positive",
        ),
    )
    op.create_index(
        "ix_student_availability_module_student",
        "student_availability",
        ["module_id", "student_id"],
    )

    op.create_table(
        "workload_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("availability_version", sa.Integer(), nullable=False),
        sa.Column("source_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_workload_plans"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_workload_plans_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_workload_plans_module_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("availability_version > 0", name="ck_workload_plans_availability_version"),
    )
    op.create_index(
        "uq_workload_plans_active_student_module",
        "workload_plans",
        ["student_id", "module_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_workload_plans_module_student_created",
        "workload_plans",
        ["module_id", "student_id", "created_at"],
    )

    op.create_table(
        "workload_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workload_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_key", sa.Text(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("window", sa.Text(), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("estimate_minutes", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_reason_code", sa.Text(), nullable=True),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("tight", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tight_message", sa.Text(), nullable=True),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_workload_plan_items"),
        sa.ForeignKeyConstraint(
            ["workload_plan_id"],
            ["workload_plans.id"],
            name="fk_workload_plan_items_workload_plan_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_section_id"],
            ["module_sections.id"],
            name="fk_workload_plan_items_source_section_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("estimate_minutes > 0", name="ck_workload_plan_items_estimate_positive"),
        sa.CheckConstraint("reason IN ('deadline', 'gap')", name="ck_workload_plan_items_reason"),
        sa.CheckConstraint(
            '"window" IS NULL OR "window" IN (\'morning\', \'afternoon\', \'evening\')',
            name="ck_workload_plan_items_window",
        ),
        sa.CheckConstraint("sort_index >= 0", name="ck_workload_plan_items_sort_index"),
        sa.CheckConstraint(
            """
            (
              scheduled_start_at IS NOT NULL
              AND scheduled_end_at IS NOT NULL
              AND scheduled_date IS NOT NULL
              AND "window" IS NOT NULL
              AND scheduled_end_at > scheduled_start_at
            )
            OR
            (
              scheduled_start_at IS NULL
              AND scheduled_end_at IS NULL
              AND scheduled_date IS NULL
              AND "window" IS NULL
              AND tight = true
              AND tight_message IS NOT NULL
            )
            """,
            name="ck_workload_plan_items_schedule_or_tight_residual",
        ),
    )
    op.create_index(
        "ix_workload_plan_items_plan_sort",
        "workload_plan_items",
        ["workload_plan_id", "sort_index"],
    )
    op.create_index(
        "ix_workload_plan_items_section",
        "workload_plan_items",
        ["source_section_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workload_plan_items_section", table_name="workload_plan_items")
    op.drop_index("ix_workload_plan_items_plan_sort", table_name="workload_plan_items")
    op.drop_table("workload_plan_items")
    op.drop_index("ix_workload_plans_module_student_created", table_name="workload_plans")
    op.drop_index("uq_workload_plans_active_student_module", table_name="workload_plans")
    op.drop_table("workload_plans")
    op.drop_index("ix_student_availability_module_student", table_name="student_availability")
    op.drop_table("student_availability")
