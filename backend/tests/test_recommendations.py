from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domains.analytics import recommendations
from app.domains.analytics.recommendations import (
    RecommendationNumericConsistencyOutputValidator,
    StudentCopySafetyOutputValidator,
)
from app.domains.analytics.service import get_or_create_agent_run, run_agent_run
from app.domains.progress.seed import seed_progress_dataset
from app.platform.db.models import Recommendation
from app.platform.llm.errors import InvalidOutput
from app.platform.llm.models.recommendation import RecommendationCopy

pytestmark = pytest.mark.anyio


def _reason() -> dict:
    return {
        "code": "topic_deadline_gap",
        "severity": "watch",
        "metricKeys": ["topicGapDueInHours", "topicTitle"],
        "lecturerText": "Financial Modelling needs attention this week",
        "studentText": "Financial Modelling is worth reviewing this week.",
        "supportingMetrics": {"topicGapDueInHours": 48, "topicTitle": "Financial Modelling"},
    }


def _payload() -> dict:
    return recommendations.build_deterministic_payload(
        reason=_reason(),
        module_id="00000000-0000-0000-0000-000000000001",
        target_key="topic:00000000-0000-0000-0000-000000000001:financial-modelling",
        target_label="Financial Modelling",
    )


def test_recommendation_validators_allow_correct_ai_copy():
    payload = _payload()
    copy = RecommendationCopy(
        lecturer_draft=(
            "Financial Modelling needs attention this week. Please suggest one focused review step."
        ),
        student_nudge="Financial Modelling is worth reviewing this week.",
    )

    recommendations.validate_recommendation_copy(
        copy,
        context=recommendations.validation_context(payload),
    )


@pytest.mark.parametrize(
    "lecturer_text",
    [
        "This student is 42% below where they should be.",
        "This student is behind the class average.",
        "This looks like anxiety affecting the work.",
        "Attendance has become a problem.",
    ],
)
def test_numeric_validator_rejects_adversarial_lecturer_copy(lecturer_text: str):
    payload = _payload()
    copy = RecommendationCopy(
        lecturer_draft=lecturer_text,
        student_nudge="Financial Modelling is worth reviewing this week.",
    )

    with pytest.raises(InvalidOutput):
        recommendations.validate_recommendation_copy(
            copy,
            context=recommendations.validation_context(payload),
        )


@pytest.mark.parametrize(
    "student_text",
    [
        "You are at risk and need urgent help.",
        "You are behind other students.",
        "This red flag means you are not putting in effort.",
        "This seems like burnout.",
    ],
)
def test_student_copy_safety_rejects_banned_student_copy(student_text: str):
    payload = _payload()
    copy = RecommendationCopy(
        lecturer_draft="Financial Modelling needs attention this week.",
        student_nudge=student_text,
    )

    with pytest.raises(InvalidOutput):
        recommendations.validate_recommendation_copy(
            copy,
            context=recommendations.validation_context(payload),
        )


def test_lecturer_tone_guard_is_student_only():
    payload = _payload()
    # Lecturer copy may be direct; student copy still stays gentle.
    copy = RecommendationCopy(
        lecturer_draft="This is at risk of slipping without a manual check-in.",
        student_nudge="Financial Modelling is worth reviewing this week.",
    )

    recommendations.validate_recommendation_copy(
        copy,
        context=recommendations.validation_context(payload),
    )


def test_standalone_output_validators_cover_positive_and_negative_controls():
    payload = _payload()
    context = recommendations.validation_context(payload)
    RecommendationNumericConsistencyOutputValidator().validate(
        text="Financial Modelling can use 48 hours of focus.",
        context=context,
    )
    with pytest.raises(InvalidOutput):
        RecommendationNumericConsistencyOutputValidator().validate(
            text="Financial Modelling can use two extra sessions.",
            context=context,
        )
    with pytest.raises(InvalidOutput):
        RecommendationNumericConsistencyOutputValidator().validate(
            text="A short review before the next quiz could help.",
            context=context,
        )
    StudentCopySafetyOutputValidator().validate(text="A short review could help.")
    with pytest.raises(InvalidOutput):
        StudentCopySafetyOutputValidator().validate(text="This is a warning.")


async def test_agent_run_creates_recommendations_from_risk_snapshots(db_session):
    summary = await seed_progress_dataset(db_session, prefix="stage11-rec-sync", reset=True, cohort_size=6)
    run, _ = await get_or_create_agent_run(
        db_session,
        trigger_type="manual_admin",
        scope_type="module",
        scope_id=summary.module_two_id,
        scheduled_for=datetime.now(UTC) + timedelta(seconds=1),
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    await db_session.commit()

    completed = await run_agent_run(db_session, run_id=run.id)

    assert completed.recommendation_count > 0
    rows = (
        await db_session.scalars(
            select(Recommendation).where(
                Recommendation.module_id == summary.module_two_id,
                Recommendation.status == "active",
            )
        )
    ).all()
    assert rows
    row = rows[0]
    assert row.algorithm_version == "risk-v1"
    assert row.input_hash
    assert row.source_cutoff_at is not None
    allowed_numbers = row.deterministic_payload["allowedNumbers"]
    assert "one" in allowed_numbers
    assert row.input_hash not in allowed_numbers
    assert str(row.id) not in allowed_numbers
    assert str(row.source_cutoff_at.year) not in allowed_numbers
    assert row.deterministic_payload["allowedFactPhrases"]


async def test_dismissed_recommendation_is_not_recreated_for_that_audience(db_session):
    summary = await seed_progress_dataset(db_session, prefix="stage11-rec-dismiss", reset=True, cohort_size=6)
    first, _ = await get_or_create_agent_run(
        db_session,
        trigger_type="manual_admin",
        scope_type="module",
        scope_id=summary.module_two_id,
        scheduled_for=datetime.now(UTC) + timedelta(seconds=1),
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    await db_session.commit()
    await run_agent_run(db_session, run_id=first.id)
    row = (
        await db_session.scalars(
            select(Recommendation).where(
                Recommendation.module_id == summary.module_two_id,
                Recommendation.status == "active",
            )
        )
    ).first()
    assert row is not None
    row.lecturer_state = "dismissed"
    row.student_state = "dismissed"
    row.status = "closed"
    row.close_reason = "cleared"
    row.closed_at = datetime.now(UTC)
    await db_session.commit()

    second, _ = await get_or_create_agent_run(
        db_session,
        trigger_type="manual_admin",
        scope_type="module",
        scope_id=summary.module_two_id,
        scheduled_for=datetime.now(UTC) + timedelta(minutes=5),
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    await db_session.commit()
    await run_agent_run(db_session, run_id=second.id)

    resurrected = await db_session.scalar(
        select(Recommendation).where(
            Recommendation.student_id == row.student_id,
            Recommendation.reason_code == row.reason_code,
            Recommendation.target_key == row.target_key,
            Recommendation.status == "active",
        )
    )
    assert resurrected is None
