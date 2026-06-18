"""Stage 9 progress and topic mastery snapshots.

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_progress_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("standing_points", sa.Numeric(5, 2), nullable=False),
        sa.Column("source_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_progress_snapshots"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_progress_snapshots_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_student_progress_snapshots_module_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "student_id",
            "module_id",
            "week_number",
            name="uq_student_progress_snapshots_student_module_week",
        ),
        sa.CheckConstraint("week_number > 0", name="ck_student_progress_snapshots_week"),
        sa.CheckConstraint(
            "standing_points >= 0 AND standing_points <= 100",
            name="ck_student_progress_snapshots_standing",
        ),
    )
    op.create_index(
        "ix_student_progress_snapshots_student_module",
        "student_progress_snapshots",
        ["student_id", "module_id", "week_number"],
    )

    op.create_table(
        "student_topic_mastery_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mastery_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("status_label", sa.Text(), nullable=False),
        sa.Column("source_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_topic_mastery_snapshots"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_topic_mastery_snapshots_student_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["course_modules.id"],
            name="fk_student_topic_mastery_snapshots_module_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["module_section_id"],
            ["module_sections.id"],
            name="fk_student_topic_mastery_snapshots_module_section_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "student_id",
            "module_id",
            "module_section_id",
            name="uq_student_topic_mastery_student_module_section",
        ),
        sa.CheckConstraint(
            "mastery_percentage >= 0 AND mastery_percentage <= 100",
            name="ck_student_topic_mastery_percentage",
        ),
        sa.CheckConstraint(
            "status_label IN ('strong', 'on_track', 'needs_attention')",
            name="ck_student_topic_mastery_status_label",
        ),
    )
    op.create_index(
        "ix_student_topic_mastery_student_module",
        "student_topic_mastery_snapshots",
        ["student_id", "module_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_student_topic_mastery_student_module",
        table_name="student_topic_mastery_snapshots",
    )
    op.drop_table("student_topic_mastery_snapshots")
    op.drop_index(
        "ix_student_progress_snapshots_student_module",
        table_name="student_progress_snapshots",
    )
    op.drop_table("student_progress_snapshots")
