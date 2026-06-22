from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    AnswerOption,
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    StudentAnswer,
)
from app.platform.query import analytics_read

pytestmark = pytest.mark.anyio


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


async def _seed_assessment_distribution(db: AsyncSession, *, prefix: str) -> SimpleNamespace:
    lecturer = AppUser(
        auth_provider_id=f"{prefix}-lecturer",
        email=f"{prefix}-lecturer@example.test",
        full_name="Assessment Lecturer",
        role="lecturer",
        timezone="UTC",
    )
    other_lecturer = AppUser(
        auth_provider_id=f"{prefix}-other-lecturer",
        email=f"{prefix}-other-lecturer@example.test",
        full_name="Other Lecturer",
        role="lecturer",
        timezone="UTC",
    )
    admin = AppUser(
        auth_provider_id=f"{prefix}-admin",
        email=f"{prefix}-admin@example.test",
        full_name="Assessment Admin",
        role="admin",
        timezone="UTC",
    )
    students = [
        AppUser(
            auth_provider_id=f"{prefix}-student-{index}",
            email=f"{prefix}-student-{index}@example.test",
            full_name=f"Assessment Student {index}",
            role="student",
            timezone="UTC",
        )
        for index in range(1, 5)
    ]
    db.add_all([lecturer, other_lecturer, admin, *students])
    await db.flush()

    module = CourseModule(title=f"{prefix} Biology", owner_id=lecturer.id, timezone="UTC", is_active=True)
    other_module = CourseModule(title=f"{prefix} Other", owner_id=other_lecturer.id, timezone="UTC", is_active=True)
    db.add_all([module, other_module])
    await db.flush()

    topic_section = ModuleSection(
        course_module_id=module.id,
        title="Cell Division",
        type="lecture",
        order_index=0,
        week_number=2,
        publish_status="published",
        status="active",
    )
    other_section = ModuleSection(
        course_module_id=other_module.id,
        title="Other Lecture",
        type="lecture",
        order_index=0,
        publish_status="published",
        status="active",
    )
    db.add_all([topic_section, other_section])
    await db.flush()

    db.add_all(
        [
            CourseMembership(user_id=lecturer.id, module_id=module.id, role="lecturer", status="active"),
            CourseMembership(
                user_id=other_lecturer.id,
                module_id=other_module.id,
                role="lecturer",
                status="active",
            ),
            *[
                CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active")
                for student in students
            ],
        ]
    )
    definition = QuizDefinition(
        module_section_id=topic_section.id,
        module_id=module.id,
        quiz_mode="post_class",
        source_scope={"sectionType": "lecture", "moduleSectionId": str(topic_section.id)},
    )
    db.add(definition)
    await db.flush()

    # Hand-computed distribution:
    # Q1: 4 answers, 1 correct, wrong M phase x2, wrong G1 phase x1 -> 25% correct.
    # Q2: 4 answers, 3 correct, wrong Ribosome x1 -> 75% correct.
    # Q3: 2 answers, cross-module provenance -> small cohort and topic unavailable.
    q1_choices = ["M phase", "M phase", "G1 phase", "S phase"]
    q2_choices = ["Mitochondrion", "Mitochondrion", "Ribosome", "Mitochondrion"]
    q3_choices = ["Alpha", "Beta"]
    for index, student in enumerate(students):
        attempt = QuizAttempt(
            quiz_definition_id=definition.id,
            student_id=student.id,
            attempt_number=1,
            status="completed",
            completed_at=datetime(2026, 6, 20, 8, index, tzinfo=UTC),
        )
        db.add(attempt)
        await db.flush()

        await _add_answered_question(
            db,
            attempt=attempt,
            question_text="Which phase copies DNA?",
            display_order=0,
            source_module_id=module.id,
            source_section_id=topic_section.id,
            source_summary_id=None,
            correct_option="S phase",
            options=["S phase", "M phase", "G1 phase", "Cytokinesis"],
            selected_option=q1_choices[index],
        )
        await _add_answered_question(
            db,
            attempt=attempt,
            question_text="Which organelle makes ATP?",
            display_order=1,
            source_module_id=module.id,
            source_section_id=topic_section.id,
            source_summary_id=None,
            correct_option="Mitochondrion",
            options=["Mitochondrion", "Ribosome", "Nucleus", "Golgi apparatus"],
            selected_option=q2_choices[index],
        )
        if index < 2:
            await _add_answered_question(
                db,
                attempt=attempt,
                question_text="Which label belongs to the unproven tiny cohort?",
                display_order=2,
                source_module_id=module.id,
                source_section_id=other_section.id,
                source_summary_id=None,
                correct_option="Alpha",
                options=["Alpha", "Beta", "Gamma", "Delta"],
                selected_option=q3_choices[index],
            )

    await db.commit()
    return SimpleNamespace(
        admin=admin,
        lecturer=lecturer,
        other_lecturer=other_lecturer,
        module=module,
        other_module=other_module,
        students=students,
        topic_section=topic_section,
    )


