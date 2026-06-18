/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProgressDashboardRead } from '../models/ProgressDashboardRead';
import type { ProgressModuleDetail } from '../models/ProgressModuleDetail';
import type { TargetGradeRequest } from '../models/TargetGradeRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ProgressService {
    /**
     * Get Progress Dashboard
     * @param authorization
     * @returns ProgressDashboardRead Successful Response
     * @throws ApiError
     */
    public static getStudentProgressDashboard(
        authorization?: (string | null),
    ): CancelablePromise<ProgressDashboardRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/progress',
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Module Progress
     * @param moduleId
     * @param authorization
     * @returns ProgressModuleDetail Successful Response
     * @throws ApiError
     */
    public static getStudentModuleProgress(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<ProgressModuleDetail> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/progress',
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
     * Set Target Grade
     * @param moduleId
     * @param requestBody
     * @param authorization
     * @returns ProgressModuleDetail Successful Response
     * @throws ApiError
     */
    public static setStudentTargetGrade(
        moduleId: string,
        requestBody: TargetGradeRequest,
        authorization?: (string | null),
    ): CancelablePromise<ProgressModuleDetail> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/student/modules/{module_id}/target-grade',
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
}
