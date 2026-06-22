from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import Recommendation, StudentRiskSnapshot
from app.platform.llm.errors import InvalidOutput
from app.platform.llm.models.recommendation import RecommendationCopy

RECOMMENDATION_COPY_PROMPT_VERSION = "v1"
RECOMMENDATION_COPY_FEATURE = "recommendation_copy"
RECOMMENDATION_COPY_PROMPT_NAME = "recommendation_copy"

MODULE_TARGET_REASONS = {
    "forecast_impossible",
    "forecast_pressure",
    "missed_recent_quizzes",
    "low_recent_quiz_score",
    "inactive_recently",
}

PEER_TERMS = (
    "class average",
    "cohort",
    "peers",
    "classmates",
    "most students",
    "everyone else",
    "below average",
    "bottom group",
    "compared with",
    "rest of the class",
    "other students",
    "behind the class",
)

DIAGNOSIS_TERMS = (
    "anxiety",
    "depression",
    "adhd",
    "burnout",
    "mental health",
    "mental-health",
    "diagnosis",
    "diagnosed",
    "struggling emotionally",
    "seems depressed",
)

UNSUPPORTED_FACT_TERMS = (
    "attendance",
    "missing assignment",
    "missing assignments",
    "falling grade",
    "falling grades",
    "poor participation",
    "late submission",
    "late submissions",
)

DOMAIN_FACT_REASON_ALLOWLIST = {
    "quiz": {"missed_recent_quizzes", "low_recent_quiz_score"},
    "quizzes": {"missed_recent_quizzes", "low_recent_quiz_score"},
    "question set": {"missed_recent_quizzes", "low_recent_quiz_score"},
    "attempt": {"missed_recent_quizzes", "low_recent_quiz_score"},
    "deadline": {"topic_deadline_gap"},
    "scheduled activity": {"inactive_recently"},
    "study session": {"inactive_recently"},
}

STUDENT_BANNED_TERMS = (
    "at risk",
    "critical",
    "failing",
    "behind the class",
    "other students",
    "mental health",
    "diagnosis",
    "you are not trying",
    "you're not trying",
    "needs support",
    "risk tier",
    "warning",
    "red flag",
    "urgent",
    "you are behind",
    "you're behind",
    "not putting in effort",
    "lazy",
    "unmotivated",
    "careless",
    "disengaged",
)

NUMBER_WORDS = {
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "half",
    "quarter",
    "third",
}

NUMBER_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s*[-/]\s*\d+(?:\.\d+)?)?(?:st|nd|rd|th)?(?:\s*%|\s*percent)?\b",
    re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"\b[a-z][a-z'-]*\b", re.IGNORECASE)


@dataclass(frozen=True)
class RecommendationCopyValidationContext:
    reason_codes: frozenset[str]
    metric_keys: frozenset[str]
    target_label: str
    allowed_numbers: frozenset[str]
    allowed_fact_phrases: frozenset[str]


class RecommendationNumericConsistencyOutputValidator:
    def validate(self, *, text: str, context: RecommendationCopyValidationContext) -> None:
        lowered = _normalize_text(text)
        for term in PEER_TERMS:
            if term in lowered:
                raise InvalidOutput("recommendation copy contains a peer comparison", error_code="peer_comparison")
        for term in DIAGNOSIS_TERMS:
            if term in lowered:
                raise InvalidOutput("recommendation copy contains diagnosis language", error_code="diagnosis")
        for term in UNSUPPORTED_FACT_TERMS:
            if term in lowered:
                raise InvalidOutput("recommendation copy contains an unsupported fact", error_code="unsupported_fact")
        for term, allowed_reasons in DOMAIN_FACT_REASON_ALLOWLIST.items():
            if term in lowered and not (allowed_reasons & context.reason_codes):
                raise InvalidOutput("recommendation copy contains an unsupported fact", error_code="unsupported_fact")

        allowed_numbers = {_normalize_number(token) for token in context.allowed_numbers}
        for token in _numeric_tokens(text):
            normalized = _normalize_number(token)
            if normalized not in allowed_numbers:
                raise InvalidOutput(
                    f"recommendation copy invented numeric token {token!r}",
                    error_code="invented_number",
                )

        allowed_reasons = set(context.reason_codes)
        for reason_code in {
            "forecast_impossible",
            "forecast_pressure",
            "missed_recent_quizzes",
            "low_recent_quiz_score",
            "inactive_recently",
            "topic_deadline_gap",
        }:
            reason_words = reason_code.replace("_", " ")
            if reason_words in lowered and reason_code not in allowed_reasons:
                raise InvalidOutput("recommendation copy introduced a new risk reason", error_code="new_reason")


