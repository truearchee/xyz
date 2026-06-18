/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FolderCreateRequest } from '../models/FolderCreateRequest';
import type { FolderUpdateRequest } from '../models/FolderUpdateRequest';
import type { GlossaryEntryDetail } from '../models/GlossaryEntryDetail';
import type { GlossaryEntryRead } from '../models/GlossaryEntryRead';
import type { GlossaryFolderRead } from '../models/GlossaryFolderRead';
import type { ManualEntryRequest } from '../models/ManualEntryRequest';
import type { PaginatedResponse_GlossaryEntryRead_ } from '../models/PaginatedResponse_GlossaryEntryRead_';
import type { PracticeAnswerFeedback } from '../models/PracticeAnswerFeedback';
import type { PracticeAnswerRequest } from '../models/PracticeAnswerRequest';
import type { PracticeAvailability } from '../models/PracticeAvailability';
import type { PracticeResult } from '../models/PracticeResult';
import type { PracticeSessionState } from '../models/PracticeSessionState';
import type { SaveHighlightRequest } from '../models/SaveHighlightRequest';
import type { SaveResponse } from '../models/SaveResponse';
import type { StartPracticeRequest } from '../models/StartPracticeRequest';
import type { UpdateEntryRequest } from '../models/UpdateEntryRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class GlossaryService {
    /**
     * Save Highlight
     * @param requestBody
     * @param authorization
     * @returns SaveResponse Successful Response
     * @throws ApiError
     */
    public static saveGlossaryHighlight(
        requestBody: SaveHighlightRequest,
        authorization?: (string | null),
    ): CancelablePromise<SaveResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/glossary/highlight',
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
     * Create Entry
     * @param requestBody
     * @param authorization
     * @returns SaveResponse Successful Response
     * @throws ApiError
     */
    public static createGlossaryEntry(
        requestBody: ManualEntryRequest,
        authorization?: (string | null),
    ): CancelablePromise<SaveResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/glossary/entries',
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
     * List Entries
     * @param subjectId
     * @param folderId
     * @param status
     * @param limit
     * @param offset
     * @param authorization
     * @returns PaginatedResponse_GlossaryEntryRead_ Successful Response
     * @throws ApiError
     */
    public static listGlossaryEntries(
        subjectId?: (string | null),
        folderId?: (string | null),
        status: string = 'active',
        limit: number = 50,
        offset?: number,
        authorization?: (string | null),
    ): CancelablePromise<PaginatedResponse_GlossaryEntryRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/glossary/entries',
            headers: {
                'Authorization': authorization,
            },
            query: {
                'subjectId': subjectId,
                'folderId': folderId,
                'status': status,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Entry
     * @param entryId
     * @param authorization
     * @returns GlossaryEntryDetail Successful Response
     * @throws ApiError
     */
    public static getGlossaryEntry(
        entryId: string,
        authorization?: (string | null),
    ): CancelablePromise<GlossaryEntryDetail> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/glossary/entries/{entry_id}',
            path: {
                'entry_id': entryId,
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
     * Update Entry
     * @param entryId
     * @param requestBody
     * @param authorization
     * @returns GlossaryEntryRead Successful Response
     * @throws ApiError
     */
    public static updateGlossaryEntry(
        entryId: string,
        requestBody: UpdateEntryRequest,
        authorization?: (string | null),
    ): CancelablePromise<GlossaryEntryRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/student/glossary/entries/{entry_id}',
            path: {
                'entry_id': entryId,
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
     * Delete Entry
     * @param entryId
     * @param authorization
     * @returns void
     * @throws ApiError
     */
    public static deleteGlossaryEntry(
        entryId: string,
        authorization?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/student/glossary/entries/{entry_id}',
            path: {
                'entry_id': entryId,
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
     * List Folders
     * @param authorization
     * @returns GlossaryFolderRead Successful Response
     * @throws ApiError
     */
    public static listGlossaryFolders(
        authorization?: (string | null),
    ): CancelablePromise<Array<GlossaryFolderRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/glossary/folders',
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Folder
     * @param requestBody
     * @param authorization
     * @returns GlossaryFolderRead Successful Response
     * @throws ApiError
     */
    public static createGlossaryFolder(
        requestBody: FolderCreateRequest,
        authorization?: (string | null),
    ): CancelablePromise<GlossaryFolderRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/glossary/folders',
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
     * Update Folder
     * @param folderId
     * @param requestBody
     * @param authorization
     * @returns GlossaryFolderRead Successful Response
     * @throws ApiError
     */
    public static updateGlossaryFolder(
        folderId: string,
        requestBody: FolderUpdateRequest,
        authorization?: (string | null),
    ): CancelablePromise<GlossaryFolderRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/student/glossary/folders/{folder_id}',
            path: {
                'folder_id': folderId,
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
     * Delete Folder
     * @param folderId
     * @param authorization
     * @returns void
     * @throws ApiError
     */
    public static deleteGlossaryFolder(
        folderId: string,
        authorization?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/student/glossary/folders/{folder_id}',
            path: {
                'folder_id': folderId,
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
     * Practice Availability
     * @param mode
     * @param scope
     * @param subjectId
     * @param authorization
     * @returns PracticeAvailability Successful Response
     * @throws ApiError
     */
    public static getGlossaryPracticeAvailability(
        mode: string,
        scope: string = 'all',
        subjectId?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<PracticeAvailability> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/glossary/practice/availability',
            headers: {
                'Authorization': authorization,
            },
            query: {
                'mode': mode,
                'scope': scope,
                'subjectId': subjectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Practice Start
     * @param requestBody
     * @param authorization
     * @returns PracticeSessionState Successful Response
     * @throws ApiError
     */
    public static startGlossaryPractice(
        requestBody: StartPracticeRequest,
        authorization?: (string | null),
    ): CancelablePromise<PracticeSessionState> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/glossary/practice/start',
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
     * Practice Session
     * @param sessionId
     * @param authorization
     * @returns PracticeSessionState Successful Response
     * @throws ApiError
     */
    public static getGlossaryPracticeSession(
        sessionId: string,
        authorization?: (string | null),
    ): CancelablePromise<PracticeSessionState> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/student/glossary/practice/{session_id}',
            path: {
                'session_id': sessionId,
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
     * Practice Answer
     * @param sessionId
     * @param requestBody
     * @param authorization
     * @returns PracticeAnswerFeedback Successful Response
     * @throws ApiError
     */
    public static answerGlossaryPractice(
        sessionId: string,
        requestBody: PracticeAnswerRequest,
        authorization?: (string | null),
    ): CancelablePromise<PracticeAnswerFeedback> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/glossary/practice/{session_id}/answer',
            path: {
                'session_id': sessionId,
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
     * Practice Complete
     * @param sessionId
     * @param authorization
     * @returns PracticeResult Successful Response
     * @throws ApiError
     */
    public static completeGlossaryPractice(
        sessionId: string,
        authorization?: (string | null),
    ): CancelablePromise<PracticeResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/student/glossary/practice/{session_id}/complete',
            path: {
                'session_id': sessionId,
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
