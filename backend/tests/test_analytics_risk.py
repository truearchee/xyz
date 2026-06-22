from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domains.analytics.risk import RiskConfig, RiskMetrics, classify_risk


def _config() -> RiskConfig:
    return RiskConfig(
        algorithm_version="risk-v1",
        recent_quiz_window=3,
        missed_quiz_watch_count=1,
        missed_quiz_needs_support_count=2,
        low_quiz_watch_average=Decimal("70"),
        low_quiz_needs_support_average=Decimal("50"),
        inactivity_watch_days=7,
        inactivity_needs_support_days=14,
        topic_deadline_watch_days=7,
        topic_deadline_needs_support_hours=48,
        activity_event_types=(
            "completed_quiz",
            "perfect_quiz_score",
            "glossary_term_saved",
            "glossary_practice_completed",
            "studied_section",
        ),
    )


def test_risk_reasons_have_exact_metric_support_and_tier_precedence():
    cutoff = datetime(2026, 6, 20, 6, tzinfo=UTC)
    result = classify_risk(
        RiskMetrics(
            student_id=uuid4(),
            module_id=uuid4(),
            forecast_state="requires_high_score",
            missed_recent_quiz_count=2,
            recent_quiz_scores=(Decimal("40"), Decimal("55"), Decimal("45")),
            days_since_activity=15,
            upcoming_work_exists=True,
            topic_gap_title="Financial Modelling",
            topic_gap_due_in_hours=24,
        ),
        config=_config(),
        source_cutoff_at=cutoff,
        computed_at=cutoff + timedelta(seconds=1),
    )

    assert result.risk_tier == "needs_support"
    assert result.algorithm_version == "risk-v1"
    assert len(result.input_hash) == 64
    assert {reason.code for reason in result.reasons} == {
        "forecast_pressure",
        "missed_recent_quizzes",
        "low_recent_quiz_score",
        "inactive_recently",
        "topic_deadline_gap",
    }
    for reason in result.reasons:
        assert set(reason.metric_keys) == set(reason.supporting_metrics)
        assert reason.student_text
        assert "at risk" not in reason.student_text.lower()
        assert "critical" not in reason.student_text.lower()
        assert "failing" not in reason.student_text.lower()


@pytest.mark.parametrize(
    ("forecast_state", "expected"),
    [
        ("on_track", "on_track"),
        ("at_risk", "watch"),
        ("requires_high_score", "needs_support"),
        ("impossible", "needs_support"),
    ],
)
def test_forecast_signal_mapping(forecast_state: str, expected: str):
    cutoff = datetime(2026, 6, 20, 6, tzinfo=UTC)
    result = classify_risk(
        RiskMetrics(
            student_id=uuid4(),
            module_id=uuid4(),
            forecast_state=forecast_state,
            missed_recent_quiz_count=0,
            recent_quiz_scores=(),
            days_since_activity=None,
            upcoming_work_exists=False,
            topic_gap_title=None,
            topic_gap_due_in_hours=None,
        ),
        config=_config(),
        source_cutoff_at=cutoff,
    )

    assert result.risk_tier == expected
