"""Assistant conversation foundation (Stage 8.1).

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-18

The per-student conversation store, shaped as a LIST of conversations (8.4-ready): each conversation
carries a ``conversation_kind`` and an OPTIONAL ``attached_section_id`` (the lecture/lab it is attached
to). One ``lecture_default`` conversation per (student, section) is enforced by a partial-unique index
scoped to that kind only, so two tabs pressing "Start chat" cannot create duplicates while
``manual``/``floating_widget``/``workspace`` conversations remain unconstrained for 8.4.

``assistant_messages`` holds the turn history with an explicit lifecycle (``pending → completed |
failed`` in 8.1; 8.3 widens to add ``streaming/partial/cancelled``). Assistant rows carry the standard
AI provenance set + ``ai_request_log_id`` (rule 6). ``grounding_status`` is added now (nullable) and
populated from 8.2 — no further migration for 8.2. ``client_idempotency_key`` + a partial-unique index
make sending double-send-safe (decision 8). Widens the enumerated ``ai_request_logs.feature`` CHECK to
gain ``'assistant'`` (the 0020/0023 precedent — each consuming feature adds its value deliberately).

NOTE (parallel-work coordination): rebased onto ``origin/main`` after Stage 7 merged — ``down_revision``
re-pointed ``0025``→``0031`` (Stage 7 landed glossary migrations 0030/0031, so 0031 is the new parent).
My assigned migration block is 0032–0037. ``alembic heads`` reports a single head ``0032``. Additive;
assistant domain only. Guards existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

FEATURE_CHECK = "ck_ai_request_logs_feature"
# Post-Stage-7 union (a CHECK is rewritten wholesale, so 0032 must carry EVERY prior feature, not just
# add its own — Stage 7's 0030 added 'glossary_definition'; dropping it would break the glossary path
# and the test_shared_check_union guard). NEW adds 'assistant'; OLD restores the Stage 7 set on downgrade.
FEATURE_VALUES_NEW = (
    "('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool', "
    "'glossary_definition', 'assistant')"
)
FEATURE_VALUES_OLD = (
    "('summary_brief', 'summary_detailed', 'post_class_quiz', 'quiz_pool', 'glossary_definition')"
)

GROUNDING_VALUES = (
    "('lecture_grounded', 'general_not_from_lecture', 'educational_redirect', "
    "'context_unavailable', 'access_denied')"
)


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
    if not _table_exists("assistant_conversations"):
        op.create_table(
            "assistant_conversations",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("conversation_kind", sa.Text(), nullable=False),
            sa.Column("attached_section_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("title", sa.Text(), nullable=True),
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
            sa.PrimaryKeyConstraint("id", name="pk_assistant_conversations"),
            sa.ForeignKeyConstraint(
                ["student_id"],
                ["app_users.id"],
                name="fk_assistant_conversations_student_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["attached_section_id"],
                ["module_sections.id"],
                name="fk_assistant_conversations_attached_section_id",
                ondelete="CASCADE",
            ),
            sa.CheckConstraint(
                "conversation_kind IN "
                "('lecture_default', 'manual', 'floating_widget', 'workspace')",
                name="ck_assistant_conversations_kind",
            ),
        )
    if not _index_exists("ix_assistant_conversations_student"):
        op.create_index(
            "ix_assistant_conversations_student",
            "assistant_conversations",
            ["student_id"],
        )
    if not _index_exists("uq_assistant_conversations_one_lecture_default"):
        # Race-safe single lecture_default per (student, section). Scoped to the kind so 8.4
        # manual/widget/workspace conversations are NOT constrained (multiple per lecture allowed later).
        op.create_index(
            "uq_assistant_conversations_one_lecture_default",
            "assistant_conversations",
            ["student_id", "attached_section_id"],
            unique=True,
            postgresql_where=sa.text("conversation_kind = 'lecture_default'"),
        )

    if not _table_exists("assistant_messages"):
        op.create_table(
            "assistant_messages",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
            # The user message an assistant message answers (self-ref); NULL on user rows.
            sa.Column("prompt_message_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("grounding_status", sa.Text(), nullable=True),
            # Provenance set (assistant rows; rule 6). Nullable — populated when a turn completes.
            sa.Column("model_id", sa.Text(), nullable=True),
            sa.Column("prompt_version", sa.Text(), nullable=True),
            sa.Column("backend_used", sa.Text(), nullable=True),
            sa.Column("input_content_hash", sa.Text(), nullable=True),
            sa.Column("ai_request_log_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_category", sa.Text(), nullable=True),
            sa.Column("failure_message_sanitized", sa.Text(), nullable=True),
            sa.Column(
                "retryable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("client_idempotency_key", sa.Text(), nullable=True),
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
            sa.PrimaryKeyConstraint("id", name="pk_assistant_messages"),
            sa.ForeignKeyConstraint(
                ["conversation_id"],
                ["assistant_conversations.id"],
                name="fk_assistant_messages_conversation_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["prompt_message_id"],
                ["assistant_messages.id"],
                name="fk_assistant_messages_prompt_message_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["ai_request_log_id"],
                ["ai_request_logs.id"],
                name="fk_assistant_messages_ai_request_log_id",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "role IN ('user', 'assistant')",
                name="ck_assistant_messages_role",
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'completed', 'failed')",
                name="ck_assistant_messages_status",
            ),
            sa.CheckConstraint(
                f"grounding_status IS NULL OR grounding_status IN {GROUNDING_VALUES}",
                name="ck_assistant_messages_grounding_status",
            ),
            sa.CheckConstraint(
                "backend_used IS NULL OR backend_used IN ('cerebras', 'nvidia')",
                name="ck_assistant_messages_backend_used",
            ),
        )
    if not _index_exists("ix_assistant_messages_conversation_created"):
        op.create_index(
            "ix_assistant_messages_conversation_created",
            "assistant_messages",
            ["conversation_id", "created_at"],
        )
    if not _index_exists("uq_assistant_messages_user_idempotency"):
        # Double-send safety (decision 8): one user message per (conversation, client key).
        op.create_index(
            "uq_assistant_messages_user_idempotency",
            "assistant_messages",
            ["conversation_id", "client_idempotency_key"],
            unique=True,
            postgresql_where=sa.text("role = 'user' AND client_idempotency_key IS NOT NULL"),
        )

    # Widen the enumerated feature CHECK to gain the assistant feature (0020/0023 precedent).
    if _constraint_exists(FEATURE_CHECK):
        op.drop_constraint(FEATURE_CHECK, "ai_request_logs", type_="check")
    op.create_check_constraint(
        FEATURE_CHECK,
        "ai_request_logs",
        f"feature IN {FEATURE_VALUES_NEW}",
    )


def downgrade() -> None:
    if _constraint_exists(FEATURE_CHECK):
        op.drop_constraint(FEATURE_CHECK, "ai_request_logs", type_="check")
    op.create_check_constraint(
        FEATURE_CHECK,
        "ai_request_logs",
        f"feature IN {FEATURE_VALUES_OLD}",
    )

    for index_name in (
        "uq_assistant_messages_user_idempotency",
        "ix_assistant_messages_conversation_created",
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name="assistant_messages")
    if _table_exists("assistant_messages"):
        op.drop_table("assistant_messages")

    for index_name in (
        "uq_assistant_conversations_one_lecture_default",
        "ix_assistant_conversations_student",
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name="assistant_conversations")
    if _table_exists("assistant_conversations"):
        op.drop_table("assistant_conversations")
