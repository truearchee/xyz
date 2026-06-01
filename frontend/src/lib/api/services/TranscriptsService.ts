/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TranscriptMeta } from '../models/TranscriptMeta';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class TranscriptsService {
    /**
     * Upload Section Transcript
     * @param moduleId
     * @param sectionId
     * @param formData
     * @param authorization
     * @returns TranscriptMeta Successful Response
     * @throws ApiError
     */
    public static uploadSectionTranscript(
        moduleId: string,
        sectionId: string,
        formData: {
            file: Blob;
        },
        authorization?: (string | null),
    ): CancelablePromise<TranscriptMeta> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/modules/{module_id}/sections/{section_id}/transcript',
            path: {
                'module_id': moduleId,
                'section_id': sectionId,
            },
            headers: {
                'Authorization': authorization,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Section Transcript
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns TranscriptMeta Successful Response
     * @throws ApiError
     */
    public static getSectionTranscript(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<TranscriptMeta> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}/transcript',
            path: {
                'module_id': moduleId,
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
