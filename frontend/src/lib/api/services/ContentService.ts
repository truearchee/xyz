/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssetDownloadUrl } from '../models/AssetDownloadUrl';
import type { SectionAssetListResponse } from '../models/SectionAssetListResponse';
import type { SectionAssetResponse } from '../models/SectionAssetResponse';
import type { SectionDetail } from '../models/SectionDetail';
import type { SectionListItem } from '../models/SectionListItem';
import type { SectionMetadataDetail } from '../models/SectionMetadataDetail';
import type { SectionMetadataPatchRequest } from '../models/SectionMetadataPatchRequest';
import type { StudentSectionDetail } from '../models/StudentSectionDetail';
import type { UpdateSectionNotesRequest } from '../models/UpdateSectionNotesRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ContentService {
    /**
     * List Sections
     * @param moduleId
     * @param authorization
     * @returns SectionListItem Successful Response
     * @throws ApiError
     */
    public static listSectionsModulesModuleIdSectionsGet(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<Array<SectionListItem>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections',
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
     * Get Section
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getSectionModulesModuleIdSectionsSectionIdGet(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<(SectionDetail | StudentSectionDetail)> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}',
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
            /**
             * Optional lab deadline set at upload time.
             */
            dueAt?: string;
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
     * Get Asset Download Url
     * @param moduleId
     * @param sectionId
     * @param assetId
     * @param authorization
     * @returns AssetDownloadUrl Successful Response
     * @throws ApiError
     */
    public static getAssetDownloadUrlModulesModuleIdSectionsSectionIdAssetsAssetIdDownloadUrlGet(
        moduleId: string,
        sectionId: string,
        assetId: string,
        authorization?: (string | null),
    ): CancelablePromise<AssetDownloadUrl> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}/assets/{asset_id}/download-url',
            path: {
                'module_id': moduleId,
                'section_id': sectionId,
                'asset_id': assetId,
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
     * Download Asset
     * @param moduleId
     * @param sectionId
     * @param assetId
     * @param authorization
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadAssetModulesModuleIdSectionsSectionIdAssetsAssetIdDownloadGet(
        moduleId: string,
        sectionId: string,
        assetId: string,
        authorization?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/modules/{module_id}/sections/{section_id}/assets/{asset_id}/download',
            path: {
                'module_id': moduleId,
                'section_id': sectionId,
                'asset_id': assetId,
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
    /**
     * Update Notes
     * @param moduleId
     * @param sectionId
     * @param requestBody
     * @param authorization
     * @returns SectionDetail Successful Response
     * @throws ApiError
     */
    public static updateNotesModulesModuleIdSectionsSectionIdNotesPatch(
        moduleId: string,
        sectionId: string,
        requestBody: UpdateSectionNotesRequest,
        authorization?: (string | null),
    ): CancelablePromise<SectionDetail> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/modules/{module_id}/sections/{section_id}/notes',
            path: {
                'module_id': moduleId,
                'section_id': sectionId,
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
     * Update Metadata
     * @param moduleId
     * @param sectionId
     * @param requestBody
     * @param authorization
     * @returns SectionMetadataDetail Successful Response
     * @throws ApiError
     */
    public static updateMetadataModulesModuleIdSectionsSectionIdMetadataPatch(
        moduleId: string,
        sectionId: string,
        requestBody: SectionMetadataPatchRequest,
        authorization?: (string | null),
    ): CancelablePromise<SectionMetadataDetail> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/modules/{module_id}/sections/{section_id}/metadata',
            path: {
                'module_id': moduleId,
                'section_id': sectionId,
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
     * Publish
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns SectionDetail Successful Response
     * @throws ApiError
     */
    public static publishModulesModuleIdSectionsSectionIdPublishPost(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<SectionDetail> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/modules/{module_id}/sections/{section_id}/publish',
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
     * Unpublish
     * @param moduleId
     * @param sectionId
     * @param authorization
     * @returns SectionDetail Successful Response
     * @throws ApiError
     */
    public static unpublishModulesModuleIdSectionsSectionIdUnpublishPost(
        moduleId: string,
        sectionId: string,
        authorization?: (string | null),
    ): CancelablePromise<SectionDetail> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/modules/{module_id}/sections/{section_id}/unpublish',
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
