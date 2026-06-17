"""Scoped student quiz read models (Stage 5c). Read-only (rule 8): the WHERE clause enforces the
already-defined visibility policy and never mutates. Zero rows for not-owner / unpublished /
unassigned / inactive / non-lecture-lab (the caller maps that to the pinned 404 — never
fetch-then-branch). This is the S7 seam: an unpublished-mid-attempt section yields None on every read.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    AnswerOption,
    CourseMembership,
    CourseModule,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    StudentAnswer,
)

# Quiz lives on lecture/lab only (mirrors the Slice 2 transcript-section restriction).
QUIZ_SECTION_TYPES = ("lecture", "lab")


@dataclass(frozen=True)
class VisibleAttempt:
    attempt_id: UUID
    student_id: UUID
    quiz_definition_id: UUID
    quiz_mode: str
    module_id: UUID
    module_section_id: UUID
    section_type: str
    status: str
    attempt_number: int
    total_questions: int | None
    correct_count: int | None
    incorrect_count: int | None
    score_percentage: Decimal | None
    completed_at: datetime | None


async def get_visible_attempt(
    db: AsyncSession, *, student_id: UUID, attempt_id: UUID
) -> VisibleAttempt | None:
    """One row iff the attempt is owned by ``student_id`` AND its section is still published+active in a
    module the student actively belongs to AND the section is lecture/lab; else None (→ pinned 404).
    Re-checked on EVERY student endpoint — the same query is the S7 unpublish-mid-attempt gate."""
    row = (
        await db.execute(
            select(
                QuizAttempt.id,
                QuizAttempt.student_id,
                QuizAttempt.quiz_definition_id,
                QuizDefinition.quiz_mode,
                QuizDefinition.module_id,
                QuizDefinition.module_section_id,
                ModuleSection.type,
                QuizAttempt.status,
                QuizAttempt.attempt_number,
                QuizAttempt.total_questions,
                QuizAttempt.correct_count,
                QuizAttempt.incorrect_count,
                QuizAttempt.score_percentage,
                QuizAttempt.completed_at,
            )
            .join(QuizDefinition, QuizDefinition.id == QuizAttempt.quiz_definition_id)
            .join(ModuleSection, ModuleSection.id == QuizDefinition.module_section_id)
            .join(CourseModule, CourseModule.id == ModuleSection.course_module_id)
            .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
            .where(
                QuizAttempt.id == attempt_id,
                QuizAttempt.student_id == student_id,
                ModuleSection.publish_status == "published",
                ModuleSection.status == "active",
                ModuleSection.type.in_(QUIZ_SECTION_TYPES),
                CourseModule.is_active.is_(True),
                CourseMembership.user_id == student_id,
                CourseMembership.role == "student",
                CourseMembership.status == "active",
            )
        )
    ).one_or_none()
    if row is None:
        return None
    return VisibleAttempt(
        attempt_id=row[0],
        student_id=row[1],
        quiz_definition_id=row[2],
        quiz_mode=row[3],
        module_id=row[4],
        module_section_id=row[5],
        section_type=row[6],
        status=row[7],
        attempt_number=row[8],
        total_questions=row[9],
        correct_count=row[10],
        incorrect_count=row[11],
        score_percentage=row[12],
        completed_at=row[13],
    )


@dataclass(frozen=True)
class QuestionRead:
    question: QuizQuestion
    options: list[AnswerOption]
    answer: StudentAnswer | None


async def get_attempt_questions_for_student(
    db: AsyncSession, *, attempt_id: UUID
) -> list[QuestionRead]:
    """Questions (display order) + options (display order) + the student's answer per question."""
    questions = (
        await db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_attempt_id == attempt_id)
            .order_by(QuizQuestion.display_order.asc(), QuizQuestion.id.asc())
        )
    ).scalars().all()
    if not questions:
        return []
    q_ids = [q.id for q in questions]
    options = (
        await db.execute(
            select(AnswerOption)
            .where(AnswerOption.quiz_question_id.in_(q_ids))
            .order_by(AnswerOption.display_order.asc(), AnswerOption.id.asc())
        )
    ).scalars().all()
    answers = (
        await db.execute(
            select(StudentAnswer).where(StudentAnswer.quiz_attempt_id == attempt_id)
        )
    ).scalars().all()
    options_by_q: dict[UUID, list[AnswerOption]] = {}
    for opt in options:
        options_by_q.setdefault(opt.quiz_question_id, []).append(opt)
    answer_by_q = {a.quiz_question_id: a for a in answers}
    return [
        QuestionRead(
            question=q,
            options=options_by_q.get(q.id, []),
            answer=answer_by_q.get(q.id),
        )
        for q in questions
    ]


@dataclass(frozen=True)
class AttemptsAggregate:
    attempt_count: int
    best_score_percentage: Decimal | None


async def get_attempts_aggregate(
    db: AsyncSession, *, student_id: UUID, section_id: UUID
) -> AttemptsAggregate:
    """Aggregate for the section's post_class definition: total attempts + best completed score.
    A single aggregate query (NOT a paginated list — ADR-041 amendment, no pagination theatre)."""
    row = (
        await db.execute(
            select(
                func.count(QuizAttempt.id),
                func.max(QuizAttempt.score_percentage),
            )
            .join(QuizDefinition, QuizDefinition.id == QuizAttempt.quiz_definition_id)
            .where(
                QuizDefinition.module_section_id == section_id,
                QuizDefinition.quiz_mode == "post_class",
                QuizAttempt.student_id == student_id,
            )
        )
    ).one()
    return AttemptsAggregate(attempt_count=int(row[0] or 0), best_score_percentage=row[1])
