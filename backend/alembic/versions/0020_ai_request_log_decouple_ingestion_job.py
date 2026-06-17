"""Decouple AIRequestLog from IngestionJob; widen the feature enum.

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-16

Stage 5b — AI calls are NOT always transcript-ingestion jobs. ``ai_request_logs.ingestion_job_id`` was
NOT NULL because every 4.5 caller was a summary job; quiz generation (Stage 5) and the assistant
(Stage 8) make gateway calls with NO IngestionJob. This makes ``ingestion_job_id`` NULLABLE (a general
decoupling, not a quiz-specific patch) and widens the ``feature`` CHECK to an EXPLICIT enumerated set
that gains the quiz feature. The CHECK stays enumerated on purpose (same discipline as the Stage-5
``event_type`` CHECK): each consuming feature adds its value deliberately, never "anything". The
gateway keeps requiring ``ingestion_job_id`` for the summary features at the APPLICATION layer — the
column is widened, the summary contract is not. Guards are existence-checked → re-runnable.
"""

from alembic import op
import sqlalchemy as sa


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

FEATURE_CHECK = "ck_ai_request_logs_feature"
# Enumerated set — extend deliberately per consuming feature; never widen to "anything".
FEATURE_VALUES_NEW = "('summary_brief', 'summary_detailed', 'post_class_quiz')"
FEATURE_VALUES_OLD = "('summary_brief', 'summary_detailed')"


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).scalar()
    )


def _column_is_nullable(table: str, column: str) -> bool | None:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).scalar()
    if result is None:
        return None
    return result == "YES"


def upgrade() -> None:
    if _column_is_nullable("ai_request_logs", "ingestion_job_id") is False:
        op.alter_column(
            "ai_request_logs",
            "ingestion_job_id",
            existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        )
    op.execute(
        "COMMENT ON COLUMN ai_request_logs.ingestion_job_id IS "
        "'Nullable: not every AI gateway call is a transcript-ingestion job "
        "(quiz generation / assistant calls have none). Summary features still require it "
        "at the application layer (gateway), not via this column constraint.'"
    )
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
    op.execute("COMMENT ON COLUMN ai_request_logs.ingestion_job_id IS NULL")
    if _column_is_nullable("ai_request_logs", "ingestion_job_id") is True:
        op.alter_column(
            "ai_request_logs",
            "ingestion_job_id",
            existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        )
