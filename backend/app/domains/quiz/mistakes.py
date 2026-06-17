"""MistakeRecord pooled-model upsert (Stage 6a identity; wired into the answer path in 6c).

Under question reuse a student can be served the SAME pool question across several attempts (each attempt
snapshots its own QuizQuestion row, so ``source_question_id`` differs every time). Keying mistakes on the
durable ``(student_id, source_quiz_definition_id, source_pool_question_id)`` triple — an ON-CONFLICT
upsert against the partial-unique ``uq_mistake_records_pool_identity`` — collapses those re-misses into ONE
record, which is what makes "stays in the bank / flips at 2" coherent. The counters
(``retake_correct_count`` / ``show_in_retake_prefix``) are PRESERVED on conflict: a re-miss never resets
progress and a cleared question does not auto-return to the prefix (Product decision #2 default). Snapshots
are refreshed to the latest occurrence but stay verbatim, so a mistake survives the pool later changing.

The NULL-pool path (pre-retrofit post_class / mistake_review misses) keeps the Stage 5 insert keyed on
``uq_mistake_records_attempt_question`` — handled by the existing ``service.answer`` path, not here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import MistakeRecord


async def upsert_pool_mistake(
    session: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    module_section_id: UUID,
    source_quiz_definition_id: UUID,
    source_quiz_attempt_id: UUID,
    source_question_id: UUID,
    source_pool_question_id: UUID,
    question_snapshot: dict,
    answer_options_snapshot: dict,
    selected_wrong_answer: str,
    correct_answer: str,
    explanation: str | None,
) -> None:
    """Create-or-update the student's mistake for this pooled question in this QuizDefinition. Runs inside
    the caller's transaction (the same one that scored the wrong answer). Idempotent under re-miss."""
    now = datetime.now(UTC)
    stmt = pg_insert(MistakeRecord).values(
        student_id=student_id,
        module_id=module_id,
        module_section_id=module_section_id,
        source_quiz_definition_id=source_quiz_definition_id,
        source_quiz_attempt_id=source_quiz_attempt_id,
        source_question_id=source_question_id,
        source_pool_question_id=source_pool_question_id,
        question_snapshot=question_snapshot,
        answer_options_snapshot=answer_options_snapshot,
        selected_wrong_answer=selected_wrong_answer,
        correct_answer=correct_answer,
        explanation=explanation,
        updated_at=now,
    )
    # Refresh the snapshot/pointers to the latest occurrence; DO NOT touch retake_correct_count or
    # show_in_retake_prefix (re-miss never resets progress; a cleared question stays cleared — D2 default).
    stmt = stmt.on_conflict_do_update(
        index_elements=["student_id", "source_quiz_definition_id", "source_pool_question_id"],
        index_where=text("source_pool_question_id IS NOT NULL"),
        set_={
            "source_quiz_attempt_id": stmt.excluded.source_quiz_attempt_id,
            "source_question_id": stmt.excluded.source_question_id,
            "module_section_id": stmt.excluded.module_section_id,
            "question_snapshot": stmt.excluded.question_snapshot,
            "answer_options_snapshot": stmt.excluded.answer_options_snapshot,
            "selected_wrong_answer": stmt.excluded.selected_wrong_answer,
            "correct_answer": stmt.excluded.correct_answer,
            "explanation": stmt.excluded.explanation,
            "updated_at": now,
        },
    )
    await session.execute(stmt)