class StudentCopySafetyOutputValidator:
    def validate(self, *, text: str) -> None:
        lowered = _normalize_text(text)
        for term in STUDENT_BANNED_TERMS:
            if term in lowered:
                raise InvalidOutput("student recommendation copy is not safe", error_code="student_copy_safety")


def validate_recommendation_copy(
    copy: RecommendationCopy,
    *,
    context: RecommendationCopyValidationContext,
) -> None:
    numeric = RecommendationNumericConsistencyOutputValidator()
    safety = StudentCopySafetyOutputValidator()
    numeric.validate(text=copy.lecturer_draft, context=context)
    numeric.validate(text=copy.student_nudge, context=context)
    safety.validate(text=copy.student_nudge)


async def sync_recommendations_for_run(db: AsyncSession, *, run_id: UUID) -> int:
    snapshots = (
        await db.scalars(
            select(StudentRiskSnapshot)
            .where(StudentRiskSnapshot.agent_run_id == run_id)
            .order_by(StudentRiskSnapshot.student_id.asc(), StudentRiskSnapshot.module_id.asc())
        )
    ).all()
    active_count = 0
    for snapshot in snapshots:
        current_keys: set[tuple[str, str]] = set()
        for reason in snapshot.risk_reasons:
            reason_code = str(reason.get("code") or "")
            if not reason_code:
                continue
            target_key, target_label = target_for_reason(snapshot.module_id, reason)
            current_keys.add((reason_code, target_key))
            dismissed = await _dismissed_audiences(
                db,
                student_id=snapshot.student_id,
                reason_code=reason_code,
                target_key=target_key,
            )
            if dismissed == {"lecturer", "student"}:
                continue
            row = await _active_recommendation(
                db,
                student_id=snapshot.student_id,
                reason_code=reason_code,
                target_key=target_key,
            )
            payload = build_deterministic_payload(
                reason=reason,
                module_id=snapshot.module_id,
                target_key=target_key,
                target_label=target_label,
            )
            input_hash = recommendation_input_hash(payload)
            now = _now()
            if row is None:
                row = Recommendation(
                    agent_run_id=snapshot.agent_run_id,
                    student_risk_snapshot_id=snapshot.id,
                    student_id=snapshot.student_id,
                    module_id=snapshot.module_id,
                    reason_code=reason_code,
                    target_key=target_key,
                    target_label=target_label,
                    deterministic_payload=payload,
                    algorithm_version=snapshot.algorithm_version,
                    input_hash=input_hash,
                    source_cutoff_at=snapshot.source_cutoff_at,
                    lecturer_state="dismissed" if "lecturer" in dismissed else "new",
                    lecturer_dismissed_at=now if "lecturer" in dismissed else None,
                    student_state="dismissed" if "student" in dismissed else "new",
                    student_dismissed_at=now if "student" in dismissed else None,
                )
                db.add(row)
            else:
                row.agent_run_id = snapshot.agent_run_id
                row.student_risk_snapshot_id = snapshot.id
                row.module_id = snapshot.module_id
                row.target_label = target_label
                row.deterministic_payload = payload
                row.algorithm_version = snapshot.algorithm_version
                row.source_cutoff_at = snapshot.source_cutoff_at
                row.updated_at = now
                if row.input_hash != input_hash:
                    row.input_hash = input_hash
                    _clear_ai_cache(row)
            active_count += 1
        await _close_cleared_for_snapshot(db, snapshot=snapshot, current_keys=current_keys)
    return active_count


async def _active_recommendation(
    db: AsyncSession,
    *,
    student_id: UUID,
    reason_code: str,
    target_key: str,
) -> Recommendation | None:
    return await db.scalar(
        select(Recommendation).where(
            Recommendation.student_id == student_id,
            Recommendation.reason_code == reason_code,
            Recommendation.target_key == target_key,
            Recommendation.status == "active",
        )
    )


async def _dismissed_audiences(
    db: AsyncSession,
    *,
    student_id: UUID,
    reason_code: str,
    target_key: str,
) -> set[str]:
    rows = (
        await db.scalars(
            select(Recommendation).where(
                Recommendation.student_id == student_id,
                Recommendation.reason_code == reason_code,
                Recommendation.target_key == target_key,
            )
        )
    ).all()
    audiences: set[str] = set()
    if any(row.lecturer_state == "dismissed" for row in rows):
        audiences.add("lecturer")
    if any(row.student_state == "dismissed" for row in rows):
        audiences.add("student")
    return audiences


