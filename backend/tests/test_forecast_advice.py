"""Stage 11.6 grade-forecast advice — deterministic payload, templates, and validator unit tests.

Pure (no DB): constructs ``ForecastResult`` directly and exercises the advice layer. Covers the owner's
test-quality additions: impossible adversarial (#1), per-state negative controls (#2), numeric
exactness with a messy decimal (#3), plus the template-self-validation invariant and hash stability.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.analytics import forecast_advice as fa
from app.domains.progress.forecast import ForecastResult
from app.platform.llm.errors import InvalidOutput
from app.platform.llm.models.forecast_advice import GradeForecastAdvice

MODULE = "Microbiology"


def _forecast(
    state: str,
    *,
    target: str = "A",
    best: str = "B",
    current: str = "C",
    req: str | None = None,
    final: str | None = None,
    target_points: str = "90",
    earned: str = "60",
    remaining: str = "0.4",
) -> ForecastResult:
    return ForecastResult(
        state=state,
        target_letter_grade=target,
        target_points=Decimal(target_points),
        earned_so_far=Decimal(earned),
        remaining_weight=Decimal(remaining),
        min_reachable=Decimal(earned),
        max_reachable=Decimal(earned) + Decimal(remaining) * Decimal("100"),
        current_letter_grade=current,
        best_reachable_letter_grade=best,
        required_remaining_average=(Decimal(req) if req is not None else None),
        final_letter_grade=final,
    )


def _validate(advice_text: str, forecast: ForecastResult, *, module_title: str = MODULE) -> None:
    payload = fa.build_deterministic_payload(forecast, module_title=module_title)
    context = fa.advice_validation_context(payload)
    fa.validate_forecast_advice(GradeForecastAdvice(advice=advice_text), context=context)


# ── req_avg_display rounding (owner #3) ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("87.7777777777777777", "87.8"),  # messy decimal → 1 dp HALF_UP
        ("87.75", "87.8"),  # HALF_UP
        ("87.74", "87.7"),
        ("9E+1", "90"),  # scientific-notation whole number → integer string
        ("90.0", "90"),
        ("87.5", "87.5"),
        ("70", "70"),
    ],
)
def test_req_avg_display_rounding(raw: str, expected: str) -> None:
    assert fa.req_avg_display(Decimal(raw)) == expected


def test_req_avg_display_none() -> None:
    assert fa.req_avg_display(None) is None


# ── template self-validation invariant: EVERY template passes BOTH validators ──────────────────────


@pytest.mark.parametrize(
    "forecast",
    [
        _forecast("at_risk", req="78"),
        _forecast("at_risk", req="87.7777777777777777"),  # messy decimal
        _forecast("requires_high_score", req="9E+1"),  # scientific-notation whole number
        _forecast("requires_high_score", req="92.5"),
        _forecast("impossible", req="117.5", target="A", best="C"),  # reqAvg > 100, never cited
        _forecast("on_track", req="55"),
        _forecast("achieved", req="0"),
        _forecast("final_no_remaining", final="B", remaining="0"),
    ],
)
def test_template_passes_both_validators_every_state(forecast: ForecastResult) -> None:
    payload = fa.build_deterministic_payload(forecast, module_title=MODULE)
    template = payload["templateAdvice"]
    # The template is the immediate render AND the fallback — it MUST pass both validators by
    # construction, or there is no safe output.
    _validate(template, forecast)


def test_template_self_validates_with_digit_bearing_module_title() -> None:
    # A module title containing a number ("Biology 101") must not trip the numeric validator — the
    # allowed set is derived from the rendered template, so its own digits are allowed.
    forecast = _forecast("at_risk", req="78")
    payload = fa.build_deterministic_payload(forecast, module_title="Biology 101")
    assert "101" in payload["allowedNumbers"]
    _validate(payload["templateAdvice"], forecast, module_title="Biology 101")


def test_impossible_template_is_honest_and_constructive() -> None:
    forecast = _forecast("impossible", target="A", best="B", req="117.5")
    payload = fa.build_deterministic_payload(forecast, module_title=MODULE)
    template = payload["templateAdvice"].lower()
    assert "b" in template  # best grade present (constructive)
    assert "more than the remaining" in template  # honest unreachable framing
    # No false hope, no shaming, no banned phrase, no ">100% needed" quote.
    for banned in ("give up", "too late", "hopeless", "fallen", "117", "failing", "at risk"):
        assert banned not in template
    assert payload["allowedNumbers"] == []  # impossible cites no number


# ── numeric exactness (owner #3) ──────────────────────────────────────────────────────────────────


def test_numeric_exactness_messy_decimal() -> None:
    forecast = _forecast("requires_high_score", req="87.7777777777777777")
    payload = fa.build_deterministic_payload(forecast, module_title=MODULE)
    template = payload["templateAdvice"]
    assert "87.8%" in template
    assert "percent" not in template.lower()  # always the "%" symbol, never the word
    assert "87.7777" not in template  # the raw un-rounded value never appears
    assert "87.8" in payload["allowedNumbers"]
    assert "87.8%" in payload["allowedNumbers"]

    # An AI output citing the raw un-rounded number is rejected.
    with pytest.raises(InvalidOutput) as exc:
        _validate(
            "A is within reach — aim for about 87.7777777777777777% on what's left.",
            forecast,
        )
    assert exc.value.error_code == "invented_number"

    # The correctly-rounded AI output passes.
    _validate("A is within reach — aim for about 87.8% on what's left.", forecast)


# ── per-state NEGATIVE CONTROLS: valid AI MUST PASS and render (owner #2) ─────────────────────────


def test_negative_control_at_risk_passes() -> None:
    forecast = _forecast("at_risk", req="78", target="A")
    _validate(
        "A is within reach — aiming for about 78% on the work that's left should get you there, and a "
        "focused review of Microbiology is a great next step.",
        forecast,
    )


def test_negative_control_requires_high_score_passes() -> None:
    forecast = _forecast("requires_high_score", req="92.5", target="A")
    _validate(
        "A is still on the table — it will take about 92.5% on what's left, so a steady, focused plan "
        "for Microbiology is your best next step.",
        forecast,
    )


def test_negative_control_impossible_passes() -> None:
    forecast = _forecast("impossible", target="A", best="B", req="117.5")
    _validate(
        "Reaching A is not possible from your current scores, but B is a strong goal still open to you "
        "— putting your focus there is well worth it, and you can revisit your target whenever you like.",
        forecast,
    )


# ── adversarial: MUST FAIL (incl. owner #1 impossible) ────────────────────────────────────────────


def test_impossible_false_hope_is_rejected() -> None:
    # Owner #1: a crafted "you can still reach A" on an impossible forecast must be rejected so the
    # honest template is what ships.
    forecast = _forecast("impossible", target="A", best="B", req="117.5")
    with pytest.raises(InvalidOutput) as exc:
        _validate("Don't worry — you can still reach A if you work hard! B is also fine.", forecast)
    assert exc.value.error_code in {"contradiction", "student_copy_safety"}


def test_impossible_missing_best_grade_is_rejected() -> None:
    forecast = _forecast("impossible", target="A", best="B", req="117.5")
    with pytest.raises(InvalidOutput) as exc:
        _validate("Reaching A is not possible from your current scores. Keep studying steadily.", forecast)
    assert exc.value.error_code == "missing_required_fact"


def test_impossible_missing_unreachable_framing_is_rejected() -> None:
    forecast = _forecast("impossible", target="A", best="B", req="117.5")
    with pytest.raises(InvalidOutput) as exc:
        _validate("B is a strong goal worth aiming for — put your focus there.", forecast)
    assert exc.value.error_code == "contradiction"


@pytest.mark.parametrize(
    "text",
    [
        "You've fallen too far to reach your target. It's too late now.",  # shaming/defeatist
        "There's no way to get there — it's hopeless.",
        "You should just give up on this one.",
    ],
)
def test_impossible_shaming_is_rejected(text: str) -> None:
    forecast = _forecast("impossible", target="A", best="B", req="117.5")
    with pytest.raises(InvalidOutput) as exc:
        _validate(text, forecast)
    assert exc.value.error_code in {"student_copy_safety", "contradiction"}


def test_at_risk_pessimism_inversion_is_rejected() -> None:
    forecast = _forecast("at_risk", req="78", target="A")
    with pytest.raises(InvalidOutput) as exc:
        _validate("Unfortunately A is out of reach now. Aim for about 78%.", forecast)
    assert exc.value.error_code == "contradiction"


def test_at_risk_overclaim_is_rejected() -> None:
    forecast = _forecast("at_risk", req="78", target="A")
    with pytest.raises(InvalidOutput) as exc:
        _validate("A is within reach — you are guaranteed to get there with 78% on what's left.", forecast)
    assert exc.value.error_code == "contradiction"


@pytest.mark.parametrize(
    "text,code",
    [
        ("A is within reach — aim for about 95% on what's left.", "invented_number"),  # wrong number
        ("A is within reach — score twenty-five more and you're set.", "invented_number"),  # hyphen word
        ("You're behind the average student — aim for 78%.", "peer_comparison"),
        ("You may be burning out — aim for 78% on what's left to reach A.", "diagnosis"),
        ("Ask your lecturer for extra credit to reach A with 78%.", "unsupported_fact"),
    ],
)
def test_at_risk_adversarial_rejected(text: str, code: str) -> None:
    forecast = _forecast("at_risk", req="78", target="A")
    with pytest.raises(InvalidOutput) as exc:
        _validate(text, forecast)
    assert exc.value.error_code == code


def test_student_safety_banned_terms_rejected() -> None:
    forecast = _forecast("at_risk", req="78", target="A")
    with pytest.raises(InvalidOutput) as exc:
        _validate("You are failing and at risk — aim for 78% to reach A.", forecast)
    assert exc.value.error_code == "student_copy_safety"


# ── input hash: stable + anti-flap + regenerates on change ────────────────────────────────────────


def test_input_hash_stable_for_identical_forecast() -> None:
    f1 = _forecast("at_risk", req="78", earned="60.00")
    f2 = _forecast("at_risk", req="78", earned="60.00")
    h1 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f1, module_title=MODULE))
    h2 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f2, module_title=MODULE))
    assert h1 == h2


def test_input_hash_does_not_flap_on_sub_rounding_score_change() -> None:
    # Two forecasts with the same state + same 1-dp required average must hash identically even if the
    # raw earned/remaining differ below the display rounding (rule-15: no needless regeneration).
    f1 = _forecast("at_risk", req="78.01", earned="60.0")
    f2 = _forecast("at_risk", req="78.02", earned="61.0")
    h1 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f1, module_title=MODULE))
    h2 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f2, module_title=MODULE))
    assert h1 == h2  # both round to 78%


def test_input_hash_changes_on_state_change() -> None:
    f1 = _forecast("at_risk", req="78")
    f2 = _forecast("requires_high_score", req="92")
    h1 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f1, module_title=MODULE))
    h2 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f2, module_title=MODULE))
    assert h1 != h2


def test_input_hash_changes_on_required_average_change() -> None:
    f1 = _forecast("at_risk", req="78")
    f2 = _forecast("at_risk", req="83")
    h1 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f1, module_title=MODULE))
    h2 = fa.forecast_advice_input_hash(fa.build_deterministic_payload(f2, module_title=MODULE))
    assert h1 != h2
