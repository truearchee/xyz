from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class TargetGradeRequest(CamelModel):
    target_letter_grade: str


class ForecastRead(CamelModel):
    state: str
    label: str
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


class TrendPointRead(CamelModel):
    week_number: int
    snapshot_date: date
    standing_points: Decimal


class TopicMasteryRead(CamelModel):
    section_id: UUID
    title: str
    section_type: str
    mastery_percentage: Decimal
    status_label: str


class BenchmarkRead(CamelModel):
    metric: str
    student_average: Decimal | None
    class_average: Decimal | None
    cohort_size: int
    suppressed: bool
    suppression_min_cohort: int


class ProgressModuleSummary(CamelModel):
    module_id: UUID
    title: str
    current_standing: Decimal | None
    current_letter_grade: str | None
    target_letter_grade: str | None
    forecast_state: str | None
    forecast_label: str | None
    latest_week_number: int | None
    latest_standing_points: Decimal | None


class ProgressDashboardRead(CamelModel):
    modules: list[ProgressModuleSummary]


class ProgressModuleDetail(CamelModel):
    module_id: UUID
    title: str
    current_standing: Decimal | None
    current_letter_grade: str | None
    target_letter_grade: str | None
    available_target_grades: list[str]
    forecast: ForecastRead | None
    trend: list[TrendPointRead]
    topics: list[TopicMasteryRead]
    benchmark: BenchmarkRead | None


FORECAST_LABELS = {
    "final_no_remaining": "Final grade",
    "achieved": "Achieved",
    "impossible": "Impossible",
    "on_track": "On track",
    "at_risk": "At risk",
    "requires_high_score": "Requires high score",
}