async def _close_cleared_for_snapshot(
    db: AsyncSession,
    *,
    snapshot: StudentRiskSnapshot,
    current_keys: set[tuple[str, str]],
) -> None:
    rows = (
        await db.scalars(
            select(Recommendation).where(
                Recommendation.student_id == snapshot.student_id,
                Recommendation.module_id == snapshot.module_id,
                Recommendation.status == "active",
            )
        )
    ).all()
    now = _now()
    for row in rows:
        if (row.reason_code, row.target_key) in current_keys:
            continue
        row.status = "closed"
        row.closed_at = now
        row.close_reason = "cleared"
        row.updated_at = now


def current_reason_keys(module_id: UUID, reasons: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(str(reason["code"]), target_for_reason(module_id, reason)[0]) for reason in reasons if reason.get("code")}


async def has_prior_dismissal(
    db: AsyncSession,
    *,
    recommendation: Recommendation,
    audience: str,
) -> bool:
    field = Recommendation.lecturer_state if audience == "lecturer" else Recommendation.student_state
    return bool(
        await db.scalar(
            select(Recommendation.id)
            .where(
                Recommendation.student_id == recommendation.student_id,
                Recommendation.reason_code == recommendation.reason_code,
                Recommendation.target_key == recommendation.target_key,
                field == "dismissed",
                Recommendation.id != recommendation.id,
            )
            .limit(1)
        )
    )


def is_visible_for_audience(
    recommendation: Recommendation,
    *,
    audience: str,
    current_keys: set[tuple[str, str]],
) -> bool:
    if recommendation.status != "active":
        return False
    if (recommendation.reason_code, recommendation.target_key) not in current_keys:
        return False
    if audience == "lecturer":
        return recommendation.lecturer_state != "dismissed"
    return recommendation.student_state != "dismissed"


def target_for_reason(module_id: UUID, reason: dict[str, Any]) -> tuple[str, str]:
    code = str(reason.get("code") or "")
    metrics = reason.get("supportingMetrics") or {}
    if code == "topic_deadline_gap":
        title = str(metrics.get("topicTitle") or "Topic").strip() or "Topic"
        return f"topic:{module_id}:{_slugify(title)}", title
    if code in MODULE_TARGET_REASONS:
        return f"module:{module_id}", "Module"
    return f"reason:{module_id}:{_slugify(code)}", code.replace("_", " ").title()


def build_deterministic_payload(
    *,
    reason: dict[str, Any],
    module_id: UUID,
    target_key: str,
    target_label: str,
) -> dict[str, Any]:
    lecturer_template = _lecturer_template(reason, target_label=target_label)
    student_template = _student_template(reason, target_label=target_label)
    next_step = _student_next_step(reason)
    supporting_metrics = _jsonable(reason.get("supportingMetrics") or {})
    metric_keys = list(reason.get("metricKeys") or [])
    allowed_fact_phrases = _allowed_fact_phrases(
        reason=reason,
        target_label=target_label,
        lecturer_template=lecturer_template,
        student_template=student_template,
        next_step=next_step,
    )
    allowed_numbers = sorted(
        _numeric_tokens(" ".join([lecturer_template, student_template, next_step]))
        | _numbers_from_value(supporting_metrics)
    )
    return {
        "reasonCode": reason.get("code"),
        "severity": reason.get("severity"),
        "target": {"key": target_key, "label": target_label, "moduleId": str(module_id)},
        "metricKeys": metric_keys,
        "supportingMetrics": supporting_metrics,
        "allowedReasonCodes": [reason.get("code")],
        "allowedMetricKeys": metric_keys,
        "allowedNumbers": allowed_numbers,
        "allowedFactPhrases": sorted(allowed_fact_phrases),
        "lecturerTemplate": lecturer_template,
        "studentTemplate": student_template,
        "studentNextStep": next_step,
    }


def validation_context(payload: dict[str, Any]) -> RecommendationCopyValidationContext:
    return RecommendationCopyValidationContext(
        reason_codes=frozenset(str(item) for item in payload.get("allowedReasonCodes") or []),
        metric_keys=frozenset(str(item) for item in payload.get("allowedMetricKeys") or []),
        target_label=str((payload.get("target") or {}).get("label") or ""),
        allowed_numbers=frozenset(str(item) for item in payload.get("allowedNumbers") or []),
        allowed_fact_phrases=frozenset(str(item) for item in payload.get("allowedFactPhrases") or []),
    )


