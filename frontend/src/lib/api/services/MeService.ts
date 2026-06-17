/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CurrentUserResponse } from '../models/CurrentUserResponse';
import type { UpdatePreferencesRequest } from '../models/UpdatePreferencesRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MeService {
    /**
     * Get Me
     * @param authorization
     * @returns CurrentUserResponse Successful Response
     * @throws ApiError
     */
    public static getMeMeGet(
        authorization?: (string | null),
    ): CancelablePromise<CurrentUserResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/me',
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Me Preferences
     * Update the caller's own preferences (Stage 7: glossary definition language). Self-scoped — a
     * user can only change their own row. New saves use the new language; existing entries keep theirs.
     * @param requestBody
     * @param authorization
     * @returns CurrentUserResponse Successful Response
     * @throws ApiError
     */
    public static updateMePreferencesMePreferencesPatch(
        requestBody: UpdatePreferencesRequest,
        authorization?: (string | null),
    ): CancelablePromise<CurrentUserResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/me/preferences',
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
