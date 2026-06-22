from __future__ import annotations

from datetime import date, datetime
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


class TriggerAgentRunRequest(CamelModel):
    trigger_type: str = "manual_admin"
    scope_type: str = "all"
    scope_id: UUID | None = None
    scheduled_for: datetime | None = None


class AgentRunRead(CamelModel):
    id: UUID
    trigger_type: str
    scope_type: str
    scope_id: UUID | None
    scheduled_for: datetime
    triggered_by_user_id: UUID | None
    algorithm_version: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    snapshot_count: int
    recommendation_count: int
    plan_count: int
    idempotency_key: str
    failure_message_sanitized: str | None
    created_at: datetime
    updated_at: datetime


class AssessmentAgentRunRead(CamelModel):
    id: UUID
    status: str
    scope_type: str
    scope_id: UUID | None
    scheduled_for: datetime
    completed_at: datetime | None
    snapshot_count: int
    recommendation_count: int


class AssessmentDistractorInsightRead(CamelModel):
    option_key: str
    option_text: str
    selected_count: int
    selected_rate_percent: Decimal | None


class AssessmentQuestionInsightRead(CamelModel):
    question_key: str
    question_text: str
    answer_count: int
    correct_count: int
    incorrect_count: int
    correct_rate_percent: Decimal | None
    small_cohort: bool
    small_cohort_message: str | None
    distractors: list[AssessmentDistractorInsightRead]


class AssessmentTopicMasteryRowRead(CamelModel):
    source_section_id: UUID
    topic_title: str
    week_number: int | None
    answer_count: int
    correct_count: int
    mastery_percent: Decimal | None
    small_cohort: bool
    small_cohort_message: str | None


class AssessmentTopicMasteryRead(CamelModel):
    available: bool
    unavailable_reason: str | None
    unmapped_answer_count: int
    unmapped_message: str | None
    rows: list[AssessmentTopicMasteryRowRead]


class LecturerAssessmentInsightsRead(CamelModel):
    module_id: UUID
    module_title: str
    latest_agent_run: AssessmentAgentRunRead | None
    small_cohort_threshold: int
    small_cohort_message: str
    questions: list[AssessmentQuestionInsightRead]
    most_missed_questions: list[AssessmentQuestionInsightRead]
    topic_mastery: AssessmentTopicMasteryRead


class RiskReasonRead(CamelModel):
    code: str
    severity: str
    metric_keys: list[str]
    lecturer_text: str
    student_text: str
    supporting_metrics: dict[str, Decimal | int | str | None]


class StudentRiskReasonRead(CamelModel):
    code: str
    student_text: str


class StudentRiskRead(CamelModel):
    student_id: UUID
    module_id: UUID
    risk_reasons: list[StudentRiskReasonRead]
    algorithm_version: str
    input_hash: str
    source_cutoff_at: datetime
    computed_at: datetime


class LecturerRosterRiskRow(CamelModel):
    student_id: UUID
    student_name: str
    student_email: str
    module_id: UUID
    risk_tier: str
    risk_label: str
    risk_reasons: list[RiskReasonRead]
    algorithm_version: str
    input_hash: str
    source_cutoff_at: datetime
    computed_at: datetime


class LecturerRosterRiskRead(CamelModel):
    module_id: UUID
    module_title: str
    needs_support_count: int
    rows: list[LecturerRosterRiskRow]


class AIProvenanceRead(CamelModel):
    model_id: str
    prompt_version: str
    input_hash: str
    generated_at: datetime


class RecommendationRead(CamelModel):
    id: UUID
    reason_code: str
    target_key: str
    target_label: str
    lecturer_state: str
    student_state: str
    ai_status: str
    lecturer_draft_text: str
    lecturer_draft_source: str
    student_nudge_text: str
    student_nudge_source: str
    student_next_step: str
    deterministic_payload: dict
    ai_provenance: AIProvenanceRead | None = None
    created_at: datetime
    updated_at: datetime


class LecturerStudentRecommendationsRead(CamelModel):
    student_id: UUID
    student_name: str
    student_email: str
    module_id: UUID
    module_title: str
    risk_reasons: list[RiskReasonRead]
    recommendations: list[RecommendationRead]


class RecommendationActionRead(CamelModel):
    id: UUID
    lecturer_state: str
    student_state: str


class StudentRecommendationRead(CamelModel):
    id: UUID
    module_id: UUID
    module_title: str
    target_label: str
    text: str
    next_step: str
    source: str
    dismissible: bool = True


class StudentRecommendationListRead(CamelModel):
    recommendations: list[StudentRecommendationRead]


class StudentRecommendationBannerRead(CamelModel):
    recommendation: StudentRecommendationRead | None = None


class ForecastAdviceRead(CamelModel):
    module_id: UUID
    forecast_state: str
    text: str
    source: str  # "ai" | "template"
    ai_status: str  # not_requested | queued | succeeded | failed | template_fallback | none


class StudentAvailabilityUpdate(CamelModel):
    study_days: list[str]
    preferred_window: str
    max_study_minutes_per_day: int


class StudentAvailabilityRead(CamelModel):
    module_id: UUID
    study_days: list[str]
    preferred_window: str
    max_study_minutes_per_day: int
    availability_version: int
    updated_at: datetime | None = None


class WorkloadPlanItemRead(CamelModel):
    id: UUID
    task_key: str
    source_section_id: UUID | None
    scheduled_date: date | None
    window: str | None
    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    label: str
    estimate_minutes: int
    reason: str
    source_reason_code: str | None
    source_metadata: dict
    tight: bool
    tight_message: str | None
    sort_index: int


class WorkloadPlanRead(CamelModel):
    id: UUID
    module_id: UUID
    algorithm_version: str
    input_hash: str
    availability_version: int
    source_cutoff_at: datetime
    is_active: bool
    superseded_at: datetime | None
    provenance: dict
    created_at: datetime
    updated_at: datetime
    items: list[WorkloadPlanItemRead]
