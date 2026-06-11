/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssignMemberRequest } from '../models/AssignMemberRequest';
import type { CreateModuleRequest } from '../models/CreateModuleRequest';
import type { CreateUserRequest } from '../models/CreateUserRequest';
import type { MaintenanceRunRead } from '../models/MaintenanceRunRead';
import type { MembershipResponse } from '../models/MembershipResponse';
import type { ModuleMemberResponse } from '../models/ModuleMemberResponse';
import type { ModuleResponse } from '../models/ModuleResponse';
import type { ReapStuckRowsRequest } from '../models/ReapStuckRowsRequest';
import type { ReconcileStorageRequest } from '../models/ReconcileStorageRequest';
import type { ResetPasswordRequest } from '../models/ResetPasswordRequest';
import type { StatusResponse } from '../models/StatusResponse';
import type { UserResponse } from '../models/UserResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminService {
    /**
     * Create User
     * @param requestBody
     * @param authorization
     * @returns UserResponse Successful Response
     * @throws ApiError
     */
    public static createUserAdminUsersPost(
        requestBody: CreateUserRequest,
        authorization?: (string | null),
    ): CancelablePromise<UserResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/users',
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
     * List Users
     * @param limit
     * @param offset
     * @param authorization
     * @returns UserResponse Successful Response
     * @throws ApiError
     */
    public static listUsersAdminUsersGet(
        limit: number = 50,
        offset?: number,
        authorization?: (string | null),
    ): CancelablePromise<Array<UserResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/users',
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
     * Get User
     * @param userId
     * @param authorization
     * @returns UserResponse Successful Response
     * @throws ApiError
     */
    public static getUserAdminUsersUserIdGet(
        userId: string,
        authorization?: (string | null),
    ): CancelablePromise<UserResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/users/{user_id}',
            path: {
                'user_id': userId,
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
     * Deactivate User
     * @param userId
     * @param authorization
     * @returns UserResponse Successful Response
     * @throws ApiError
     */
    public static deactivateUserAdminUsersUserIdDeactivatePost(
        userId: string,
        authorization?: (string | null),
    ): CancelablePromise<UserResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/users/{user_id}/deactivate',
            path: {
                'user_id': userId,
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
     * Reset Password
     * @param userId
     * @param requestBody
     * @param authorization
     * @returns StatusResponse Successful Response
     * @throws ApiError
     */
    public static resetPasswordAdminUsersUserIdResetPasswordPost(
        userId: string,
        requestBody: ResetPasswordRequest,
        authorization?: (string | null),
    ): CancelablePromise<StatusResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/users/{user_id}/reset-password',
            path: {
                'user_id': userId,
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
     * Create Module
     * @param requestBody
     * @param authorization
     * @returns ModuleResponse Successful Response
     * @throws ApiError
     */
    public static createModuleAdminModulesPost(
        requestBody: CreateModuleRequest,
        authorization?: (string | null),
    ): CancelablePromise<ModuleResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/modules',
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
     * List Modules
     * @param limit
     * @param offset
     * @param authorization
     * @returns ModuleResponse Successful Response
     * @throws ApiError
     */
    public static listModulesAdminModulesGet(
        limit: number = 50,
        offset?: number,
        authorization?: (string | null),
    ): CancelablePromise<Array<ModuleResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/modules',
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
     * Assign To Module
     * @param moduleId
     * @param requestBody
     * @param authorization
     * @returns MembershipResponse Successful Response
     * @throws ApiError
     */
    public static assignToModuleAdminModulesModuleIdMembersPost(
        moduleId: string,
        requestBody: AssignMemberRequest,
        authorization?: (string | null),
    ): CancelablePromise<MembershipResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/modules/{module_id}/members',
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
     * List Module Members
     * @param moduleId
     * @param authorization
     * @returns ModuleMemberResponse Successful Response
     * @throws ApiError
     */
    public static listModuleMembersAdminModulesModuleIdMembersGet(
        moduleId: string,
        authorization?: (string | null),
    ): CancelablePromise<Array<ModuleMemberResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/modules/{module_id}/members',
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
     * Remove From Module
     * @param moduleId
     * @param userId
     * @param authorization
     * @returns StatusResponse Successful Response
     * @throws ApiError
     */
    public static removeFromModuleAdminModulesModuleIdMembersUserIdDelete(
        moduleId: string,
        userId: string,
        authorization?: (string | null),
    ): CancelablePromise<StatusResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/admin/modules/{module_id}/members/{user_id}',
            path: {
                'module_id': moduleId,
                'user_id': userId,
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
     * Reap Stuck Rows
     * @param authorization
     * @param requestBody
     * @returns MaintenanceRunRead Successful Response
     * @throws ApiError
     */
    public static reapStuckRowsAdminMaintenanceReapStuckRowsPost(
        authorization?: (string | null),
        requestBody?: (ReapStuckRowsRequest | null),
    ): CancelablePromise<MaintenanceRunRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/maintenance/reap-stuck-rows',
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
     * Reconcile Storage
     * @param authorization
     * @param requestBody
     * @returns MaintenanceRunRead Successful Response
     * @throws ApiError
     */
    public static reconcileStorageAdminMaintenanceReconcileStoragePost(
        authorization?: (string | null),
        requestBody?: (ReconcileStorageRequest | null),
    ): CancelablePromise<MaintenanceRunRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/maintenance/reconcile-storage',
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
