/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActiveSummaryPreviewRead } from '../models/ActiveSummaryPreviewRead';
import type { TranscriptMeta } from '../models/TranscriptMeta';
import type { TranscriptProcessingStatus } from '../models/TranscriptProcessingStatus';
import type { TranscriptSummariesRead } from '../models/TranscriptSummariesRead';
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
    /**
     * Get Section Transcript Processing Status
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns TranscriptProcessingStatus Successful Response
     * @throws ApiError
     */
    public static getSectionTranscriptProcessingStatus(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<TranscriptProcessingStatus> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}/transcript-processing-status',
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
    /**
     * Retry Section Transcript Processing
     * @param moduleId
     * @param sectionId
     * @param transcriptId
     * @param authorization
     * @returns TranscriptProcessingStatus Successful Response
     * @throws ApiError
     */
    public static retrySectionTranscriptProcessing(
        moduleId: string,
        sectionId: string,
        transcriptId: string,
        authorization?: (string | null),
    ): CancelablePromise<TranscriptProcessingStatus> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/modules/{module_id}/sections/{section_id}/transcript/{transcript_id}/retry',
            path: {
                'module_id': moduleId,
                'section_id': sectionId,
                'transcript_id': transcriptId,
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
     * Get Section Transcript Summaries
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns TranscriptSummariesRead Successful Response
     * @throws ApiError
     */
    public static getSectionTranscriptSummaries(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<TranscriptSummariesRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}/transcript-summaries',
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
    /**
     * Get Section Active Summary Preview
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns ActiveSummaryPreviewRead Successful Response
     * @throws ApiError
     */
    public static getSectionActiveSummaryPreview(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<ActiveSummaryPreviewRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}/transcript-active-summary-preview',
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
