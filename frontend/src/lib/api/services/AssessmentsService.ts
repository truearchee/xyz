/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssessmentScopeResponse } from '../models/AssessmentScopeResponse';
import type { CreateAssessmentScopeRequest } from '../models/CreateAssessmentScopeRequest';
import type { PaginatedResponse_AssessmentScopeResponse_ } from '../models/PaginatedResponse_AssessmentScopeResponse_';
import type { UpdateAssessmentScopeRequest } from '../models/UpdateAssessmentScopeRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AssessmentsService {
    /**
     * Create Assessment Scope
     * @param moduleId
     * @param requestBody
     * @param authorization
     * @returns AssessmentScopeResponse Successful Response
     * @throws ApiError
     */
    public static createAssessmentScope(
        moduleId: string,
        requestBody: CreateAssessmentScopeRequest,
        authorization?: (string | null),
    ): CancelablePromise<AssessmentScopeResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/lecturer/modules/{module_id}/assessment-scopes',
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
     * List Assessment Scopes
     * @param moduleId
     * @param limit
     * @param offset
     * @param authorization
     * @returns PaginatedResponse_AssessmentScopeResponse_ Successful Response
     * @throws ApiError
     */
    public static listAssessmentScopes(
        moduleId: string,
        limit: number = 50,
        offset?: number,
        authorization?: (string | null),
    ): CancelablePromise<PaginatedResponse_AssessmentScopeResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/lecturer/modules/{module_id}/assessment-scopes',
            path: {
                'module_id': moduleId,
            },
            headers: {
                'Authorization': authorization,
            },
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Assessment Scope
     * @param scopeId
     * @param authorization
     * @returns AssessmentScopeResponse Successful Response
     * @throws ApiError
     */
    public static getAssessmentScope(
        scopeId: string,
        authorization?: (string | null),
    ): CancelablePromise<AssessmentScopeResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/lecturer/assessment-scopes/{scope_id}',
            path: {
                'scope_id': scopeId,
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
     * Update Assessment Scope
     * @param scopeId
     * @param requestBody
     * @param authorization
     * @returns AssessmentScopeResponse Successful Response
     * @throws ApiError
     */
    public static updateAssessmentScope(
        scopeId: string,
        requestBody: UpdateAssessmentScopeRequest,
        authorization?: (string | null),
    ): CancelablePromise<AssessmentScopeResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/lecturer/assessment-scopes/{scope_id}',
            path: {
                'scope_id': scopeId,
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
