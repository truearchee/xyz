"""Assistant modes — homework foundation (Stage 8.6a).

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-20

Stage 8.6 teaches the assistant task-specific *modes* keyed on ``conversation_kind`` (the coordinator
dispatches behavior by kind). 8.6a adds the FIRST mode — Homework help — plus the reusable binding the
mode needs:

- ``ck_assistant_conversations_kind`` gains ``'homework_help'`` (drop + recreate — Postgres can't widen an
  IN-list in place). The four existing kinds (lecture_default/manual/floating_widget/workspace) are
  preserved and all keep mapping to the existing general-chat path. ``exam_prep``/``time_management`` are
  added by 8.6b/8.6c, NOT here (out of 8.6a scope).
- ``attached_module_id`` — a nullable FK to the module a homework conversation is bound to (homework binds a
  module; the existing ``attached_section_id`` optionally narrows it to one lecture/lab). ON DELETE CASCADE
  mirrors ``attached_section_id``.
- Two partial-unique indexes implement resume-or-create (D2): one active homework conversation per
  (student, module [, section]). They are split on the nullable ``attached_section_id`` so the natural key
  is TOTAL — Postgres treats NULLs as distinct in a unique index, so a single index over
  (student, module, section) would NOT prevent two "module, no section" rows; the second index closes that.

My assigned migration block is 0042–0047; this uses 0042 only. ``alembic heads`` reports a single head
0041 before and 0042 after (chain …→0040→0041→0042; 0034–0037 frozen for 8.3). Additive; assistant domain
only. Guards existence-checked → re-runnable. Downgrade deletes the un-round-trippable ``homework_help``
rows before restoring the narrowed CHECK (0040/0041 precedent).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

KIND_CHECK = "ck_assistant_conversations_kind"
FK_MODULE = "fk_assistant_conversations_module"
ONE_HOMEWORK_SECTION_INDEX = "uq_assistant_conversations_one_homework_section"
ONE_HOMEWORK_MODULE_INDEX = "uq_assistant_conversations_one_homework_module"

KIND_WITH_HOMEWORK = (
    "conversation_kind IN "
    "('lecture_default', 'manual', 'floating_widget', 'workspace', 'homework_help')"
)
KIND_LEGACY = (
    "conversation_kind IN "
    "('lecture_default', 'manual', 'floating_widget', 'workspace')"
)


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
    # Homework binds a module (optionally narrowed to a section by the existing attached_section_id).
    if not _column_exists("assistant_conversations", "attached_module_id"):
        op.add_column(
            "assistant_conversations",
            sa.Column("attached_module_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _constraint_exists(FK_MODULE):
        op.create_foreign_key(
            FK_MODULE,
            "assistant_conversations",
            "course_modules",
            ["attached_module_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Widen the kind CHECK to admit homework_help (drop + recreate). Existing values preserved.
    if _constraint_exists(KIND_CHECK):
        op.drop_constraint(KIND_CHECK, "assistant_conversations", type_="check")
    op.create_check_constraint(KIND_CHECK, "assistant_conversations", KIND_WITH_HOMEWORK)

    # Resume-or-create (D2): one active homework conversation per (student, module [, section]). Split on
    # the nullable section so the natural key is total (see module docstring). deleted_at IS NULL so a
    # soft-deleted homework chat frees its slot (invariant A), matching the lecture_default index.
    if not _index_exists(ONE_HOMEWORK_SECTION_INDEX):
        op.create_index(
            ONE_HOMEWORK_SECTION_INDEX,
            "assistant_conversations",
            ["student_id", "attached_module_id", "attached_section_id"],
            unique=True,
            postgresql_where=sa.text(
                "conversation_kind = 'homework_help' "
                "AND attached_section_id IS NOT NULL AND deleted_at IS NULL"
            ),
        )
    if not _index_exists(ONE_HOMEWORK_MODULE_INDEX):
        op.create_index(
            ONE_HOMEWORK_MODULE_INDEX,
            "assistant_conversations",
            ["student_id", "attached_module_id"],
            unique=True,
            postgresql_where=sa.text(
                "conversation_kind = 'homework_help' "
                "AND attached_section_id IS NULL AND deleted_at IS NULL"
            ),
        )


def downgrade() -> None:
    # homework_help rows cannot round-trip into the narrowed CHECK; remove them first (0040/0041 precedent).
    op.execute(
        """
        DELETE FROM assistant_messages
        WHERE conversation_id IN (
          SELECT id FROM assistant_conversations WHERE conversation_kind = 'homework_help'
        )
        """
    )
    op.execute("DELETE FROM assistant_conversations WHERE conversation_kind = 'homework_help'")

    if _index_exists(ONE_HOMEWORK_MODULE_INDEX):
        op.drop_index(ONE_HOMEWORK_MODULE_INDEX, table_name="assistant_conversations")
    if _index_exists(ONE_HOMEWORK_SECTION_INDEX):
        op.drop_index(ONE_HOMEWORK_SECTION_INDEX, table_name="assistant_conversations")

    if _constraint_exists(KIND_CHECK):
        op.drop_constraint(KIND_CHECK, "assistant_conversations", type_="check")
    op.create_check_constraint(KIND_CHECK, "assistant_conversations", KIND_LEGACY)

    if _constraint_exists(FK_MODULE):
        op.drop_constraint(FK_MODULE, "assistant_conversations", type_="foreignkey")
    if _column_exists("assistant_conversations", "attached_module_id"):
        op.drop_column("assistant_conversations", "attached_module_id")
