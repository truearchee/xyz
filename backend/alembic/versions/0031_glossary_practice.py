"""Stage 7b/7c glossary practice: review state + practice sessions/answers.

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-17

Additive, no shared-CHECK edits (the glossary_practice_completed event type was added in 0030). Three
tables back Flashcards (review state, hardcoded Leitner intervals) and Multiple-Choice (deck-sampled,
no AI). Leaner than the Slice-6 four-table quiz set — no AI-generated shareable question artifact, so a
card/question maps 1:1 to an answer slot. Guards existence-checked (re-runnable).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0031"
down_revision = "0030"
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
    # --- glossary_review_state ---
    if not _table_exists("glossary_review_state"):
        op.create_table(
            "glossary_review_state",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("glossary_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("box", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "due_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("total_reviews", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("correct_streak", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
            sa.PrimaryKeyConstraint("id", name="pk_glossary_review_state"),
            sa.ForeignKeyConstraint(
                ["glossary_entry_id"],
                ["glossary_entries.id"],
                name="fk_glossary_review_state_entry_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_glossary_review_state_student_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["subject_id"],
                ["course_modules.id"],
                name="fk_glossary_review_state_subject_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("glossary_entry_id", name="uq_glossary_review_state_entry"),
        )
    if not _index_exists("ix_glossary_review_state_due"):
        op.create_index(
            "ix_glossary_review_state_due",
            "glossary_review_state",
            ["student_id", "subject_id", "due_at"],
        )

    # --- glossary_practice_sessions ---
    if not _table_exists("glossary_practice_sessions"):
        op.create_table(
            "glossary_practice_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("scope", sa.Text(), nullable=False),
            sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("mode", sa.Text(), nullable=False),
            sa.Column(
                "status", sa.Text(), nullable=False, server_default=sa.text("'in_progress'")
            ),
            sa.Column("total_count", sa.Integer(), nullable=True),
            sa.Column("correct_count", sa.Integer(), nullable=True),
            sa.Column("not_known_count", sa.Integer(), nullable=True),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.PrimaryKeyConstraint("id", name="pk_glossary_practice_sessions"),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_glossary_practice_sessions_student_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["subject_id"],
                ["course_modules.id"],
                name="fk_glossary_practice_sessions_subject_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "scope IN ('course', 'all')", name="ck_glossary_practice_sessions_scope"
            ),
            sa.CheckConstraint(
                "mode IN ('flashcard', 'multiple_choice')",
                name="ck_glossary_practice_sessions_mode",
            ),
            sa.CheckConstraint(
                "status IN ('in_progress', 'completed')",
                name="ck_glossary_practice_sessions_status",
            ),
        )
    if not _index_exists("uq_glossary_practice_sessions_one_active"):
        op.create_index(
            "uq_glossary_practice_sessions_one_active",
            "glossary_practice_sessions",
            ["student_id", "mode"],
            unique=True,
            postgresql_where=sa.text("status = 'in_progress'"),
        )

    # --- glossary_practice_answers ---
    if not _table_exists("glossary_practice_answers"):
        op.create_table(
            "glossary_practice_answers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("practice_session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("glossary_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column("selected_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("correct_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "distractor_entry_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("is_correct", sa.Boolean(), nullable=True),
            sa.Column("outcome", sa.Text(), nullable=True),
            sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_glossary_practice_answers"),
            sa.ForeignKeyConstraint(
                ["practice_session_id"],
                ["glossary_practice_sessions.id"],
                name="fk_glossary_practice_answers_session_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["glossary_entry_id"],
                ["glossary_entries.id"],
                name="fk_glossary_practice_answers_entry_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "practice_session_id",
                "display_order",
                name="uq_glossary_practice_answers_session_order",
            ),
            sa.CheckConstraint(
                "outcome IS NULL OR outcome IN ('known', 'not_known')",
                name="ck_glossary_practice_answers_outcome",
            ),
        )
    if not _index_exists("ix_glossary_practice_answers_session"):
        op.create_index(
            "ix_glossary_practice_answers_session",
            "glossary_practice_answers",
            ["practice_session_id"],
        )


def downgrade() -> None:
    if _table_exists("glossary_practice_answers"):
        op.drop_table("glossary_practice_answers")
    if _table_exists("glossary_practice_sessions"):
        op.drop_table("glossary_practice_sessions")
    if _table_exists("glossary_review_state"):
        op.drop_table("glossary_review_state")
