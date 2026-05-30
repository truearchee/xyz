/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SectionAssetListResponse } from '../models/SectionAssetListResponse';
import type { SectionAssetResponse } from '../models/SectionAssetResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ContentService {
    /**
     * List Assets
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns SectionAssetListResponse Successful Response
     * @throws ApiError
     */
    public static listAssetsModulesModuleIdSectionsSectionIdAssetsGet(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<SectionAssetListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}/assets',
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
     * Upload Asset
     * @param moduleId
     * @param sectionId
     * @param formData
     * @param authorization
     * @returns SectionAssetResponse Successful Response
     * @throws ApiError
     */
    public static uploadAssetModulesModuleIdSectionsSectionIdAssetsPost(
        moduleId: string,
        sectionId: string,
        formData: {
            file: Blob;
        },
        authorization?: (string | null),
    ): CancelablePromise<SectionAssetResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/modules/{module_id}/sections/{section_id}/assets',
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
     * Replace Asset
     * @param moduleId
     * @param sectionId
     * @param assetId
     * @param formData
     * @param authorization
     * @returns SectionAssetResponse Successful Response
     * @throws ApiError
     */
    public static replaceAssetModulesModuleIdSectionsSectionIdAssetsAssetIdPut(
        moduleId: string,
        sectionId: string,
        assetId: string,
        formData: {
            file: Blob;
        },
        authorization?: (string | null),
    ): CancelablePromise<SectionAssetResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/modules/{module_id}/sections/{section_id}/assets/{asset_id}',
            path: {
                'module_id': moduleId,
                'section_id': sectionId,
                'asset_id': assetId,
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
}
