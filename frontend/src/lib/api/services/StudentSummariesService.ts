/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StudentSectionListItem } from '../models/StudentSectionListItem';
import type { StudentSectionRead } from '../models/StudentSectionRead';
import type { StudentSectionSummariesRead } from '../models/StudentSectionSummariesRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudentSummariesService {
    /**
     * Get Student Module Sections
     * @param moduleId
     * @param authorization
     * @returns StudentSectionListItem Successful Response
     * @throws ApiError
     */
    public static getStudentModuleSections(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<Array<StudentSectionListItem>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/modules/{module_id}/sections',
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
     * Get Student Section
     * @param sectionId
     * @param authorization
     * @returns StudentSectionRead Successful Response
     * @throws ApiError
     */
    public static getStudentSection(
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<StudentSectionRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/sections/{section_id}',
            path: {
                'section_id': sectionId,
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
     * Get Student Section Summaries Route
     * @param sectionId
     * @param authorization
     * @returns StudentSectionSummariesRead Successful Response
     * @throws ApiError
     */
    public static getStudentSectionSummaries(
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<StudentSectionSummariesRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/sections/{section_id}/summaries',
            path: {
                'section_id': sectionId,
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
