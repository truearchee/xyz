"""Stage 5a — quiz/event schema DB constraints (migrations 0014–0019).

Proves the integrity guards the engine relies on: event idempotency, the post-class one-per-section
rule, the one-active-attempt invariant, attempt-number uniqueness, DB-enforced answer idempotency,
mistake-snapshot idempotency, the event-type and status CHECKs, and FK cascade. Each test drives a
real Postgres round-trip via the migrated test DB.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    AnswerOption,
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    MistakeRecord,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    StudentActivityEvent,
    StudentAnswer,
)

pytestmark = pytest.mark.anyio


async def _seed_section(session: AsyncSession) -> tuple[AppUser, CourseModule, ModuleSection]:
    student = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"student-{uuid4()}@example.com",
        full_name="Quiz Student",
        role="student",
        timezone="UTC",
    )
    owner = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"owner-{uuid4()}@example.com",
        full_name="Quiz Owner",
        role="lecturer",
        timezone="UTC",
    )
    session.add_all([student, owner])
    await session.flush()

    module = CourseModule(title="Quiz Module", owner_id=owner.id, timezone="UTC", is_active=True)
    session.add(module)
    await session.flush()

    session.add(
        CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active")
    )
    section = ModuleSection(
        course_module_id=module.id,
        title="Lecture 1",
        type="lecture",
        order_index=0,
        publish_status="published",
        status="active",
    )
    session.add(section)
    await session.flush()
    return student, module, section


async def _seed_definition(
    session: AsyncSession, *, section: ModuleSection, module: CourseModule, quiz_mode: str = "post_class"
) -> QuizDefinition:
    definition = QuizDefinition(
        module_section_id=section.id,
        module_id=module.id,
        quiz_mode=quiz_mode,
        source_scope={"sectionType": section.type, "moduleSectionId": str(section.id)},
    )
    session.add(definition)
    await session.flush()
    return definition


def _attempt(
    *, definition_id: UUID, student_id: UUID, attempt_number: int, status: str
) -> QuizAttempt:
    return QuizAttempt(
        quiz_definition_id=definition_id,
        student_id=student_id,
        attempt_number=attempt_number,
        status=status,
    )


async def test_event_idempotency_unique(db_session: AsyncSession) -> None:
    student, module, _section = await _seed_section(db_session)
    source_id = uuid4()
    db_session.add(
        StudentActivityEvent(
            student_id=student.id,
            module_id=module.id,
            event_type="completed_quiz",
            source_id=source_id,
        )
    )
    await db_session.flush()

    db_session.add(
        StudentActivityEvent(
            student_id=student.id,
            module_id=module.id,
            event_type="completed_quiz",
            source_id=source_id,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "uq_student_activity_events_type_source" in str(exc_info.value)


async def test_event_type_check_rejects_unknown(db_session: AsyncSession) -> None:
    student, module, _section = await _seed_section(db_session)
    db_session.add(
        StudentActivityEvent(
            student_id=student.id,
            module_id=module.id,
            event_type="bogus_event",
            source_id=uuid4(),
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "ck_student_activity_events_event_type" in str(exc_info.value)


async def test_quiz_definition_post_class_partial_unique(db_session: AsyncSession) -> None:
    _student, module, section = await _seed_section(db_session)
    await _seed_definition(db_session, section=section, module=module, quiz_mode="post_class")
    # A different mode for the same section is allowed (partial index is scoped to post_class).
    await _seed_definition(db_session, section=section, module=module, quiz_mode="recap")

    db_session.add(
        QuizDefinition(
            module_section_id=section.id,
            module_id=module.id,
            quiz_mode="post_class",
            source_scope={"sectionType": section.type, "moduleSectionId": str(section.id)},
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "uq_quiz_definitions_post_class_section" in str(exc_info.value)


async def test_quiz_definitions_mode_check_rejects_unknown(db_session: AsyncSession) -> None:
    _student, module, section = await _seed_section(db_session)
    db_session.add(
        QuizDefinition(
            module_section_id=section.id,
            module_id=module.id,
            quiz_mode="weekly_exam",
            source_scope={"sectionType": section.type, "moduleSectionId": str(section.id)},
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "ck_quiz_definitions_quiz_mode" in str(exc_info.value)


async def test_quiz_attempts_one_active_partial_unique(db_session: AsyncSession) -> None:
    student, module, section = await _seed_section(db_session)
    definition = await _seed_definition(db_session, section=section, module=module)
    db_session.add(_attempt(definition_id=definition.id, student_id=student.id, attempt_number=1, status="generating"))
    await db_session.flush()

    db_session.add(_attempt(definition_id=definition.id, student_id=student.id, attempt_number=2, status="generating"))
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "uq_quiz_attempts_one_active" in str(exc_info.value)


async def test_quiz_attempts_one_active_allows_after_completion(db_session: AsyncSession) -> None:
    student, module, section = await _seed_section(db_session)
    definition = await _seed_definition(db_session, section=section, module=module)
    db_session.add(_attempt(definition_id=definition.id, student_id=student.id, attempt_number=1, status="completed"))
    await db_session.flush()

    # A completed attempt is outside the one-active partial index → a new generating attempt is allowed.
    db_session.add(_attempt(definition_id=definition.id, student_id=student.id, attempt_number=2, status="generating"))
    await db_session.flush()
    count = await db_session.scalar(
        select(func.count()).select_from(QuizAttempt).where(QuizAttempt.student_id == student.id)
    )
    assert count == 2


async def test_quiz_attempts_unique_student_def_number(db_session: AsyncSession) -> None:
    student, module, section = await _seed_section(db_session)
    definition = await _seed_definition(db_session, section=section, module=module)
    # Both completed so the one-active index does not mask the attempt-number uniqueness violation.
    db_session.add(_attempt(definition_id=definition.id, student_id=student.id, attempt_number=1, status="completed"))
    await db_session.flush()

    db_session.add(_attempt(definition_id=definition.id, student_id=student.id, attempt_number=1, status="completed"))
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "uq_quiz_attempts_student_def_number" in str(exc_info.value)


async def test_quiz_attempts_status_check_rejects_abandoned(db_session: AsyncSession) -> None:
    student, module, section = await _seed_section(db_session)
    definition = await _seed_definition(db_session, section=section, module=module)
    db_session.add(_attempt(definition_id=definition.id, student_id=student.id, attempt_number=1, status="abandoned"))
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "ck_quiz_attempts_status" in str(exc_info.value)


async def test_quiz_attempts_failure_category_check_rejects_unknown(
    db_session: AsyncSession,
) -> None:
    student, module, section = await _seed_section(db_session)
    definition = await _seed_definition(db_session, section=section, module=module)
    db_session.add(
        QuizAttempt(
            quiz_definition_id=definition.id,
            student_id=student.id,
            attempt_number=1,
            status="failed",
            failure_category="redis_bad_day",
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "ck_quiz_attempts_failure_category" in str(exc_info.value)


async def _seed_attempt_question_option(
    db_session: AsyncSession,
) -> tuple[QuizAttempt, QuizQuestion, AnswerOption]:
    student, module, section = await _seed_section(db_session)
    definition = await _seed_definition(db_session, section=section, module=module)
    attempt = _attempt(definition_id=definition.id, student_id=student.id, attempt_number=1, status="in_progress")
    db_session.add(attempt)
    await db_session.flush()
    question = QuizQuestion(quiz_attempt_id=attempt.id, question_text="What is 2+2?", display_order=0)
    db_session.add(question)
    await db_session.flush()
    option = AnswerOption(quiz_question_id=question.id, text="4", display_order=0, is_correct=True)
    db_session.add(option)
    await db_session.flush()
    return attempt, question, option


async def test_student_answers_unique_attempt_question(db_session: AsyncSession) -> None:
    attempt, question, option = await _seed_attempt_question_option(db_session)
    db_session.add(
        StudentAnswer(
            quiz_attempt_id=attempt.id,
            quiz_question_id=question.id,
            selected_answer_option_id=option.id,
            is_correct=True,
        )
    )
    await db_session.flush()

    db_session.add(
        StudentAnswer(
            quiz_attempt_id=attempt.id,
            quiz_question_id=question.id,
            selected_answer_option_id=option.id,
            is_correct=True,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "uq_student_answers_attempt_question" in str(exc_info.value)


async def test_quiz_questions_question_type_check_rejects_unknown(
    db_session: AsyncSession,
) -> None:
    attempt, _question, _option = await _seed_attempt_question_option(db_session)
    db_session.add(
        QuizQuestion(
            quiz_attempt_id=attempt.id,
            question_text="Explain the topic.",
            display_order=1,
            question_type="essay",
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "ck_quiz_questions_question_type" in str(exc_info.value)


async def test_quiz_questions_source_type_check_rejects_unknown(
    db_session: AsyncSession,
) -> None:
    attempt, _question, _option = await _seed_attempt_question_option(db_session)
    db_session.add(
        QuizQuestion(
            quiz_attempt_id=attempt.id,
            question_text="What source is this?",
            display_order=1,
            source_type="pooled_question",
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "ck_quiz_questions_source_type" in str(exc_info.value)


async def test_mistake_records_unique_attempt_question(db_session: AsyncSession) -> None:
    student, module, section = await _seed_section(db_session)
    definition = await _seed_definition(db_session, section=section, module=module)
    attempt = _attempt(definition_id=definition.id, student_id=student.id, attempt_number=1, status="in_progress")
    db_session.add(attempt)
    await db_session.flush()
    question = QuizQuestion(quiz_attempt_id=attempt.id, question_text="Q", display_order=0)
    db_session.add(question)
    await db_session.flush()

    def _mistake() -> MistakeRecord:
        return MistakeRecord(
            student_id=student.id,
            module_id=module.id,
            module_section_id=section.id,
            source_quiz_definition_id=definition.id,
            source_quiz_attempt_id=attempt.id,
            source_question_id=question.id,
            question_snapshot={"questionText": "Q"},
            answer_options_snapshot={"options": []},
            selected_wrong_answer="wrong",
            correct_answer="right",
        )

    db_session.add(_mistake())
    await db_session.flush()
    db_session.add(_mistake())
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "uq_mistake_records_attempt_question" in str(exc_info.value)


async def test_cascade_delete_attempt_removes_children(db_session: AsyncSession) -> None:
    attempt, question, option = await _seed_attempt_question_option(db_session)
    db_session.add(
        StudentAnswer(
            quiz_attempt_id=attempt.id,
            quiz_question_id=question.id,
            selected_answer_option_id=option.id,
            is_correct=True,
        )
    )
    await db_session.flush()

    await db_session.delete(attempt)
    await db_session.flush()

    assert (
        await db_session.scalar(
            select(func.count()).select_from(QuizQuestion).where(QuizQuestion.id == question.id)
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(AnswerOption).where(AnswerOption.id == option.id)
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(StudentAnswer)
            .where(StudentAnswer.quiz_attempt_id == attempt.id)
        )
        == 0
    )
