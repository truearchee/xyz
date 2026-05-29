"""Create DB spine tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auth_provider_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "timezone",
            sa.Text(),
            server_default=sa.text("'UTC'"),
            nullable=False,
        ),
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
            "role IN ('student', 'lecturer', 'admin')",
            name="ck_app_users_role",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_users"),
        sa.UniqueConstraint("auth_provider_id", name="uq_app_users_auth_provider_id"),
        sa.UniqueConstraint("email", name="uq_app_users_email"),
    )

    op.create_table(
        "course_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timezone", sa.Text(), server_default=sa.text("'UTC'"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["app_users.id"],
            name="fk_course_modules_owner_id_app_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_course_modules"),
    )

    op.create_table(
        "course_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("role IN ('student', 'lecturer')", name="ck_course_memberships_role"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_course_memberships_status"),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_course_memberships_module_id_course_modules",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_users.id"],
            name="fk_course_memberships_user_id_app_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_course_memberships"),
    )
    op.create_index(
        "ix_course_memberships_active_user_module",
        "course_memberships",
        ["user_id", "module_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "module_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=True),
        sa.Column("session_date", sa.Date(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("lecturer_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "type IN ('lecture', 'lab', 'assignment', 'supplementary')",
            name="ck_module_sections_type",
        ),
        sa.CheckConstraint(
            "publish_status IN ('draft', 'published', 'unpublished')",
            name="ck_module_sections_publish_status",
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_module_sections_status"),
        sa.CheckConstraint("order_index >= 0", name="ck_module_sections_order_index"),
        sa.CheckConstraint(
            "week_number IS NULL OR week_number > 0",
            name="ck_module_sections_week_number",
        ),
        sa.ForeignKeyConstraint(
            ["course_module_id"],
            ["course_modules.id"],
            name="fk_module_sections_course_module_id_course_modules",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_module_sections"),
        sa.UniqueConstraint(
            "course_module_id",
            "order_index",
            name="uq_module_sections_module_order",
        ),
    )
    op.create_index(
        "ix_module_sections_module_week",
        "module_sections",
        ["course_module_id", "week_number"],
        unique=False,
    )
    op.create_index(
        "ix_module_sections_module_session_date",
        "module_sections",
        ["course_module_id", "session_date"],
        unique=False,
    )
    op.create_index(
        "ix_module_sections_due_at",
        "module_sections",
        ["due_at"],
        unique=False,
        postgresql_where=sa.text("due_at IS NOT NULL"),
    )
    op.create_index(
        "ix_module_sections_module_publish_status",
        "module_sections",
        ["course_module_id", "publish_status"],
        unique=False,
    )

    op.create_table(
        "section_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "processing_status",
            sa.Text(),
            server_default=sa.text("'uploaded'"),
            nullable=False,
        ),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "processing_status IN ('uploaded', 'processing', 'completed', 'failed')",
            name="ck_section_assets_processing_status",
        ),
        sa.CheckConstraint("file_size > 0", name="ck_section_assets_file_size"),
        sa.ForeignKeyConstraint(
            ["module_section_id"],
            ["module_sections.id"],
            name="fk_section_assets_module_section_id_module_sections",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["app_users.id"],
            name="fk_section_assets_uploaded_by_id_app_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_section_assets"),
    )


def downgrade() -> None:
    op.drop_table("section_assets")
    op.drop_index("ix_module_sections_module_publish_status", table_name="module_sections")
    op.drop_index(
        "ix_module_sections_due_at",
        table_name="module_sections",
        postgresql_where=sa.text("due_at IS NOT NULL"),
    )
    op.drop_index("ix_module_sections_module_session_date", table_name="module_sections")
    op.drop_index("ix_module_sections_module_week", table_name="module_sections")
    op.drop_table("module_sections")
    op.drop_index(
        "ix_course_memberships_active_user_module",
        table_name="course_memberships",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("course_memberships")
    op.drop_table("course_modules")
    op.drop_table("app_users")
