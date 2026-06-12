"""Student-summary list index on generated_lecture_summaries.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-11

Stage 4.7 — Student-facing summaries. The §8.1 batched module-list query resolves the coarse per-section
``summaries_state`` by looking up summary rows for many sections' active transcripts at once. The 0008
table only indexed ``ingestion_jobs`` (the one-active summary-job index) and the provenance unique
constraint leads with ``transcript_id`` — nothing serves ``(module_section_id, summary_type)``. This adds
that index so the student list read does not seq-scan the table. Existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_gen_summaries_section_type"


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"),
            {"name": name},
        ).scalar()
    )


def upgrade() -> None:
    if not _index_exists(INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            "generated_lecture_summaries",
            ["module_section_id", "summary_type"],
        )


def downgrade() -> None:
    if _index_exists(INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="generated_lecture_summaries")
