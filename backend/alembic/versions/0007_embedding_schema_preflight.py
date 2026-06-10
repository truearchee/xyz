"""Add transcript embedding provenance constraints.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


PROVENANCE_CONSTRAINT = "ck_transcript_chunks_embedding_provenance"
ACTIVE_EMBED_INDEX = "ingestion_jobs_one_active_embed_per_transcript"


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
    }


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = :name
                """
            ),
            {"name": name},
        ).scalar()
    )


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = :name
                """
            ),
            {"name": name},
        ).scalar()
    )


def _assert_embedding_column_is_vector_384() -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT atttypid::regtype::text AS type_name, atttypmod
            FROM pg_attribute
            WHERE attrelid = 'transcript_chunks'::regclass
              AND attname = 'embedding'
              AND NOT attisdropped
            """
        )
    ).one()
    if row.type_name != "vector" or row.atttypmod != 384:
        raise RuntimeError(
            "transcript_chunks.embedding must be vector(384) before 4.4 provenance migration"
        )


def _assert_no_existing_embeddings() -> None:
    bind = op.get_bind()
    count = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM transcript_chunks
            WHERE embedding IS NOT NULL
            """
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Refusing 4.4 provenance migration with pre-existing non-null embeddings"
        )


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _assert_embedding_column_is_vector_384()
    _assert_no_existing_embeddings()

    _add_column_if_missing(
        "transcript_chunks",
        sa.Column("embedding_model_revision", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        "transcript_chunks",
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "transcript_chunks",
        sa.Column("embedding_normalization", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        "transcript_chunks",
        sa.Column("embedding_input_hash", sa.Text(), nullable=True),
    )

    if not _constraint_exists(PROVENANCE_CONSTRAINT):
        op.create_check_constraint(
            PROVENANCE_CONSTRAINT,
            "transcript_chunks",
            """
            embedding IS NULL
            OR (
                embedding_model IS NOT NULL
                AND embedding_model_revision IS NOT NULL
                AND embedding_dimension = 384
                AND embedding_normalization = 'l2'
                AND embedding_version IS NOT NULL
                AND embedding_input_hash IS NOT NULL
            )
            """,
        )

    if not _index_exists(ACTIVE_EMBED_INDEX):
        op.create_index(
            ACTIVE_EMBED_INDEX,
            "ingestion_jobs",
            ["transcript_id", "job_type"],
            unique=True,
            postgresql_where=sa.text(
                "job_type = 'embed' AND status IN ('queued', 'running')"
            ),
        )


def downgrade() -> None:
    if _index_exists(ACTIVE_EMBED_INDEX):
        op.drop_index(ACTIVE_EMBED_INDEX, table_name="ingestion_jobs")
    if _constraint_exists(PROVENANCE_CONSTRAINT):
        op.drop_constraint(
            PROVENANCE_CONSTRAINT,
            "transcript_chunks",
            type_="check",
        )

    columns = _column_names("transcript_chunks")
    for column_name in (
        "embedding_input_hash",
        "embedding_normalization",
        "embedding_dimension",
        "embedding_model_revision",
    ):
        if column_name in columns:
            op.drop_column("transcript_chunks", column_name)
