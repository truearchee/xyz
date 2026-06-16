"""Module schedule config (Stage 5.5a) on course_modules.

Revision ID: 0020
Revises: 0013
Create Date: 2026-06-16

Stage 5.5 — Module Schedule & Section Metadata. Schedule-driven section generation needs the
creation-time schedule recorded on the module as provenance (D10): the weekday this course's weeks
start on, the weekday→sectionType pattern, and the (non-generating) quiz weekday. ``starts_on`` /
``ends_on`` already hold courseStartDate/courseEndDate (reused). These three columns are NULLABLE:
NULL means "no schedule configured" (legacy / ORM-direct rows), and the 422 / validation lives in the
service layer, not the DB — so test helpers that build CourseModule directly keep working.

down_revision is pinned to 0013 (this branch's head) during development. At merge, rebase ONLY this
revision's down_revision to the then-current head so ``alembic heads`` stays singular. Existence-checked
→ re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0020"
down_revision = "0013"
branch_labels = None
depends_on = None

TABLE = "course_modules"
COLUMNS = ("week_start_day", "session_pattern", "quiz_day")


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def upgrade() -> None:
    if not _column_exists(TABLE, "week_start_day"):
        op.add_column(TABLE, sa.Column("week_start_day", sa.Text(), nullable=True))
    if not _column_exists(TABLE, "session_pattern"):
        op.add_column(TABLE, sa.Column("session_pattern", postgresql.JSONB(), nullable=True))
    if not _column_exists(TABLE, "quiz_day"):
        op.add_column(TABLE, sa.Column("quiz_day", sa.Text(), nullable=True))


def downgrade() -> None:
    for column in COLUMNS:
        if _column_exists(TABLE, column):
            op.drop_column(TABLE, column)
