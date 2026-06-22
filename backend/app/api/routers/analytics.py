from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics import service
from app.domains.analytics.schemas import (
    AgentRunRead,
    ForecastAdviceRead,
    LecturerAssessmentInsightsRead,
    LecturerRosterRiskRead,
    LecturerStudentRecommendationsRead,
    RecommendationActionRead,
    StudentRecommendationBannerRead,
    StudentRecommendationListRead,
    StudentRiskRead,
    StudentAvailabilityRead,
    StudentAvailabilityUpdate,
    TriggerAgentRunRequest,
    WorkloadPlanRead,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.workers.queues import agent_run_status_is_requeueable, enqueue_run_agent_if_needed


router = APIRouter(tags=["analytics"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]
_NO_STORE = "private, no-store"


@router.post(
    "/admin/analytics/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="triggerAgentRun",
)
async def trigger_agent_run(
    payload: TriggerAgentRunRequest,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    response.headers["Cache-Control"] = _NO_STORE
    run, _created = await service.trigger_manual_run(db, payload=payload, current_user=current_user)
    if agent_run_status_is_requeueable(run.status):
        enqueue_run_agent_if_needed(run.id)
    return run


@router.get(
    "/admin/analytics/agent-runs/{run_id}",
    response_model=AgentRunRead,
    operation_id="getAgentRun",
)
async def get_agent_run(
    run_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_run(db, run_id=run_id, current_user=current_user)


@router.get(
    "/lecturer/modules/{module_id}/analytics/roster-risk",
    response_model=LecturerRosterRiskRead,
    operation_id="getLecturerRosterRisk",
)
async def get_lecturer_roster_risk(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> LecturerRosterRiskRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_lecturer_roster_risk(db, module_id=module_id, current_user=current_user)


@router.get(
    "/lecturer/modules/{module_id}/analytics/assessment-insights",
    response_model=LecturerAssessmentInsightsRead,
    operation_id="getLecturerAssessmentInsights",
)
async def get_lecturer_assessment_insights(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> LecturerAssessmentInsightsRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_lecturer_assessment_insights(
        db,
        module_id=module_id,
        current_user=current_user,
    )


@router.get(
    "/student/modules/{module_id}/risk",
    response_model=StudentRiskRead,
    operation_id="getStudentModuleRisk",
)
async def get_student_module_risk(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentRiskRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_student_risk(db, module_id=module_id, current_user=current_user)


@router.get(
    "/student/modules/{module_id}/workload/availability",
    response_model=StudentAvailabilityRead,
    operation_id="getStudentWorkloadAvailability",
)
async def get_student_workload_availability(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentAvailabilityRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_student_workload_availability(
        db,
        module_id=module_id,
        current_user=current_user,
    )


@router.put(
    "/student/modules/{module_id}/workload/availability",
    response_model=StudentAvailabilityRead,
    operation_id="updateStudentWorkloadAvailability",
)
async def update_student_workload_availability(
    module_id: UUID,
    payload: StudentAvailabilityUpdate,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentAvailabilityRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.update_student_workload_availability(
        db,
        module_id=module_id,
        payload=payload,
        current_user=current_user,
    )


@router.get(
    "/student/modules/{module_id}/workload/plan",
    response_model=WorkloadPlanRead,
    operation_id="getStudentWorkloadPlan",
)
async def get_student_workload_plan(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkloadPlanRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_student_workload_plan(
        db,
        module_id=module_id,
        current_user=current_user,
    )


@router.get(
    "/student/workload/plans/{plan_id}/calendar.ics",
    operation_id="exportStudentWorkloadCalendar",
)
async def export_student_workload_calendar(
    plan_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    exported = await service.export_student_workload_calendar(
        db,
        plan_id=plan_id,
        current_user=current_user,
    )
    return Response(
        content=exported.content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": _NO_STORE,
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
        },
    )


@router.post(
    "/student/modules/{module_id}/workload/plan:generate",
    response_model=WorkloadPlanRead,
    operation_id="generateStudentWorkloadPlan",
)
async def generate_student_workload_plan(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkloadPlanRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.generate_student_workload_plan(
        db,
        module_id=module_id,
        current_user=current_user,
    )


@router.get(
    "/lecturer/modules/{module_id}/analytics/students/{student_id}/recommendations",
    response_model=LecturerStudentRecommendationsRead,
    operation_id="getLecturerStudentRecommendations",
)
async def get_lecturer_student_recommendations(
    module_id: UUID,
    student_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> LecturerStudentRecommendationsRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_lecturer_student_recommendations(
        db,
        module_id=module_id,
        student_id=student_id,
        current_user=current_user,
    )


@router.post(
    "/lecturer/recommendations/{recommendation_id}/mark-acted",
    response_model=RecommendationActionRead,
    operation_id="markLecturerRecommendationActed",
)
async def mark_lecturer_recommendation_acted(
    recommendation_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> RecommendationActionRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.lecturer_mark_recommendation_acted(
        db,
        recommendation_id=recommendation_id,
        current_user=current_user,
    )


@router.post(
    "/lecturer/recommendations/{recommendation_id}/dismiss",
    response_model=RecommendationActionRead,
    operation_id="dismissLecturerRecommendation",
)
async def dismiss_lecturer_recommendation(
    recommendation_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> RecommendationActionRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.lecturer_dismiss_recommendation(
        db,
        recommendation_id=recommendation_id,
        current_user=current_user,
    )


@router.get(
    "/student/modules/{module_id}/recommendations",
    response_model=StudentRecommendationListRead,
    operation_id="getStudentModuleRecommendations",
)
async def get_student_module_recommendations(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentRecommendationListRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_student_module_recommendations(
        db,
        module_id=module_id,
        current_user=current_user,
    )


@router.get(
    "/student/modules/{module_id}/forecast-advice",
    response_model=ForecastAdviceRead,
    operation_id="getStudentModuleForecastAdvice",
)
async def get_student_module_forecast_advice(
    module_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> ForecastAdviceRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_student_module_forecast_advice(
        db,
        module_id=module_id,
        current_user=current_user,
    )


@router.get(
    "/student/recommendations/banner",
    response_model=StudentRecommendationBannerRead,
    operation_id="getStudentRecommendationBanner",
)
async def get_student_recommendation_banner(
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> StudentRecommendationBannerRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.get_student_recommendation_banner(db, current_user=current_user)


@router.post(
    "/student/recommendations/{recommendation_id}/dismiss",
    response_model=RecommendationActionRead,
    operation_id="dismissStudentRecommendation",
)
async def dismiss_student_recommendation(
    recommendation_id: UUID,
    response: Response,
    db: DbSession,
    current_user: CurrentUser,
) -> RecommendationActionRead:
    response.headers["Cache-Control"] = _NO_STORE
    return await service.student_dismiss_recommendation(
        db,
        recommendation_id=recommendation_id,
        current_user=current_user,
    )
