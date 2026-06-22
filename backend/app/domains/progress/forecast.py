from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


HUNDRED = Decimal("100")
ZERO = Decimal("0")
WEIGHT_TOLERANCE = Decimal("0.0001")


@dataclass(frozen=True)
class GradeBoundaryInput:
    letter_grade: str
    lower_bound: Decimal


@dataclass(frozen=True)
class GradeComponentInput:
    id: str
    weight: Decimal
    percentage_score: Decimal | None


@dataclass(frozen=True)
class ForecastInput:
    boundaries: tuple[GradeBoundaryInput, ...]
    components: tuple[GradeComponentInput, ...]
    target_letter_grade: str
    on_track_max: Decimal = Decimal("70")
    at_risk_max: Decimal = Decimal("85")


@dataclass(frozen=True)
class ForecastResult:
    state: str
    target_letter_grade: str
    target_points: Decimal
    earned_so_far: Decimal
    remaining_weight: Decimal
    min_reachable: Decimal
    max_reachable: Decimal
    current_letter_grade: str
    best_reachable_letter_grade: str
    required_remaining_average: Decimal | None
    final_letter_grade: str | None = None


class ForecastError(ValueError):
    pass


def build_forecast_input(
    *,
    boundaries: Iterable[tuple[str, Decimal]],
    components: Iterable[tuple[Any, Decimal, Decimal | None]],
    target_letter_grade: str,
    on_track_max: Decimal = Decimal("70"),
    at_risk_max: Decimal = Decimal("85"),
) -> ForecastInput:
    """Assemble a ``ForecastInput`` from read-model rows — the single assembly path.

    The progress dashboard (Stage 9) and the analytics agent (Stage 11) compute the SAME forecast from
    the same data by routing through this one helper (zero drift). ``boundaries`` are
    ``(letter_grade, lower_bound)`` pairs; ``components`` are ``(id, weight, percentage_score)`` triples.
    The grade math itself lives ONLY in :func:`calculate_forecast`; this function does no arithmetic.
    """
    return ForecastInput(
        boundaries=tuple(
            GradeBoundaryInput(letter_grade=letter, lower_bound=lower)
            for letter, lower in boundaries
        ),
        components=tuple(
            GradeComponentInput(
                id=str(component_id),
                weight=weight,
                percentage_score=percentage_score,
            )
            for component_id, weight, percentage_score in components
        ),
        target_letter_grade=target_letter_grade,
        on_track_max=on_track_max,
        at_risk_max=at_risk_max,
    )


def calculate_forecast(input_: ForecastInput) -> ForecastResult:
    boundaries = _sorted_boundaries(input_.boundaries)
    target = _boundary_for_letter(boundaries, input_.target_letter_grade)
    _validate_components(input_.components)
    _validate_thresholds(input_.on_track_max, input_.at_risk_max)

    earned_so_far = sum(
        (component.percentage_score or ZERO) * component.weight
        for component in input_.components
        if component.percentage_score is not None
    )
    remaining_weight = sum(
        component.weight for component in input_.components if component.percentage_score is None
    )
    min_reachable = earned_so_far
    max_reachable = earned_so_far + remaining_weight * HUNDRED
    current_letter = _letter_for_points(boundaries, earned_so_far)
    best_reachable = _letter_for_points(boundaries, max_reachable)

    if remaining_weight == ZERO:
        return ForecastResult(
            state="final_no_remaining",
            target_letter_grade=target.letter_grade,
            target_points=target.lower_bound,
            earned_so_far=earned_so_far,
            remaining_weight=remaining_weight,
            min_reachable=min_reachable,
            max_reachable=max_reachable,
            current_letter_grade=current_letter,
            best_reachable_letter_grade=best_reachable,
            required_remaining_average=None,
            final_letter_grade=_letter_for_points(boundaries, earned_so_far),
        )

    if min_reachable >= target.lower_bound:
        return ForecastResult(
            state="achieved",
            target_letter_grade=target.letter_grade,
            target_points=target.lower_bound,
            earned_so_far=earned_so_far,
            remaining_weight=remaining_weight,
            min_reachable=min_reachable,
            max_reachable=max_reachable,
            current_letter_grade=current_letter,
            best_reachable_letter_grade=best_reachable,
            required_remaining_average=ZERO,
        )

    if max_reachable < target.lower_bound:
        required = (target.lower_bound - earned_so_far) / remaining_weight
        return ForecastResult(
            state="impossible",
            target_letter_grade=target.letter_grade,
            target_points=target.lower_bound,
            earned_so_far=earned_so_far,
            remaining_weight=remaining_weight,
            min_reachable=min_reachable,
            max_reachable=max_reachable,
            current_letter_grade=current_letter,
            best_reachable_letter_grade=best_reachable,
            required_remaining_average=required,
        )

    required = (target.lower_bound - earned_so_far) / remaining_weight
    if required <= input_.on_track_max:
        state = "on_track"
    elif required <= input_.at_risk_max:
        state = "at_risk"
    else:
        state = "requires_high_score"

    return ForecastResult(
        state=state,
        target_letter_grade=target.letter_grade,
        target_points=target.lower_bound,
        earned_so_far=earned_so_far,
        remaining_weight=remaining_weight,
        min_reachable=min_reachable,
        max_reachable=max_reachable,
        current_letter_grade=current_letter,
        best_reachable_letter_grade=best_reachable,
        required_remaining_average=required,
    )


def _sorted_boundaries(boundaries: tuple[GradeBoundaryInput, ...]) -> tuple[GradeBoundaryInput, ...]:
    if not boundaries:
        raise ForecastError("grade boundaries are required")
    ordered = tuple(sorted(boundaries, key=lambda boundary: boundary.lower_bound, reverse=True))
    if ordered[-1].lower_bound != ZERO:
        raise ForecastError("lowest grade boundary must start at 0")
    return ordered


def _boundary_for_letter(
    boundaries: tuple[GradeBoundaryInput, ...],
    letter_grade: str,
) -> GradeBoundaryInput:
    for boundary in boundaries:
        if boundary.letter_grade == letter_grade:
            return boundary
    raise ForecastError(f"unknown target grade: {letter_grade}")


def _letter_for_points(boundaries: tuple[GradeBoundaryInput, ...], points: Decimal) -> str:
    for boundary in boundaries:
        if points >= boundary.lower_bound:
            return boundary.letter_grade
    return boundaries[-1].letter_grade


def _validate_components(components: tuple[GradeComponentInput, ...]) -> None:
    if not components:
        raise ForecastError("grade components are required")
    weight_sum = sum(component.weight for component in components)
    if abs(weight_sum - Decimal("1.0000")) > WEIGHT_TOLERANCE:
        raise ForecastError("grade component weights must sum to 1.0000")
    for component in components:
        if component.weight <= ZERO or component.weight > Decimal("1"):
            raise ForecastError("component weight must be between 0 and 1")
        if component.percentage_score is not None and not ZERO <= component.percentage_score <= HUNDRED:
            raise ForecastError("percentage score must be between 0 and 100")


def _validate_thresholds(on_track_max: Decimal, at_risk_max: Decimal) -> None:
    if on_track_max < ZERO or at_risk_max < on_track_max or at_risk_max > HUNDRED:
        raise ForecastError("invalid forecast thresholds")
