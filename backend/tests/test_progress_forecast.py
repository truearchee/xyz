from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.progress.forecast import (
    ForecastError,
    ForecastInput,
    GradeBoundaryInput,
    GradeComponentInput,
    calculate_forecast,
)


BOUNDARIES = (
    GradeBoundaryInput("A", Decimal("93")),
    GradeBoundaryInput("A-", Decimal("87")),
    GradeBoundaryInput("B+", Decimal("84")),
    GradeBoundaryInput("B", Decimal("80")),
    GradeBoundaryInput("C", Decimal("70")),
    GradeBoundaryInput("F", Decimal("0")),
)


def _components(earned: Decimal, remaining: Decimal) -> tuple[GradeComponentInput, ...]:
    graded_weight = Decimal("1") - remaining
    if remaining == Decimal("0"):
        return (GradeComponentInput("graded", Decimal("1"), earned),)
    return (
        GradeComponentInput("graded", graded_weight, earned / graded_weight),
        GradeComponentInput("remaining", remaining, None),
    )


@pytest.mark.parametrize(
    ("target", "earned", "remaining", "state"),
    [
        ("A-", Decimal("80.5"), Decimal("0.1"), "on_track"),
        ("A", Decimal("85"), Decimal("0.1"), "at_risk"),
        ("A", Decimal("74"), Decimal("0.2"), "requires_high_score"),
        ("A", Decimal("72"), Decimal("0.2"), "impossible"),
        ("B", Decimal("82"), Decimal("0.1"), "achieved"),
        ("A", Decimal("85"), Decimal("0"), "final_no_remaining"),
    ],
)
def test_forecast_returns_each_state(target, earned, remaining, state):
    result = calculate_forecast(
        ForecastInput(boundaries=BOUNDARIES, components=_components(earned, remaining), target_letter_grade=target)
    )
    assert result.state == state


def test_impossible_reports_best_reachable_letter_and_required_over_100():
    result = calculate_forecast(
        ForecastInput(
            boundaries=BOUNDARIES,
            components=_components(Decimal("66"), Decimal("0.2")),
            target_letter_grade="A",
        )
    )
    assert result.state == "impossible"
    assert result.best_reachable_letter_grade == "B+"
    assert result.required_remaining_average is not None
    assert result.required_remaining_average > Decimal("100")


def test_final_no_remaining_never_reports_required_remaining():
    result = calculate_forecast(
        ForecastInput(
            boundaries=BOUNDARIES,
            components=(GradeComponentInput("all", Decimal("1"), Decimal("85")),),
            target_letter_grade="A",
        )
    )
    assert result.state == "final_no_remaining"
    assert result.final_letter_grade == "B+"
    assert result.required_remaining_average is None


def test_decimal_boundaries_are_inclusive():
    result = calculate_forecast(
        ForecastInput(
            boundaries=BOUNDARIES,
            components=_components(Decimal("80"), Decimal("0.1")),
            target_letter_grade="A-",
        )
    )
    assert result.required_remaining_average == Decimal("70")
    assert result.state == "on_track"


def test_invalid_component_weights_are_refused():
    with pytest.raises(ForecastError, match="sum"):
        calculate_forecast(
            ForecastInput(
                boundaries=BOUNDARIES,
                components=(GradeComponentInput("bad", Decimal("0.9"), Decimal("90")),),
                target_letter_grade="A",
            )
        )


def test_unknown_target_is_refused():
    with pytest.raises(ForecastError, match="unknown target"):
        calculate_forecast(
            ForecastInput(
                boundaries=BOUNDARIES,
                components=_components(Decimal("80"), Decimal("0.1")),
                target_letter_grade="Z",
            )
        )
