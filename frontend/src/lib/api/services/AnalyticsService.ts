/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentRunRead } from '../models/AgentRunRead';
import type { ForecastAdviceRead } from '../models/ForecastAdviceRead';
import type { LecturerAssessmentInsightsRead } from '../models/LecturerAssessmentInsightsRead';
import type { LecturerRosterRiskRead } from '../models/LecturerRosterRiskRead';
import type { LecturerStudentRecommendationsRead } from '../models/LecturerStudentRecommendationsRead';
import type { RecommendationActionRead } from '../models/RecommendationActionRead';
import type { StudentAvailabilityRead } from '../models/StudentAvailabilityRead';
import type { StudentAvailabilityUpdate } from '../models/StudentAvailabilityUpdate';
import type { StudentRecommendationBannerRead } from '../models/StudentRecommendationBannerRead';
import type { StudentRecommendationListRead } from '../models/StudentRecommendationListRead';
import type { StudentRiskRead } from '../models/StudentRiskRead';
import type { TriggerAgentRunRequest } from '../models/TriggerAgentRunRequest';
import type { WorkloadPlanRead } from '../models/WorkloadPlanRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AnalyticsService {
    /**
     * Trigger Agent Run
     * @param requestBody
     * @param authorization
     * @returns AgentRunRead Successful Response
     * @throws ApiError
     */
    public static triggerAgentRun(
        requestBody: TriggerAgentRunRequest,
        authorization?: (string | null),
    ): CancelablePromise<AgentRunRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/analytics/agent-runs',
            headers: {
                'Authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Agent Run
     * @param runId
     * @param authorization
     * @returns AgentRunRead Successful Response
     * @throws ApiError
     */
    public static getAgentRun(
        runId: string,
        authorization?: (string | null),
    ): CancelablePromise<AgentRunRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/analytics/agent-runs/{run_id}',
            path: {
                'run_id': runId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Lecturer Roster Risk
     * @param moduleId
     * @param authorization
     * @returns LecturerRosterRiskRead Successful Response
     * @throws ApiError
     */
    public static getLecturerRosterRisk(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<LecturerRosterRiskRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/lecturer/modules/{module_id}/analytics/roster-risk',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Lecturer Assessment Insights
     * @param moduleId
     * @param authorization
     * @returns LecturerAssessmentInsightsRead Successful Response
     * @throws ApiError
     */
    public static getLecturerAssessmentInsights(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<LecturerAssessmentInsightsRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/lecturer/modules/{module_id}/analytics/assessment-insights',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Student Module Risk
     * @param moduleId
     * @param authorization
     * @returns StudentRiskRead Successful Response
     * @throws ApiError
     */
    public static getStudentModuleRisk(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<StudentRiskRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/risk',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Student Workload Availability
     * @param moduleId
     * @param authorization
     * @returns StudentAvailabilityRead Successful Response
     * @throws ApiError
     */
    public static getStudentWorkloadAvailability(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<StudentAvailabilityRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/workload/availability',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Student Workload Availability
     * @param moduleId
     * @param requestBody
     * @param authorization
     * @returns StudentAvailabilityRead Successful Response
     * @throws ApiError
     */
    public static updateStudentWorkloadAvailability(
        moduleId: string,
        requestBody: StudentAvailabilityUpdate,
        authorization?: (string | null),
    ): CancelablePromise<StudentAvailabilityRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/student/modules/{module_id}/workload/availability',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Student Workload Plan
     * @param moduleId
     * @param authorization
     * @returns WorkloadPlanRead Successful Response
     * @throws ApiError
     */
    public static getStudentWorkloadPlan(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<WorkloadPlanRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/workload/plan',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Student Workload Calendar
     * @param planId
     * @param authorization
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportStudentWorkloadCalendar(
        planId: string,
        authorization?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/workload/plans/{plan_id}/calendar.ics',
            path: {
                'plan_id': planId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Generate Student Workload Plan
     * @param moduleId
     * @param authorization
     * @returns WorkloadPlanRead Successful Response
     * @throws ApiError
     */
    public static generateStudentWorkloadPlan(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<WorkloadPlanRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/modules/{module_id}/workload/plan:generate',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Lecturer Student Recommendations
     * @param moduleId
     * @param studentId
     * @param authorization
     * @returns LecturerStudentRecommendationsRead Successful Response
     * @throws ApiError
     */
    public static getLecturerStudentRecommendations(
        moduleId: string,
        studentId: string,
        authorization?: (string | null),
    ): CancelablePromise<LecturerStudentRecommendationsRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/lecturer/modules/{module_id}/analytics/students/{student_id}/recommendations',
            path: {
                'module_id': moduleId,
                'student_id': studentId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Mark Lecturer Recommendation Acted
     * @param recommendationId
     * @param authorization
     * @returns RecommendationActionRead Successful Response
     * @throws ApiError
     */
    public static markLecturerRecommendationActed(
        recommendationId: string,
        authorization?: (string | null),
    ): CancelablePromise<RecommendationActionRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/lecturer/recommendations/{recommendation_id}/mark-acted',
            path: {
                'recommendation_id': recommendationId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Dismiss Lecturer Recommendation
     * @param recommendationId
     * @param authorization
     * @returns RecommendationActionRead Successful Response
     * @throws ApiError
     */
    public static dismissLecturerRecommendation(
        recommendationId: string,
        authorization?: (string | null),
    ): CancelablePromise<RecommendationActionRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/lecturer/recommendations/{recommendation_id}/dismiss',
            path: {
                'recommendation_id': recommendationId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Student Module Recommendations
     * @param moduleId
     * @param authorization
     * @returns StudentRecommendationListRead Successful Response
     * @throws ApiError
     */
    public static getStudentModuleRecommendations(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<StudentRecommendationListRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/recommendations',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Student Module Forecast Advice
     * @param moduleId
     * @param authorization
     * @returns ForecastAdviceRead Successful Response
     * @throws ApiError
     */
    public static getStudentModuleForecastAdvice(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<ForecastAdviceRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/forecast-advice',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Student Recommendation Banner
     * @param authorization
     * @returns StudentRecommendationBannerRead Successful Response
     * @throws ApiError
     */
    public static getStudentRecommendationBanner(
        authorization?: (string | null),
    ): CancelablePromise<StudentRecommendationBannerRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/recommendations/banner',
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Dismiss Student Recommendation
     * @param recommendationId
     * @param authorization
     * @returns RecommendationActionRead Successful Response
     * @throws ApiError
     */
    public static dismissStudentRecommendation(
        recommendationId: string,
        authorization?: (string | null),
    ): CancelablePromise<RecommendationActionRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/recommendations/{recommendation_id}/dismiss',
            path: {
                'recommendation_id': recommendationId,
            },
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
