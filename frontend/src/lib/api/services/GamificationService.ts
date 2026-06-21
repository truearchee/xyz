/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GamificationRead } from '../models/GamificationRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class GamificationService {
    /**
     * Get Student Gamification
     * @param authorization
     * @returns GamificationRead Successful Response
     * @throws ApiError
     */
    public static getStudentGamification(
        authorization?: (string | null),
    ): CancelablePromise<GamificationRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/gamification',
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
