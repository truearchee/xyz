"""Stage 10 — widen ck_student_activity_events_event_type with 'studied_section'.

Revision ID: 0080
Revises: 0041
Create Date: 2026-06-20

Stage 10 (gamification) uses the migration block 0080+ (Stage 11 is actively climbing from 0056 and
owns 0057-0079; Stage 8.6 took 0042). This is the first of two Stage 10 migrations (0081 adds the
gamification tables). It is ADDITIVE only: the content-domain ``studied_section`` engagement event (the
"opened a summary" signal that keeps a streak alive) becomes a legal ``event_type``. The allowed set is
WIDENED (union), never replaced, so every existing event stays valid.

A CHECK is rewritten wholesale by Postgres, so this drops and recreates
``ck_student_activity_events_event_type`` with the FULL union of every consuming stage's values.

⚠ PARALLEL-STAGE GUARD: if any other branch ALSO widens this CHECK, whichever merges SECOND must
recreate it with the UNION of BOTH branches' values, or the earlier addition is silently dropped. The
model source-of-truth tuple (STUDENT_ACTIVITY_EVENT_TYPES) + the CI union test
(tests/test_shared_check_union.py) are the guard. Per the Stage 10/11 coordination note Stage 11 is
consumer-only and adds NO event types, so in practice this is the only widening — but the guard stays.

REBASE NOTE: ``down_revision`` is pinned to this tree's head (0041) for local dev. At merge, repoint it
to main's then-current head so the chain is single-headed, keeping this in the 0080+ block. The branch
that merges SECOND re-runs the Alembic round-trip (upgrade → base → upgrade) and confirms one head.

Guards are existence-checked so a partially-applied run is re-runnable (matches 0030).
"""

from alembic import op
import sqlalchemy as sa


revision = "0080"
down_revision = "0041"
branch_labels = None
depends_on = None


EVENT_TYPE_CONSTRAINT = "ck_student_activity_events_event_type"

# Head-at-this-revision values (Stage 5 quiz events + Stage 7 glossary events) and the new union with
# Stage 10's 'studied_section'. A CHECK is rewritten wholesale, so dropping any prior value here would
# silently remove it from the live DB (the test_shared_check_union CI test guards exactly this).
_EVENT_TYPE_PRIOR = (
    "event_type IN ('completed_quiz', 'perfect_quiz_score', "
    "'glossary_term_saved', 'glossary_practice_completed')"
)
_EVENT_TYPE_NEW = (
    "event_type IN ('completed_quiz', 'perfect_quiz_score', "
    "'glossary_term_saved', 'glossary_practice_completed', 'studied_section')"
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
    if _constraint_exists(EVENT_TYPE_CONSTRAINT):
        op.drop_constraint(EVENT_TYPE_CONSTRAINT, "student_activity_events", type_="check")
    op.create_check_constraint(
        EVENT_TYPE_CONSTRAINT, "student_activity_events", _EVENT_TYPE_NEW
    )


def downgrade() -> None:
    if _constraint_exists(EVENT_TYPE_CONSTRAINT):
        op.drop_constraint(EVENT_TYPE_CONSTRAINT, "student_activity_events", type_="check")
    op.create_check_constraint(
        EVENT_TYPE_CONSTRAINT, "student_activity_events", _EVENT_TYPE_PRIOR
    )
