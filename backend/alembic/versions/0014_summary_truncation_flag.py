"""Summary truncation label on generated_lecture_summaries (Option A, F-4.5-50).

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-13

Stage 4.5 corrective — Option A (labeled-interim). A full real lecture transcript (~46KB / ~11.6K tokens)
exceeds K2-Think-v2's provider-side request-time ceiling → HTTP 408 on BOTH routes. The transcript is now
TRUNCATED to a char budget before the model call; this records whether that happened so the UI can label it
("based on the first portion of the transcript") — truncation is never silent. Full coverage of over-budget
transcripts is map-reduce (F-4.5-51, own spec, out of 4.5). Existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

TABLE = "generated_lecture_summaries"
COLUMNS = ("truncated", "source_char_count", "summarized_char_count")


def _columns() -> set[str]:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": TABLE},
    ).scalars().all()
    return set(rows)


def upgrade() -> None:
    existing = _columns()
    if "truncated" not in existing:
        op.add_column(
            TABLE,
            sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "source_char_count" not in existing:
        op.add_column(TABLE, sa.Column("source_char_count", sa.Integer(), nullable=True))
    if "summarized_char_count" not in existing:
        op.add_column(TABLE, sa.Column("summarized_char_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    existing = _columns()
    for col in COLUMNS:
        if col in existing:
            op.drop_column(TABLE, col)
