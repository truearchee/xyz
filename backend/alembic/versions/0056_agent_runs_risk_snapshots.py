"""Stage 11.1 agent runs and deterministic risk snapshots.

Revision ID: 0056
Revises: 0082
Create Date: 2026-06-20

Stage 11 uses the assigned migration block 0056-0072. This first migration adds the
scheduler/run ledger and deterministic risk snapshot history. No AI or Stage 10 data is involved.

REBASE NOTE (three-branch landing): originally parented at 0041 (this branch's then-head). At the
final landing onto main, ``down_revision`` is re-parented from 0041 to the rebased main head 0082
(the no-op merge of Stage 8.6 head 0044 and Stage 10 head 0081) so the chain is single-headed:
0082 -> 0056 -> 0057 -> 0058 -> 0059. The Stage 11 numbers (0056-0059) do not collide with main's
(0042-0044, 0080-0082), so the files are re-parented, not renumbered.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0056"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("recommendation_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("plan_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("failure_message_sanitized", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["app_users.id"],
            name="fk_agent_runs_triggered_by_user_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_agent_runs_idempotency_key"),
        sa.CheckConstraint(
            "trigger_type IN ('scheduled_daily', 'pre_deadline', 'manual_admin')",
            name="ck_agent_runs_trigger_type",
        ),
        sa.CheckConstraint(
            "scope_type IN ('all', 'module', 'student', 'deadline')",
            name="ck_agent_runs_scope_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint("snapshot_count >= 0", name="ck_agent_runs_snapshot_count"),
        sa.CheckConstraint("recommendation_count >= 0", name="ck_agent_runs_recommendation_count"),
        sa.CheckConstraint("plan_count >= 0", name="ck_agent_runs_plan_count"),
    )
    op.create_index(
        "ix_agent_runs_status_scheduled_for",
        "agent_runs",
        ["status", "scheduled_for"],
    )
    op.create_index("ix_agent_runs_trigger_type", "agent_runs", ["trigger_type"])

    op.create_table(
        "student_risk_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_tier", sa.Text(), nullable=False),
        sa.Column(
            "risk_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("source_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_risk_snapshots"),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_student_risk_snapshots_agent_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_risk_snapshots_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_student_risk_snapshots_module_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "agent_run_id",
            "student_id",
            "module_id",
            name="uq_student_risk_snapshots_run_student_module",
        ),
        sa.CheckConstraint(
            "risk_tier IN ('on_track', 'watch', 'needs_support')",
            name="ck_student_risk_snapshots_risk_tier",
        ),
    )
    op.create_index(
        "ix_student_risk_snapshots_student_module_computed",
        "student_risk_snapshots",
        ["student_id", "module_id", "computed_at"],
    )
    op.create_index(
        "ix_student_risk_snapshots_module_tier",
        "student_risk_snapshots",
        ["module_id", "risk_tier"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_risk_snapshots_module_tier", table_name="student_risk_snapshots")
    op.drop_index(
        "ix_student_risk_snapshots_student_module_computed",
        table_name="student_risk_snapshots",
    )
    op.drop_table("student_risk_snapshots")
    op.drop_index("ix_agent_runs_trigger_type", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status_scheduled_for", table_name="agent_runs")
    op.drop_table("agent_runs")
