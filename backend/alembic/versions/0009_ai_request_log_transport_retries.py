"""Add in-row transport-retry provenance to ai_request_logs and the terminal provider categories.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-11

Stage 4.5b — first real K2Think call. Additive over the 0008 head:
- ai_request_logs gains provider_attempt_count, rate_limit_backoff_count, last_provider_status_code,
  retry_events_json (jsonb), backend_route_source — the in-call 429 backoff is recorded IN the single
  gateway-attempt row, not as new rows (§9).
- The ai_request_logs.status and ingestion_jobs.failure_category CHECKs gain
  'provider_config_error' / 'provider_auth_error' — terminal, non-retryable 4xx config/auth (§8).
All guards are existence-checked so a partially-applied run is re-runnable (matches 0008).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


STATUS_CONSTRAINT = "ck_ai_request_logs_status"
ROUTE_SOURCE_CONSTRAINT = "ck_ai_request_logs_backend_route_source"
FAILURE_CATEGORY_CONSTRAINT = "ck_ingestion_jobs_failure_category"

NEW_COLUMNS = (
    ("provider_attempt_count", lambda: sa.Column("provider_attempt_count", sa.Integer(), nullable=True)),
    ("rate_limit_backoff_count", lambda: sa.Column("rate_limit_backoff_count", sa.Integer(), nullable=True)),
    ("last_provider_status_code", lambda: sa.Column("last_provider_status_code", sa.Integer(), nullable=True)),
    ("retry_events_json", lambda: sa.Column("retry_events_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True)),
    ("backend_route_source", lambda: sa.Column("backend_route_source", sa.Text(), nullable=True)),
)

# status sets — 0008 head value and the 4.5b value (terminal 4xx config/auth added).
_STATUS_0008 = (
    "status IN ('running', 'succeeded', 'rate_limited', 'provider_transient', "
    "'invalid_output', 'invalid_input', 'failed')"
)
_STATUS_0009 = (
    "status IN ('running', 'succeeded', 'rate_limited', 'provider_transient', "
    "'invalid_output', 'invalid_input', 'provider_config_error', "
    "'provider_auth_error', 'failed')"
)
_FAILURE_0008 = (
    "failure_category IS NULL OR failure_category IN "
    "('provider_transient', 'rate_limited', 'invalid_output', 'invalid_input', 'failed')"
)
_FAILURE_0009 = (
    "failure_category IS NULL OR failure_category IN "
    "('provider_transient', 'rate_limited', 'invalid_output', 'invalid_input', "
    "'provider_config_error', 'provider_auth_error', 'failed')"
)


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
    }


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).scalar()
    )


def upgrade() -> None:
    existing = _column_names("ai_request_logs")
    for name, factory in NEW_COLUMNS:
        if name not in existing:
            op.add_column("ai_request_logs", factory())

    if not _constraint_exists(ROUTE_SOURCE_CONSTRAINT):
        op.create_check_constraint(
            ROUTE_SOURCE_CONSTRAINT,
            "ai_request_logs",
            "backend_route_source IS NULL OR "
            "backend_route_source IN ('requested', 'provider_echoed')",
        )

    # Replace the status CHECK to admit the terminal provider categories (§8).
    if _constraint_exists(STATUS_CONSTRAINT):
        op.drop_constraint(STATUS_CONSTRAINT, "ai_request_logs", type_="check")
    op.create_check_constraint(STATUS_CONSTRAINT, "ai_request_logs", _STATUS_0009)

    if _constraint_exists(FAILURE_CATEGORY_CONSTRAINT):
        op.drop_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", type_="check")
    op.create_check_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", _FAILURE_0009)


def downgrade() -> None:
    if _constraint_exists(FAILURE_CATEGORY_CONSTRAINT):
        op.drop_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", type_="check")
    op.create_check_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", _FAILURE_0008)

    if _constraint_exists(STATUS_CONSTRAINT):
        op.drop_constraint(STATUS_CONSTRAINT, "ai_request_logs", type_="check")
    op.create_check_constraint(STATUS_CONSTRAINT, "ai_request_logs", _STATUS_0008)

    if _constraint_exists(ROUTE_SOURCE_CONSTRAINT):
        op.drop_constraint(ROUTE_SOURCE_CONSTRAINT, "ai_request_logs", type_="check")

    existing = _column_names("ai_request_logs")
    for name, _ in reversed(NEW_COLUMNS):
        if name in existing:
            op.drop_column("ai_request_logs", name)
