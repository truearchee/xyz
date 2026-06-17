"""Stage 6c — retake reinforcement + mistakes-bank backend gate.

Proves the remaining backend-only Stage 6 behavior after 6b pulled forward event metadata and pooled
mistake creation: source-quiz retakes start with the current student's active mistake prefix, correct
prefix answers flip the prefix flag after two cumulative source-quiz retakes, and the per-module
mistakes-bank is own-student-only with pinned 404s for hidden modules.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.domains.quiz.assembly_service as assembly_service
import app.domains.quiz.pool_service as pool_service
from app.domains.quiz import service as quiz_service
from app.domains.quiz.assembly_service import (
    start_pooled_attempt,
    try_assemble_attempt_async,
)
from app.domains.quiz.pool_service import ensure_section_pool, generate_section_pool_async
from app.domains.quiz.scope_service import RECAP_MODE, canonical_scope_key, get_or_create_pooled_definition
from app.platform.db.models import (
    AnswerOption,
    CourseMembership,
    MistakeRecord,
    PoolQuestion,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    SectionQuestionPool,
)
from tests.test_quiz_recap_examprep import (
    _ctx,
    _factory,
    _gateway,
    _ready_section,
    _seed_base,
    _user,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def captured(monkeypatch) -> SimpleNamespace:
    pools: list = []
    assemblies: list = []
    monkeypatch.setattr(
        pool_service, "enqueue_generate_section_pool", lambda pid: pools.append(pid) or f"quiz-pool:{pid}"
    )
    monkeypatch.setattr(
        pool_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"q:{aid}"
    )
    monkeypatch.setattr(
        assembly_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"q:{aid}"
    )
    return SimpleNamespace(pools=pools, assemblies=assemblies)


async def _pool_question_for_section(
    db_session: AsyncSession, *, section_id: UUID
) -> PoolQuestion:
    pool = (
        await db_session.scalars(
            select(SectionQuestionPool).where(SectionQuestionPool.module_section_id == section_id)
        )
    ).one()
    return (
        await db_session.scalars(
            select(PoolQuestion)
            .where(PoolQuestion.section_question_pool_id == pool.id)
            .order_by(PoolQuestion.id.asc())
            .limit(1)
        )
    ).one()


async def _create_source_mistake(
    db_session: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    section_id: UUID,
    definition_id: UUID,
    pool_question_id: UUID | None = None,
    text: str = "missed concept",
) -> SimpleNamespace:
    attempt = QuizAttempt(
        quiz_definition_id=definition_id,
        student_id=student_id,
        attempt_number=1,
        status="completed",
        total_questions=1,
        correct_count=0,
        incorrect_count=1,
    )
    db_session.add(attempt)
    await db_session.flush()
    question = QuizQuestion(
        quiz_attempt_id=attempt.id,
        question_text=f"{text}?",
        display_order=0,
        question_type="multiple_choice",
        explanation=f"explain {text}",
        source_type="new_generated",
        source_pool_question_id=pool_question_id,
        source_module_id=module_id,
        source_section_id=section_id,
    )
    db_session.add(question)
    await db_session.flush()
    options = [
        AnswerOption(quiz_question_id=question.id, text="wrong", display_order=0, is_correct=False),
        AnswerOption(quiz_question_id=question.id, text="right", display_order=1, is_correct=True),
    ]
    db_session.add_all(options)
    await db_session.flush()
    mistake = MistakeRecord(
        student_id=student_id,
        module_id=module_id,
        module_section_id=section_id,
        source_quiz_definition_id=definition_id,
        source_quiz_attempt_id=attempt.id,
        source_question_id=question.id,
        source_pool_question_id=pool_question_id,
        question_snapshot={
            "questionText": f"{text}?",
            "displayOrder": 0,
            "explanation": f"explain {text}",
        },
        answer_options_snapshot={
            "options": [
                {"id": str(options[0].id), "text": "wrong", "displayOrder": 0, "isCorrect": False},
                {"id": str(options[1].id), "text": "right", "displayOrder": 1, "isCorrect": True},
            ]
        },
        selected_wrong_answer="wrong",
        correct_answer="right",
        explanation=f"explain {text}",
    )
    db_session.add(mistake)
    await db_session.flush()
    return SimpleNamespace(attempt=attempt, question=question, mistake=mistake, options=options)


async def _create_prefix_attempt_question(
    db_session: AsyncSession,
    *,
    student_id: UUID,
    definition_id: UUID,
    mistake_id: UUID,
    attempt_number: int,
) -> SimpleNamespace:
    attempt = QuizAttempt(
        quiz_definition_id=definition_id,
        student_id=student_id,
        attempt_number=attempt_number,
        status="in_progress",
        total_questions=1,
        new_question_count=0,
        mistake_review_question_count=1,
    )
    db_session.add(attempt)
    await db_session.flush()
    question = QuizQuestion(
        quiz_attempt_id=attempt.id,
        question_text="prefix?",
        display_order=0,
        question_type="multiple_choice",
        explanation="prefix explanation",
        source_type="mistake_review",
        source_mistake_record_id=mistake_id,
    )
    db_session.add(question)
    await db_session.flush()
    wrong = AnswerOption(quiz_question_id=question.id, text="wrong", display_order=0, is_correct=False)
    right = AnswerOption(quiz_question_id=question.id, text="right", display_order=1, is_correct=True)
    db_session.add_all([wrong, right])
    await db_session.flush()
    return SimpleNamespace(attempt=attempt, question=question, wrong=wrong, right=right)


async def test_retake_prefix_snapshots_active_mistakes_first_and_excludes_pool_question(
    db_session: AsyncSession, captured
) -> None:
    base = await _seed_base(db_session)
    section = await _ready_section(db_session, base, title="W1", order=0, week=1)
    await db_session.commit()
    factory = _factory(db_session)
    ensured = await ensure_section_pool(factory, section_id=section.id)
    await generate_section_pool_async(ensured.pool_id, gateway=_gateway(factory), session_factory=factory)
    pool_question = await _pool_question_for_section(db_session, section_id=section.id)
    definition_id = await get_or_create_pooled_definition(
        factory,
        module_id=base.module.id,
        quiz_mode=RECAP_MODE,
        scope_key=canonical_scope_key([section.id]),
        section_ids=[section.id],
    )
    source = await _create_source_mistake(
        db_session,
        student_id=base.student.id,
        module_id=base.module.id,
        section_id=section.id,
        definition_id=definition_id,
        pool_question_id=pool_question.id,
        text="gradient descent",
    )
    await db_session.commit()

    start = await start_pooled_attempt(
        factory, student_id=base.student.id, quiz_definition_id=definition_id
    )
    await try_assemble_attempt_async(start.attempt_id, session_factory=factory, seed_override=123)

    rows = (
        await db_session.scalars(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_attempt_id == start.attempt_id)
            .order_by(QuizQuestion.display_order.asc())
        )
    ).all()
    attempt = await db_session.get(QuizAttempt, start.attempt_id)
    assert rows[0].source_type == "mistake_review"
    assert rows[0].source_mistake_record_id == source.mistake.id
    assert rows[0].question_text == "gradient descent?"
    assert attempt.mistake_review_question_count == 1
    assert attempt.new_question_count == 5
    assert pool_question.id not in {
        row.source_pool_question_id for row in rows[1:] if row.source_pool_question_id is not None
    }


async def test_correct_prefix_answer_flips_after_two_source_retakes_and_duplicate_is_idempotent(
    db_session: AsyncSession,
) -> None:
    base = await _seed_base(db_session)
    section = await _ready_section(db_session, base, title="W1", order=0, week=1)
    definition = QuizDefinition(
        module_section_id=None,
        module_id=base.module.id,
        quiz_mode="recap",
        scope_key=hashlib.sha256(str(section.id).encode()).hexdigest(),
        source_scope={"quizMode": "recap", "sectionIds": [str(section.id)]},
    )
    db_session.add(definition)
    await db_session.flush()
    source = await _create_source_mistake(
        db_session,
        student_id=base.student.id,
        module_id=base.module.id,
        section_id=section.id,
        definition_id=definition.id,
        text="chain rule",
    )
    first = await _create_prefix_attempt_question(
        db_session,
        student_id=base.student.id,
        definition_id=definition.id,
        mistake_id=source.mistake.id,
        attempt_number=2,
    )
    await db_session.commit()

    payload = {"questionId": str(first.question.id), "selectedAnswerOptionId": str(first.right.id)}
    feedback = await quiz_service.answer(
        db_session,
        current_user=_ctx(base.student),
        attempt_id=first.attempt.id,
        payload=quiz_service.AnswerSubmission.model_validate(payload),
    )
    assert feedback.is_correct is True
    duplicate = await quiz_service.answer(
        db_session,
        current_user=_ctx(base.student),
        attempt_id=first.attempt.id,
        payload=quiz_service.AnswerSubmission.model_validate(payload),
    )
    assert duplicate.already_answered is True
    row = await db_session.get(MistakeRecord, source.mistake.id)
    assert row.retake_correct_count == 1
    assert row.show_in_retake_prefix is True

    first.attempt.status = "completed"
    second = await _create_prefix_attempt_question(
        db_session,
        student_id=base.student.id,
        definition_id=definition.id,
        mistake_id=source.mistake.id,
        attempt_number=3,
    )
    await db_session.commit()
    await quiz_service.answer(
        db_session,
        current_user=_ctx(base.student),
        attempt_id=second.attempt.id,
        payload=quiz_service.AnswerSubmission(
            question_id=second.question.id,
            selected_answer_option_id=second.right.id,
        ),
    )
    row = await db_session.get(MistakeRecord, source.mistake.id)
    assert row.retake_correct_count == 2
    assert row.show_in_retake_prefix is False


async def test_bank_practice_does_not_advance_prefix_or_duplicate_mistake(
    db_session: AsyncSession,
) -> None:
    base = await _seed_base(db_session)
    section = await _ready_section(db_session, base, title="W1", order=0, week=1)
    definition = QuizDefinition(
        module_section_id=section.id,
        module_id=base.module.id,
        quiz_mode="post_class",
        source_scope={"sectionId": str(section.id)},
    )
    db_session.add(definition)
    await db_session.flush()
    source = await _create_source_mistake(
        db_session,
        student_id=base.student.id,
        module_id=base.module.id,
        section_id=section.id,
        definition_id=definition.id,
        text="bank only",
    )
    await db_session.commit()

    bank_attempt = await quiz_service.start_mistakes_bank(
        db_session, current_user=_ctx(base.student), module_id=base.module.id
    )
    question = bank_attempt.questions[0]
    options = (
        await db_session.scalars(
            select(AnswerOption).where(AnswerOption.quiz_question_id == question.id)
        )
    ).all()
    right = next(o for o in options if o.is_correct)
    await quiz_service.answer(
        db_session,
        current_user=_ctx(base.student),
        attempt_id=bank_attempt.id,
        payload=quiz_service.AnswerSubmission(
            question_id=question.id,
            selected_answer_option_id=right.id,
        ),
    )
    row = await db_session.get(MistakeRecord, source.mistake.id)
    assert row.retake_correct_count == 0
    assert row.show_in_retake_prefix is True

    bank_attempt_2 = await quiz_service.start_mistakes_bank(
        db_session, current_user=_ctx(base.student), module_id=base.module.id
    )
    # Same active attempt resumes; answer duplicate/wrong path must not create another MistakeRecord.
    assert bank_attempt_2.id == bank_attempt.id
    count = (
        await db_session.scalar(
            select(func.count()).select_from(MistakeRecord).where(MistakeRecord.student_id == base.student.id)
        )
    )
    assert count == 1


async def test_mistakes_bank_list_start_is_own_student_only_with_404_rules(
    db_session: AsyncSession,
) -> None:
    base = await _seed_base(db_session)
    section = await _ready_section(db_session, base, title="W1", order=0, week=1)
    student_b = _user("student")
    outsider = _user("student")
    db_session.add_all([student_b, outsider])
    await db_session.flush()
    db_session.add(
        CourseMembership(user_id=student_b.id, module_id=base.module.id, role="student", status="active")
    )
    definition = QuizDefinition(
        module_section_id=section.id,
        module_id=base.module.id,
        quiz_mode="post_class",
        source_scope={"sectionId": str(section.id)},
    )
    db_session.add(definition)
    await db_session.flush()
    a_mistake = await _create_source_mistake(
        db_session,
        student_id=base.student.id,
        module_id=base.module.id,
        section_id=section.id,
        definition_id=definition.id,
        text="student a",
    )
    b_mistake = await _create_source_mistake(
        db_session,
        student_id=student_b.id,
        module_id=base.module.id,
        section_id=section.id,
        definition_id=definition.id,
        text="student b",
    )
    await db_session.commit()

    items_a, total_a = await quiz_service.list_mistakes_bank(
        db_session, current_user=_ctx(base.student), module_id=base.module.id, limit=50, offset=0
    )
    assert total_a == 1
    assert [item.id for item in items_a] == [a_mistake.mistake.id]

    items_b, total_b = await quiz_service.list_mistakes_bank(
        db_session, current_user=_ctx(student_b), module_id=base.module.id, limit=50, offset=0
    )
    assert total_b == 1
    assert [item.id for item in items_b] == [b_mistake.mistake.id]

    bank_attempt = await quiz_service.start_mistakes_bank(
        db_session, current_user=_ctx(base.student), module_id=base.module.id
    )
    assert bank_attempt.status == "in_progress"
    assert [q.question_text for q in bank_attempt.questions] == ["student a?"]

    with pytest.raises(HTTPException) as exc:
        await quiz_service.list_mistakes_bank(
            db_session, current_user=_ctx(outsider), module_id=base.module.id, limit=50, offset=0
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await quiz_service.start_mistakes_bank(
            db_session, current_user=_ctx(outsider), module_id=base.module.id
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await quiz_service.list_mistakes_bank(
            db_session, current_user=_ctx(base.lecturer), module_id=base.module.id, limit=50, offset=0
        )
    assert exc.value.status_code == 403
