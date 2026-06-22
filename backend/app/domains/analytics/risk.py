from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from uuid import UUID


RISK_TIERS = ("on_track", "watch", "needs_support")
RISK_LABELS = {
    "on_track": "On track",
    "watch": "Watch",
    "needs_support": "Needs support",
}
SEVERITY_RANK = {"watch": 1, "needs_support": 2}


@dataclass(frozen=True)
class RiskConfig:
    algorithm_version: str
    recent_quiz_window: int
    missed_quiz_watch_count: int
    missed_quiz_needs_support_count: int
    low_quiz_watch_average: Decimal
    low_quiz_needs_support_average: Decimal
    inactivity_watch_days: int
    inactivity_needs_support_days: int
    topic_deadline_watch_days: int
    topic_deadline_needs_support_hours: int


@dataclass(frozen=True)
class RiskMetrics:
    student_id: UUID
    module_id: UUID
    forecast_state: str | None
    missed_recent_quiz_count: int
    recent_quiz_scores: tuple[Decimal, ...]
    days_since_activity: int | None
    upcoming_work_exists: bool
    topic_gap_title: str | None
    topic_gap_due_in_hours: int | None


@dataclass(frozen=True)
class RiskReason:
    code: str
    severity: str
    metric_keys: list[str]
    lecturer_text: str
    student_text: str
    supporting_metrics: dict[str, Decimal | int | str | None]


@dataclass(frozen=True)
class RiskResult:
    risk_tier: str
    reasons: list[RiskReason]
    algorithm_version: str
    input_hash: str
    source_cutoff_at: datetime
    computed_at: datetime


