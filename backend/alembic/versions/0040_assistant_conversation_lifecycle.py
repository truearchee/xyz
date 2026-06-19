"""Assistant conversation lifecycle (Stage 8.4 — workspace + floating widget).

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-19

Adds the conversation-management columns the 8.4 Workspace + floating widget need, on top of the 8.1
shape (ADR-049): a ``deleted_at`` soft-delete tombstone, a ``title_source`` (auto|manual) so a manual
rename is never overwritten by the derived lecture title, and a ``last_activity_at`` used to order the
conversation list newest-first. The single load-bearing change is the **partial-unique index rebuild**:
``uq_assistant_conversations_one_lecture_default`` gains ``AND deleted_at IS NULL`` so that a
soft-deleted lecture chat frees the (student, section) slot and reopening the lecture creates a FRESH
conversation (invariant A) instead of resurrecting the tombstone.

8.1 already enforces one active ``lecture_default`` per (student, section), so there is NO duplicate
data to collapse (prereq #4 resolved against the live schema). ``title`` and the user-message
``client_idempotency_key`` partial-unique index already exist (0032) — not re-added here.

My assigned migration block is 0040–0045; this uses 0040 only (0041–0045 reserved). ``alembic heads``
reports a single head 0039 (chain 0032→0033→0038→0039; 0034–0037 frozen for 8.3). Additive; assistant
domain only. Guards existence-checked → re-runnable. Downgrade restores the original index predicate.
"""

from alembic import op
import sqlalchemy as sa


revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

ONE_LECTURE_DEFAULT_INDEX = "uq_assistant_conversations_one_lecture_default"
TITLE_SOURCE_CHECK = "ck_assistant_conversations_title_source"


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
    # Soft-delete tombstone (invariants C/E). Removed from the list; reopen → 404; never hard-deleted.
    if not _column_exists("assistant_conversations", "deleted_at"):
        op.add_column(
            "assistant_conversations",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )

    # title_source: a manual rename is never overwritten by the derived lecture title. NOT NULL with a
    # server_default so existing 8.1 rows become 'auto' (their title is derived-on-read from the section).
    if not _column_exists("assistant_conversations", "title_source"):
        op.add_column(
            "assistant_conversations",
            sa.Column(
                "title_source",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'auto'"),
            ),
        )
    if not _constraint_exists(TITLE_SOURCE_CHECK):
        op.create_check_constraint(
            TITLE_SOURCE_CHECK,
            "assistant_conversations",
            "title_source IN ('auto', 'manual')",
        )

    # last_activity_at orders the conversation list newest-first; bumped on user-message creation and
    # successful assistant completion only (never rename/delete). Nullable + backfilled from updated_at;
    # read paths COALESCE(last_activity_at, updated_at) so a NULL can never mis-sort. The backfill only
    # touches NULL rows → idempotent / re-runnable.
    if not _column_exists("assistant_conversations", "last_activity_at"):
        op.add_column(
            "assistant_conversations",
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute(
        "UPDATE assistant_conversations SET last_activity_at = updated_at "
        "WHERE last_activity_at IS NULL"
    )

    # The load-bearing change: rebuild the one-active partial-unique index to also exclude tombstones,
    # so delete-then-reopen creates a fresh row (invariant A). Scoped to lecture_default only (8.4 uses
    # only that kind); manual/floating_widget/workspace stay unconstrained per ADR-049.
    if _index_exists(ONE_LECTURE_DEFAULT_INDEX):
        op.drop_index(ONE_LECTURE_DEFAULT_INDEX, table_name="assistant_conversations")
    op.create_index(
        ONE_LECTURE_DEFAULT_INDEX,
        "assistant_conversations",
        ["student_id", "attached_section_id"],
        unique=True,
        postgresql_where=sa.text("conversation_kind = 'lecture_default' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    # 0039 has no deleted_at column and its unique index counts every lecture_default row. A real 8.4
    # lifecycle can contain a soft-deleted tombstone plus a fresh active row for the same student/section;
    # those rows cannot round-trip into 0039. Remove tombstones first so the old uniqueness predicate can
    # be restored without either failing the downgrade or resurrecting deleted conversations.
    if _column_exists("assistant_conversations", "deleted_at"):
        op.execute(
            """
            DELETE FROM assistant_messages
            WHERE conversation_id IN (
              SELECT id FROM assistant_conversations WHERE deleted_at IS NOT NULL
            )
            """
        )
        op.execute("DELETE FROM assistant_conversations WHERE deleted_at IS NOT NULL")

    # Restore the original predicate (kind only, no deleted_at clause).
    if _index_exists(ONE_LECTURE_DEFAULT_INDEX):
        op.drop_index(ONE_LECTURE_DEFAULT_INDEX, table_name="assistant_conversations")
    op.create_index(
        ONE_LECTURE_DEFAULT_INDEX,
        "assistant_conversations",
        ["student_id", "attached_section_id"],
        unique=True,
        postgresql_where=sa.text("conversation_kind = 'lecture_default'"),
    )

    if _constraint_exists(TITLE_SOURCE_CHECK):
        op.drop_constraint(TITLE_SOURCE_CHECK, "assistant_conversations", type_="check")
    if _column_exists("assistant_conversations", "title_source"):
        op.drop_column("assistant_conversations", "title_source")
    if _column_exists("assistant_conversations", "last_activity_at"):
        op.drop_column("assistant_conversations", "last_activity_at")
    if _column_exists("assistant_conversations", "deleted_at"):
        op.drop_column("assistant_conversations", "deleted_at")
