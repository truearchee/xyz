"""MaintenanceRun observability table for recovery runs.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-11

Stage 4.6c — Recovery. Adds the ``maintenance_runs`` table: one row per stuck-row-reaper /
storage-reconciliation execution (counts in ``summary_json``). This is what Stage 12 verifies recovery
from — queryable, not log-scraping. Guards are existence-checked so a partial run is re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012"
down_revision = "0011"
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
    if not _table_exists("maintenance_runs"):
        op.create_table(
            "maintenance_runs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_type", sa.Text(), nullable=False),
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column(
                "status", sa.Text(), nullable=False, server_default=sa.text("'running'")
            ),
            sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_maintenance_runs"),
            sa.ForeignKeyConstraint(
                ["triggered_by_user_id"],
                ["app_users.id"],
                name="fk_maintenance_runs_triggered_by_user_id",
            ),
            sa.CheckConstraint(
                "run_type IN ('stuck_row_reaper', 'storage_reconciliation')",
                name="ck_maintenance_runs_run_type",
            ),
            sa.CheckConstraint(
                "mode IN ('report_only', 'cleanup')",
                name="ck_maintenance_runs_mode",
            ),
            sa.CheckConstraint(
                "status IN ('running', 'completed', 'failed')",
                name="ck_maintenance_runs_status",
            ),
        )
    if not _index_exists("ix_maintenance_runs_run_type_started_at"):
        op.create_index(
            "ix_maintenance_runs_run_type_started_at",
            "maintenance_runs",
            ["run_type", "started_at"],
        )


def downgrade() -> None:
    if _index_exists("ix_maintenance_runs_run_type_started_at"):
        op.drop_index("ix_maintenance_runs_run_type_started_at", table_name="maintenance_runs")
    if _table_exists("maintenance_runs"):
        op.drop_table("maintenance_runs")
