"""Stage 11.6 grade-forecast advice — deterministic payload, per-state templates, and validators.

The advice EXPLAINS Stage 9's deterministic forecast; it never calculates. The deterministic template
is the immediate, validator-safe render and the AI fallback. The AI phrasing layer (forecast_advice_ai)
must pass the numeric/fact-consistency + state-aware contradiction validator AND the reused student-copy
safety guard before any AI text is persisted or served.

Reuses the Stage 11.2 copy-guard machinery (single source for the banned-idea set + number
normalization), extended with a grade-advice / impossible-case lexicon and a contradiction guard.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domains.analytics.recommendations import (
    DIAGNOSIS_TERMS,
    NUMBER_PATTERN,
    NUMBER_WORDS,
    PEER_TERMS,
    WORD_PATTERN,
    StudentCopySafetyOutputValidator,
    _normalize_number,
    _normalize_text,
)
from app.domains.progress.forecast import ForecastResult
from app.platform.db.models.forecast_advice import StudentForecastAdvice
from app.platform.llm.errors import InvalidOutput
from app.platform.llm.models.forecast_advice import (
    GRADE_FORECAST_ADVICE_SCHEMA_VERSION,
    GRADE_FORECAST_ADVICE_SECTION_TYPE,
    GradeForecastAdvice,
)

ALGORITHM_VERSION = "forecast-advice-v1"
ADVICE_PROMPT_NAME = "grade_forecast_advice"
ADVICE_PROMPT_VERSION = "v1"
ADVICE_FEATURE = "grade_forecast_advice"
ADVICE_SECTION_TYPE = GRADE_FORECAST_ADVICE_SECTION_TYPE

# Rule-15 frugality: only states where guidance genuinely helps get an AI call. The rest render the
# deterministic line only (the course outcome is settled / comfortably on track).
AI_ELIGIBLE_STATES = frozenset({"at_risk", "requires_high_score", "impossible"})

# 11.6-specific copy guards — LAYERED on top of the reused 11.2 sets (we extend, never mutate the shared
# tuples, so 11.2's controls stay green). Defeatist / shaming framing is the impossible-case core. The
# neutral fact "isn't possible" / "not possible" stays ALLOWED — the honest template needs it.
ADVICE_BANNED_TERMS = (
    "too far",
    "fallen behind",
    "falling behind",
    "no way",
    "give up",
    "gave up",
    "giving up",
    "blew it",
    "blown it",
    "hopeless",
    "too late",
    "out of reach",
    "no longer achievable",
    "no longer reachable",
    "can't get",
    "cannot get",
    "won't reach",
    "will never",
    "doomed",
    "lost cause",
    "write off",
    "written off",
    "throw in the towel",
    "no point",
    "not worth",
    "in trouble",
    "in danger",
    "thin ice",
    "underperforming",
    "struggling",
    "slacking",
    "not trying",
    "poor effort",
    "bad grades",
    "weak performance",
)

ADVICE_PEER_TERMS = (
    "average student",
    "others in the",
    "fellow students",
    "where the class",
    "than the class",
    "ahead of you",
    "top of the class",
    "top of the cohort",
)

ADVICE_DIAGNOSIS_TERMS = (
    "burning out",
    "burned out",
    "burnt out",
    "anxious",
    "stressed out",
    "overwhelmed",
    "mentally exhausted",
    "checked out",
    "losing motivation",
    "lost motivation",
    "demotivated",
    "depressed",
)

# Facts the forecast cannot support — the model commonly invents these on the impossible card.
ADVICE_UNSUPPORTED_FACT_TERMS = (
    "extra credit",
    "bonus marks",
    "resit",
    "retake",
    "make-up",
    "makeup",
    "deferral",
    "deadline",
    "due date",
    "drop the module",
    "withdraw",
    "appeal",
    "office hours",
    "professor will",
    "lecturer will",
)

# State-aware contradiction families (substring, post-_normalize_text). The reachable set is broad so
# the impossible guard rejects any "the target is still attainable" framing; the unreachable set is
# broad so a reasoning model's natural paraphrases of impossibility still satisfy the honest-framing
# requirement (avoids silent AI death on the impossible card) and are rejected in reachable states.
REACHABLE_CLAIMS = (
    "still reach",
    "can reach",
    "still possible",
    "within reach",
    "still achievable",
    "still attainable",
    "still reachable",
    "can still get",
    "can still hit",
    "can still earn",
    "can still make",
    "still get there",
    "on track for",
    "is reachable",
    "is attainable",
    "you can get there",
    "not out of reach",
)
UNREACHABLE_CLAIMS = (
    "not possible",
    "isn't possible",
    "is not possible",
    "no longer possible",
    "no longer reachable",
    "no longer achievable",
    "no longer attainable",
    "no longer within reach",
    "not reachable",
    "not attainable",
    "not achievable",
    "out of reach",
    "beyond reach",
    "cannot reach",
    "can't reach",
    "can no longer",
    "won't reach",
    "can't be earned",
    "cannot be earned",
    "more than the remaining",
)
OVERCLAIM_TERMS = (
    "guaranteed",
    "guarantee",
    "certain",
    "definitely",
    "for sure",
    "no doubt",
    "no question",
    "in the bag",
)

# Small spelled numbers appear constantly in supportive prose ("one focused step", "a couple of
# topics", "half the work"), so flagging them as invented figures would wrongly reject valid advice and
# silently kill the AI layer (owner #2). Digits and LARGE/compound spelled numbers ("twenty",
# "twenty-five") remain the invented-figure channels we guard. The required average is always a digit.
PROSE_SAFE_NUMBER_WORDS = frozenset(
    {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
     "half", "quarter", "third"}
)


@dataclass(frozen=True)
class ForecastAdviceValidationContext:
    forecast_state: str
    allowed_numbers: frozenset[str]
    target_letter_grade: str
    best_reachable_letter_grade: str
    required_remaining_average_display: str | None


# ── number formatting (resolves the template-self-validation BLOCKER) ─────────────────────────────


def req_avg_display(value: Decimal | None) -> str | None:
    """The required remaining average rounded HALF_UP to 1 dp, as the single display + allowed-set value.

    Returns an integer string when the rounded value is whole (``90``), else 1 dp (``87.8``). The raw
    Stage 9 ``Decimal`` is never displayed (it has up to 26 dp) — both the template and ``allowedNumbers``
    use this one value, so the template always passes its own numeric validator and the hash never flaps.
    """
    if value is None:
        return None
    quantized = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return str(int(quantized))
    return str(quantized)


def _mentions_grade(text: str, grade: str) -> bool:
    """True if ``grade`` (e.g. ``A``, ``B+``) appears as a standalone token in the ORIGINAL-case text.

    Grade letters are uppercase, so matching the original case keeps the lowercase article "a" from ever
    counting as the grade "A".
    """
    if not grade:
        return False
    # Exclude +/- from the boundaries so a base letter ("A") is not satisfied by a different,
    # prefix-sharing grade ("A+"), and so suffixed grades ("B+") match exactly.
    pattern = r"(?<![A-Za-z0-9+\-])" + re.escape(grade) + r"(?![A-Za-z0-9+\-])"
    return re.search(pattern, text) is not None


def _advice_numeric_tokens(text: str) -> set[str]:
    """Numeric tokens to guard: all digits, plus LARGE/compound spelled numbers.

    Digits (percentages/scores) are the strong guard. Hyphenated spelled numbers ("twenty-five") are an
    invented-figure evasion channel, so each part is split out. Bare small prose number-words ("one",
    "half") are intentionally NOT flagged — see PROSE_SAFE_NUMBER_WORDS.
    """
    tokens = {_normalize_number(match.group(0)) for match in NUMBER_PATTERN.finditer(text)}
    for match in WORD_PATTERN.finditer(text.lower()):
        word = match.group(0)
        parts = re.split(r"[-']", word) if ("-" in word or "'" in word) else [word]
        for part in parts:
            if part in NUMBER_WORDS and part not in PROSE_SAFE_NUMBER_WORDS:
                tokens.add(part)
    return {token for token in tokens if token}


# ── deterministic template advice (per state; validator-safe by construction) ─────────────────────


def template_advice(forecast: ForecastResult, *, module_title: str) -> str:
    state = forecast.state
    target = forecast.target_letter_grade
    best = forecast.best_reachable_letter_grade
    final = forecast.final_letter_grade or forecast.current_letter_grade
    req = req_avg_display(forecast.required_remaining_average)
    if state == "at_risk":
        return (
            f"{target} is within reach — around {req}% on the work that's left gets you there. "
            f"A focused review of {module_title} is a strong next step."
        )
    if state == "requires_high_score":
        return (
            f"{target} is still on the table — it will take about {req}% on what's left, so a focused "
            f"plan for {module_title} is your best next step."
        )
    if state == "impossible":
        return (
            f"Aiming for {best} is your strongest goal from here — putting your focus there is well "
            f"worth it. Reaching {target} would now take more than the remaining work can add, so it "
            f"may help to revisit your target when you're ready."
        )
    if state == "on_track":
        return (
            f"You're on track for {target} — keeping your current pace on the remaining work should "
            f"get you there."
        )
    if state == "achieved":
        return (
            f"You've already done enough to reach {target} — nice work. Keeping steady will hold it."
        )
    if state == "final_no_remaining":
        return f"Your final result for {module_title} is {final}."
    return f"Keep going with {module_title} — every focused study step helps."


def build_deterministic_payload(forecast: ForecastResult, *, module_title: str) -> dict:
    state = forecast.state
    template = template_advice(forecast, module_title=module_title)
    req_display = req_avg_display(forecast.required_remaining_average)

    # allowedNumbers: from the RENDERED template (the 11.2 invariant — the template's own numbers are
    # tautologically allowed, incl. any digits in the module title) PLUS the cited required-average in
    # both bare and %-suffixed forms. Impossible cites no number, so its allowed set stays empty (no
    # ">100% needed" quote is possible).
    allowed_numbers = set(_advice_numeric_tokens(template))
    if state in AI_ELIGIBLE_STATES and state != "impossible" and req_display is not None:
        allowed_numbers.add(_normalize_number(req_display))
        allowed_numbers.add(_normalize_number(f"{req_display}%"))

    allowed_fact_phrases = {
        _normalize_text(value)
        for value in (
            forecast.target_letter_grade,
            forecast.best_reachable_letter_grade,
            forecast.current_letter_grade,
            forecast.final_letter_grade or "",
            module_title,
        )
        if value
    }

    return {
        "schemaVersion": GRADE_FORECAST_ADVICE_SCHEMA_VERSION,
        "forecastState": state,
        "targetLetterGrade": forecast.target_letter_grade,
        "currentLetterGrade": forecast.current_letter_grade,
        "bestReachableLetterGrade": forecast.best_reachable_letter_grade,
        "finalLetterGrade": forecast.final_letter_grade,
        "requiredRemainingAverageDisplay": req_display,
        "moduleTitle": module_title,
        "allowedNumbers": sorted(allowed_numbers),
        "allowedFactPhrases": sorted(allowed_fact_phrases),
        "templateAdvice": template,
        "aiEligible": state in AI_ELIGIBLE_STATES,
    }


def forecast_advice_input_hash(payload: dict) -> str:
    """Hash the display-relevant payload so the AI cache regenerates iff the rendered advice changes.

    Keyed on the template + state + allowed numbers (quantized via ``req_avg_display``), NOT the raw
    Stage 9 Decimals — reproducible across environments and stable near threshold boundaries (rule 15).
    """
    canonical = {
        "algorithmVersion": ALGORITHM_VERSION,
        "forecastState": payload.get("forecastState"),
        "templateAdvice": payload.get("templateAdvice"),
        "allowedNumbers": payload.get("allowedNumbers"),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def advice_validation_context(payload: dict) -> ForecastAdviceValidationContext:
    return ForecastAdviceValidationContext(
        forecast_state=str(payload.get("forecastState") or ""),
        allowed_numbers=frozenset(str(item) for item in payload.get("allowedNumbers") or []),
        target_letter_grade=str(payload.get("targetLetterGrade") or ""),
        best_reachable_letter_grade=str(payload.get("bestReachableLetterGrade") or ""),
        required_remaining_average_display=(
            str(payload["requiredRemainingAverageDisplay"])
            if payload.get("requiredRemainingAverageDisplay") is not None
            else None
        ),
    )


def advice_prompt_blob(payload: dict) -> str:
    blob = {
        "deterministicPayload": payload,
        "contract": {
            "noNumbersOutsideAllowedNumbers": True,
            "percentSymbolNotWord": True,
            "noPeerComparisons": True,
            "noDiagnoses": True,
            "noInventedFacts": True,
            "honestAndConstructiveOnImpossible": True,
            "studentTone": "calm, kind, specific, no risk labels, no shame, no false hope",
        },
    }
    return json.dumps(blob, sort_keys=True, separators=(",", ":"))


# ── validators ────────────────────────────────────────────────────────────────────────────────────


class ForecastAdviceNumericConsistencyValidator:
    """Numeric/fact consistency + state-aware contradiction guard for grade advice.

    The AI invents no number outside ``allowedNumbers`` and no peer/diagnosis/unsupported fact; it does
    not contradict the deterministic forecast state; and it includes the state-relevant deterministic
    facts (target + required average for reachable states; the best-reachable grade + honest unreachable
    framing for impossible).
    """

    def validate(self, *, text: str, context: ForecastAdviceValidationContext) -> None:
        lowered = _normalize_text(text)

        for term in (*PEER_TERMS, *ADVICE_PEER_TERMS):
            if term in lowered:
                raise InvalidOutput("grade advice contains a peer comparison", error_code="peer_comparison")
        for term in (*DIAGNOSIS_TERMS, *ADVICE_DIAGNOSIS_TERMS):
            if term in lowered:
                raise InvalidOutput("grade advice contains diagnosis language", error_code="diagnosis")
        for term in ADVICE_UNSUPPORTED_FACT_TERMS:
            if term in lowered:
                raise InvalidOutput("grade advice contains an unsupported fact", error_code="unsupported_fact")

        allowed = {_normalize_number(token) for token in context.allowed_numbers}
        for token in _advice_numeric_tokens(text):
            if _normalize_number(token) not in allowed:
                raise InvalidOutput(
                    f"grade advice invented numeric token {token!r}",
                    error_code="invented_number",
                )

        self._check_contradiction(text=text, lowered=lowered, context=context)

    def _check_contradiction(
        self,
        *,
        text: str,
        lowered: str,
        context: ForecastAdviceValidationContext,
    ) -> None:
        state = context.forecast_state
        has_reachable = any(phrase in lowered for phrase in REACHABLE_CLAIMS)
        has_unreachable = any(phrase in lowered for phrase in UNREACHABLE_CLAIMS)

        if state == "impossible":
            if has_reachable:
                raise InvalidOutput(
                    "grade advice claims an unreachable target is still reachable",
                    error_code="contradiction",
                )
            if not has_unreachable:
                raise InvalidOutput(
                    "grade advice omits the honest unreachable framing",
                    error_code="contradiction",
                )
            if not _mentions_grade(text, context.best_reachable_letter_grade):
                raise InvalidOutput(
                    "grade advice omits the best reachable grade",
                    error_code="missing_required_fact",
                )
        elif state in {"at_risk", "requires_high_score"}:
            if has_unreachable:
                raise InvalidOutput(
                    "grade advice claims a reachable target is unreachable",
                    error_code="contradiction",
                )
            for term in OVERCLAIM_TERMS:
                if term in lowered:
                    raise InvalidOutput("grade advice overclaims certainty", error_code="contradiction")
            if not _mentions_grade(text, context.target_letter_grade):
                raise InvalidOutput(
                    "grade advice omits the target grade",
                    error_code="missing_required_fact",
                )
            req = context.required_remaining_average_display
            if req is not None and req.lower() not in lowered:
                raise InvalidOutput(
                    "grade advice omits the required remaining average",
                    error_code="missing_required_fact",
                )
        else:
            # on_track / achieved / final_no_remaining: never claim the target is unreachable.
            if has_unreachable:
                raise InvalidOutput(
                    "grade advice claims a reachable target is unreachable",
                    error_code="contradiction",
                )


def validate_forecast_advice(
    advice: GradeForecastAdvice,
    *,
    context: ForecastAdviceValidationContext,
) -> None:
    """Run both validators; any failure rejects the whole AI result (regenerate, then template)."""
    ForecastAdviceNumericConsistencyValidator().validate(text=advice.advice, context=context)
    # Reuse the 11.2 student-copy safety guard unchanged (same banned-idea set) ...
    StudentCopySafetyOutputValidator().validate(text=advice.advice)
    # ... then the 11.6 grade-advice / impossible-case shaming lexicon (layered).
    lowered = _normalize_text(advice.advice)
    for term in ADVICE_BANNED_TERMS:
        if term in lowered:
            raise InvalidOutput("grade advice copy is not safe", error_code="student_copy_safety")


# ── read helpers (mirror recommendations.student_text / provenance) ───────────────────────────────


def advice_text(row: StudentForecastAdvice) -> tuple[str, str]:
    if _has_current_ai(row) and row.ai_text:
        return row.ai_text, "ai"
    return str(row.deterministic_payload["templateAdvice"]), "template"


def _has_current_ai(row: StudentForecastAdvice) -> bool:
    return (
        row.ai_status == "succeeded"
        and row.ai_input_hash == row.input_hash
        and row.ai_prompt_version == ADVICE_PROMPT_VERSION
    )
