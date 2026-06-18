'use client';

import {
  type ActiveSummaryPreviewRead,
  AdminService,
  type AnswerFeedback,
  type AnswerSubmission,
  ApiError,
  AssessmentsService,
  type AssessmentScopeResponse,
  type AssignMemberRequest,
  ContentService,
  type CreateAssessmentScopeRequest,
  type CreateModuleRequest,
  type CreateUserRequest,
  type ExamPrepScopeSummary,
  MeService,
  type ModuleScheduleInput,
  type ModuleSchedulePreviewResponse,
  ModulesService,
  OpenAPI,
  type PaginatedResponse_AssessmentScopeResponse_,
  type PaginatedResponse_MistakeBankItem_,
  type QuizAttemptForStudent,
  type QuizAttemptResult,
  type QuizAttemptsSummary,
  type QuizAvailabilityResponse,
  QuizService,
  type RecapScopeRequest,
  type ResetPasswordRequest,
  type SectionAssetListResponse,
  type SectionMetadataPatchRequest,
  type SectionMetadataDetail,
  type SectionWeekRead,
  type ScopeAvailabilityResponse,
  type StudentSectionListItem,
  type StudentSectionRead,
  type StudentSectionSummariesRead,
  StudentSummariesService,
  TranscriptsService,
  type TranscriptMeta,
  type TranscriptProcessingStatus,
  type TranscriptSummariesRead,
  type UpdateSectionNotesRequest,
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

function encodedContentPath(input: {
  moduleId: string;
  sectionId: string;
  assetId?: string;
}): string {
  const base = `/modules/${encodeURIComponent(input.moduleId)}/sections/${encodeURIComponent(
    input.sectionId,
  )}/assets`;
  if (!input.assetId) {
    return base;
  }
  return `${base}/${encodeURIComponent(input.assetId)}`;
}

function attachmentFileName(disposition: string | null, fallback: string): string {
  if (!disposition) {
    return fallback;
  }
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      return fallback;
    }
  }
  return disposition.match(/filename="([^"]+)"/i)?.[1] ?? fallback;
}

