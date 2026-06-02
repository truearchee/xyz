"""Add transcript chunks.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


class Vector(sa.types.UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dimensions})"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "ingestion_jobs",
        sa.Column("result_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "transcript_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("end_segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_sequence_number", sa.Integer(), nullable=False),
        sa.Column("end_sequence_number", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.BigInteger(), nullable=True),
        sa.Column("end_time", sa.BigInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("token_count_method", sa.Text(), nullable=False),
        sa.Column("normalization_version", sa.Text(), nullable=False),
        sa.Column("chunking_version", sa.Text(), nullable=False),
        sa.Column("is_oversized", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_version", sa.Text(), nullable=True),
        sa.Column("embedding_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("token_count > 0", name="ck_transcript_chunks_token_count"),
        sa.CheckConstraint(
            "length(btrim(text)) > 0",
            name="ck_transcript_chunks_text_not_blank",
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_transcript_chunks_chunk_index"),
        sa.CheckConstraint(
            "end_sequence_number >= start_sequence_number",
            name="ck_transcript_chunks_sequence_range",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_transcript_chunks_transcript_id_transcripts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["start_segment_id"],
            ["transcript_segments.id"],
            name="fk_transcript_chunks_start_segment_id_transcript_segments",
        ),
        sa.ForeignKeyConstraint(
            ["end_segment_id"],
            ["transcript_segments.id"],
            name="fk_transcript_chunks_end_segment_id_transcript_segments",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transcript_id",
            "chunk_index",
            name="uq_transcript_chunks_transcript_chunk_index",
        ),
    )


def downgrade() -> None:
    op.drop_table("transcript_chunks")
    op.drop_column("ingestion_jobs", "result_metadata")
