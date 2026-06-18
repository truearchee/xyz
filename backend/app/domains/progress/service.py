from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.progress.forecast import (
    ForecastInput,
    GradeBoundaryInput,
    GradeComponentInput,
    calculate_forecast,
)
from app.domains.progress.schemas import (
    BenchmarkRead,
    ForecastRead,
    ProgressDashboardRead,
    ProgressModuleDetail,
    ProgressModuleSummary,
    TargetGradeRequest,
    TopicMasteryRead,
    TrendPointRead,
    FORECAST_LABELS,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import StudentTargetGradeGoal
from app.platform.query import progress_read


async def get_dashboard(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
) -> ProgressDashboardRead:
    _require_student(current_user)
    modules = await progress_read.list_student_progress_modules(db, student_id=current_user.user_id)
    summaries: list[ProgressModuleSummary] = []
    for module in modules:
        detail = await _build_module_detail(db, student_id=current_user.user_id, module_id=module.id)
        summaries.append(
            ProgressModuleSummary(
                module_id=module.id,
                title=module.title,
                current_standing=detail.current_standing,
                current_letter_grade=detail.current_letter_grade,
                target_letter_grade=detail.target_letter_grade,
                forecast_state=detail.forecast.state if detail.forecast else None,
                forecast_label=detail.forecast.label if detail.forecast else None,
                latest_week_number=detail.trend[-1].week_number if detail.trend else None,
                latest_standing_points=detail.trend[-1].standing_points if detail.trend else None,
            )
        )
    return ProgressDashboardRead(modules=summaries)


async def get_module_progress(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
) -> ProgressModuleDetail:
    _require_student(current_user)
    module = await progress_read.get_visible_student_module(
        db,
        student_id=current_user.user_id,
        module_id=module_id,
    )
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    return await _build_module_detail(db, student_id=current_user.user_id, module_id=module_id)


async def set_target_grade(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    payload: TargetGradeRequest,
) -> ProgressModuleDetail:
    _require_student(current_user)
    module = await progress_read.get_visible_student_module(
        db,
        student_id=current_user.user_id,
        module_id=module_id,
    )
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")

    bundle = await progress_read.get_grade_scheme_bundle(
        db,
        student_id=current_user.user_id,
        module_id=module_id,
    )
    valid_targets = {boundary.letter_grade for boundary in bundle.boundaries} if bundle else set()
    if payload.target_letter_grade not in valid_targets:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown target grade")

    stmt = (
        insert(StudentTargetGradeGoal)
        .values(
            student_id=current_user.user_id,
            module_id=module_id,
            target_letter_grade=payload.target_letter_grade,
            status="active",
        )
        .on_conflict_do_update(
            index_elements=[
                StudentTargetGradeGoal.student_id,
                StudentTargetGradeGoal.module_id,
            ],
            index_where=StudentTargetGradeGoal.status == "active",
            set_={
                "target_letter_grade": payload.target_letter_grade,
                "updated_at": func.now(),
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
    return await _build_module_detail(db, student_id=current_user.user_id, module_id=module_id)


async def _build_module_detail(
    db: AsyncSession,
    *,
    student_id: UUID,
    module_id: UUID,
) -> ProgressModuleDetail:
    module = await progress_read.get_visible_student_module(db, student_id=student_id, module_id=module_id)
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")

    bundle = await progress_read.get_grade_scheme_bundle(db, student_id=student_id, module_id=module_id)
    target = await progress_read.get_active_target_goal(db, student_id=student_id, module_id=module_id)
    trend_rows = await progress_read.list_progress_snapshots(
        db,
        student_id=student_id,
        module_id=module_id,
    )
    topic_rows = await progress_read.list_topic_mastery(db, student_id=student_id, module_id=module_id)

    forecast = None
    current_standing = trend_rows[-1].standing_points if trend_rows else None
    current_letter = None
    available_targets: list[str] = []
    benchmark = None
    if bundle is not None:
        available_targets = [boundary.letter_grade for boundary in bundle.boundaries]
        if target is not None:
            forecast_result = calculate_forecast(
                ForecastInput(
                    boundaries=tuple(
                        GradeBoundaryInput(
                            letter_grade=boundary.letter_grade,
                            lower_bound=boundary.lower_bound,
                        )
                        for boundary in bundle.boundaries
                    ),
                    components=tuple(
                        GradeComponentInput(
                            id=str(component.id),
                            weight=component.weight,
                            percentage_score=component.percentage_score,
                        )
                        for component in bundle.components
                    ),
                    target_letter_grade=target.target_letter_grade,
                    on_track_max=bundle.scheme.on_track_max,
                    at_risk_max=bundle.scheme.at_risk_max,
                )
            )
            current_standing = forecast_result.earned_so_far
            current_letter = forecast_result.current_letter_grade
            forecast = ForecastRead(
                state=forecast_result.state,
                label=FORECAST_LABELS[forecast_result.state],
                target_letter_grade=forecast_result.target_letter_grade,
                target_points=forecast_result.target_points,
                earned_so_far=forecast_result.earned_so_far,
                remaining_weight=forecast_result.remaining_weight,
                min_reachable=forecast_result.min_reachable,
                max_reachable=forecast_result.max_reachable,
                current_letter_grade=forecast_result.current_letter_grade,
                best_reachable_letter_grade=forecast_result.best_reachable_letter_grade,
                required_remaining_average=forecast_result.required_remaining_average,
                final_letter_grade=forecast_result.final_letter_grade,
            )
        student_avg, class_avg, cohort_size = await progress_read.get_quiz_average_benchmark(
            db,
            student_id=student_id,
            module_id=module_id,
        )
        suppressed = cohort_size < bundle.scheme.benchmark_min_cohort
        benchmark = BenchmarkRead(
            metric="quiz_average",
            student_average=None if suppressed else _decimal_or_none(student_avg),
            class_average=None if suppressed else _decimal_or_none(class_avg),
            cohort_size=cohort_size,
            suppressed=suppressed,
            suppression_min_cohort=bundle.scheme.benchmark_min_cohort,
        )

    return ProgressModuleDetail(
        module_id=module.id,
        title=module.title,
        current_standing=current_standing,
        current_letter_grade=current_letter,
        target_letter_grade=target.target_letter_grade if target else None,
        available_target_grades=available_targets,
        forecast=forecast,
        trend=[
            TrendPointRead(
                week_number=row.week_number,
                snapshot_date=row.snapshot_date,
                standing_points=row.standing_points,
            )
            for row in trend_rows
        ],
        topics=[
            TopicMasteryRead(
                section_id=section.id,
                title=section.title,
                section_type=section.type,
                mastery_percentage=snapshot.mastery_percentage,
                status_label=snapshot.status_label,
            )
            for snapshot, section in topic_rows
        ],
        benchmark=benchmark,
    )


def _require_student(current_user: CurrentUserContext) -> None:
    if current_user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def _decimal_or_none(value) -> Decimal | None:
    return None if value is None else Decimal(value)
