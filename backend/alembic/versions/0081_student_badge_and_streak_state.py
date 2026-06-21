"""Stage 10 — gamification tables: student_badges + student_streak_state.

Revision ID: 0081
Revises: 0080
Create Date: 2026-06-20

Second of two Stage 10 migrations (block 0080+). Additive, new tables only:
- ``student_badges`` — earned badges; sticky + idempotent via UNIQUE(student_id, badge_key,
  scope_type, scope_id). ``scope_id`` is NEVER NULL (all-zeros sentinel for global scope) so the unique
  key is total (Postgres treats NULLs as distinct).
- ``student_streak_state`` — per-student persisted monotonic ``longest_streak`` + ``last_seen`` marker
  (the current streak is recomputed on read).

Both tables are created in one transaction (DDL is transactional on Postgres → all-or-nothing), so no
existence guards are needed (matches 0039). REBASE NOTE: chained 0081 → 0080; if 0080's down_revision is
repointed at merge to keep a single head, 0081 follows it automatically.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_badges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("badge_key", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("qualified_value", sa.Integer(), nullable=True),
        sa.Column("threshold", sa.Integer(), nullable=True),
        sa.Column("triggering_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_student_badges"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_badges_student_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "student_id",
            "badge_key",
            "scope_type",
            "scope_id",
            name="uq_student_badges_student_key_scope",
        ),
        sa.CheckConstraint(
            "scope_type IN ('global', 'module', 'topic', 'section')",
            name="ck_student_badges_scope_type",
        ),
    )
    op.create_index(
        "ix_student_badges_student",
        "student_badges",
        ["student_id"],
    )

    op.create_table(
        "student_streak_state",
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_seen_gamification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("student_id", name="pk_student_streak_state"),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["app_users.id"],
            name="fk_student_streak_state_student_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("longest_streak >= 0", name="ck_student_streak_state_longest"),
    )


def downgrade() -> None:
    op.drop_table("student_streak_state")
    op.drop_index("ix_student_badges_student", table_name="student_badges")
    op.drop_table("student_badges")
