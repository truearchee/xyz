"""Assistant modes — exam-prep (Stage 8.6b).

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-20

Adds the SECOND assistant mode (exam_prep) on the 8.6a foundation:

- ``ck_assistant_conversations_kind`` gains ``'exam_prep'`` (drop + recreate). The 8.6a values are
  preserved. (``time_management`` is added by 8.6c, NOT here.)
- ``attached_assessment_scope_id`` — a nullable FK to the named ``AssessmentScope`` an exam-prep
  conversation is bound to (its covered weeks drive the grounded summaries; the conversation's
  ``attached_module_id`` is set to the scope's module). ON DELETE CASCADE.
- ``uq_assistant_conversations_one_exam_prep`` — resume-or-create (D2): one active exam-prep conversation
  per (student, assessment_scope); ``deleted_at IS NULL`` frees the slot on soft-delete (invariant A).

My assigned migration block is 0042–0047; this uses 0043 only. ``alembic heads`` reports a single head
0042 before and 0043 after (chain …→0041→0042→0043; 0034–0037 frozen for 8.3). Additive; assistant domain
only. Guards existence-checked → re-runnable. Downgrade deletes the un-round-trippable ``exam_prep`` rows
before restoring the narrowed CHECK (0042 precedent).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

KIND_CHECK = "ck_assistant_conversations_kind"
FK_SCOPE = "fk_assistant_conversations_assessment_scope"
ONE_EXAM_PREP_INDEX = "uq_assistant_conversations_one_exam_prep"

KIND_WITH_EXAM_PREP = (
    "conversation_kind IN "
    "('lecture_default', 'manual', 'floating_widget', 'workspace', 'homework_help', 'exam_prep')"
)
KIND_BEFORE = (
    "conversation_kind IN "
    "('lecture_default', 'manual', 'floating_widget', 'workspace', 'homework_help')"
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
    if not _column_exists("assistant_conversations", "attached_assessment_scope_id"):
        op.add_column(
            "assistant_conversations",
            sa.Column("attached_assessment_scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _constraint_exists(FK_SCOPE):
        op.create_foreign_key(
            FK_SCOPE,
            "assistant_conversations",
            "assessment_scopes",
            ["attached_assessment_scope_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if _constraint_exists(KIND_CHECK):
        op.drop_constraint(KIND_CHECK, "assistant_conversations", type_="check")
    op.create_check_constraint(KIND_CHECK, "assistant_conversations", KIND_WITH_EXAM_PREP)

    if not _index_exists(ONE_EXAM_PREP_INDEX):
        op.create_index(
            ONE_EXAM_PREP_INDEX,
            "assistant_conversations",
            ["student_id", "attached_assessment_scope_id"],
            unique=True,
            postgresql_where=sa.text(
                "conversation_kind = 'exam_prep' AND deleted_at IS NULL"
            ),
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM assistant_messages
        WHERE conversation_id IN (
          SELECT id FROM assistant_conversations WHERE conversation_kind = 'exam_prep'
        )
        """
    )
    op.execute("DELETE FROM assistant_conversations WHERE conversation_kind = 'exam_prep'")

    if _index_exists(ONE_EXAM_PREP_INDEX):
        op.drop_index(ONE_EXAM_PREP_INDEX, table_name="assistant_conversations")

    if _constraint_exists(KIND_CHECK):
        op.drop_constraint(KIND_CHECK, "assistant_conversations", type_="check")
    op.create_check_constraint(KIND_CHECK, "assistant_conversations", KIND_BEFORE)

    if _constraint_exists(FK_SCOPE):
        op.drop_constraint(FK_SCOPE, "assistant_conversations", type_="foreignkey")
    if _column_exists("assistant_conversations", "attached_assessment_scope_id"):
        op.drop_column("assistant_conversations", "attached_assessment_scope_id")
