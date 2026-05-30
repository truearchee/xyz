"""Convert section assets to storage metadata.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_section_assets_uploaded_by_id_app_users",
        "section_assets",
        type_="foreignkey",
    )
    op.alter_column(
        "section_assets",
        "file_url",
        new_column_name="storage_key",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "section_assets",
        "uploaded_by_id",
        new_column_name="uploaded_by_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
    )
    op.add_column("section_assets", sa.Column("checksum_sha256", sa.Text(), nullable=True))
    op.execute(
        "UPDATE section_assets SET checksum_sha256 = repeat('0', 64) "
        "WHERE checksum_sha256 IS NULL"
    )
    op.alter_column(
        "section_assets",
        "checksum_sha256",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "section_assets",
        "processing_status",
        server_default=sa.text("'completed'"),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE section_assets SET processing_status = 'completed' "
        "WHERE processing_status = 'uploaded'"
    )
    op.create_foreign_key(
        "fk_section_assets_uploaded_by_user_id_app_users",
        "section_assets",
        "app_users",
        ["uploaded_by_user_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_section_assets_storage_key",
        "section_assets",
        ["storage_key"],
    )
    op.create_index(
        "ix_section_assets_section",
        "section_assets",
        ["module_section_id"],
        unique=False,
    )
    op.create_index(
        "ix_section_assets_uploader",
        "section_assets",
        ["uploaded_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_section_assets_uploader", table_name="section_assets")
    op.drop_index("ix_section_assets_section", table_name="section_assets")
    op.drop_constraint(
        "uq_section_assets_storage_key",
        "section_assets",
        type_="unique",
    )
    op.drop_constraint(
        "fk_section_assets_uploaded_by_user_id_app_users",
        "section_assets",
        type_="foreignkey",
    )
    op.alter_column(
        "section_assets",
        "processing_status",
        server_default=sa.text("'uploaded'"),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.drop_column("section_assets", "checksum_sha256")
    op.alter_column(
        "section_assets",
        "uploaded_by_user_id",
        new_column_name="uploaded_by_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
    )
    op.alter_column(
        "section_assets",
        "storage_key",
        new_column_name="file_url",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.create_foreign_key(
        "fk_section_assets_uploaded_by_id_app_users",
        "section_assets",
        "app_users",
        ["uploaded_by_id"],
        ["id"],
    )
