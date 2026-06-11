"""Retry failure taxonomy: per-step sanitized failure_category values + parse one-active index.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-11

Stage 4.6b — Retry. Two additive changes:
- Widen ``ck_ingestion_jobs_failure_category`` so parse/chunk/embed can record a sanitized category
  (the existing provider-centric summary values stay). The internal full reason still lives on
  ``error_message``; the lecturer sees only the sanitized category (surfaced by the status projection).
- Add the parse one-active partial-unique index — the "current job" pointer 4.6b fencing keys off
  (parse has exactly one job per transcript, so it is safe; chunk stays WITHOUT one because two chunk
  jobs legitimately coexist, per the 4.6a deviation).
Guards are existence-checked so a partially-applied run is re-runnable (matches 0008/0009/0010).
"""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


FAILURE_CATEGORY_CONSTRAINT = "ck_ingestion_jobs_failure_category"
PARSE_ACTIVE_INDEX = "ingestion_jobs_one_active_parse_per_transcript"

# 0009/0010 head value (provider-centric, summary-only).
_FAILURE_0010 = (
    "failure_category IS NULL OR failure_category IN "
    "('provider_transient', 'rate_limited', 'invalid_output', 'invalid_input', "
    "'provider_config_error', 'provider_auth_error', 'failed')"
)
# 4.6b value: add the per-step sanitized categories.
_FAILURE_0011 = (
    "failure_category IS NULL OR failure_category IN "
    "('provider_transient', 'rate_limited', 'invalid_output', 'invalid_input', "
    "'provider_config_error', 'provider_auth_error', 'failed', "
    "'parse_failed', 'chunk_failed', 'embedding_failed', "
    "'storage_missing', 'unsupported_file', 'crashed')"
)


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
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
    if _constraint_exists(FAILURE_CATEGORY_CONSTRAINT):
        op.drop_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", type_="check")
    op.create_check_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", _FAILURE_0011)

    if not _index_exists(PARSE_ACTIVE_INDEX):
        op.create_index(
            PARSE_ACTIVE_INDEX,
            "ingestion_jobs",
            ["transcript_id", "job_type"],
            unique=True,
            postgresql_where=sa.text(
                "job_type = 'parse' AND status IN ('queued', 'running')"
            ),
        )


def downgrade() -> None:
    if _index_exists(PARSE_ACTIVE_INDEX):
        op.drop_index(PARSE_ACTIVE_INDEX, table_name="ingestion_jobs")

    if _constraint_exists(FAILURE_CATEGORY_CONSTRAINT):
        op.drop_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", type_="check")
    op.create_check_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", _FAILURE_0010)