async def _add_answered_question(
    db: AsyncSession,
    *,
    attempt: QuizAttempt,
    question_text: str,
    display_order: int,
    source_module_id,
    source_section_id,
    source_summary_id,
    correct_option: str,
    options: list[str],
    selected_option: str,
) -> None:
    question = QuizQuestion(
        quiz_attempt_id=attempt.id,
        question_text=question_text,
        display_order=display_order,
        source_type="new_generated",
        source_module_id=source_module_id,
        source_section_id=source_section_id,
        source_summary_id=source_summary_id,
    )
    db.add(question)
    await db.flush()
    selected = None
    for order, option_text in enumerate(options):
        option = AnswerOption(
            quiz_question_id=question.id,
            text=option_text,
            display_order=order,
            is_correct=option_text == correct_option,
        )
        db.add(option)
        await db.flush()
        if option_text == selected_option:
            selected = option
    assert selected is not None
    db.add(
        StudentAnswer(
            quiz_attempt_id=attempt.id,
            quiz_question_id=question.id,
            selected_answer_option_id=selected.id,
            is_correct=selected.is_correct,
        )
    )
    await db.flush()


async def test_assessment_insights_compute_exact_aggregates_and_topic_fallback(
    db_session: AsyncSession,
) -> None:
    seed = await _seed_assessment_distribution(db_session, prefix="stage11-assessment-read")

    insights = await analytics_read.get_assessment_insights(db_session, module_id=seed.module.id)

    assert insights is not None
    assert insights.module_title == "stage11-assessment-read Biology"
    by_question = {question.question_text: question for question in insights.questions}
    copied = by_question["Which phase copies DNA?"]
    assert copied.answer_count == 4
    assert copied.correct_count == 1
    assert copied.incorrect_count == 3
    assert copied.correct_rate_percent == Decimal("25.00")
    assert [(item.option_text, item.selected_count) for item in copied.distractors] == [
        ("M phase", 2),
        ("G1 phase", 1),
    ]

    atp = by_question["Which organelle makes ATP?"]
    assert atp.answer_count == 4
    assert atp.correct_count == 3
    assert atp.correct_rate_percent == Decimal("75.00")
    assert [(item.option_text, item.selected_count) for item in atp.distractors] == [("Ribosome", 1)]

    tiny = by_question["Which label belongs to the unproven tiny cohort?"]
    assert tiny.answer_count == 2
    assert tiny.small_cohort is True
    assert tiny.correct_rate_percent is None
    assert tiny.small_cohort_message == analytics_read.SMALL_COHORT_MESSAGE

    assert [question.question_text for question in insights.most_missed_questions] == [
        "Which phase copies DNA?",
        "Which organelle makes ATP?",
    ]
    topic = insights.topic_mastery
    assert topic.available is True
    assert topic.unmapped_answer_count == 2
    assert topic.unmapped_message == "Topic mastery unavailable for 2 submissions without question provenance."
    assert len(topic.rows) == 1
    topic_row = topic.rows[0]
    assert topic_row.source_section_id == seed.topic_section.id
    assert topic_row.topic_title == "Cell Division"
    assert topic_row.topic_title != "Other Lecture"
    assert topic_row.week_number == 2
    assert topic_row.answer_count == 8
    assert topic_row.correct_count == 4
    assert topic_row.mastery_percent == Decimal("50.00")


async def test_assessment_insights_endpoint_is_scoped_and_aggregate_only(
    auth_client,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    seed = await _seed_assessment_distribution(db_session, prefix="stage11-assessment-api")

    response = await auth_client.get(
        f"/lecturer/modules/{seed.module.id}/analytics/assessment-insights",
        headers=_headers(seed.lecturer, jwt_factory),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["moduleId"] == str(seed.module.id)
    assert body["questions"]
    assert body["topicMastery"]["unmappedAnswerCount"] == 2
    assert "Assessment Student" not in response.text
    for student in seed.students:
        assert str(student.id) not in response.text
        assert student.email not in response.text
        assert student.full_name not in response.text

    cross_course = await auth_client.get(
        f"/lecturer/modules/{seed.module.id}/analytics/assessment-insights",
        headers=_headers(seed.other_lecturer, jwt_factory),
    )
    assert cross_course.status_code == 403

    student_forbidden = await auth_client.get(
        f"/lecturer/modules/{seed.module.id}/analytics/assessment-insights",
        headers=_headers(seed.students[0], jwt_factory),
    )
    assert student_forbidden.status_code == 403

    admin_forbidden = await auth_client.get(
        f"/lecturer/modules/{seed.module.id}/analytics/assessment-insights",
        headers=_headers(seed.admin, jwt_factory),
    )
    assert admin_forbidden.status_code == 403