def classify_risk(
    metrics: RiskMetrics,
    *,
    config: RiskConfig,
    source_cutoff_at: datetime,
    computed_at: datetime | None = None,
) -> RiskResult:
    computed = computed_at or datetime.now(UTC)
    reasons: list[RiskReason] = []

    if metrics.forecast_state == "impossible":
        reasons.append(
            RiskReason(
                code="forecast_impossible",
                severity="needs_support",
                metric_keys=["forecastState"],
                lecturer_text="Target grade is not reachable from the current scores",
                student_text="Your target may need a different path from here; focus on the strongest remaining opportunities.",
                supporting_metrics={"forecastState": metrics.forecast_state},
            )
        )
    elif metrics.forecast_state in {"at_risk", "requires_high_score"}:
        severity = "needs_support" if metrics.forecast_state == "requires_high_score" else "watch"
        reasons.append(
            RiskReason(
                code="forecast_pressure",
                severity=severity,
                metric_keys=["forecastState"],
                lecturer_text=(
                    "Forecast requires unusually high remaining scores"
                    if severity == "needs_support"
                    else "Forecast needs attention to stay on target"
                ),
                student_text="Your target could use a little extra attention in the next study block.",
                supporting_metrics={"forecastState": metrics.forecast_state},
            )
        )

    missed = metrics.missed_recent_quiz_count
    if missed >= config.missed_quiz_needs_support_count:
        reasons.append(
            RiskReason(
                code="missed_recent_quizzes",
                severity="needs_support",
                metric_keys=["missedRecentQuizCount", "recentQuizWindow"],
                lecturer_text=f"Missed {missed} of the last {config.recent_quiz_window} quiz opportunities",
                student_text="Recent quiz practice could use a little time.",
                supporting_metrics={
                    "missedRecentQuizCount": missed,
                    "recentQuizWindow": config.recent_quiz_window,
                },
            )
        )
    elif missed >= config.missed_quiz_watch_count:
        reasons.append(
            RiskReason(
                code="missed_recent_quizzes",
                severity="watch",
                metric_keys=["missedRecentQuizCount", "recentQuizWindow"],
                lecturer_text=f"Missed {missed} of the last {config.recent_quiz_window} quiz opportunities",
                student_text="A recent quiz is still a good next step.",
                supporting_metrics={
                    "missedRecentQuizCount": missed,
                    "recentQuizWindow": config.recent_quiz_window,
                },
            )
        )

    if metrics.recent_quiz_scores:
        average = sum(metrics.recent_quiz_scores) / Decimal(len(metrics.recent_quiz_scores))
        if average < config.low_quiz_needs_support_average:
            reasons.append(
                RiskReason(
                    code="low_recent_quiz_score",
                    severity="needs_support",
                    metric_keys=["recentQuizAverage", "recentQuizCount"],
                    lecturer_text=f"Recent quiz average is {average:.0f}%",
                    student_text="Recent quiz results suggest reviewing the core ideas before the next attempt.",
                    supporting_metrics={
                        "recentQuizAverage": average,
                        "recentQuizCount": len(metrics.recent_quiz_scores),
                    },
                )
            )
        elif average < config.low_quiz_watch_average:
            reasons.append(
                RiskReason(
                    code="low_recent_quiz_score",
                    severity="watch",
                    metric_keys=["recentQuizAverage", "recentQuizCount"],
                    lecturer_text=f"Recent quiz average is {average:.0f}%",
                    student_text="A short review before the next quiz could help.",
                    supporting_metrics={
                        "recentQuizAverage": average,
                        "recentQuizCount": len(metrics.recent_quiz_scores),
                    },
                )
            )

    if metrics.days_since_activity is not None and metrics.upcoming_work_exists:
        if metrics.days_since_activity >= config.inactivity_needs_support_days:
            reasons.append(
                RiskReason(
                    code="inactive_recently",
                    severity="needs_support",
                    metric_keys=["daysSinceActivity"],
                    lecturer_text=f"No recorded activity for {metrics.days_since_activity} days",
                    student_text="A small study session soon would help rebuild momentum.",
                    supporting_metrics={"daysSinceActivity": metrics.days_since_activity},
                )
            )
        elif metrics.days_since_activity >= config.inactivity_watch_days:
            reasons.append(
                RiskReason(
                    code="inactive_recently",
                    severity="watch",
                    metric_keys=["daysSinceActivity"],
                    lecturer_text=f"No recorded activity for {metrics.days_since_activity} days",
                    student_text="It may be a good moment to check the next activity.",
                    supporting_metrics={"daysSinceActivity": metrics.days_since_activity},
                )
            )

    if metrics.topic_gap_title and metrics.topic_gap_due_in_hours is not None:
        if metrics.topic_gap_due_in_hours <= config.topic_deadline_needs_support_hours:
            reasons.append(
                RiskReason(
                    code="topic_deadline_gap",
                    severity="needs_support",
                    metric_keys=["topicGapDueInHours", "topicTitle"],
                    lecturer_text=f"{metrics.topic_gap_title} needs attention before an upcoming deadline",
                    student_text=f"{metrics.topic_gap_title} could use a little extra time before the deadline.",
                    supporting_metrics={
                        "topicGapDueInHours": metrics.topic_gap_due_in_hours,
                        "topicTitle": metrics.topic_gap_title,
                    },
                )
            )
        elif metrics.topic_gap_due_in_hours <= config.topic_deadline_watch_days * 24:
            reasons.append(
                RiskReason(
                    code="topic_deadline_gap",
                    severity="watch",
                    metric_keys=["topicGapDueInHours", "topicTitle"],
                    lecturer_text=f"{metrics.topic_gap_title} needs attention this week",
                    student_text=f"{metrics.topic_gap_title} is worth reviewing this week.",
                    supporting_metrics={
                        "topicGapDueInHours": metrics.topic_gap_due_in_hours,
                        "topicTitle": metrics.topic_gap_title,
                    },
                )
            )

    tier = _tier_for_reasons(reasons)
    return RiskResult(
        risk_tier=tier,
        reasons=reasons,
        algorithm_version=config.algorithm_version,
        input_hash=input_hash(metrics=metrics, config=config, source_cutoff_at=source_cutoff_at),
        source_cutoff_at=source_cutoff_at,
        computed_at=computed,
    )


def reason_to_dict(reason: RiskReason) -> dict:
    data = asdict(reason)
    data["metricKeys"] = data.pop("metric_keys")
    data["lecturerText"] = data.pop("lecturer_text")
    data["studentText"] = data.pop("student_text")
    data["supportingMetrics"] = _jsonable(data.pop("supporting_metrics"))
    return data


def input_hash(*, metrics: RiskMetrics, config: RiskConfig, source_cutoff_at: datetime) -> str:
    payload = {
        "algorithmVersion": config.algorithm_version,
        "config": _jsonable(asdict(config)),
        "metrics": _jsonable(asdict(metrics)),
        "sourceCutoffAt": source_cutoff_at.isoformat(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tier_for_reasons(reasons: list[RiskReason]) -> str:
    if not reasons:
        return "on_track"
    highest = max(SEVERITY_RANK[reason.severity] for reason in reasons)
    return "needs_support" if highest == SEVERITY_RANK["needs_support"] else "watch"


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
