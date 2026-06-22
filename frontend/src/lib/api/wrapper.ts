'use client';

import {
  type ActiveSummaryPreviewRead,
  AdminService,
  AnalyticsService,
  type AgentRunRead,
  type AnswerFeedback,
  type AnswerSubmission,
  ApiError,
  AssessmentsService,
  type AssessmentScopeResponse,
  type AssignMemberRequest,
  type AssistantAvailabilityResponse,
  AssistantService,
  type ConversationListItem,
  type ConversationRead,
  type CreateConversationRequest,
  type KeysetPage_MessageRead_,
  type LecturerAssessmentInsightsRead,
  type LecturerRosterRiskRead,
  type LecturerStudentRecommendationsRead,
  type MessageRead,
  type PaginatedResponse_ConversationListItem_,
  type RenameConversationRequest,
  type SendMessageRequest,
  type SendMessageResponse,
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
  type ProgressDashboardRead,
  type ProgressModuleDetail,
  ProgressService,
  GamificationService,
  type GamificationRead,
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
  type StudentRiskRead,
  type ForecastAdviceRead,
  type StudentAvailabilityRead,
  type StudentAvailabilityUpdate,
  type RecommendationActionRead,
  type StudentRecommendationBannerRead,
  type StudentRecommendationListRead,
  StudentSummariesService,
  TranscriptsService,
  type TranscriptMeta,
  type TranscriptProcessingStatus,
  type TranscriptSummariesRead,
  type TriggerAgentRunRequest,
  type UpdateSectionNotesRequest,
  GlossaryService,
  type FolderCreateRequest,
  type FolderUpdateRequest,
  type GlossaryEntryDetail,
  type GlossaryEntryRead,
  type GlossaryFolderRead,
  type ManualEntryRequest,
  type PaginatedResponse_GlossaryEntryRead_,
  type PracticeAnswerFeedback,
  type PracticeAnswerRequest,
  type PracticeAvailability,
  type PracticeResult,
  type PracticeSessionState,
  type SaveHighlightRequest,
  type SaveResponse,
  type StartPracticeRequest,
  type TargetGradeRequest,
  type UpdateEntryRequest,
  type UpdatePreferencesRequest,
  type WorkloadPlanRead,
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

async function downloadWorkloadPlanCalendar(
  planId: string,
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
    `${OpenAPI.BASE}/student/workload/plans/${encodeURIComponent(planId)}/calendar.ics`,
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
        `xyz-lms-workload-plan-${planId}.ics`,
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
  throw new Error(body || response.statusText || 'Calendar export failed');
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
    updatePreferences: (requestBody: UpdatePreferencesRequest) =>
      withAuthRecovery(() =>
        MeService.updateMePreferencesMePreferencesPatch(requestBody),
      ),
  },
  glossary: {
    saveHighlight: (requestBody: SaveHighlightRequest): Promise<SaveResponse> =>
      withAuthRecovery(() => GlossaryService.saveGlossaryHighlight(requestBody)),
    createEntry: (requestBody: ManualEntryRequest): Promise<SaveResponse> =>
      withAuthRecovery(() => GlossaryService.createGlossaryEntry(requestBody)),
    listEntries: (params?: {
      subjectId?: string | null;
      folderId?: string | null;
      status?: string;
      limit?: number;
      offset?: number;
    }): Promise<PaginatedResponse_GlossaryEntryRead_> =>
      withAuthRecovery(() =>
        GlossaryService.listGlossaryEntries(
          params?.subjectId ?? undefined,
          params?.folderId ?? undefined,
          params?.status ?? 'active',
          params?.limit ?? 50,
          params?.offset ?? 0,
        ),
      ),
    getEntry: (entryId: string): Promise<GlossaryEntryDetail> =>
      withAuthRecovery(() => GlossaryService.getGlossaryEntry(entryId)),
    updateEntry: (
      entryId: string,
      requestBody: UpdateEntryRequest,
    ): Promise<GlossaryEntryRead> =>
      withAuthRecovery(() => GlossaryService.updateGlossaryEntry(entryId, requestBody)),
    deleteEntry: (entryId: string): Promise<void> =>
      withAuthRecovery(() => GlossaryService.deleteGlossaryEntry(entryId)),
    listFolders: (): Promise<Array<GlossaryFolderRead>> =>
      withAuthRecovery(() => GlossaryService.listGlossaryFolders()),
    createFolder: (requestBody: FolderCreateRequest): Promise<GlossaryFolderRead> =>
      withAuthRecovery(() => GlossaryService.createGlossaryFolder(requestBody)),
    updateFolder: (
      folderId: string,
      requestBody: FolderUpdateRequest,
    ): Promise<GlossaryFolderRead> =>
      withAuthRecovery(() => GlossaryService.updateGlossaryFolder(folderId, requestBody)),
    deleteFolder: (folderId: string): Promise<void> =>
      withAuthRecovery(() => GlossaryService.deleteGlossaryFolder(folderId)),
    practice: {
      availability: (
        mode: string,
        scope: string,
        subjectId?: string | null,
      ): Promise<PracticeAvailability> =>
        withAuthRecovery(() =>
          GlossaryService.getGlossaryPracticeAvailability(mode, scope, subjectId ?? undefined),
        ),
      start: (requestBody: StartPracticeRequest): Promise<PracticeSessionState> =>
        withAuthRecovery(() => GlossaryService.startGlossaryPractice(requestBody)),
      getSession: (sessionId: string): Promise<PracticeSessionState> =>
        withAuthRecovery(() => GlossaryService.getGlossaryPracticeSession(sessionId)),
      answer: (
        sessionId: string,
        requestBody: PracticeAnswerRequest,
      ): Promise<PracticeAnswerFeedback> =>
        withAuthRecovery(() => GlossaryService.answerGlossaryPractice(sessionId, requestBody)),
      complete: (sessionId: string): Promise<PracticeResult> =>
        withAuthRecovery(() => GlossaryService.completeGlossaryPractice(sessionId)),
    },
  },
  modules: {
    get: (moduleId: string) =>
      withAuthRecovery(() => ModulesService.getModuleModulesModuleIdGet(moduleId)),
    list: () => withAuthRecovery(() => ModulesService.listModulesModulesGet()),
  },
  progress: {
    getDashboard: (): Promise<ProgressDashboardRead> =>
      withAuthRecovery(() => ProgressService.getStudentProgressDashboard()),
    getModule: (moduleId: string): Promise<ProgressModuleDetail> =>
      withAuthRecovery(() => ProgressService.getStudentModuleProgress(moduleId)),
    setTargetGrade: (
      moduleId: string,
      requestBody: TargetGradeRequest,
    ): Promise<ProgressModuleDetail> =>
      withAuthRecovery(() =>
        ProgressService.setStudentTargetGrade(moduleId, requestBody),
      ),
  },
  gamification: {
    get: (): Promise<GamificationRead> =>
      withAuthRecovery(() => GamificationService.getStudentGamification()),
  },
  analytics: {
    triggerAgentRun: (requestBody: TriggerAgentRunRequest): Promise<AgentRunRead> =>
      withAuthRecovery(() => AnalyticsService.triggerAgentRun(requestBody)),
    getAgentRun: (runId: string): Promise<AgentRunRead> =>
      withAuthRecovery(() => AnalyticsService.getAgentRun(runId)),
    getLecturerRosterRisk: (moduleId: string): Promise<LecturerRosterRiskRead> =>
      withAuthRecovery(() => AnalyticsService.getLecturerRosterRisk(moduleId)),
    getLecturerAssessmentInsights: (
      moduleId: string,
    ): Promise<LecturerAssessmentInsightsRead> =>
      withAuthRecovery(() =>
        AnalyticsService.getLecturerAssessmentInsights(moduleId),
      ),
    getStudentRisk: (moduleId: string): Promise<StudentRiskRead> =>
      withAuthRecovery(() => AnalyticsService.getStudentModuleRisk(moduleId)),
    getStudentForecastAdvice: (moduleId: string): Promise<ForecastAdviceRead> =>
      withAuthRecovery(() =>
        AnalyticsService.getStudentModuleForecastAdvice(moduleId),
      ),
    getStudentWorkloadAvailability: (
      moduleId: string,
    ): Promise<StudentAvailabilityRead> =>
      withAuthRecovery(() =>
        AnalyticsService.getStudentWorkloadAvailability(moduleId),
      ),
    updateStudentWorkloadAvailability: (
      moduleId: string,
      requestBody: StudentAvailabilityUpdate,
    ): Promise<StudentAvailabilityRead> =>
      withAuthRecovery(() =>
        AnalyticsService.updateStudentWorkloadAvailability(moduleId, requestBody),
      ),
    getStudentWorkloadPlan: (moduleId: string): Promise<WorkloadPlanRead> =>
      withAuthRecovery(() => AnalyticsService.getStudentWorkloadPlan(moduleId)),
    generateStudentWorkloadPlan: (moduleId: string): Promise<WorkloadPlanRead> =>
      withAuthRecovery(() => AnalyticsService.generateStudentWorkloadPlan(moduleId)),
    downloadWorkloadPlanCalendar,
    getLecturerStudentRecommendations: (
      moduleId: string,
      studentId: string,
    ): Promise<LecturerStudentRecommendationsRead> =>
      withAuthRecovery(() =>
        AnalyticsService.getLecturerStudentRecommendations(moduleId, studentId),
      ),
    markLecturerRecommendationActed: (
      recommendationId: string,
    ): Promise<RecommendationActionRead> =>
      withAuthRecovery(() =>
        AnalyticsService.markLecturerRecommendationActed(recommendationId),
      ),
    dismissLecturerRecommendation: (
      recommendationId: string,
    ): Promise<RecommendationActionRead> =>
      withAuthRecovery(() =>
        AnalyticsService.dismissLecturerRecommendation(recommendationId),
      ),
    getStudentModuleRecommendations: (
      moduleId: string,
    ): Promise<StudentRecommendationListRead> =>
      withAuthRecovery(() =>
        AnalyticsService.getStudentModuleRecommendations(moduleId),
      ),
    getStudentRecommendationBanner: (): Promise<StudentRecommendationBannerRead> =>
      withAuthRecovery(() => AnalyticsService.getStudentRecommendationBanner()),
    dismissStudentRecommendation: (
      recommendationId: string,
    ): Promise<RecommendationActionRead> =>
      withAuthRecovery(() =>
        AnalyticsService.dismissStudentRecommendation(recommendationId),
      ),
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
  assistant: {
    getAvailability: (sectionId: string): Promise<AssistantAvailabilityResponse> =>
      withAuthRecovery(() =>
        AssistantService.getStudentAssistantAvailability(sectionId),
      ),
    openConversation: (sectionId: string): Promise<ConversationRead> =>
      withAuthRecovery(() =>
        AssistantService.openStudentAssistantConversation(sectionId),
      ),
    // 8.6a: create (or resume) a mode conversation — homework_help in 8.6a. Idempotent server-side.
    createConversation: (
      requestBody: CreateConversationRequest,
    ): Promise<ConversationRead> =>
      withAuthRecovery(() =>
        AssistantService.createStudentAssistantConversation(requestBody),
      ),
    listConversations: (
      limit = 30,
      offset = 0,
    ): Promise<PaginatedResponse_ConversationListItem_> =>
      withAuthRecovery(() =>
        AssistantService.listStudentAssistantConversations(limit, offset),
      ),
    getConversation: (conversationId: string): Promise<ConversationListItem> =>
      withAuthRecovery(() =>
        AssistantService.getStudentAssistantConversation(conversationId),
      ),
    listMessages: (
      conversationId: string,
      before?: string,
      limit = 30,
    ): Promise<KeysetPage_MessageRead_> =>
      withAuthRecovery(() =>
        AssistantService.listStudentAssistantMessages(conversationId, limit, before),
      ),
    send: (
      conversationId: string,
      requestBody: SendMessageRequest,
    ): Promise<SendMessageResponse> =>
      withAuthRecovery(() =>
        AssistantService.sendStudentAssistantMessage(conversationId, requestBody),
      ),
    retry: (messageId: string): Promise<MessageRead> =>
      withAuthRecovery(() =>
        AssistantService.retryStudentAssistantMessage(messageId),
      ),
    rename: (
      conversationId: string,
      requestBody: RenameConversationRequest,
    ): Promise<ConversationRead> =>
      withAuthRecovery(() =>
        AssistantService.renameStudentAssistantConversation(conversationId, requestBody),
      ),
    deleteConversation: (conversationId: string): Promise<void> =>
      withAuthRecovery(() =>
        AssistantService.deleteStudentAssistantConversation(conversationId),
      ),
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
