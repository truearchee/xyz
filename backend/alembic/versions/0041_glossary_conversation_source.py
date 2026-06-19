"""Glossary conversation source (Stage 8.5 — save-to-glossary from the assistant).

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-19

Lets a glossary entry record that it originated from an assistant chat reply. Additive to the Stage 7a
``glossary_source_references`` table:

- ``source_conversation_id`` / ``source_message_id`` — nullable FKs to the assistant tables (mirrors the
  existing ``source_quiz_attempt_id`` cross-domain FK precedent from 7a; ``SET NULL`` so deleting a
  conversation/message never destroys the entry's provenance trail).
- the ``source_type`` CHECK gains ``'conversation'`` (drop + recreate — Postgres can't widen an IN-list
  in place).
- a partial-unique index ``uq_glossary_source_references_conversation_message`` on
  ``(glossary_entry_id, source_message_id)`` WHERE ``source_type = 'conversation'`` so the duplicate-save
  "attach this chat as another source" path is IDEMPOTENT (same entry + same message never attached
  twice, 8.5 D3). The predicate excludes every summary/manual/quiz row (they have NULL source_message_id),
  so it cannot affect existing data or the existing non-idempotent attach behavior.

No definition-prompt or cache-key change (ADR-055): chat saves get a subject-level definition (the same
input a manual add sends), so the cache key is untouched and no new AI behavior ships.

My assigned migration block is 0041–0046; this uses 0041 only. ``alembic heads`` reports a single head
0040 before and 0041 after (chain …→0039→0040→0041). Additive; guards existence-checked → re-runnable.
Downgrade deletes the un-round-trippable ``'conversation'`` rows before restoring the narrowed CHECK
(0040 precedent).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

SOURCE_TYPE_CHECK = "ck_glossary_source_references_source_type"
CONVERSATION_MESSAGE_INDEX = "uq_glossary_source_references_conversation_message"
FK_CONVERSATION = "fk_glossary_source_references_conversation"
FK_MESSAGE = "fk_glossary_source_references_message"


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


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"),
            {"name": name},
        ).scalar()
    )


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).scalar()
    )


def upgrade() -> None:
    # Cross-domain provenance FKs (SET NULL — a deleted conversation/message keeps the entry's trail).
    if not _column_exists("glossary_source_references", "source_conversation_id"):
        op.add_column(
            "glossary_source_references",
            sa.Column("source_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _constraint_exists(FK_CONVERSATION):
        op.create_foreign_key(
            FK_CONVERSATION,
            "glossary_source_references",
            "assistant_conversations",
            ["source_conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _column_exists("glossary_source_references", "source_message_id"):
        op.add_column(
            "glossary_source_references",
            sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _constraint_exists(FK_MESSAGE):
        op.create_foreign_key(
            FK_MESSAGE,
            "glossary_source_references",
            "assistant_messages",
            ["source_message_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Widen the source_type CHECK to include 'conversation' (drop + recreate).
    if _constraint_exists(SOURCE_TYPE_CHECK):
        op.drop_constraint(SOURCE_TYPE_CHECK, "glossary_source_references", type_="check")
    op.create_check_constraint(
        SOURCE_TYPE_CHECK,
        "glossary_source_references",
        "source_type IN ('summary', 'manual', 'quiz', 'conversation')",
    )

    # Idempotent conversation source-attach: same entry + same message never twice. Partial predicate
    # leaves summary/manual/quiz rows (NULL source_message_id) entirely unaffected.
    if not _index_exists(CONVERSATION_MESSAGE_INDEX):
        op.create_index(
            CONVERSATION_MESSAGE_INDEX,
            "glossary_source_references",
            ["glossary_entry_id", "source_message_id"],
            unique=True,
            postgresql_where=sa.text(
                "source_type = 'conversation' AND source_message_id IS NOT NULL"
            ),
        )


def downgrade() -> None:
    # 'conversation' rows cannot round-trip into the narrowed CHECK; remove them first (0040 precedent).
    op.execute("DELETE FROM glossary_source_references WHERE source_type = 'conversation'")

    if _index_exists(CONVERSATION_MESSAGE_INDEX):
        op.drop_index(CONVERSATION_MESSAGE_INDEX, table_name="glossary_source_references")

    if _constraint_exists(SOURCE_TYPE_CHECK):
        op.drop_constraint(SOURCE_TYPE_CHECK, "glossary_source_references", type_="check")
    op.create_check_constraint(
        SOURCE_TYPE_CHECK,
        "glossary_source_references",
        "source_type IN ('summary', 'manual', 'quiz')",
    )

    if _constraint_exists(FK_MESSAGE):
        op.drop_constraint(FK_MESSAGE, "glossary_source_references", type_="foreignkey")
    if _column_exists("glossary_source_references", "source_message_id"):
        op.drop_column("glossary_source_references", "source_message_id")
    if _constraint_exists(FK_CONVERSATION):
        op.drop_constraint(FK_CONVERSATION, "glossary_source_references", type_="foreignkey")
    if _column_exists("glossary_source_references", "source_conversation_id"):
        op.drop_column("glossary_source_references", "source_conversation_id")
