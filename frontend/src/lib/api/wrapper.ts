'use client';

import {
  AdminService,
  ApiError,
  type AssignMemberRequest,
  ContentService,
  type CreateModuleRequest,
  type CreateUserRequest,
  MeService,
  ModulesService,
  OpenAPI,
  type ResetPasswordRequest,
} from './index';
import { consumeForcedBearerToken } from '../e2e/e2eAuthOverride';
import { getSupabaseBrowserClient } from '../supabase/client';

OpenAPI.BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const E2E_TEST_HOOKS_ENABLED =
  process.env.NEXT_PUBLIC_E2E_TEST_HOOKS === 'true';

export class AuthRequiredError extends Error {
  readonly status = 401;

  constructor(message = 'Authentication required') {
    super(message);
    this.name = 'AuthRequiredError';
  }
}

export class ForbiddenError extends Error {
  readonly status = 403;
  readonly body: unknown;

  constructor(message = 'Forbidden', body?: unknown) {
    super(message);
    this.name = 'ForbiddenError';
    this.body = body;
  }
}

OpenAPI.TOKEN = async () => {
  if (E2E_TEST_HOOKS_ENABLED) {
    const forcedToken = consumeForcedBearerToken();
    if (forcedToken) {
      return forcedToken;
    }
  }

  const supabase = getSupabaseBrowserClient();
  const { data, error } = await supabase.auth.getSession();
  if (error) {
    throw error;
  }

  return data.session?.access_token ?? '';
};

async function redirectToLogin() {
  const supabase = getSupabaseBrowserClient();
  await supabase.auth.signOut();

  if (typeof window !== 'undefined') {
    window.location.assign('/login');
  }
}

async function withAuthRecovery<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 401) {
      await redirectToLogin();
      throw new AuthRequiredError(caught.message);
    }

    if (caught instanceof ApiError && caught.status === 403) {
      throw new ForbiddenError(caught.message, caught.body);
    }

    throw caught;
  }
}

export const api = {
  admin: {
    assignMember: (moduleId: string, requestBody: AssignMemberRequest) =>
      withAuthRecovery(() =>
        AdminService.assignToModuleAdminModulesModuleIdMembersPost(
          moduleId,
          requestBody,
        ),
      ),
    createModule: (requestBody: CreateModuleRequest) =>
      withAuthRecovery(() =>
        AdminService.createModuleAdminModulesPost(requestBody),
      ),
    createUser: (requestBody: CreateUserRequest) =>
      withAuthRecovery(() => AdminService.createUserAdminUsersPost(requestBody)),
    deactivateUser: (userId: string) =>
      withAuthRecovery(() =>
        AdminService.deactivateUserAdminUsersUserIdDeactivatePost(userId),
      ),
    listModuleMembers: (moduleId: string) =>
      withAuthRecovery(() =>
        AdminService.listModuleMembersAdminModulesModuleIdMembersGet(moduleId),
      ),
    listModules: () =>
      withAuthRecovery(() => AdminService.listModulesAdminModulesGet()),
    listUsers: () => withAuthRecovery(() => AdminService.listUsersAdminUsersGet()),
    removeMember: (moduleId: string, userId: string) =>
      withAuthRecovery(() =>
        AdminService.removeFromModuleAdminModulesModuleIdMembersUserIdDelete(
          moduleId,
          userId,
        ),
      ),
    resetPassword: (userId: string, requestBody: ResetPasswordRequest) =>
      withAuthRecovery(() =>
        AdminService.resetPasswordAdminUsersUserIdResetPasswordPost(
          userId,
          requestBody,
        ),
      ),
  },
  content: {
    getAssetDownloadUrl: (moduleId: string, sectionId: string, assetId: string) =>
      withAuthRecovery(() =>
        ContentService.getAssetDownloadUrlModulesModuleIdSectionsSectionIdAssetsAssetIdDownloadUrlGet(
          moduleId,
          sectionId,
          assetId,
        ),
      ),
    getSection: (moduleId: string, sectionId: string) =>
      withAuthRecovery(() =>
        ContentService.getSectionModulesModuleIdSectionsSectionIdGet(
          moduleId,
          sectionId,
        ),
      ),
    listSections: (moduleId: string) =>
      withAuthRecovery(() =>
        ContentService.listSectionsModulesModuleIdSectionsGet(moduleId),
      ),
    publishSection: (moduleId: string, sectionId: string) =>
      withAuthRecovery(() =>
        ContentService.publishModulesModuleIdSectionsSectionIdPublishPost(
          moduleId,
          sectionId,
        ),
      ),
    uploadAsset: (moduleId: string, sectionId: string, file: File) =>
      withAuthRecovery(() =>
        ContentService.uploadAssetModulesModuleIdSectionsSectionIdAssetsPost(
          moduleId,
          sectionId,
          { file },
        ),
      ),
  },
  me: {
    get: () => withAuthRecovery(() => MeService.getMeMeGet()),
  },
  modules: {
    list: () => withAuthRecovery(() => ModulesService.listModulesModulesGet()),
  },
};
