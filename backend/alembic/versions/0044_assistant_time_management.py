"""Assistant modes — time-management (Stage 8.6c).

Revision ID: 0044
Revises: 0043
Create Date: 2026-06-20

Adds the THIRD assistant mode (time_management) on the 8.6b foundation:

- ``ck_assistant_conversations_kind`` gains ``'time_management'``. Time management is a standing,
  conversation-only mode bound to the current student, not to a module, section, scope, calendar, or plan.
- ``uq_assistant_conversations_one_time_management`` implements resume-or-create (D2): one active
  time-management conversation per student. ``deleted_at IS NULL`` frees the slot after soft-delete.

No WorkloadPlan / InternalCalendarEvent / .ics artifact is introduced here; Stage 11 owns saved planning.
"""

from alembic import op
import sqlalchemy as sa


revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

KIND_CHECK = "ck_assistant_conversations_kind"
ONE_TIME_MANAGEMENT_INDEX = "uq_assistant_conversations_one_time_management"

KIND_WITH_TIME_MANAGEMENT = (
    "conversation_kind IN "
    "('lecture_default', 'manual', 'floating_widget', 'workspace', 'homework_help', "
    "'exam_prep', 'time_management')"
)
KIND_BEFORE = (
    "conversation_kind IN "
    "('lecture_default', 'manual', 'floating_widget', 'workspace', 'homework_help', 'exam_prep')"
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
    if _constraint_exists(KIND_CHECK):
        op.drop_constraint(KIND_CHECK, "assistant_conversations", type_="check")
    op.create_check_constraint(KIND_CHECK, "assistant_conversations", KIND_WITH_TIME_MANAGEMENT)

    if not _index_exists(ONE_TIME_MANAGEMENT_INDEX):
        op.create_index(
            ONE_TIME_MANAGEMENT_INDEX,
            "assistant_conversations",
            ["student_id"],
            unique=True,
            postgresql_where=sa.text(
                "conversation_kind = 'time_management' AND deleted_at IS NULL"
            ),
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM assistant_messages
        WHERE conversation_id IN (
          SELECT id FROM assistant_conversations WHERE conversation_kind = 'time_management'
        )
        """
    )
    op.execute("DELETE FROM assistant_conversations WHERE conversation_kind = 'time_management'")

    if _index_exists(ONE_TIME_MANAGEMENT_INDEX):
        op.drop_index(ONE_TIME_MANAGEMENT_INDEX, table_name="assistant_conversations")

    if _constraint_exists(KIND_CHECK):
        op.drop_constraint(KIND_CHECK, "assistant_conversations", type_="check")
    op.create_check_constraint(KIND_CHECK, "assistant_conversations", KIND_BEFORE)
