"""Add transcript segments and ingestion jobs.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=True),
        sa.Column("end_ms", sa.BigInteger(), nullable=True),
        sa.Column("speaker_name", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sequence_number >= 0", name="ck_transcript_segments_sequence_number"),
        sa.CheckConstraint(
            "(start_ms IS NULL AND end_ms IS NULL) OR (start_ms IS NOT NULL AND end_ms IS NOT NULL)",
            name="ck_transcript_segments_timestamp_pair",
        ),
        sa.CheckConstraint("start_ms IS NULL OR start_ms >= 0", name="ck_transcript_segments_start_ms"),
        sa.CheckConstraint("end_ms IS NULL OR end_ms > start_ms", name="ck_transcript_segments_end_ms"),
        sa.CheckConstraint("length(trim(text)) > 0", name="ck_transcript_segments_text_not_blank"),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_transcript_segments_transcript_id_transcripts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transcript_id",
            "sequence_number",
            name="uq_transcript_segments_transcript_sequence",
        ),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("processor_version", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "job_type IN ('parse', 'chunk', 'embed', 'generate_brief_summary', 'generate_detailed_summary')",
            name="ck_ingestion_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_ingestion_jobs_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_ingestion_jobs_attempts"),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_ingestion_jobs_transcript_id_transcripts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ingestion_jobs_idempotency_key",
        "ingestion_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_ingestion_jobs_transcript_job_type",
        "ingestion_jobs",
        ["transcript_id", "job_type"],
        unique=False,
    )
    op.create_index(
        "ix_transcripts_status_created_at",
        "transcripts",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transcripts_status_created_at", table_name="transcripts")
    op.drop_index("ix_ingestion_jobs_transcript_job_type", table_name="ingestion_jobs")
    op.drop_index("uq_ingestion_jobs_idempotency_key", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_table("transcript_segments")
