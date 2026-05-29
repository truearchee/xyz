"""Baseline migration. No tables. Proves Alembic and pgvector run.

Revision ID: 0001
Revises: —
Create Date: 2026-05-29
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
