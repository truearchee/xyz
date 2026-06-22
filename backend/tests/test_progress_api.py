from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.domains.progress.seed import seed_progress_dataset
from app.platform.db.models import (
    AIRequestLog,
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    StudentGradeRecord,
    StudentProgressSnapshot,
    StudentTargetGradeGoal,
    StudentTopicMasterySnapshot,
)

pytestmark = pytest.mark.anyio


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


async def _user_by_email(db_session, email: str) -> AppUser:
    user = await db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


async def test_progress_seed_realizes_all_six_states(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage9-api", reset=True, cohort_size=6)
    expected = {
        "a": (summary.module_one_id, "on_track"),
        "b": (summary.module_one_id, "at_risk"),
        "c": (summary.module_two_id, "requires_high_score"),
        "d": (summary.module_two_id, "impossible"),
        "e": (summary.module_one_id, "achieved"),
        "f": (summary.module_one_id, "final_no_remaining"),
    }
    for key, (module_id, state) in expected.items():
        user = await _user_by_email(db_session, summary.student_emails_by_key[key])
        response = await auth_client.get(
            f"/student/modules/{module_id}/progress",
            headers=_headers(user, jwt_factory),
        )
        assert response.status_code == 200, response.text
        assert response.json()["forecast"]["state"] == state


async def test_progress_seed_reset_is_idempotent(db_session):
    prefix = "stage9-reset"
    await seed_progress_dataset(db_session, prefix=prefix, reset=True, cohort_size=6)
    summary = await seed_progress_dataset(db_session, prefix=prefix, reset=True, cohort_size=6)

    module_ids = select(CourseModule.id).where(CourseModule.title.like(f"{prefix} Module %"))
    assert await db_session.scalar(select(func.count()).select_from(module_ids.subquery())) == 2
    assert (
        await db_session.scalar(
            select(func.count()).select_from(AppUser).where(AppUser.email.like(f"{prefix}-%@example.test"))
        )
        == 7
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(CourseMembership).where(CourseMembership.module_id.in_(module_ids))
        )
        == 14
    )
    assert summary.student_emails_by_key["a"] == f"{prefix}-student-a@example.test"


