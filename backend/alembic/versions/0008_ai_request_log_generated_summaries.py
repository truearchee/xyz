"""Add AIRequestLog + GeneratedLectureSummary tables and summary job support.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-10

Stage 4.5a — AI provenance + capacity infrastructure (deterministic provider).
Creates the gateway-attempt log and the success-only summary artifact table, adds
ingestion_jobs.failure_category, and extends the migration-0007 one-active partial-unique
index pattern to the two summary job types.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


SUMMARY_ACTIVE_INDEX = "ingestion_jobs_one_active_summary_per_transcript"
FAILURE_CATEGORY_CONSTRAINT = "ck_ingestion_jobs_failure_category"


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
    if not _table_exists("ai_request_logs"):
        op.create_table(
            "ai_request_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("ingestion_job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "attempt_number", sa.Integer(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column("feature", sa.Text(), nullable=False),
            sa.Column("model_id", sa.Text(), nullable=False),
            sa.Column("prompt_version", sa.Text(), nullable=False),
            sa.Column("prompt_content_hash", sa.Text(), nullable=False),
            sa.Column("rendered_prompt_hash", sa.Text(), nullable=False),
            sa.Column("input_content_hash", sa.Text(), nullable=False),
            sa.Column("backend_used", sa.Text(), nullable=True),
            sa.Column("estimated_prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("reasoning_level", sa.Text(), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column(
                "request_started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("request_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("provider_request_id", sa.Text(), nullable=True),
            sa.Column("error_class", sa.Text(), nullable=True),
            sa.Column("error_code", sa.Text(), nullable=True),
            sa.Column("debug_text_truncated", sa.Text(), nullable=True),
            sa.Column(
                "status", sa.Text(), nullable=False, server_default=sa.text("'running'")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_ai_request_logs"),
            sa.ForeignKeyConstraint(
                ["ingestion_job_id"],
                ["ingestion_jobs.id"],
                name="fk_ai_request_logs_ingestion_job_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "attempt_number >= 1", name="ck_ai_request_logs_attempt_number"
            ),
            sa.CheckConstraint(
                "feature IN ('summary_brief', 'summary_detailed')",
                name="ck_ai_request_logs_feature",
            ),
            sa.CheckConstraint(
                "backend_used IS NULL OR backend_used IN ('cerebras', 'nvidia')",
                name="ck_ai_request_logs_backend_used",
            ),
            sa.CheckConstraint(
                "status IN ('running', 'succeeded', 'rate_limited', 'provider_transient', "
                "'invalid_output', 'invalid_input', 'failed')",
                name="ck_ai_request_logs_status",
            ),
        )
        op.create_index(
            "ix_ai_request_logs_feature_created_at",
            "ai_request_logs",
            ["feature", "created_at"],
        )
        op.create_index(
            "ix_ai_request_logs_ingestion_job_id",
            "ai_request_logs",
            ["ingestion_job_id"],
        )

    if not _table_exists("generated_lecture_summaries"):
        op.create_table(
            "generated_lecture_summaries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("summary_type", sa.Text(), nullable=False),
            sa.Column(
                "content_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("content_schema_version", sa.Text(), nullable=False),
            sa.Column("model_id", sa.Text(), nullable=False),
            sa.Column("prompt_version", sa.Text(), nullable=False),
            sa.Column("prompt_content_hash", sa.Text(), nullable=False),
            sa.Column("backend_used", sa.Text(), nullable=False),
            sa.Column("reasoning_level", sa.Text(), nullable=True),
            sa.Column("source_transcript_checksum", sa.Text(), nullable=False),
            sa.Column("input_hash", sa.Text(), nullable=False),
            sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "generated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
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
            sa.PrimaryKeyConstraint("id", name="pk_generated_lecture_summaries"),
            sa.ForeignKeyConstraint(
                ["transcript_id"],
                ["transcripts.id"],
                name="fk_gen_summaries_transcript_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["module_section_id"],
                ["module_sections.id"],
                name="fk_gen_summaries_module_section_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["ai_request_log_id"],
                ["ai_request_logs.id"],
                name="fk_gen_summaries_ai_request_log_id",
            ),
            sa.CheckConstraint(
                "summary_type IN ('brief', 'detailed_study')",
                name="ck_gen_summaries_summary_type",
            ),
            sa.CheckConstraint(
                "backend_used IN ('cerebras', 'nvidia')",
                name="ck_gen_summaries_backend_used",
            ),
            sa.UniqueConstraint(
                "transcript_id",
                "summary_type",
                "source_transcript_checksum",
                "prompt_version",
                "prompt_content_hash",
                "input_hash",
                name="uq_gen_summaries_provenance",
            ),
        )

    if "failure_category" not in _column_names("ingestion_jobs"):
        op.add_column(
            "ingestion_jobs",
            sa.Column("failure_category", sa.Text(), nullable=True),
        )
    if not _constraint_exists(FAILURE_CATEGORY_CONSTRAINT):
        op.create_check_constraint(
            FAILURE_CATEGORY_CONSTRAINT,
            "ingestion_jobs",
            "failure_category IS NULL OR failure_category IN "
            "('provider_transient', 'rate_limited', 'invalid_output', 'invalid_input', 'failed')",
        )

    if not _index_exists(SUMMARY_ACTIVE_INDEX):
        op.create_index(
            SUMMARY_ACTIVE_INDEX,
            "ingestion_jobs",
            ["transcript_id", "job_type"],
            unique=True,
            postgresql_where=sa.text(
                "job_type IN ('generate_brief_summary', 'generate_detailed_summary') "
                "AND status IN ('queued', 'running')"
            ),
        )


def downgrade() -> None:
    if _index_exists(SUMMARY_ACTIVE_INDEX):
        op.drop_index(SUMMARY_ACTIVE_INDEX, table_name="ingestion_jobs")
    if _constraint_exists(FAILURE_CATEGORY_CONSTRAINT):
        op.drop_constraint(FAILURE_CATEGORY_CONSTRAINT, "ingestion_jobs", type_="check")
    if "failure_category" in _column_names("ingestion_jobs"):
        op.drop_column("ingestion_jobs", "failure_category")
    if _table_exists("generated_lecture_summaries"):
        op.drop_table("generated_lecture_summaries")
    if _table_exists("ai_request_logs"):
        op.drop_table("ai_request_logs")
