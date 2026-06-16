"""StudentActivityEvent — the platform activity event spine.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-16

Stage 5 (§8) — the activity event spine. One immutable row per student action instance.
``UNIQUE(event_type, source_id)`` is the idempotency guard (source_id = the quiz attempt id; not a FK).
The CHECK encodes only the values Stage 5 emits (completed_quiz, perfect_quiz_score) and is widened per
consuming slice (same pattern 0011 used to widen ck_ingestion_jobs_failure_category). Guards are
existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


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
    if not _table_exists("student_activity_events"):
        op.create_table(
            "student_activity_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_student_activity_events"),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_student_activity_events_student_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["module_id"],
                ["course_modules.id"],
                name="fk_student_activity_events_module_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "event_type IN ('completed_quiz', 'perfect_quiz_score')",
                name="ck_student_activity_events_event_type",
            ),
            sa.UniqueConstraint(
                "event_type",
                "source_id",
                name="uq_student_activity_events_type_source",
            ),
        )
    if not _index_exists("ix_student_activity_events_student_type"):
        op.create_index(
            "ix_student_activity_events_student_type",
            "student_activity_events",
            ["student_id", "event_type"],
        )


def downgrade() -> None:
    if _index_exists("ix_student_activity_events_student_type"):
        op.drop_index(
            "ix_student_activity_events_student_type",
            table_name="student_activity_events",
        )
    if _table_exists("student_activity_events"):
        op.drop_table("student_activity_events")
