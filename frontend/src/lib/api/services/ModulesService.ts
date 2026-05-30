/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModuleDetail } from '../models/ModuleDetail';
import type { ModuleSummary } from '../models/ModuleSummary';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ModulesService {
    /**
     * List Modules
     * @param authorization
     * @returns ModuleSummary Successful Response
     * @throws ApiError
     */
    public static listModulesModulesGet(
        authorization?: (string | null),
    ): CancelablePromise<Array<ModuleSummary>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules',
            headers: {
                'Authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Module
     * @param moduleId
     * @param authorization
     * @returns ModuleDetail Successful Response
     * @throws ApiError
     */
    public static getModuleModulesModuleIdGet(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<ModuleDetail> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}',
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
}
