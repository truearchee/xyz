from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domains.analytics.risk import (
    RISK_LABELS,
    RiskConfig,
    RiskMetrics,
    RiskResult,
    classify_risk,
    reason_to_dict,
)
from app.domains.analytics.calendar_export import (
    CalendarDeadline,
    CalendarExport,
    CalendarPlanItem,
    build_workload_calendar,
)
from app.domains.analytics import forecast_advice, recommendations
from app.domains.analytics.workload import (
    AvailabilityInput,
    DeadlineInput,
    RiskSnapshotInput,
    WorkloadConfig,
    WorkloadInputs,
    build_workload_plan,
    validate_availability,
)
from app.domains.analytics.schemas import (
    AIProvenanceRead,
    AgentRunRead,
    AssessmentAgentRunRead,
    AssessmentDistractorInsightRead,
    AssessmentQuestionInsightRead,
    AssessmentTopicMasteryRead,
    AssessmentTopicMasteryRowRead,
    ForecastAdviceRead,
    LecturerRosterRiskRead,
    LecturerAssessmentInsightsRead,
    LecturerRosterRiskRow,
    LecturerStudentRecommendationsRead,
    RecommendationActionRead,
    RecommendationRead,
    RiskReasonRead,
    StudentRecommendationBannerRead,
    StudentRecommendationListRead,
    StudentRecommendationRead,
    StudentRiskReasonRead,
    StudentRiskRead,
    StudentAvailabilityRead,
    StudentAvailabilityUpdate,
    TriggerAgentRunRequest,
    WorkloadPlanItemRead,
    WorkloadPlanRead,
)
from app.domains.progress.forecast import (
    ForecastResult,
    build_forecast_input,
    calculate_forecast,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.config import settings
from app.platform.db.models import (
    AgentRun,
    CourseModule,
    ModuleSection,
    Recommendation,
    StudentAvailability,
    StudentForecastAdvice,
    StudentRiskSnapshot,
    WorkloadPlan,
    WorkloadPlanItem,
)
from app.platform.query import analytics_read
from app.platform.rate_limit import enforce_fixed_window_rate_limit
from app.workers.queues import (
    enqueue_generate_forecast_advice,
    enqueue_generate_recommendation_copy,
)


def risk_config() -> RiskConfig:
    return RiskConfig(
        algorithm_version=settings.RISK_ALGORITHM_VERSION,
        recent_quiz_window=settings.RISK_RECENT_QUIZ_WINDOW,
        missed_quiz_watch_count=settings.RISK_MISSED_QUIZ_WATCH_COUNT,
        missed_quiz_needs_support_count=settings.RISK_MISSED_QUIZ_NEEDS_SUPPORT_COUNT,
        low_quiz_watch_average=Decimal(settings.RISK_LOW_QUIZ_WATCH_AVERAGE),
        low_quiz_needs_support_average=Decimal(settings.RISK_LOW_QUIZ_NEEDS_SUPPORT_AVERAGE),
        inactivity_watch_days=settings.RISK_INACTIVITY_WATCH_DAYS,
        inactivity_needs_support_days=settings.RISK_INACTIVITY_NEEDS_SUPPORT_DAYS,
        topic_deadline_watch_days=settings.RISK_TOPIC_DEADLINE_WATCH_DAYS,
        topic_deadline_needs_support_hours=settings.RISK_TOPIC_DEADLINE_NEEDS_SUPPORT_HOURS,
    )


def workload_config() -> WorkloadConfig:
    return WorkloadConfig(
        algorithm_version=settings.WORKLOAD_PLAN_ALGORITHM_VERSION,
        daily_overflow_percent=settings.WORKLOAD_PLAN_DAILY_OVERFLOW_PERCENT,
        deadline_estimate_minutes=settings.WORKLOAD_PLAN_DEADLINE_ESTIMATE_MINUTES,
        gap_estimate_minutes=settings.WORKLOAD_PLAN_GAP_ESTIMATE_MINUTES,
        window_morning_start=settings.WORKLOAD_PLAN_WINDOW_MORNING_START,
        window_morning_end=settings.WORKLOAD_PLAN_WINDOW_MORNING_END,
        window_afternoon_start=settings.WORKLOAD_PLAN_WINDOW_AFTERNOON_START,
        window_afternoon_end=settings.WORKLOAD_PLAN_WINDOW_AFTERNOON_END,
        window_evening_start=settings.WORKLOAD_PLAN_WINDOW_EVENING_START,
        window_evening_end=settings.WORKLOAD_PLAN_WINDOW_EVENING_END,
        legacy_fallback_horizon_days=settings.WORKLOAD_PLAN_LEGACY_FALLBACK_HORIZON_DAYS,
        min_availability_minutes=settings.WORKLOAD_PLAN_MIN_AVAILABILITY_MINUTES,
        max_availability_minutes=settings.WORKLOAD_PLAN_MAX_AVAILABILITY_MINUTES,
    )


async def trigger_manual_run(
    db: AsyncSession,
    *,
    payload: TriggerAgentRunRequest,
    current_user: CurrentUserContext,
) -> tuple[AgentRunRead, bool]:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    await enforce_fixed_window_rate_limit(
        key=f"agent-run:manual-trigger:{current_user.user_id}",
        limit=settings.AGENT_RUN_MANUAL_TRIGGER_RATE_LIMIT,
        window_seconds=settings.AGENT_RUN_MANUAL_TRIGGER_RATE_WINDOW_SECONDS,
    )
    if payload.trigger_type != "manual_admin":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported trigger type")
    if payload.scope_type not in {"all", "module", "student"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported scope type")
    if payload.scope_type == "all" and payload.scope_id is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scopeId must be empty for all")
    if payload.scope_type != "all" and payload.scope_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="scopeId is required")

    scheduled_for = payload.scheduled_for or default_manual_scheduled_for()
    run, created = await get_or_create_agent_run(
        db,
        trigger_type="manual_admin",
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        scheduled_for=scheduled_for,
        triggered_by_user_id=current_user.user_id,
        algorithm_version=settings.RISK_ALGORITHM_VERSION,
    )
    await db.commit()
    return AgentRunRead.model_validate(run), created


async def get_run(db: AsyncSession, *, run_id: UUID, current_user: CurrentUserContext) -> AgentRunRead:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return AgentRunRead.model_validate(run)


async def get_or_create_agent_run(
    db: AsyncSession,
    *,
    trigger_type: str,
    scope_type: str,
    scope_id: UUID | None,
    scheduled_for: datetime,
    triggered_by_user_id: UUID | None,
    algorithm_version: str,
) -> tuple[AgentRun, bool]:
    idempotency_key = agent_run_idempotency_key(
        trigger_type=trigger_type,
        scope_type=scope_type,
        scope_id=scope_id,
        scheduled_for=scheduled_for,
        algorithm_version=algorithm_version,
    )
    stmt = (
        insert(AgentRun)
        .values(
            trigger_type=trigger_type,
            scope_type=scope_type,
            scope_id=scope_id,
            scheduled_for=scheduled_for,
            triggered_by_user_id=triggered_by_user_id,
            algorithm_version=algorithm_version,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=[AgentRun.idempotency_key])
        .returning(AgentRun)
    )
    inserted = (await db.execute(stmt)).scalar_one_or_none()
    if inserted is not None:
        return inserted, True
    existing = await db.scalar(select(AgentRun).where(AgentRun.idempotency_key == idempotency_key))
    if existing is None:  # pragma: no cover - defensive
        raise RuntimeError("AgentRun upsert neither inserted nor found an existing row")
    return existing, False


async def run_agent_run(db: AsyncSession, *, run_id: UUID) -> AgentRunRead:
    run = await db.get(AgentRun, run_id, with_for_update=True)
    if run is None:
        raise RuntimeError(f"AgentRun {run_id} not found")
    if run.status == "completed":
        return AgentRunRead.model_validate(run)
    if run.status == "running":
        return AgentRunRead.model_validate(run)

    now = datetime.now(UTC)
    run.status = "running"
    run.started_at = now
    run.failure_message_sanitized = None
    await db.flush()

    try:
        results = await compute_risk_for_scope(
            db,
            scope_type=run.scope_type,
            scope_id=run.scope_id,
            source_cutoff_at=run.scheduled_for,
        )
        for subject, result in results:
            db.add(
                StudentRiskSnapshot(
                    agent_run_id=run.id,
                    student_id=subject.student_id,
                    module_id=subject.module_id,
                    risk_tier=result.risk_tier,
                    risk_reasons=[reason_to_dict(reason) for reason in result.reasons],
                    algorithm_version=result.algorithm_version,
                    input_hash=result.input_hash,
                    source_cutoff_at=result.source_cutoff_at,
                    computed_at=result.computed_at,
                )
            )
        await db.flush()
        recommendation_count = await recommendations.sync_recommendations_for_run(db, run_id=run.id)
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.snapshot_count = len(results)
        run.recommendation_count = recommendation_count
        run.plan_count = 0
        run.updated_at = datetime.now(UTC)
        await _prune_old_snapshots(db)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        failed_run = await db.get(AgentRun, run_id, with_for_update=True)
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.completed_at = datetime.now(UTC)
            failed_run.failure_message_sanitized = _sanitize_failure(exc)
            failed_run.updated_at = datetime.now(UTC)
        await db.commit()
        raise

    refreshed = await db.get(AgentRun, run_id)
    if refreshed is None:  # pragma: no cover - defensive
        raise RuntimeError(f"AgentRun {run_id} disappeared")
    return AgentRunRead.model_validate(refreshed)


async def get_lecturer_roster_risk(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> LecturerRosterRiskRead:
    if current_user.role != "lecturer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.lecturer_has_module(db, lecturer_id=current_user.user_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    rows = await _current_risk_rows(db, module_id=module_id)
    module_title = rows[0][0].module_title if rows else ""
    rendered = [
        LecturerRosterRiskRow(
            student_id=subject.student_id,
            student_name=subject.student_name,
            student_email=subject.student_email,
            module_id=subject.module_id,
            risk_tier=result.risk_tier,
            risk_label=RISK_LABELS[result.risk_tier],
            risk_reasons=[_reason_read(reason_to_dict(reason)) for reason in result.reasons],
            algorithm_version=result.algorithm_version,
            input_hash=result.input_hash,
            source_cutoff_at=result.source_cutoff_at,
            computed_at=result.computed_at,
        )
        for subject, result in rows
    ]
    rendered.sort(key=lambda row: (_risk_sort(row.risk_tier), row.student_name.lower(), str(row.student_id)))
    return LecturerRosterRiskRead(
        module_id=module_id,
        module_title=module_title,
        needs_support_count=sum(1 for row in rendered if row.risk_tier == "needs_support"),
        rows=rendered,
    )


async def get_lecturer_assessment_insights(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> LecturerAssessmentInsightsRead:
    if current_user.role != "lecturer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.lecturer_has_module(db, lecturer_id=current_user.user_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    insights = await analytics_read.get_assessment_insights(db, module_id=module_id)
    if insights is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    return _assessment_insights_read(insights)


async def get_student_risk(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> StudentRiskRead:
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.student_has_module(db, student_id=current_user.user_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    rows = await _current_risk_rows(db, module_id=module_id, student_id=current_user.user_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    subject, result = rows[0]
    return StudentRiskRead(
        student_id=subject.student_id,
        module_id=subject.module_id,
        risk_reasons=[_student_reason_read(reason_to_dict(reason)) for reason in result.reasons],
        algorithm_version=result.algorithm_version,
        input_hash=result.input_hash,
        source_cutoff_at=result.source_cutoff_at,
        computed_at=result.computed_at,
    )


async def get_student_workload_availability(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> StudentAvailabilityRead:
    await _require_student_module(db, module_id=module_id, current_user=current_user)
    row = await _student_availability(db, student_id=current_user.user_id, module_id=module_id)
    if row is None:
        availability = _default_availability_input(config=workload_config())
        return StudentAvailabilityRead(
            module_id=module_id,
            study_days=list(availability.study_days),
            preferred_window=availability.preferred_window,
            max_study_minutes_per_day=availability.max_study_minutes_per_day,
            availability_version=availability.availability_version,
            updated_at=None,
        )
    return _availability_read(row)


async def update_student_workload_availability(
    db: AsyncSession,
    *,
    module_id: UUID,
    payload: StudentAvailabilityUpdate,
    current_user: CurrentUserContext,
) -> StudentAvailabilityRead:
    await _require_student_module(db, module_id=module_id, current_user=current_user)
    config = workload_config()
    try:
        next_availability = validate_availability(
            AvailabilityInput(
                study_days=tuple(payload.study_days),
                preferred_window=payload.preferred_window,
                max_study_minutes_per_day=payload.max_study_minutes_per_day,
                availability_version=1,
            ),
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    row = await _student_availability(db, student_id=current_user.user_id, module_id=module_id)
    now = datetime.now(UTC)
    if row is None:
        row = StudentAvailability(
            student_id=current_user.user_id,
            module_id=module_id,
            study_days=list(next_availability.study_days),
            preferred_window=next_availability.preferred_window,
            max_study_minutes_per_day=next_availability.max_study_minutes_per_day,
            availability_version=1,
            updated_at=now,
        )
        db.add(row)
    else:
        changed = (
            row.study_days != list(next_availability.study_days)
            or row.preferred_window != next_availability.preferred_window
            or row.max_study_minutes_per_day != next_availability.max_study_minutes_per_day
        )
        if changed:
            row.study_days = list(next_availability.study_days)
            row.preferred_window = next_availability.preferred_window
            row.max_study_minutes_per_day = next_availability.max_study_minutes_per_day
            row.availability_version += 1
            row.updated_at = now
    await db.commit()
    await db.refresh(row)
    return _availability_read(row)


async def generate_student_workload_plan(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> WorkloadPlanRead:
    await _require_student_module(db, module_id=module_id, current_user=current_user)
    config = workload_config()
    availability_row = await _student_availability(db, student_id=current_user.user_id, module_id=module_id)
    if availability_row is None:
        availability_row = await _create_default_availability(
            db,
            student_id=current_user.user_id,
            module_id=module_id,
            config=config,
        )
    source_cutoff_at = datetime.now(UTC)
    context = await analytics_read.get_workload_module_context(
        db,
        module_id=module_id,
        source_cutoff_at=source_cutoff_at,
    )
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    risk_snapshot = await analytics_read.latest_risk_snapshot(
        db,
        student_id=current_user.user_id,
        module_id=module_id,
    )
    forecast_context = await analytics_read.get_workload_forecast_context(
        db,
        student_id=current_user.user_id,
        module_id=module_id,
    )
    try:
        result = build_workload_plan(
            WorkloadInputs(
                student_id=current_user.user_id,
                module_id=module_id,
                module_title=context.module_title,
                module_timezone=context.timezone,
                course_ends_on=context.ends_on,
                source_cutoff_at=source_cutoff_at,
                availability=AvailabilityInput(
                    study_days=tuple(availability_row.study_days),
                    preferred_window=availability_row.preferred_window,
                    max_study_minutes_per_day=availability_row.max_study_minutes_per_day,
                    availability_version=availability_row.availability_version,
                ),
                deadlines=tuple(
                    DeadlineInput(
                        section_id=deadline.section_id,
                        title=deadline.title,
                        section_type=deadline.section_type,
                        week_number=deadline.week_number,
                        due_at=deadline.due_at,
                    )
                    for deadline in context.deadlines
                ),
                risk_snapshot=None
                if risk_snapshot is None
                else RiskSnapshotInput(
                    id=risk_snapshot.id,
                    risk_reasons=tuple(risk_snapshot.risk_reasons),
                    input_hash=risk_snapshot.input_hash,
                    source_cutoff_at=risk_snapshot.source_cutoff_at,
                ),
                forecast_context=forecast_context,
            ),
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    now = datetime.now(UTC)
    active_plans = (
        await db.scalars(
            select(WorkloadPlan)
            .where(
                WorkloadPlan.student_id == current_user.user_id,
                WorkloadPlan.module_id == module_id,
                WorkloadPlan.is_active.is_(True),
            )
            .with_for_update()
        )
    ).all()
    for existing in active_plans:
        existing.is_active = False
        existing.superseded_at = now
        existing.updated_at = now

    plan = WorkloadPlan(
        student_id=current_user.user_id,
        module_id=module_id,
        algorithm_version=result.algorithm_version,
        input_hash=result.input_hash,
        availability_version=result.availability_version,
        source_cutoff_at=result.source_cutoff_at,
        is_active=True,
        provenance=result.provenance,
        updated_at=now,
    )
    db.add(plan)
    await db.flush()
    for item in result.items:
        db.add(
            WorkloadPlanItem(
                workload_plan_id=plan.id,
                source_section_id=item.source_section_id,
                task_key=item.task_key,
                scheduled_date=item.scheduled_date,
                window=item.window,
                scheduled_start_at=item.scheduled_start_at,
                scheduled_end_at=item.scheduled_end_at,
                label=item.label,
                estimate_minutes=item.estimate_minutes,
                reason=item.reason,
                source_reason_code=item.source_reason_code,
                source_metadata=item.source_metadata,
                tight=item.tight,
                tight_message=item.tight_message,
                sort_index=item.sort_index,
            )
        )
    await db.commit()
    read = await _workload_plan_by_id(db, plan_id=plan.id, student_id=current_user.user_id)
    if read is None:  # pragma: no cover - defensive
        raise RuntimeError("Generated workload plan could not be read")
    return read


async def get_student_workload_plan(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> WorkloadPlanRead:
    await _require_student_module(db, module_id=module_id, current_user=current_user)
    plan = await _active_workload_plan(db, student_id=current_user.user_id, module_id=module_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workload plan not found")
    read = await _workload_plan_by_id(db, plan_id=plan.id, student_id=current_user.user_id)
    if read is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workload plan not found")
    return read


async def export_student_workload_calendar(
    db: AsyncSession,
    *,
    plan_id: UUID,
    current_user: CurrentUserContext,
) -> CalendarExport:
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    plan = await db.get(WorkloadPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workload plan not found")
    if plan.student_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not plan.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workload plan is no longer active")

    module = await db.get(CourseModule, plan.module_id)
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")

    items = (
        await db.scalars(
            select(WorkloadPlanItem)
            .where(WorkloadPlanItem.workload_plan_id == plan.id)
            .order_by(WorkloadPlanItem.sort_index.asc(), WorkloadPlanItem.id.asc())
        )
    ).all()
    deadlines = (
        await db.scalars(
            select(ModuleSection)
            .where(
                ModuleSection.course_module_id == plan.module_id,
                ModuleSection.status == "active",
                ModuleSection.publish_status == "published",
                ModuleSection.due_at.is_not(None),
                ModuleSection.due_at >= plan.source_cutoff_at,
            )
            .order_by(ModuleSection.due_at.asc(), ModuleSection.id.asc())
        )
    ).all()

    content = build_workload_calendar(
        plan_id=plan.id,
        module_title=module.title,
        calendar_timezone=_calendar_timezone(module),
        exported_at=datetime.now(UTC),
        plan_items=[
            CalendarPlanItem(
                id=item.id,
                label=item.label,
                estimate_minutes=item.estimate_minutes,
                reason=item.reason,
                scheduled_start_at=item.scheduled_start_at,
                scheduled_end_at=item.scheduled_end_at,
                tight=item.tight,
                tight_message=item.tight_message,
            )
            for item in items
        ],
        deadlines=[
            CalendarDeadline(
                id=deadline.id,
                title=deadline.title,
                due_at=deadline.due_at,
            )
            for deadline in deadlines
            if deadline.due_at is not None
        ],
    )
    return CalendarExport(
        content=content,
        filename=f"xyz-lms-workload-plan-{plan.id}.ics",
    )


async def get_lecturer_student_recommendations(
    db: AsyncSession,
    *,
    module_id: UUID,
    student_id: UUID,
    current_user: CurrentUserContext,
) -> LecturerStudentRecommendationsRead:
    if current_user.role != "lecturer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.lecturer_has_module(db, lecturer_id=current_user.user_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.student_has_module(db, student_id=student_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    current = await _current_risk_rows(db, module_id=module_id, student_id=student_id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    subject, result = current[0]
    reason_dicts = [reason_to_dict(reason) for reason in result.reasons]
    current_keys = recommendations.current_reason_keys(module_id, reason_dicts)
    rows = await _active_recommendation_rows(db, student_id=student_id, module_id=module_id)
    visible = [
        row
        for row in rows
        if recommendations.is_visible_for_audience(row, audience="lecturer", current_keys=current_keys)
    ]
    queued = False
    for row in visible:
        queued = await _ensure_ai_queued(db, row) or queued
    if queued:
        await db.commit()

    return LecturerStudentRecommendationsRead(
        student_id=subject.student_id,
        student_name=subject.student_name,
        student_email=subject.student_email,
        module_id=subject.module_id,
        module_title=subject.module_title,
        risk_reasons=[_reason_read(reason) for reason in reason_dicts],
        recommendations=[_recommendation_read(row) for row in _sort_recommendations(visible)],
    )


async def lecturer_mark_recommendation_acted(
    db: AsyncSession,
    *,
    recommendation_id: UUID,
    current_user: CurrentUserContext,
) -> RecommendationActionRead:
    row = await _recommendation_for_lecturer(db, recommendation_id=recommendation_id, current_user=current_user)
    now = datetime.now(UTC)
    row.lecturer_state = "acted"
    row.lecturer_acted_at = now
    row.updated_at = now
    await db.commit()
    return RecommendationActionRead(id=row.id, lecturer_state=row.lecturer_state, student_state=row.student_state)


async def lecturer_dismiss_recommendation(
    db: AsyncSession,
    *,
    recommendation_id: UUID,
    current_user: CurrentUserContext,
) -> RecommendationActionRead:
    row = await _recommendation_for_lecturer(db, recommendation_id=recommendation_id, current_user=current_user)
    now = datetime.now(UTC)
    row.lecturer_state = "dismissed"
    row.lecturer_dismissed_at = now
    row.updated_at = now
    await db.commit()
    return RecommendationActionRead(id=row.id, lecturer_state=row.lecturer_state, student_state=row.student_state)


async def get_student_module_recommendations(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> StudentRecommendationListRead:
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.student_has_module(db, student_id=current_user.user_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    rows = await _visible_student_recommendations(db, student_id=current_user.user_id, module_id=module_id)
    titles = await _module_titles(db, {row.module_id for row in rows})
    if rows:
        await _mark_student_shown(db, rows)
    return StudentRecommendationListRead(
        recommendations=[_student_recommendation_read(row, module_title=titles.get(row.module_id, "")) for row in rows[:1]]
    )


async def get_student_recommendation_banner(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
) -> StudentRecommendationBannerRead:
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    rows = await _visible_student_recommendations(db, student_id=current_user.user_id, module_id=None)
    if rows:
        titles = await _module_titles(db, {rows[0].module_id})
        await _mark_student_shown(db, rows[:1])
        return StudentRecommendationBannerRead(
            recommendation=_student_recommendation_read(rows[0], module_title=titles.get(rows[0].module_id, ""))
        )
    return StudentRecommendationBannerRead(recommendation=None)


async def student_dismiss_recommendation(
    db: AsyncSession,
    *,
    recommendation_id: UUID,
    current_user: CurrentUserContext,
) -> RecommendationActionRead:
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    row = await db.get(Recommendation, recommendation_id)
    if row is None or row.student_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    now = datetime.now(UTC)
    row.student_state = "dismissed"
    row.student_dismissed_at = now
    row.updated_at = now
    await db.commit()
    return RecommendationActionRead(id=row.id, lecturer_state=row.lecturer_state, student_state=row.student_state)


async def get_student_module_forecast_advice(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> ForecastAdviceRead:
    """Student-self grade-forecast advice for a module. AI explains Stage 9's deterministic forecast.

    The deterministic template renders immediately; lazy/cached AI swaps in when ready (poll). Authz:
    non-student → 403; not enrolled → 404; advice is derived from the auth context so a student can only
    ever read their own (no other student's data is in the payload).
    """
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.student_has_module(db, student_id=current_user.user_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")

    forecast = await _forecast_result(db, student_id=current_user.user_id, module_id=module_id)
    if forecast is None:
        # No target/scheme yet → nothing to explain. Valid, non-500 empty-but-sane payload.
        return ForecastAdviceRead(
            module_id=module_id,
            forecast_state="none",
            text="Set a target grade on your forecast to see personalised advice here.",
            source="template",
            ai_status="none",
        )

    titles = await _module_titles(db, {module_id})
    module_title = titles.get(module_id) or "this module"
    payload = forecast_advice.build_deterministic_payload(forecast, module_title=module_title)
    input_hash = forecast_advice.forecast_advice_input_hash(payload)
    now = datetime.now(UTC)

    # Race-safe upsert of the one-row-per-(student, module) advice cache, then COMMIT so the row id is
    # stable before any enqueue (the stable job id dedupes concurrent reads).
    stmt = (
        insert(StudentForecastAdvice)
        .values(
            student_id=current_user.user_id,
            module_id=module_id,
            algorithm_version=forecast_advice.ALGORITHM_VERSION,
            input_hash=input_hash,
            source_cutoff_at=now,
            forecast_state=forecast.state,
            deterministic_payload=payload,
        )
        .on_conflict_do_update(
            index_elements=[
                StudentForecastAdvice.student_id,
                StudentForecastAdvice.module_id,
            ],
            set_={
                "algorithm_version": forecast_advice.ALGORITHM_VERSION,
                "input_hash": input_hash,
                "source_cutoff_at": now,
                "forecast_state": forecast.state,
                "deterministic_payload": payload,
                "updated_at": func.now(),
            },
            # Only rewrite when the forecast actually changed — avoids write amplification on every
            # poll and keeps source_cutoff_at meaningful (when the inputs last changed, not last read).
            where=StudentForecastAdvice.input_hash != input_hash,
        )
    )
    await db.execute(stmt)
    await db.commit()

    row = await db.scalar(
        select(StudentForecastAdvice).where(
            StudentForecastAdvice.student_id == current_user.user_id,
            StudentForecastAdvice.module_id == module_id,
        )
    )
    if row is None:  # pragma: no cover - defensive: row was created/updated above
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")

    # Lazy AI: regenerate when the cache is stale for an AI-eligible state — but not while queued, and
    # not re-attempting a terminal failure for THIS exact forecast (rule-15; also avoids a poll loop
    # under forced AI-unavailable). The deterministic template renders immediately either way.
    if bool(payload.get("aiEligible")):
        attempted_current = row.ai_input_hash == input_hash
        current_success = (
            row.ai_status == "succeeded"
            and attempted_current
            and row.ai_prompt_version == forecast_advice.ADVICE_PROMPT_VERSION
        )
        terminal_for_current = attempted_current and row.ai_status in {"template_fallback", "failed"}
        if not current_success and row.ai_status != "queued" and not terminal_for_current:
            # Bound adversarial input-variation cost: a throttled student still gets the deterministic
            # template now; the AI regenerates on a later view (never a 429 on the read).
            throttled = False
            try:
                await enforce_fixed_window_rate_limit(
                    key=f"forecast-advice:generate:{current_user.user_id}:{module_id}",
                    limit=settings.FORECAST_ADVICE_GENERATION_RATE_LIMIT,
                    window_seconds=settings.FORECAST_ADVICE_GENERATION_RATE_WINDOW_SECONDS,
                )
            except HTTPException as exc:
                if exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
                    raise
                throttled = True
            if not throttled:
                row.ai_status = "queued"
                row.updated_at = now
                await db.commit()
                enqueue_generate_forecast_advice(row.id)

    text, source = forecast_advice.advice_text(row)
    return ForecastAdviceRead(
        module_id=module_id,
        forecast_state=row.forecast_state,
        text=text,
        source=source,
        ai_status=row.ai_status,
    )


async def compute_risk_for_scope(
    db: AsyncSession,
    *,
    scope_type: str,
    scope_id: UUID | None,
    source_cutoff_at: datetime,
) -> list[tuple[analytics_read.StudentModuleRiskSubject, RiskResult]]:
    if scope_type == "all":
        return await _current_risk_rows(db, source_cutoff_at=source_cutoff_at)
    if scope_type == "module":
        if scope_id is None:
            raise RuntimeError("module scope requires scope_id")
        return await _current_risk_rows(db, module_id=scope_id, source_cutoff_at=source_cutoff_at)
    if scope_type == "student":
        if scope_id is None:
            raise RuntimeError("student scope requires scope_id")
        return await _current_risk_rows(db, student_id=scope_id, source_cutoff_at=source_cutoff_at)
    return []


async def _current_risk_rows(
    db: AsyncSession,
    *,
    module_id: UUID | None = None,
    student_id: UUID | None = None,
    source_cutoff_at: datetime | None = None,
) -> list[tuple[analytics_read.StudentModuleRiskSubject, RiskResult]]:
    cutoff = source_cutoff_at or datetime.now(UTC)
    config = risk_config()
    subjects = await analytics_read.list_risk_subjects(db, module_id=module_id, student_id=student_id)
    rows: list[tuple[analytics_read.StudentModuleRiskSubject, RiskResult]] = []
    for subject in subjects:
        metrics = await _risk_metrics_for_subject(db, subject=subject, config=config, source_cutoff_at=cutoff)
        rows.append((subject, classify_risk(metrics, config=config, source_cutoff_at=cutoff)))
    return rows


async def _risk_metrics_for_subject(
    db: AsyncSession,
    *,
    subject: analytics_read.StudentModuleRiskSubject,
    config: RiskConfig,
    source_cutoff_at: datetime,
) -> RiskMetrics:
    forecast_state = await _forecast_state(
        db,
        student_id=subject.student_id,
        module_id=subject.module_id,
    )
    missed = await analytics_read.count_missed_recent_quizzes(
        db,
        student_id=subject.student_id,
        module_id=subject.module_id,
        limit=config.recent_quiz_window,
        source_cutoff_at=source_cutoff_at,
    )
    scores = await analytics_read.list_recent_quiz_scores(
        db,
        student_id=subject.student_id,
        module_id=subject.module_id,
        limit=config.recent_quiz_window,
        source_cutoff_at=source_cutoff_at,
    )
    latest_activity = await analytics_read.latest_activity_at(
        db,
        student_id=subject.student_id,
        module_id=subject.module_id,
        source_cutoff_at=source_cutoff_at,
    )
    days_since_activity = None
    if latest_activity is not None:
        days_since_activity = max(0, (source_cutoff_at - latest_activity).days)
    upcoming = await analytics_read.has_upcoming_work(
        db,
        module_id=subject.module_id,
        source_cutoff_at=source_cutoff_at,
    )
    topic_gap = await analytics_read.earliest_topic_deadline_gap(
        db,
        student_id=subject.student_id,
        module_id=subject.module_id,
        source_cutoff_at=source_cutoff_at,
        within_hours=config.topic_deadline_watch_days * 24,
    )
    gap_hours = None
    if topic_gap is not None:
        gap_hours = max(0, int((topic_gap.due_at - source_cutoff_at).total_seconds() // 3600))
    return RiskMetrics(
        student_id=subject.student_id,
        module_id=subject.module_id,
        forecast_state=forecast_state,
        missed_recent_quiz_count=missed,
        recent_quiz_scores=tuple(scores),
        days_since_activity=days_since_activity,
        upcoming_work_exists=upcoming,
        topic_gap_title=topic_gap.title if topic_gap else None,
        topic_gap_due_in_hours=gap_hours,
    )


async def _forecast_result(
    db: AsyncSession, *, student_id: UUID, module_id: UUID
) -> ForecastResult | None:
    """The full deterministic Stage 9 forecast for (student, module), or None when no target/scheme.

    Single computation path: assembles inputs via ``analytics_read.get_grade_forecast_inputs`` and the
    shared ``build_forecast_input`` helper, then calls Stage 9's ``calculate_forecast``. The grade math
    is never duplicated here (11.6 hard line: AI explains, never calculates).
    """
    inputs = await analytics_read.get_grade_forecast_inputs(db, student_id=student_id, module_id=module_id)
    if inputs is None or inputs.target_letter_grade is None:
        return None
    return calculate_forecast(
        build_forecast_input(
            boundaries=inputs.boundaries,
            components=[
                (component.id, component.weight, component.percentage_score)
                for component in inputs.components
            ],
            target_letter_grade=inputs.target_letter_grade,
            on_track_max=inputs.on_track_max,
            at_risk_max=inputs.at_risk_max,
        )
    )


async def _forecast_state(db: AsyncSession, *, student_id: UUID, module_id: UUID) -> str | None:
    result = await _forecast_result(db, student_id=student_id, module_id=module_id)
    return result.state if result else None


def default_manual_scheduled_for(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    tz = ZoneInfo(settings.INSTITUTION_TIMEZONE)
    local = current.astimezone(tz)
    scheduled_local = local.replace(
        hour=settings.SCHEDULER_DAILY_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    if scheduled_local > local:
        scheduled_local = scheduled_local - timedelta(days=1)
    return scheduled_local.astimezone(UTC)


def agent_run_idempotency_key(
    *,
    trigger_type: str,
    scope_type: str,
    scope_id: UUID | None,
    scheduled_for: datetime,
    algorithm_version: str,
) -> str:
    scope = str(scope_id) if scope_id else ""
    return "|".join(
        [
            trigger_type,
            scope_type,
            scope,
            scheduled_for.astimezone(UTC).isoformat(),
            algorithm_version,
        ]
    )


def _reason_read(data: dict) -> RiskReasonRead:
    return RiskReasonRead.model_validate(data)


def _student_reason_read(data: dict) -> StudentRiskReasonRead:
    return StudentRiskReasonRead(code=data["code"], student_text=data["studentText"])


async def _require_student_module(
    db: AsyncSession,
    *,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> None:
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if not await analytics_read.student_has_module(db, student_id=current_user.user_id, module_id=module_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


async def _student_availability(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> StudentAvailability | None:
    return await db.scalar(
        select(StudentAvailability).where(
            StudentAvailability.student_id == student_id,
            StudentAvailability.module_id == module_id,
        )
    )


def _default_availability_input(*, config: WorkloadConfig) -> AvailabilityInput:
    try:
        return validate_availability(
            AvailabilityInput(
                study_days=tuple(day.strip() for day in settings.WORKLOAD_PLAN_DEFAULT_STUDY_DAYS.split(",")),
                preferred_window=settings.WORKLOAD_PLAN_DEFAULT_PREFERRED_WINDOW,
                max_study_minutes_per_day=settings.WORKLOAD_PLAN_DEFAULT_AVAILABILITY_MINUTES,
                availability_version=1,
            ),
            config=config,
        )
    except ValueError as exc:  # pragma: no cover - configuration guard
        raise RuntimeError(f"Invalid workload default availability: {exc}") from exc


async def _create_default_availability(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
    config: WorkloadConfig,
) -> StudentAvailability:
    availability = _default_availability_input(config=config)
    row = StudentAvailability(
        student_id=student_id,
        module_id=module_id,
        study_days=list(availability.study_days),
        preferred_window=availability.preferred_window,
        max_study_minutes_per_day=availability.max_study_minutes_per_day,
        availability_version=availability.availability_version,
        updated_at=datetime.now(UTC),
    )
    db.add(row)
    await db.flush()
    return row


def _availability_read(row: StudentAvailability) -> StudentAvailabilityRead:
    return StudentAvailabilityRead(
        module_id=row.module_id,
        study_days=list(row.study_days),
        preferred_window=row.preferred_window,
        max_study_minutes_per_day=row.max_study_minutes_per_day,
        availability_version=row.availability_version,
        updated_at=row.updated_at,
    )


def _calendar_timezone(module: CourseModule) -> str:
    for value in (module.timezone, settings.INSTITUTION_TIMEZONE, "UTC"):
        candidate = (value or "").strip()
        if not candidate:
            continue
        try:
            ZoneInfo(candidate)
            return candidate
        except Exception:
            continue
    return "UTC"


async def _active_workload_plan(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> WorkloadPlan | None:
    return await db.scalar(
        select(WorkloadPlan)
        .where(
            WorkloadPlan.student_id == student_id,
            WorkloadPlan.module_id == module_id,
            WorkloadPlan.is_active.is_(True),
        )
        .order_by(WorkloadPlan.created_at.desc(), WorkloadPlan.id.desc())
        .limit(1)
    )


async def _workload_plan_by_id(
    db: AsyncSession,
    *,
    plan_id: UUID,
    student_id: UUID,
) -> WorkloadPlanRead | None:
    plan = await db.scalar(
        select(WorkloadPlan).where(
            WorkloadPlan.id == plan_id,
            WorkloadPlan.student_id == student_id,
        )
    )
    if plan is None:
        return None
    items = (
        await db.scalars(
            select(WorkloadPlanItem)
            .where(WorkloadPlanItem.workload_plan_id == plan.id)
            .order_by(WorkloadPlanItem.sort_index.asc(), WorkloadPlanItem.id.asc())
        )
    ).all()
    return WorkloadPlanRead(
        id=plan.id,
        module_id=plan.module_id,
        algorithm_version=plan.algorithm_version,
        input_hash=plan.input_hash,
        availability_version=plan.availability_version,
        source_cutoff_at=plan.source_cutoff_at,
        is_active=plan.is_active,
        superseded_at=plan.superseded_at,
        provenance=plan.provenance,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        items=[
            WorkloadPlanItemRead(
                id=item.id,
                task_key=item.task_key,
                source_section_id=item.source_section_id,
                scheduled_date=item.scheduled_date,
                window=item.window,
                scheduled_start_at=item.scheduled_start_at,
                scheduled_end_at=item.scheduled_end_at,
                label=item.label,
                estimate_minutes=item.estimate_minutes,
                reason=item.reason,
                source_reason_code=item.source_reason_code,
                source_metadata=item.source_metadata,
                tight=item.tight,
                tight_message=item.tight_message,
                sort_index=item.sort_index,
            )
            for item in items
        ],
    )


async def _active_recommendation_rows(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID | None,
) -> list[Recommendation]:
    stmt = select(Recommendation).where(
        Recommendation.student_id == student_id,
        Recommendation.status == "active",
    )
    if module_id is not None:
        stmt = stmt.where(Recommendation.module_id == module_id)
    return list((await db.scalars(stmt)).all())


async def _visible_student_recommendations(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID | None,
) -> list[Recommendation]:
    rows = await _active_recommendation_rows(db, student_id=student_id, module_id=module_id)
    by_module: dict[UUID, list[Recommendation]] = {}
    for row in rows:
        by_module.setdefault(row.module_id, []).append(row)
    visible: list[Recommendation] = []
    for row_module_id, module_rows in by_module.items():
        current = await _current_risk_rows(db, module_id=row_module_id, student_id=student_id)
        if not current:
            continue
        reason_dicts = [reason_to_dict(reason) for reason in current[0][1].reasons]
        current_keys = recommendations.current_reason_keys(row_module_id, reason_dicts)
        visible.extend(
            row
            for row in module_rows
            if recommendations.is_visible_for_audience(row, audience="student", current_keys=current_keys)
        )
    return _sort_recommendations(visible)


async def _mark_student_shown(db: AsyncSession, rows: list[Recommendation]) -> None:
    now = datetime.now(UTC)
    changed = False
    for row in rows:
        if row.student_state == "new":
            row.student_state = "shown"
            row.student_shown_at = now
            row.updated_at = now
            changed = True
    if changed:
        await db.commit()


async def _recommendation_for_lecturer(
    db: AsyncSession,
    *,
    recommendation_id: UUID,
    current_user: CurrentUserContext,
) -> Recommendation:
    if current_user.role != "lecturer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    row = await db.get(Recommendation, recommendation_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    if not await analytics_read.lecturer_has_module(
        db,
        lecturer_id=current_user.user_id,
        module_id=row.module_id,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return row


async def _ensure_ai_queued(db: AsyncSession, row: Recommendation) -> bool:
    current = (
        row.ai_status == "succeeded"
        and row.ai_input_hash == row.input_hash
        and row.ai_prompt_version == recommendations.RECOMMENDATION_COPY_PROMPT_VERSION
    )
    if current or row.ai_status == "queued":
        return False
    row.ai_status = "queued"
    row.updated_at = datetime.now(UTC)
    await db.flush()
    enqueue_generate_recommendation_copy(row.id)
    return True


def _recommendation_read(row: Recommendation) -> RecommendationRead:
    lecturer_text, lecturer_source = recommendations.lecturer_text(row)
    student_nudge, student_source = recommendations.student_text(row)
    provenance = _ai_provenance_read(row)
    return RecommendationRead(
        id=row.id,
        reason_code=row.reason_code,
        target_key=row.target_key,
        target_label=row.target_label,
        lecturer_state=row.lecturer_state,
        student_state=row.student_state,
        ai_status=row.ai_status,
        lecturer_draft_text=lecturer_text,
        lecturer_draft_source=lecturer_source,
        student_nudge_text=student_nudge,
        student_nudge_source=student_source,
        student_next_step=str(row.deterministic_payload.get("studentNextStep") or ""),
        deterministic_payload=row.deterministic_payload,
        ai_provenance=provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _assessment_insights_read(
    insights: analytics_read.AssessmentInsights,
) -> LecturerAssessmentInsightsRead:
    return LecturerAssessmentInsightsRead(
        module_id=insights.module_id,
        module_title=insights.module_title,
        latest_agent_run=(
            AssessmentAgentRunRead(
                id=insights.latest_agent_run.id,
                status=insights.latest_agent_run.status,
                scope_type=insights.latest_agent_run.scope_type,
                scope_id=insights.latest_agent_run.scope_id,
                scheduled_for=insights.latest_agent_run.scheduled_for,
                completed_at=insights.latest_agent_run.completed_at,
                snapshot_count=insights.latest_agent_run.snapshot_count,
                recommendation_count=insights.latest_agent_run.recommendation_count,
            )
            if insights.latest_agent_run is not None
            else None
        ),
        small_cohort_threshold=insights.small_cohort_threshold,
        small_cohort_message=insights.small_cohort_message,
        questions=[_assessment_question_read(question) for question in insights.questions],
        most_missed_questions=[
            _assessment_question_read(question) for question in insights.most_missed_questions
        ],
        topic_mastery=AssessmentTopicMasteryRead(
            available=insights.topic_mastery.available,
            unavailable_reason=insights.topic_mastery.unavailable_reason,
            unmapped_answer_count=insights.topic_mastery.unmapped_answer_count,
            unmapped_message=insights.topic_mastery.unmapped_message,
            rows=[
                AssessmentTopicMasteryRowRead(
                    source_section_id=row.source_section_id,
                    topic_title=row.topic_title,
                    week_number=row.week_number,
                    answer_count=row.answer_count,
                    correct_count=row.correct_count,
                    mastery_percent=row.mastery_percent,
                    small_cohort=row.small_cohort,
                    small_cohort_message=row.small_cohort_message,
                )
                for row in insights.topic_mastery.rows
            ],
        ),
    )


def _assessment_question_read(
    question: analytics_read.AssessmentQuestionInsight,
) -> AssessmentQuestionInsightRead:
    return AssessmentQuestionInsightRead(
        question_key=question.question_key,
        question_text=question.question_text,
        answer_count=question.answer_count,
        correct_count=question.correct_count,
        incorrect_count=question.incorrect_count,
        correct_rate_percent=question.correct_rate_percent,
        small_cohort=question.small_cohort,
        small_cohort_message=question.small_cohort_message,
        distractors=[
            AssessmentDistractorInsightRead(
                option_key=distractor.option_key,
                option_text=distractor.option_text,
                selected_count=distractor.selected_count,
                selected_rate_percent=distractor.selected_rate_percent,
            )
            for distractor in question.distractors
        ],
    )


def _student_recommendation_read(row: Recommendation, *, module_title: str) -> StudentRecommendationRead:
    text, source = recommendations.student_text(row)
    return StudentRecommendationRead(
        id=row.id,
        module_id=row.module_id,
        module_title=module_title,
        target_label=row.target_label,
        text=text,
        next_step=str(row.deterministic_payload.get("studentNextStep") or ""),
        source=source,
    )


async def _module_titles(db: AsyncSession, module_ids: set[UUID]) -> dict[UUID, str]:
    if not module_ids:
        return {}
    rows = (await db.execute(select(CourseModule.id, CourseModule.title).where(CourseModule.id.in_(module_ids)))).all()
    return {row.id: row.title for row in rows}


def _ai_provenance_read(row: Recommendation) -> AIProvenanceRead | None:
    if not row.ai_model_id or not row.ai_prompt_version or not row.ai_input_hash or not row.ai_generated_at:
        return None
    return AIProvenanceRead(
        model_id=row.ai_model_id,
        prompt_version=row.ai_prompt_version,
        input_hash=row.ai_input_hash,
        generated_at=row.ai_generated_at,
    )


def _sort_recommendations(rows: list[Recommendation]) -> list[Recommendation]:
    return sorted(
        rows,
        key=lambda row: (
            _severity_sort(str(row.deterministic_payload.get("severity") or "watch")),
            row.created_at,
            str(row.id),
        ),
    )


def _severity_sort(severity: str) -> int:
    return {"needs_support": 0, "watch": 1}.get(severity, 2)


def _risk_sort(tier: str) -> int:
    return {"needs_support": 0, "watch": 1, "on_track": 2}[tier]


async def _prune_old_snapshots(db: AsyncSession) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=settings.RISK_SNAPSHOT_RETENTION_DAYS)
    newer_snapshot = aliased(StudentRiskSnapshot)
    await db.execute(
        delete(StudentRiskSnapshot)
        .where(StudentRiskSnapshot.computed_at < cutoff)
        .where(
            exists(
                select(1)
                .select_from(newer_snapshot)
                .where(
                    newer_snapshot.student_id == StudentRiskSnapshot.student_id,
                    newer_snapshot.module_id == StudentRiskSnapshot.module_id,
                    newer_snapshot.computed_at > StudentRiskSnapshot.computed_at,
                )
            )
        )
    )


def _sanitize_failure(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:500]