async def test_target_grade_upsert_recomputes_and_keeps_one_active_goal(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage9-target", reset=True, cohort_size=6)
    user = await _user_by_email(db_session, summary.student_emails_by_key["a"])
    response = await auth_client.put(
        f"/student/modules/{summary.module_one_id}/target-grade",
        headers=_headers(user, jwt_factory),
        json={"targetLetterGrade": "B"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["targetLetterGrade"] == "B"
    assert body["forecast"]["state"] == "achieved"
    response = await auth_client.put(
        f"/student/modules/{summary.module_one_id}/target-grade",
        headers=_headers(user, jwt_factory),
        json={"targetLetterGrade": "A-"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["targetLetterGrade"] == "A-"
    count = await db_session.scalar(
        select(func.count())
        .select_from(StudentTargetGradeGoal)
        .where(
            StudentTargetGradeGoal.student_id == user.id,
            StudentTargetGradeGoal.module_id == summary.module_one_id,
            StudentTargetGradeGoal.status == "active",
        )
    )
    assert count == 1


async def test_progress_json_is_current_student_only_and_creates_no_ai_log(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage9-privacy", reset=True, cohort_size=6)
    user = await _user_by_email(db_session, summary.student_emails_by_key["d"])
    before = await db_session.scalar(select(func.count()).select_from(AIRequestLog))
    dashboard_response = await auth_client.get(
        "/student/progress",
        headers=_headers(user, jwt_factory),
    )
    assert dashboard_response.status_code == 200, dashboard_response.text
    response = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/progress",
        headers=_headers(user, jwt_factory),
    )
    assert response.status_code == 200, response.text
    for text in (dashboard_response.text, response.text):
        for key, email in summary.student_emails_by_key.items():
            assert email not in text
            assert str(summary.student_ids_by_key[key]) not in text
        assert "Stage 9 Student" not in text
        assert "studentId" not in text
        assert "student_id" not in text
        assert "gradeRecords" not in text
        assert "grade_records" not in text
        assert "componentScores" not in text
        assert "component_scores" not in text
        assert "percentageScore" not in text
        assert "percentage_score" not in text
        assert "perStudent" not in text
        assert "individualStanding" not in text
    assert response.json()["benchmark"]["cohortSize"] == 6
    assert response.json()["benchmark"]["suppressed"] is False
    after = await db_session.scalar(select(func.count()).select_from(AIRequestLog))
    assert after == before


async def test_module_progress_omits_topic_mastery_for_unpublished_sections(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage9-topic-visibility", reset=True, cohort_size=6)
    user = await _user_by_email(db_session, summary.student_emails_by_key["d"])
    hidden_section = await db_session.scalar(
        select(ModuleSection).where(
            ModuleSection.course_module_id == summary.module_two_id,
            ModuleSection.title == "M2 Financial Modelling",
        )
    )
    assert hidden_section is not None
    hidden_section.publish_status = "unpublished"
    await db_session.commit()

    response = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/progress",
        headers=_headers(user, jwt_factory),
    )
    assert response.status_code == 200, response.text
    topics = response.json()["topics"]
    assert str(hidden_section.id) not in {topic["sectionId"] for topic in topics}
    assert "M2 Financial Modelling" not in {topic["title"] for topic in topics}
    assert "M2 Applied Lab" in {topic["title"] for topic in topics}


async def test_benchmark_student_average_is_caller_only_and_hides_other_student_averages(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage9-benchmark-privacy", reset=True, cohort_size=6)
    sentinel_scores = {
        "a": Decimal("12.34"),
        "b": Decimal("23.45"),
        "c": Decimal("34.56"),
        "d": Decimal("71.23"),
        "e": Decimal("45.67"),
        "f": Decimal("56.78"),
    }
    definition_ids = select(QuizDefinition.id).where(QuizDefinition.module_id == summary.module_two_id)
    for key, score in sentinel_scores.items():
        await db_session.execute(
            update(QuizAttempt)
            .where(
                QuizAttempt.quiz_definition_id.in_(definition_ids),
                QuizAttempt.student_id == summary.student_ids_by_key[key],
            )
            .values(score_percentage=score)
        )
    await db_session.commit()

    caller_key = "d"
    user = await _user_by_email(db_session, summary.student_emails_by_key[caller_key])
    response = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/progress",
        headers=_headers(user, jwt_factory),
    )
    assert response.status_code == 200, response.text
    raw = response.text
    benchmark = response.json()["benchmark"]
    assert benchmark["cohortSize"] == 6
    assert benchmark["suppressed"] is False
    assert Decimal(benchmark["studentAverage"]) == sentinel_scores[caller_key]
    assert Decimal(benchmark["classAverage"]) != sentinel_scores[caller_key]
    for key, score in sentinel_scores.items():
        if key == caller_key:
            continue
        assert Decimal(benchmark["studentAverage"]) != score
        assert str(score) not in raw
    assert "perStudent" not in raw
    assert "individualStanding" not in raw
    assert "componentScores" not in raw


async def test_progress_authz_uses_403_for_non_student_and_404_for_unassigned(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage9-authz", reset=True, cohort_size=6)
    lecturer = await _user_by_email(db_session, "stage9-authz-lecturer@example.test")
    student_c = await _user_by_email(db_session, summary.student_emails_by_key["c"])
    response = await auth_client.get(
        f"/student/modules/{summary.module_one_id}/progress",
        headers=_headers(lecturer, jwt_factory),
    )
    assert response.status_code == 403

    # Current-user-only route: a student can read only modules they belong to. A random module id
    # is existence-hidden as 404 rather than exposing a foreign student/resource distinction.
    response = await auth_client.get(
        "/student/modules/00000000-0000-4000-8000-000000000999/progress",
        headers=_headers(student_c, jwt_factory),
    )
    assert response.status_code == 404


async def test_progress_reads_are_read_only_and_no_forecast_table_exists(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage9-readonly", reset=True, cohort_size=6)
    user = await _user_by_email(db_session, summary.student_emails_by_key["a"])
    before = {
        "ai_logs": await db_session.scalar(select(func.count()).select_from(AIRequestLog)),
        "targets": await db_session.scalar(select(func.count()).select_from(StudentTargetGradeGoal)),
        "grade_records": await db_session.scalar(select(func.count()).select_from(StudentGradeRecord)),
        "progress_snapshots": await db_session.scalar(select(func.count()).select_from(StudentProgressSnapshot)),
        "mastery_snapshots": await db_session.scalar(
            select(func.count()).select_from(StudentTopicMasterySnapshot)
        ),
    }

    dashboard_response = await auth_client.get("/student/progress", headers=_headers(user, jwt_factory))
    assert dashboard_response.status_code == 200, dashboard_response.text
    module_response = await auth_client.get(
        f"/student/modules/{summary.module_one_id}/progress",
        headers=_headers(user, jwt_factory),
    )
    assert module_response.status_code == 200, module_response.text

    after = {
        "ai_logs": await db_session.scalar(select(func.count()).select_from(AIRequestLog)),
        "targets": await db_session.scalar(select(func.count()).select_from(StudentTargetGradeGoal)),
        "grade_records": await db_session.scalar(select(func.count()).select_from(StudentGradeRecord)),
        "progress_snapshots": await db_session.scalar(select(func.count()).select_from(StudentProgressSnapshot)),
        "mastery_snapshots": await db_session.scalar(
            select(func.count()).select_from(StudentTopicMasterySnapshot)
        ),
    }
    assert after == before
    assert await db_session.scalar(select(func.to_regclass("public.grade_forecasts"))) is None
    assert await db_session.scalar(select(func.to_regclass("public.student_grade_forecasts"))) is None
