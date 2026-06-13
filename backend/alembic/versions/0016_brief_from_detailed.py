"""Brief-from-detailed DAG check-constraint extensions (Stage 4.5.1b, ADR-052).

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-13

The brief is now derived from the completed detailed summary (a small BRIEF-route call), not
re-summarized from the transcript. Two additive constraint widenings:
  - ai_request_logs.feature gains 'brief_from_detailed' (the derived-brief gateway call).
  - generated_lecture_summaries.generation_strategy gains 'derived_from_detailed' (the derived brief's
    provenance label — informational; quiz-eligibility is a property of the DETAILED it derived from).

DROP IF EXISTS + ADD throughout → re-runnable.
"""

from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai_request_logs DROP CONSTRAINT IF EXISTS ck_ai_request_logs_feature")
    op.execute(
        "ALTER TABLE ai_request_logs ADD CONSTRAINT ck_ai_request_logs_feature "
        "CHECK (feature IN ('summary_brief', 'summary_detailed', "
        "'detailed_summary_map', 'detailed_summary_reduce', 'brief_from_detailed'))"
    )
    op.execute(
        "ALTER TABLE generated_lecture_summaries "
        "DROP CONSTRAINT IF EXISTS ck_gen_summaries_generation_strategy"
    )
    op.execute(
        "ALTER TABLE generated_lecture_summaries ADD CONSTRAINT ck_gen_summaries_generation_strategy "
        "CHECK (generation_strategy IN ('single_call', 'map_reduce', 'truncated_fallback', "
        "'derived_from_detailed'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ai_request_logs DROP CONSTRAINT IF EXISTS ck_ai_request_logs_feature")
    op.execute(
        "ALTER TABLE ai_request_logs ADD CONSTRAINT ck_ai_request_logs_feature "
        "CHECK (feature IN ('summary_brief', 'summary_detailed', "
        "'detailed_summary_map', 'detailed_summary_reduce'))"
    )
    op.execute(
        "ALTER TABLE generated_lecture_summaries "
        "DROP CONSTRAINT IF EXISTS ck_gen_summaries_generation_strategy"
    )
    op.execute(
        "ALTER TABLE generated_lecture_summaries ADD CONSTRAINT ck_gen_summaries_generation_strategy "
        "CHECK (generation_strategy IN ('single_call', 'map_reduce', 'truncated_fallback'))"
    )