async function downloadAttachmentAsset(
  moduleId: string,
  sectionId: string,
  assetId: string,
  fallbackFileName: string,
): Promise<{ blob: Blob; fileName: string }> {
  const tokenResolver = OpenAPI.TOKEN;
  const token =
    typeof tokenResolver === 'function'
      ? await tokenResolver({ method: 'GET', url: '' })
      : tokenResolver;

  if (!token) {
    await redirectToLogin();
    throw new AuthRequiredError();
  }

  const response = await fetch(
    `${OpenAPI.BASE}${encodedContentPath({ assetId, moduleId, sectionId })}/download`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );

  if (response.ok) {
    return {
      blob: await response.blob(),
      fileName: attachmentFileName(
        response.headers.get('Content-Disposition'),
        fallbackFileName,
      ),
    };
  }

  if (response.status === 401) {
    await redirectToLogin();
    throw new AuthRequiredError(response.statusText || 'Unauthorized');
  }
  const body = await response.text();
  if (response.status === 403) {
    throw new ForbiddenError(response.statusText || 'Forbidden', body);
  }
  throw new Error(body || response.statusText || 'Download failed');
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
    previewModuleSchedule: (
      requestBody: ModuleScheduleInput,
    ): Promise<ModuleSchedulePreviewResponse> =>
      withAuthRecovery(() =>
        AdminService.previewModuleSectionsAdminModulesPreviewSectionsPost(
          requestBody,
        ),
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
    listSectionsByWeek: (
      moduleId: string,
      coveredWeeks?: Array<number> | null,
      includeUnstamped = false,
    ): Promise<Array<SectionWeekRead>> =>
      withAuthRecovery(() =>
        AdminService.listAdminModuleSectionsByWeekAdminModulesModuleIdSectionsByWeekGet(
          moduleId,
          coveredWeeks,
          includeUnstamped,
        ),
      ),
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
    downloadAttachmentAsset,
    getSection: (moduleId: string, sectionId: string) =>
      withAuthRecovery(() =>
        ContentService.getSectionModulesModuleIdSectionsSectionIdGet(
          moduleId,
          sectionId,
        ),
      ),
    listAssets: (
      moduleId: string,
      sectionId: string,
    ): Promise<SectionAssetListResponse> =>
      withAuthRecovery(() =>
        ContentService.listAssetsModulesModuleIdSectionsSectionIdAssetsGet(
          moduleId,
          sectionId,
        ),
      ),
    listSections: (moduleId: string) =>
      withAuthRecovery(() =>
        ContentService.listSectionsModulesModuleIdSectionsGet(moduleId),
      ),
    listSectionsByWeek: (
      moduleId: string,
      coveredWeeks?: Array<number> | null,
      includeUnstamped = false,
    ): Promise<Array<SectionWeekRead>> =>
      withAuthRecovery(() =>
        ContentService.listSectionsByWeekModulesModuleIdSectionsByWeekGet(
          moduleId,
          coveredWeeks,
          includeUnstamped,
        ),
      ),
    publishSection: (moduleId: string, sectionId: string) =>
      withAuthRecovery(() =>
        ContentService.publishModulesModuleIdSectionsSectionIdPublishPost(
          moduleId,
          sectionId,
        ),
      ),
    unpublishSection: (moduleId: string, sectionId: string) =>
      withAuthRecovery(() =>
        ContentService.unpublishModulesModuleIdSectionsSectionIdUnpublishPost(
          moduleId,
          sectionId,
        ),
      ),
    updateNotes: (
      moduleId: string,
      sectionId: string,
      requestBody: UpdateSectionNotesRequest,
    ) =>
      withAuthRecovery(() =>
        ContentService.updateNotesModulesModuleIdSectionsSectionIdNotesPatch(
          moduleId,
          sectionId,
          requestBody,
        ),
      ),
    updateMetadata: (
      moduleId: string,
      sectionId: string,
      requestBody: SectionMetadataPatchRequest,
    ): Promise<SectionMetadataDetail> =>
      withAuthRecovery(() =>
        ContentService.updateMetadataModulesModuleIdSectionsSectionIdMetadataPatch(
          moduleId,
          sectionId,
          requestBody,
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
    get: (moduleId: string) =>
      withAuthRecovery(() => ModulesService.getModuleModulesModuleIdGet(moduleId)),
    list: () => withAuthRecovery(() => ModulesService.listModulesModulesGet()),
  },
  assessments: {
    create: (
      moduleId: string,
      requestBody: CreateAssessmentScopeRequest,
    ): Promise<AssessmentScopeResponse> =>
      withAuthRecovery(() =>
        AssessmentsService.createAssessmentScope(moduleId, requestBody),
      ),
    list: (
      moduleId: string,
      limit = 50,
      offset = 0,
    ): Promise<PaginatedResponse_AssessmentScopeResponse_> =>
      withAuthRecovery(() =>
        AssessmentsService.listAssessmentScopes(moduleId, limit, offset),
      ),
    get: (scopeId: string): Promise<AssessmentScopeResponse> =>
      withAuthRecovery(() => AssessmentsService.getAssessmentScope(scopeId)),
  },
  quiz: {
    getAvailability: (sectionId: string): Promise<QuizAvailabilityResponse> =>
      withAuthRecovery(() => QuizService.getStudentQuizAvailability(sectionId)),
    start: (sectionId: string): Promise<QuizAttemptForStudent> =>
      withAuthRecovery(() => QuizService.startStudentQuiz(sectionId)),
    getAttempt: (attemptId: string): Promise<QuizAttemptForStudent> =>
      withAuthRecovery(() => QuizService.getStudentQuizAttempt(attemptId)),
    retryAttempt: (attemptId: string): Promise<QuizAttemptForStudent> =>
      withAuthRecovery(() => QuizService.retryStudentQuizAttempt(attemptId)),
    answer: (
      attemptId: string,
      requestBody: AnswerSubmission,
    ): Promise<AnswerFeedback> =>
      withAuthRecovery(() =>
        QuizService.answerStudentQuizQuestion(attemptId, requestBody),
      ),
    complete: (attemptId: string): Promise<QuizAttemptResult> =>
      withAuthRecovery(() => QuizService.completeStudentQuiz(attemptId)),
    getAttemptsSummary: (sectionId: string): Promise<QuizAttemptsSummary> =>
      withAuthRecovery(() => QuizService.getStudentQuizAttemptsSummary(sectionId)),
    getRecapAvailability: (
      moduleId: string,
      requestBody: RecapScopeRequest,
    ): Promise<ScopeAvailabilityResponse> =>
      withAuthRecovery(() =>
        QuizService.getStudentRecapAvailability(moduleId, requestBody),
      ),
    startRecap: (
      moduleId: string,
      requestBody: RecapScopeRequest,
    ): Promise<QuizAttemptForStudent> =>
      withAuthRecovery(() =>
        QuizService.startStudentRecapQuiz(moduleId, requestBody),
      ),
    listExamPrepScopes: (moduleId: string): Promise<Array<ExamPrepScopeSummary>> =>
      withAuthRecovery(() => QuizService.listStudentExamPrepScopes(moduleId)),
    startExamPrep: (scopeId: string): Promise<QuizAttemptForStudent> =>
      withAuthRecovery(() => QuizService.startStudentExamPrepQuiz(scopeId)),
    listMistakesBank: (
      moduleId: string,
      limit = 50,
      offset = 0,
    ): Promise<PaginatedResponse_MistakeBankItem_> =>
      withAuthRecovery(() =>
        QuizService.listStudentMistakesBank(moduleId, limit, offset),
      ),
    startMistakesBank: (moduleId: string): Promise<QuizAttemptForStudent> =>
      withAuthRecovery(() => QuizService.startStudentMistakesBank(moduleId)),
  },
  studentSummaries: {
    listSections: (moduleId: string): Promise<Array<StudentSectionListItem>> =>
      withAuthRecovery(() =>
        StudentSummariesService.getStudentModuleSections(moduleId),
      ),
    getSection: (sectionId: string): Promise<StudentSectionRead> =>
      withAuthRecovery(() => StudentSummariesService.getStudentSection(sectionId)),
    getSummaries: (sectionId: string): Promise<StudentSectionSummariesRead> =>
      withAuthRecovery(() =>
        StudentSummariesService.getStudentSectionSummaries(sectionId),
      ),
  },
  transcripts: {
    getActive: (
      moduleId: string,
      sectionId: string,
    ): Promise<TranscriptMeta> =>
      withAuthRecovery(() =>
        TranscriptsService.getSectionTranscript(moduleId, sectionId),
      ),
    getProcessingStatus: (
      moduleId: string,
      sectionId: string,
    ): Promise<TranscriptProcessingStatus> =>
      withAuthRecovery(() =>
        TranscriptsService.getSectionTranscriptProcessingStatus(
          moduleId,
          sectionId,
        ),
      ),
    getSummaries: (
      moduleId: string,
      sectionId: string,
    ): Promise<TranscriptSummariesRead> =>
      withAuthRecovery(() =>
        TranscriptsService.getSectionTranscriptSummaries(moduleId, sectionId),
      ),
    getActiveSummaryPreview: (
      moduleId: string,
      sectionId: string,
    ): Promise<ActiveSummaryPreviewRead> =>
      withAuthRecovery(() =>
        TranscriptsService.getSectionActiveSummaryPreview(moduleId, sectionId),
      ),
    retry: (
      moduleId: string,
      sectionId: string,
      transcriptId: string,
    ): Promise<TranscriptProcessingStatus> =>
      withAuthRecovery(() =>
        TranscriptsService.retrySectionTranscriptProcessing(
          moduleId,
          sectionId,
          transcriptId,
        ),
      ),
  },
};
