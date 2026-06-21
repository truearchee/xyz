"""Merge Stage 10 and Stage 8.6 migration heads.

Revision ID: 0082
Revises: 0044, 0081
Create Date: 2026-06-21

No schema changes. This merge revision joins the Stage 8.6 assistant-mode branch
(``0042`` -> ``0043`` -> ``0044``) with the Stage 10 gamification branch
(``0080`` -> ``0081``) after rebasing Stage 8.6 on top of main.
"""

revision = "0082"
down_revision = ("0044", "0081")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
