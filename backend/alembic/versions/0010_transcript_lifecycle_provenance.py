"""Transcript lifecycle state, supersession lineage, and per-row job provenance.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-11

Stage 4.6a — Foundation. Additive/cutover over the 0009 head:
- transcripts: replace boolean ``is_active`` with ``lifecycle_state`` (active|pending|superseded),
  add supersession lineage (replacement_of/superseded_by/supersession_reason; superseded_at kept),
  re-point the one-active partial-unique index to ``lifecycle_state='active'`` and add a one-pending
  partial-unique index. Clean pre-MVP cut — ``is_active`` is removed (ADR-46-A).
- transcript_segments / transcript_chunks / generated_lecture_summaries: add nullable
  ``created_by_ingestion_job_id`` provenance pointers; transcript_chunks additionally gains
  ``embedding_created_by_ingestion_job_id`` so embed cannot clobber chunk-creation provenance.
Deferred to 4.6b: parse/chunk "current job" pointer indexes. The chunk pipeline legitimately keeps
two chunk jobs (old + new processor version, distinct idempotency keys) queued at once and serializes
them at runtime via the transcript lock, so a one-active-chunk partial-unique index would break that
tested replacement path. The fencing "current job" pointer for parse/chunk is designed in 4.6b
alongside the retry that consumes it; embed/summary already have their one-active indexes from 0007/0008.
All guards are existence-checked so a partially-applied run is re-runnable (matches 0008/0009).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


ACTIVE_INDEX = "uq_active_transcript_per_section"
PENDING_INDEX = "uq_pending_transcript_per_section"


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
    }


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": name},
        ).scalar()
    )


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"
            ),
            {"name": name},
        ).scalar()
    )


def _add_provenance_column(table: str, column: str, fk_name: str) -> None:
    if column not in _column_names(table):
        op.add_column(
            table,
            sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True),
        )
    if not _constraint_exists(fk_name):
        op.create_foreign_key(
            fk_name,
            table,
            "ingestion_jobs",
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def upgrade() -> None:
    transcript_columns = _column_names("transcripts")

    # --- A. Transcript lifecycle cutover ---------------------------------------------------------
    if "lifecycle_state" not in transcript_columns:
        op.add_column(
            "transcripts",
            sa.Column(
                "lifecycle_state",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'active'"),
            ),
        )
        # Backfill from the legacy boolean + supersession timestamp before constraints land.
        op.execute(
            sa.text(
                """
                UPDATE transcripts SET lifecycle_state = CASE
                    WHEN superseded_at IS NOT NULL THEN 'superseded'
                    WHEN is_active = true THEN 'active'
                    ELSE 'superseded'
                END
                """
            )
        )

    if "replacement_of_transcript_id" not in transcript_columns:
        op.add_column(
            "transcripts",
            sa.Column(
                "replacement_of_transcript_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    if not _constraint_exists("fk_transcripts_replacement_of_transcript_id"):
        op.create_foreign_key(
            "fk_transcripts_replacement_of_transcript_id",
            "transcripts",
            "transcripts",
            ["replacement_of_transcript_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if "superseded_by_transcript_id" not in transcript_columns:
        op.add_column(
            "transcripts",
            sa.Column(
                "superseded_by_transcript_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    if not _constraint_exists("fk_transcripts_superseded_by_transcript_id"):
        op.create_foreign_key(
            "fk_transcripts_superseded_by_transcript_id",
            "transcripts",
            "transcripts",
            ["superseded_by_transcript_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if "supersession_reason" not in transcript_columns:
        op.add_column(
            "transcripts",
            sa.Column("supersession_reason", sa.Text(), nullable=True),
        )

    if not _constraint_exists("ck_transcripts_lifecycle_state"):
        op.create_check_constraint(
            "ck_transcripts_lifecycle_state",
            "transcripts",
            "lifecycle_state IN ('active', 'pending', 'superseded')",
        )
    if not _constraint_exists("ck_transcripts_supersession_reason"):
        op.create_check_constraint(
            "ck_transcripts_supersession_reason",
            "transcripts",
            "supersession_reason IS NULL OR "
            "supersession_reason IN ('replaced_active', 'discarded_pending')",
        )
    if not _constraint_exists("ck_transcripts_superseded_has_ts"):
        op.create_check_constraint(
            "ck_transcripts_superseded_has_ts",
            "transcripts",
            "lifecycle_state <> 'superseded' OR superseded_at IS NOT NULL",
        )
    if not _constraint_exists("ck_transcripts_active_no_ts"):
        op.create_check_constraint(
            "ck_transcripts_active_no_ts",
            "transcripts",
            "lifecycle_state <> 'active' OR superseded_at IS NULL",
        )
    if _constraint_exists("ck_transcripts_active_not_superseded"):
        op.drop_constraint(
            "ck_transcripts_active_not_superseded", "transcripts", type_="check"
        )

    # Re-point the one-active index to lifecycle_state (keep the NAME so the IntegrityError
    # string-match in service.py keeps working), and add the one-pending index.
    if _index_exists(ACTIVE_INDEX):
        op.drop_index(ACTIVE_INDEX, table_name="transcripts")
    op.create_index(
        ACTIVE_INDEX,
        "transcripts",
        ["module_section_id"],
        unique=True,
        postgresql_where=sa.text("lifecycle_state = 'active'"),
    )
    if not _index_exists(PENDING_INDEX):
        op.create_index(
            PENDING_INDEX,
            "transcripts",
            ["module_section_id"],
            unique=True,
            postgresql_where=sa.text("lifecycle_state = 'pending'"),
        )

    if "is_active" in transcript_columns:
        op.drop_column("transcripts", "is_active")

    # --- B. Per-row job provenance ---------------------------------------------------------------
    _add_provenance_column(
        "transcript_segments",
        "created_by_ingestion_job_id",
        "fk_transcript_segments_created_by_ingestion_job_id",
    )
    _add_provenance_column(
        "transcript_chunks",
        "created_by_ingestion_job_id",
        "fk_transcript_chunks_created_by_ingestion_job_id",
    )
    _add_provenance_column(
        "transcript_chunks",
        "embedding_created_by_ingestion_job_id",
        "fk_transcript_chunks_embedding_created_by_ingestion_job_id",
    )
    _add_provenance_column(
        "generated_lecture_summaries",
        "created_by_ingestion_job_id",
        "fk_gen_summaries_created_by_ingestion_job_id",
    )


def _drop_provenance_column(table: str, column: str, fk_name: str) -> None:
    if _constraint_exists(fk_name):
        op.drop_constraint(fk_name, table, type_="foreignkey")
    if column in _column_names(table):
        op.drop_column(table, column)


def downgrade() -> None:
    _drop_provenance_column(
        "generated_lecture_summaries",
        "created_by_ingestion_job_id",
        "fk_gen_summaries_created_by_ingestion_job_id",
    )
    _drop_provenance_column(
        "transcript_chunks",
        "embedding_created_by_ingestion_job_id",
        "fk_transcript_chunks_embedding_created_by_ingestion_job_id",
    )
    _drop_provenance_column(
        "transcript_chunks",
        "created_by_ingestion_job_id",
        "fk_transcript_chunks_created_by_ingestion_job_id",
    )
    _drop_provenance_column(
        "transcript_segments",
        "created_by_ingestion_job_id",
        "fk_transcript_segments_created_by_ingestion_job_id",
    )

    # Restore the legacy is_active column and re-point the active index back to it.
    if "is_active" not in _column_names("transcripts"):
        op.add_column(
            "transcripts",
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
        op.execute(
            sa.text(
                "UPDATE transcripts SET is_active = (lifecycle_state = 'active')"
            )
        )

    if _index_exists(PENDING_INDEX):
        op.drop_index(PENDING_INDEX, table_name="transcripts")
    if _index_exists(ACTIVE_INDEX):
        op.drop_index(ACTIVE_INDEX, table_name="transcripts")
    op.create_index(
        ACTIVE_INDEX,
        "transcripts",
        ["module_section_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    if not _constraint_exists("ck_transcripts_active_not_superseded"):
        op.create_check_constraint(
            "ck_transcripts_active_not_superseded",
            "transcripts",
            "NOT (is_active = true AND superseded_at IS NOT NULL)",
        )
    for name in (
        "ck_transcripts_active_no_ts",
        "ck_transcripts_superseded_has_ts",
        "ck_transcripts_supersession_reason",
        "ck_transcripts_lifecycle_state",
    ):
        if _constraint_exists(name):
            op.drop_constraint(name, "transcripts", type_="check")

    for fk_name in (
        "fk_transcripts_superseded_by_transcript_id",
        "fk_transcripts_replacement_of_transcript_id",
    ):
        if _constraint_exists(fk_name):
            op.drop_constraint(fk_name, "transcripts", type_="foreignkey")

    transcript_columns = _column_names("transcripts")
    for column in (
        "supersession_reason",
        "superseded_by_transcript_id",
        "replacement_of_transcript_id",
        "lifecycle_state",
    ):
        if column in transcript_columns:
            op.drop_column("transcripts", column)