def recommendation_input_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ai_prompt_blob(recommendation: Recommendation) -> str:
    payload = {
        "deterministicPayload": recommendation.deterministic_payload,
        "contract": {
            "noNumbersOutsideAllowedNumbers": True,
            "noPeerComparisons": True,
            "noDiagnoses": True,
            "noNewRiskReasons": True,
            "studentTone": "gentle, calm, no risk labels, no shame",
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def ai_provenance(recommendation: Recommendation) -> dict[str, str | None]:
    if not recommendation.ai_model_id or not recommendation.ai_generated_at:
        return {}
    return {
        "modelId": recommendation.ai_model_id,
        "promptVersion": recommendation.ai_prompt_version,
        "inputHash": recommendation.ai_input_hash,
        "generatedAt": recommendation.ai_generated_at.isoformat(),
    }


def lecturer_text(recommendation: Recommendation) -> tuple[str, str]:
    if _has_current_ai(recommendation) and recommendation.lecturer_ai_text:
        return recommendation.lecturer_ai_text, "ai"
    return str(recommendation.deterministic_payload["lecturerTemplate"]), "template"


def student_text(recommendation: Recommendation) -> tuple[str, str]:
    if _has_current_ai(recommendation) and recommendation.student_ai_text:
        return recommendation.student_ai_text, "ai"
    return str(recommendation.deterministic_payload["studentTemplate"]), "template"


def _has_current_ai(recommendation: Recommendation) -> bool:
    return (
        recommendation.ai_status == "succeeded"
        and recommendation.ai_input_hash == recommendation.input_hash
        and recommendation.ai_prompt_version == RECOMMENDATION_COPY_PROMPT_VERSION
    )


def _clear_ai_cache(row: Recommendation) -> None:
    row.lecturer_ai_text = None
    row.student_ai_text = None
    row.ai_status = "not_requested"
    row.ai_failure_message_sanitized = None
    row.ai_request_log_id = None
    row.ai_model_id = None
    row.ai_prompt_version = None
    row.ai_input_hash = None
    row.ai_generated_at = None


def _lecturer_template(reason: dict[str, Any], *, target_label: str) -> str:
    text = str(reason.get("lecturerText") or "This student may benefit from a brief check-in.")
    return f"{text}. Suggested manual follow-up: share one focused next step for {target_label}."


def _student_template(reason: dict[str, Any], *, target_label: str) -> str:
    text = str(reason.get("studentText") or "A small study step could help.")
    return f"{text} A short review of {target_label} is a good next step."


def _student_next_step(reason: dict[str, Any]) -> str:
    code = str(reason.get("code") or "")
    if code in {"missed_recent_quizzes", "low_recent_quiz_score"}:
        return "Review the latest quiz practice and try one focused question set."
    if code in {"forecast_impossible", "forecast_pressure"}:
        return "Focus on the strongest remaining course opportunities."
    if code == "inactive_recently":
        return "Start with a short study session and the next scheduled activity."
    if code == "topic_deadline_gap":
        return "Review this topic before the upcoming deadline."
    return "Choose one short review activity."


def _allowed_fact_phrases(
    *,
    reason: dict[str, Any],
    target_label: str,
    lecturer_template: str,
    student_template: str,
    next_step: str,
) -> set[str]:
    phrases = {
        _normalize_text(target_label),
        _normalize_text(str(reason.get("code") or "")),
        _normalize_text(str(reason.get("lecturerText") or "")),
        _normalize_text(str(reason.get("studentText") or "")),
        _normalize_text(lecturer_template),
        _normalize_text(student_template),
        _normalize_text(next_step),
    }
    metrics = reason.get("supportingMetrics") or {}
    for value in metrics.values():
        if isinstance(value, str):
            phrases.add(_normalize_text(value))
    return {phrase for phrase in phrases if phrase}


def _numeric_tokens(text: str) -> set[str]:
    tokens = {_normalize_number(match.group(0)) for match in NUMBER_PATTERN.finditer(text)}
    for match in WORD_PATTERN.finditer(text.lower()):
        word = match.group(0)
        if word in NUMBER_WORDS:
            tokens.add(word)
    return {token for token in tokens if token}


def _numbers_from_value(value: Any) -> set[str]:
    tokens: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            tokens |= _numbers_from_value(item)
    elif isinstance(value, list):
        for item in value:
            tokens |= _numbers_from_value(item)
    elif isinstance(value, (int, float, Decimal)):
        text = str(value)
        tokens.add(_normalize_number(text))
        if Decimal(str(value)) == Decimal(str(value)).to_integral():
            tokens.add(str(int(Decimal(str(value)))))
    elif isinstance(value, str):
        tokens |= _numeric_tokens(value)
    return tokens


def _normalize_number(token: str) -> str:
    return re.sub(r"\s+", "", token.strip().lower().replace("percent", "%"))


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "target"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _now() -> datetime:
    return datetime.now(UTC)
