import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getFirstTranscriptChunkText,
  getMembershipsForModule,
  getSectionsForModule,
  runPsqlJson,
  sqlLiteral,
  waitForSummariesSettled,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

/**
 * Stage 8.6b browser gate — Exam-prep mode (deterministic provider; route confirmed by the rule-11
 * exam-prep smoke). A student enters Exam prep from the WORKSPACE, picks a NAMED AssessmentScope (covered
 * weeks read-only), and the assistant discusses ONLY that scope grounded in the covered weeks' permitted
 * summaries. The conversation carries conversation_kind='exam_prep' (mode LABEL), the coordinator grounds
 * + writes feature='assistant', the quiz-pointer CTA reflects the real scope availability (the assistant
 * NEVER generates a quiz — no saved artifact), and another module's scope cannot be opened (404). The
 * existing general/lecture chat + homework are unaffected (their specs run in the same active suite).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const STUDENT2_EMAIL = 'student2_e2e@example.test';
const ANSWER_MARKER = 'concise study-assistant answer';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const TRANSCRIPT_FILE = 'sentinel-lecture.vtt';

test.setTimeout(300_000);
test.use({ actionTimeout: 20_000, navigationTimeout: 45_000 });

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };

async function waitForHooks(page: Page) {
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
}
async function signIn(page: Page, email: string, expectedPath: string) {
  await page.goto('/login');
  await waitForHooks(page);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(new RegExp(`${expectedPath}$`));
  await waitForHooks(page);
}
async function signInPage(context: BrowserContext, email: string, expectedPath: string): Promise<Page> {
  const page = await context.newPage();
  await signIn(page, email, expectedPath);
  return page;
}
async function getAccessToken(page: Page): Promise<string> {
  const session = (await page.evaluate(() => window.__xyzE2E!.getSession())) as {
    data: { session: { access_token: string } | null };
  };
  const token = session.data.session?.access_token;
  expect(token).toBeTruthy();
  return token as string;
}
async function createApiContext(token: string): Promise<APIRequestContext> {
  return playwrightRequest.newContext({
    baseURL: API_BASE_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
}
async function apiJson<T>(ctx: APIRequestContext, method: 'GET' | 'POST', path: string, body?: unknown): Promise<ApiResponse<T>> {
  const response = method === 'GET' ? await ctx.get(path) : await ctx.post(path, body === undefined ? undefined : { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}
async function apiUpload<T>(ctx: APIRequestContext, path: string, fileName: string, buffer: Buffer, mimeType: string): Promise<ApiResponse<T>> {
  const response = await ctx.post(path, { multipart: { file: { name: fileName, mimeType, buffer } } });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the Stage 8.6b gate');
  return runId;
}
function manifestPathForRunId(runId: string): string {
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) throw new Error(`Invalid E2E run id: ${runId}`);
  return resolve('tests/e2e/.runs', `${runId}.json`);
}
function recordManifestValue(runId: string, field: string, value: string) {
  const manifest = JSON.parse(readFileSync(manifestPathForRunId(runId), 'utf8')) as Record<string, string[] | string>;
  const current = Array.isArray(manifest[field]) ? (manifest[field] as string[]) : [];
  manifest[field] = [...new Set([...current, value])];
  writeFileSync(manifestPathForRunId(runId), `${JSON.stringify(manifest, null, 2)}\n`);
}
function recordMany(runId: string, field: string, values: string[]) {
  for (const value of values) recordManifestValue(runId, field, value);
}

function conversationKind(conversationId: string): string | null {
  return runPsqlJson(`SELECT to_json(conversation_kind)::text FROM assistant_conversations WHERE id = ${sqlLiteral(conversationId)}::uuid;`) as unknown as string | null;
}
function examPrepConversation(studentId: string, scopeId: string): { id: string; moduleId: string | null; scopeId: string | null } | null {
  return runPsqlJson(
    `SELECT json_build_object('id', id, 'moduleId', attached_module_id, 'scopeId', attached_assessment_scope_id)::text
     FROM assistant_conversations
     WHERE student_id = ${sqlLiteral(studentId)}::uuid AND conversation_kind = 'exam_prep'
       AND attached_assessment_scope_id = ${sqlLiteral(scopeId)}::uuid AND deleted_at IS NULL
     ORDER BY created_at DESC LIMIT 1;`,
  ) as unknown as { id: string; moduleId: string | null; scopeId: string | null } | null;
}
function completedGroundings(conversationId: string): string[] {
  return runPsqlJson(
    `SELECT coalesce(json_agg(grounding_status ORDER BY created_at), '[]')::text
     FROM assistant_messages WHERE conversation_id = ${sqlLiteral(conversationId)}::uuid
       AND role = 'assistant' AND status = 'completed';`,
  ) as unknown as string[];
}
function assistantLogFeatures(conversationId: string): string[] {
  return runPsqlJson(
    `SELECT coalesce(json_agg(DISTINCT l.feature), '[]')::text
     FROM assistant_messages m JOIN ai_request_logs l ON l.id = m.ai_request_log_id
     WHERE m.conversation_id = ${sqlLiteral(conversationId)}::uuid;`,
  ) as unknown as string[];
}
// Scoped to THIS run's fresh module — the standing student may have quiz attempts from the 5d/6d specs
// that run earlier in the full suite; the assertion is "the assistant created no quiz for THIS exam".
function quizAttemptCountForModule(studentId: string, moduleId: string): number {
  return runPsqlJson(
    `SELECT to_json(count(*)::int)::text FROM quiz_attempts qa
     JOIN quiz_definitions qd ON qd.id = qa.quiz_definition_id
     WHERE qa.student_id = ${sqlLiteral(studentId)}::uuid AND qd.module_id = ${sqlLiteral(moduleId)}::uuid;`,
  ) as unknown as number;
}

async function createModule(runId: string, adminContext: APIRequestContext, title: string) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) throw new Error('Standing lecturer/student E2E users are required');
  const create = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title,
    description: `8.6b gate ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    schedule: {
      courseStartDate: '2026-01-12',
      courseEndDate: '2026-05-01',
      weekStartDay: 'monday',
      sessionPattern: [{ weekday: 'monday', sectionType: 'lecture' }],
      quizDay: 'friday',
    },
  });
  expect(create.status).toBe(201);
  const moduleId = create.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);
  const assign = await apiJson(adminContext, 'POST', `/admin/modules/${moduleId}/members`, { userId: student.id, role: 'student' });
  expect(assign.status).toBe(201);
  recordMany(runId, 'membershipIds', getMembershipsForModule(moduleId).map((m: { id: string }) => m.id));
  const sections = getSectionsForModule(moduleId) as SectionRow[];
  recordMany(runId, 'sectionIds', sections.map((s) => s.id));
  return { moduleId, section: sections.filter((s) => s.type === 'lecture')[0] };
}

async function publishEmbedSummarize(runId: string, apiLecturer: APIRequestContext, moduleId: string, sectionId: string): Promise<string> {
  const upload = await apiUpload<{ id: string }>(apiLecturer, `/modules/${moduleId}/sections/${sectionId}/transcript`, TRANSCRIPT_FILE, readFileSync(resolve(TRANSCRIPT_DIR, TRANSCRIPT_FILE)), 'text/vtt');
  expect(upload.status).toBe(201);
  const transcriptId = getActiveTranscriptForSection(sectionId).id as string;
  recordManifestValue(runId, 'transcriptIds', transcriptId);
  const artifacts = await waitForTranscriptEmbedded(transcriptId, 120_000);
  recordMany(runId, 'ingestionJobIds', artifacts.jobs.map((j: { id: string }) => j.id));
  recordMany(runId, 'transcriptChunkIds', artifacts.counts.chunkIds);
  recordMany(runId, 'transcriptSegmentIds', artifacts.counts.segmentIds);
  if (artifacts.transcript?.storageKey) recordManifestValue(runId, 'storageKeys', artifacts.transcript.storageKey);
  // Exam-prep eligibility needs the detailed summary READY (resolve_section_eligibility).
  await waitForSummariesSettled(transcriptId, 120_000);
  const publish = await apiJson(apiLecturer, 'POST', `/modules/${moduleId}/sections/${sectionId}/publish`);
  expect(publish.status).toBe(200);
  return transcriptId;
}

async function ask(page: Page, text: string, expectedCompleted: number) {
  await page.getByTestId('workspace-input').fill(text);
  await page.getByTestId('workspace-send').click();
  await expect(page.locator('[data-testid="workspace-message-assistant"][data-state="completed"]')).toHaveCount(expectedCompleted, { timeout: 60_000 });
}

test('8.6b exam-prep browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminCtx = await browser.newContext();
  const lecturerCtx = await browser.newContext();
  const studentCtx = await browser.newContext();
  let apiStudent: APIRequestContext | null = null;

  try {
    const adminPage = await signInPage(adminCtx, ADMIN_EMAIL, '/admin');
    const apiAdmin = await createApiContext(await getAccessToken(adminPage));
    const moduleTitle = `Stage 8.6b Exam ${runId}-${Date.now()}`;
    const { moduleId, section } = await createModule(runId, apiAdmin, moduleTitle);

    const lecturerPage = await signInPage(lecturerCtx, LECTURER_EMAIL, '/lecturer');
    const apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    const transcriptId = await publishEmbedSummarize(runId, apiLecturer, moduleId, section.id);
    const chunkText = getFirstTranscriptChunkText(transcriptId) as string;
    const studentId = getAppUserByEmail(STUDENT_EMAIL).id as string;

    // lecturer creates a NAMED AssessmentScope covering week 1 (the seeded lecture)
    const scopeName = `Stage 8.6b Midterm ${runId}`;
    const scopeRes = await apiJson<{ id: string }>(apiLecturer, 'POST', `/lecturer/modules/${moduleId}/assessment-scopes`, { name: scopeName, coveredWeeks: [1] });
    expect([200, 201]).toContain(scopeRes.status);
    const scopeId = scopeRes.body.id;

    // ── student enters Exam prep from the WORKSPACE → picks the named scope → starts ──
    const page = await signInPage(studentCtx, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(page));
    await page.goto('/student/assistant');
    await expect(page.getByTestId('assistant-workspace')).toBeVisible();
    await page.getByTestId('assistant-new-examprep').click();
    await expect(page.getByTestId('assistant-examprep-picker')).toBeVisible();
    await page.getByTestId('assistant-examprep-module').filter({ hasText: moduleTitle }).click();
    const scopeRow = page.getByTestId('assistant-examprep-scope').filter({ hasText: scopeName });
    await expect(scopeRow).toContainText('weeks 1'); // covered weeks read-only
    await scopeRow.getByTestId('assistant-examprep-start').click();

    // ── routed to the conversation: mode LABEL + read-only scope pill + quiz CTA ──
    await expect(page).toHaveURL(/\/student\/assistant\/[0-9a-f-]+$/);
    const conversationId = page.url().split('/').pop() as string;
    await expect(page.getByTestId('assistant-mode-label')).toHaveText('Exam prep');
    await expect(page.getByTestId('assistant-context-pill')).toContainText(scopeName);
    await expect(page.getByTestId('assistant-context-pill')).toContainText('weeks 1');
    await expect(page.getByTestId('workspace-examprep-starters')).toBeVisible();
    await expect(page.locator('select')).toHaveCount(0); // mode is a LABEL, never a selector
    // the practice-quiz CTA is the REAL pointer (summaries are ready → available), and it only LINKS
    await expect(page.getByTestId('assistant-examprep-quiz-cta')).toHaveText('Practice with the exam-prep quiz');
    await expect(page.getByTestId('assistant-examprep-quiz-cta')).toHaveAttribute('href', `/student/modules/${moduleId}`);

    // ── grounded discussion of exactly that scope ──
    await ask(page, chunkText, 1);
    const reply = page.locator('[data-testid="workspace-message-assistant"][data-state="completed"]').first();
    await expect(reply).toContainText(ANSWER_MARKER);
    await expect(reply.getByTestId('workspace-basis-text')).toContainText('exam');

    // backend truth: exam_prep kind, grounded, logged feature='assistant'
    expect(conversationKind(conversationId)).toBe('exam_prep');
    expect(completedGroundings(conversationId)).toEqual(['lecture_grounded']);
    expect(assistantLogFeatures(conversationId)).toEqual(['assistant']);
    // no saved artifact: the assistant never started/generated a quiz for THIS exam (no attempt in its module)
    expect(quizAttemptCountForModule(studentId, moduleId)).toBe(0);
    const conv = examPrepConversation(studentId, scopeId);
    expect(conv?.id).toBe(conversationId);
    expect(conv?.scopeId).toBe(scopeId);

    // ── isolation: a scope in a module the student is NOT in cannot be opened (404, never 403) ──
    const otherTitle = `Stage 8.6b Other ${runId}-${Date.now()}`;
    const otherCreate = await apiJson<{ id: string }>(apiAdmin, 'POST', '/admin/modules', {
      title: otherTitle, description: 'isolation', ownerId: getAppUserByEmail(LECTURER_EMAIL).id, timezone: 'UTC',
      schedule: { courseStartDate: '2026-01-12', courseEndDate: '2026-05-01', weekStartDay: 'monday', sessionPattern: [{ weekday: 'monday', sectionType: 'lecture' }], quizDay: 'friday' },
    });
    expect(otherCreate.status).toBe(201);
    recordManifestValue(runId, 'moduleIds', otherCreate.body.id);
    recordMany(runId, 'sectionIds', (getSectionsForModule(otherCreate.body.id) as SectionRow[]).map((s) => s.id));
    const otherScope = await apiJson<{ id: string }>(apiLecturer, 'POST', `/lecturer/modules/${otherCreate.body.id}/assessment-scopes`, { name: 'Other Midterm', coveredWeeks: [1] });
    expect([200, 201]).toContain(otherScope.status);
    const crossScope = await apiJson(apiStudent, 'POST', '/student/assistant/conversations', { conversationKind: 'exam_prep', assessmentScopeId: otherScope.body.id });
    expect(crossScope.status).toBe(404); // student is not a member of the other module → pinned 404

    // ── the exam-prep chat persists in the workspace list (module title + "Exam prep" chip) ──
    await page.goto('/student/assistant');
    const row = page.getByTestId('assistant-conversation-row').filter({ hasText: moduleTitle });
    await expect(row).toBeVisible();
    await expect(row).toContainText('Exam prep');
  } finally {
    await apiStudent?.dispose();
    await adminCtx.close();
    await lecturerCtx.close();
    await studentCtx.close();
  }
});
