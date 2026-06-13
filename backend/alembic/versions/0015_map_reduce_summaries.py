"""Map-reduce summarization schema (Stage 4.5.1a, F-4.5-51).

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-13

Removes the single-call transcript-size ceiling: the detailed summary is now produced by partitioning
the transcript into consecutive map-units, summarizing each in its own call, and reducing the partials
into one coherent summary. This migration adds:
  - ``map_unit_summaries`` — one persisted partial per map-unit, with partition-bound identity (C3) so a
    budget change or transcript replacement never reuses a stale partial on resume.
  - ``generated_lecture_summaries.generation_strategy`` (single_call|map_reduce|truncated_fallback) +
    ``generation_metadata`` — the STATE downstream gating (Stage 5) reads, never the UI label.
  - the ``ai_request_logs.feature`` check constraint extended for the map/reduce phases.

Existence-checked + IF EXISTS throughout → re-runnable.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

GEN_TABLE = "generated_lecture_summaries"
MAP_TABLE = "map_unit_summaries"


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": table},
    ).scalars().all()
    return set(rows)


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT to_regclass(:t)"),
            {"t": f"public.{table}"},
        ).scalar()
    )


def upgrade() -> None:
    # 1 — generation_strategy / generation_metadata on the existing summaries table.
    gen_cols = _columns(GEN_TABLE)
    if "generation_strategy" not in gen_cols:
        op.add_column(
            GEN_TABLE,
            sa.Column(
                "generation_strategy",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'single_call'"),
            ),
        )
    if "generation_metadata" not in gen_cols:
        op.add_column(GEN_TABLE, sa.Column("generation_metadata", postgresql.JSONB(), nullable=True))
    op.execute(
        f"ALTER TABLE {GEN_TABLE} DROP CONSTRAINT IF EXISTS ck_gen_summaries_generation_strategy"
    )
    op.execute(
        f"ALTER TABLE {GEN_TABLE} ADD CONSTRAINT ck_gen_summaries_generation_strategy "
        "CHECK (generation_strategy IN ('single_call', 'map_reduce', 'truncated_fallback'))"
    )

    # 2 — map_unit_summaries (one persisted partial per map-unit; partition-bound identity).
    if not _table_exists(MAP_TABLE):
        op.create_table(
            MAP_TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "transcript_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("transcripts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("unit_index", sa.Integer(), nullable=False),
            sa.Column(
                "start_segment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("transcript_segments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "end_segment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("transcript_segments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("partition_config_hash", sa.Text(), nullable=False),
            sa.Column("source_transcript_checksum", sa.Text(), nullable=False),
            sa.Column("map_prompt_version", sa.Text(), nullable=False),
            sa.Column(
                "ai_request_log_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("ai_request_logs.id"),
                nullable=True,
            ),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("partial_content", postgresql.JSONB(), nullable=True),
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
            sa.UniqueConstraint(
                "transcript_id",
                "unit_index",
                "partition_config_hash",
                "source_transcript_checksum",
                name="uq_map_unit_summaries_identity",
            ),
            sa.CheckConstraint(
                "status IN ('queued', 'running', 'succeeded', 'failed')",
                name="ck_map_unit_summaries_status",
            ),
            sa.CheckConstraint("unit_index >= 0", name="ck_map_unit_summaries_unit_index"),
        )
        op.create_index(
            "ix_map_unit_summaries_transcript_partition",
            MAP_TABLE,
            ["transcript_id", "partition_config_hash"],
        )

    # 3 — extend the AIRequestLog feature check for the map/reduce phases.
    op.execute("ALTER TABLE ai_request_logs DROP CONSTRAINT IF EXISTS ck_ai_request_logs_feature")
    op.execute(
        "ALTER TABLE ai_request_logs ADD CONSTRAINT ck_ai_request_logs_feature "
        "CHECK (feature IN ('summary_brief', 'summary_detailed', "
        "'detailed_summary_map', 'detailed_summary_reduce'))"
    )


def downgrade() -> None:
    # Revert the AIRequestLog feature check to the pre-4.5.1 two-value form.
    op.execute("ALTER TABLE ai_request_logs DROP CONSTRAINT IF EXISTS ck_ai_request_logs_feature")
    op.execute(
        "ALTER TABLE ai_request_logs ADD CONSTRAINT ck_ai_request_logs_feature "
        "CHECK (feature IN ('summary_brief', 'summary_detailed'))"
    )

    if _table_exists(MAP_TABLE):
        op.drop_index("ix_map_unit_summaries_transcript_partition", table_name=MAP_TABLE)
        op.drop_table(MAP_TABLE)

    op.execute(
        f"ALTER TABLE {GEN_TABLE} DROP CONSTRAINT IF EXISTS ck_gen_summaries_generation_strategy"
    )
    gen_cols = _columns(GEN_TABLE)
    if "generation_metadata" in gen_cols:
        op.drop_column(GEN_TABLE, "generation_metadata")
    if "generation_strategy" in gen_cols:
        op.drop_column(GEN_TABLE, "generation_strategy")
