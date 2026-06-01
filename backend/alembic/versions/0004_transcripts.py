"""Add transcripts table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source_type",
            sa.Text(),
            server_default=sa.text("'manual_upload'"),
            nullable=False,
        ),
        sa.Column("original_file_name", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'uploaded'"),
            nullable=False,
        ),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('uploaded', 'queued', 'parsing', 'chunking', 'embedding', 'generating', 'completed', 'failed')",
            name="ck_transcripts_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual_upload', 'zoom_import')",
            name="ck_transcripts_source_type",
        ),
        sa.CheckConstraint(
            "NOT (is_active = true AND superseded_at IS NOT NULL)",
            name="ck_transcripts_active_not_superseded",
        ),
        sa.CheckConstraint(
            "source_type <> 'manual_upload' OR uploaded_by_user_id IS NOT NULL",
            name="ck_transcripts_manual_upload_has_uploader",
        ),
        sa.CheckConstraint("file_size > 0", name="ck_transcripts_file_size"),
        sa.CheckConstraint(
            "checksum ~ '^[a-f0-9]{64}$'",
            name="ck_transcripts_checksum_lower_hex",
        ),
        sa.ForeignKeyConstraint(
            ["module_section_id"],
            ["module_sections.id"],
            name="fk_transcripts_module_section_id_module_sections",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["app_users.id"],
            name="fk_transcripts_uploaded_by_user_id_app_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_active_transcript_per_section",
        "transcripts",
        ["module_section_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "uq_transcripts_storage_key",
        "transcripts",
        ["storage_key"],
        unique=True,
    )
    op.create_index(
        "ix_transcripts_module_section_id",
        "transcripts",
        ["module_section_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transcripts_module_section_id", table_name="transcripts")
    op.drop_index("uq_transcripts_storage_key", table_name="transcripts")
    op.drop_index("uq_active_transcript_per_section", table_name="transcripts")
    op.drop_table("transcripts")
