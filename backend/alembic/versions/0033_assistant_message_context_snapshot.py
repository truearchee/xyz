"""Assistant message context snapshot (Stage 8.2).

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-18

Adds ``assistant_messages.context_snapshot`` (JSONB, nullable) — the server-side generation-time audit
snapshot of what an answer was actually grounded on (contextType, module/section ids+titles, active
transcript id + source checksum, retrieved chunk refs {chunkId, distance, tokenCount}, retrieval
threshold + embedding model/version + retrieval config version, groundingStatus, promptVersion, modelId,
generatedAt). Written at message completion so the student-facing "answer basis" reflects what was used
and cannot drift if the transcript is later replaced. NEVER serialized to the browser (the read model
composes only a safe human basis from it). Additive; assistant domain only. Guard existence-checked →
re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
                """
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    if not _column_exists("assistant_messages", "context_snapshot"):
        op.add_column(
            "assistant_messages",
            sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("assistant_messages", "context_snapshot"):
        op.drop_column("assistant_messages", "context_snapshot")
