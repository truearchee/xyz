"""Add section asset kind for lab attachments.

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-16

Stage 5.5c distinguishes processable PDF assets from download-only lab attachments. Existing
``section_assets`` rows predate this distinction and are backfilled to ``processable``.
"""

from alembic import op
import sqlalchemy as sa


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

TABLE = "section_assets"
COLUMN = "asset_kind"
CHECK = "ck_section_assets_asset_kind"


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def _constraint_exists(table: str, constraint: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE table_schema = 'public' "
                "AND table_name = :table "
                "AND constraint_name = :constraint"
            ),
            {"table": table, "constraint": constraint},
        ).scalar()
    )


def upgrade() -> None:
    if not _column_exists(TABLE, COLUMN):
        op.add_column(
            TABLE,
            sa.Column(
                COLUMN,
                sa.Text(),
                nullable=True,
                server_default=sa.text("'processable'"),
            ),
        )

    op.execute(
        "UPDATE section_assets SET asset_kind = 'processable' "
        "WHERE asset_kind IS NULL"
    )
    op.alter_column(
        TABLE,
        COLUMN,
        existing_type=sa.Text(),
        nullable=False,
        server_default=sa.text("'processable'"),
    )

    if not _constraint_exists(TABLE, CHECK):
        op.create_check_constraint(
            CHECK,
            TABLE,
            "asset_kind IN ('processable', 'attachment')",
        )


def downgrade() -> None:
    if _constraint_exists(TABLE, CHECK):
        op.drop_constraint(CHECK, TABLE, type_="check")
    if _column_exists(TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
