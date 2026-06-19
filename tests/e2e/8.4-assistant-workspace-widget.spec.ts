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
  countActiveAssistantConversations,
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getAssistantConversationLifecycle,
  getAssistantConversations,
  getAssistantMessages,
  getFirstTranscriptChunkText,
  getMembershipsForModule,
  getSectionsForModule,
  insertSection,
  seedPendingAssistantTurn,
  seedProcessingTranscriptForSection,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

// Stage 8.4 browser gate (Option A — navigation/UX, no new AI surface). Proves: the inline lecture panel
// and the floating widget are a SINGLE source of truth for the same lecture conversation (a message sent
// in one is visible in the other; no duplicate row); the Workspace lists/opens/renames/soft-deletes only
// the caller's own chats with the exact retention copy; current-access-wins (unpublish → filtered + 404);
// delete-while-pending closes + 404s; and two students on the same lecture are fully isolated.
// Deterministic provider at the boundary (full gateway path runs, rule 11). No streaming (8.3).

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const STUDENT2_EMAIL = 'student2_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const TRANSCRIPT_FILE = 'sentinel-lecture.vtt';

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };

test.setTimeout(600_000);

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

async function apiJson<T>(
  context: APIRequestContext,
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response = method === 'GET' ? await context.get(path) : await context.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

async function apiUpload<T>(
  context: APIRequestContext,
  path: string,
  fileName: string,
  buffer: Buffer,
  mimeType: string,
): Promise<ApiResponse<T>> {
  const response = await context.post(path, { multipart: { file: { name: fileName, mimeType, buffer } } });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 8.4 gate');
  return runId;
}

type RunManifest = { [key: string]: string[] | string; runId: string };
function manifestPathForRunId(runId: string): string {
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) throw new Error(`Invalid E2E run id: ${runId}`);
  return resolve('tests/e2e/.runs', `${runId}.json`);
}
function recordManifestValue(runId: string, field: string, value: string) {
  const manifest = JSON.parse(readFileSync(manifestPathForRunId(runId), 'utf8')) as RunManifest;
  const current = Array.isArray(manifest[field]) ? manifest[field] : [];
  manifest[field] = [...new Set([...current, value])];
  writeFileSync(manifestPathForRunId(runId), `${JSON.stringify(manifest, null, 2)}\n`);
}
function recordMany(runId: string, field: string, values: string[]) {
  for (const value of values) recordManifestValue(runId, field, value);
}

function nthSectionOfType(sections: SectionRow[], type: 'lecture' | 'lab', index = 0): SectionRow {
  const matches = sections.filter((c) => c.type === type);
  const s = matches[index];
  if (!s) throw new Error(`Missing generated ${type} section #${index} (have ${matches.length})`);
  return s;
}

async function createModule(runId: string, adminContext: APIRequestContext, title: string) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  if (!owner?.id) throw new Error('Standing lecturer E2E user is required');
  const create = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title,
    description: `8.4 gate ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    schedule: {
      courseStartDate: '2026-01-12',
      courseEndDate: '2026-05-01',
      weekStartDay: 'monday',
      sessionPattern: [
        { weekday: 'monday', sectionType: 'lecture' },
        { weekday: 'tuesday', sectionType: 'lecture' },
        { weekday: 'wednesday', sectionType: 'lecture' },
      ],
      quizDay: 'friday',
    },
  });
  expect(create.status).toBe(201);
  const moduleId = create.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);
  return { moduleId, sections: getSectionsForModule(moduleId) as SectionRow[] };
}

async function assignStudent(adminContext: APIRequestContext, moduleId: string, email: string) {
  const student = getAppUserByEmail(email);
  if (!student?.id) throw new Error(`Standing student E2E user ${email} is required`);
  const assign = await apiJson(adminContext, 'POST', `/admin/modules/${moduleId}/members`, {
    userId: student.id,
    role: 'student',
  });
  expect(assign.status).toBe(201);
}

async function publish(api: APIRequestContext, moduleId: string, sectionId: string) {
  const r = await apiJson(api, 'POST', `/modules/${moduleId}/sections/${sectionId}/publish`);
  expect(r.status).toBe(200);
}

async function unpublish(api: APIRequestContext, moduleId: string, sectionId: string) {
  const r = await apiJson(api, 'POST', `/modules/${moduleId}/sections/${sectionId}/unpublish`);
  expect(r.status).toBe(200);
}

async function uploadAndEmbed(runId: string, apiLecturer: APIRequestContext, moduleId: string, sectionId: string) {
  const upload = await apiUpload<{ id: string }>(
    apiLecturer,
    `/modules/${moduleId}/sections/${sectionId}/transcript`,
    TRANSCRIPT_FILE,
    readFileSync(resolve(TRANSCRIPT_DIR, TRANSCRIPT_FILE)),
    'text/vtt',
  );
  expect(upload.status).toBe(201);
  const transcriptId = getActiveTranscriptForSection(sectionId).id;
  recordManifestValue(runId, 'transcriptIds', transcriptId);
  const artifacts = await waitForTranscriptEmbedded(transcriptId, 95_000);
  recordMany(runId, 'ingestionJobIds', artifacts.jobs.map((j: { id: string }) => j.id));
  recordMany(runId, 'transcriptChunkIds', artifacts.counts.chunkIds);
  recordMany(runId, 'transcriptSegmentIds', artifacts.counts.segmentIds);
}

async function startInlineChat(page: Page) {
  await page.getByTestId('assistant-start-chat').click();
  await expect(page.getByTestId('assistant-messages')).toBeVisible();
}

async function askInline(page: Page, text: string, expectedUserMessages: number) {
  await page.getByTestId('assistant-input').fill(text);
  await page.getByTestId('assistant-send').click();
  await expect(page.getByTestId('assistant-message-user')).toHaveCount(expectedUserMessages, { timeout: 60_000 });
  // a turn settles when no assistant bubble is still pending
  await expect(page.locator('[data-testid="assistant-message-assistant"][data-state="completed"]')).toHaveCount(
    expectedUserMessages,
    { timeout: 60_000 },
  );
}

function countUserMessagesWithContent(conversationId: string, content: string): number {
  return (getAssistantMessages(conversationId) as Array<{ role: string; content: string | null }>).filter(
    (message) => message.role === 'user' && message.content === content,
  ).length;
}

async function failNextAcceptedAssistantSend(page: Page) {
  await page.evaluate(() => {
    const originalFetch = window.fetch.bind(window);
    let shouldFail = true;
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : String(input);
      const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
      if (shouldFail && method === 'POST' && /\/student\/assistant\/conversations\/[^/]+\/messages$/.test(url)) {
        shouldFail = false;
        await originalFetch(input, init);
        throw new TypeError('Simulated send timeout after the backend accepted the request');
      }
      return originalFetch(input, init);
    };
  });
}

async function lectureUrl(moduleId: string, sectionId: string) {
  return `/student/modules/${moduleId}/sections/${sectionId}`;
}

test('8.4 single source of truth + workspace + rename + delete + isolation', async ({ browser }) => {
  const runId = requireRunId();
  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();
  let apiStudent: APIRequestContext | null = null;
  const student2Context = await browser.newContext();
  let apiStudent2: APIRequestContext | null = null;

  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    const apiAdmin = await createApiContext(await getAccessToken(adminPage));

    const a = await createModule(runId, apiAdmin, `Stage 8.4 Module ${runId}`);
    await assignStudent(apiAdmin, a.moduleId, STUDENT_EMAIL);
    await assignStudent(apiAdmin, a.moduleId, STUDENT2_EMAIL);
    recordMany(runId, 'membershipIds', getMembershipsForModule(a.moduleId).map((m: { id: string }) => m.id));
    recordMany(runId, 'sectionIds', a.sections.map((s) => s.id));
    const a1 = nthSectionOfType(a.sections, 'lecture', 0);
    const a2 = nthSectionOfType(a.sections, 'lecture', 1);

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    const apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    await uploadAndEmbed(runId, apiLecturer, a.moduleId, a1.id);
    await uploadAndEmbed(runId, apiLecturer, a.moduleId, a2.id);
    await publish(apiLecturer, a.moduleId, a1.id);
    await publish(apiLecturer, a.moduleId, a2.id);

    const studentId = getAppUserByEmail(STUDENT_EMAIL).id;
    const student2Id = getAppUserByEmail(STUDENT2_EMAIL).id;

    const page = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    await page.goto(await lectureUrl(a.moduleId, a1.id));

    // ── SINGLE SOURCE OF TRUTH: inline panel + floating widget = the SAME lecture conversation ──
    const a1GroundedQuestion = getFirstTranscriptChunkText(getActiveTranscriptForSection(a1.id).id);
    await expect(page.getByTestId('assistant-start-chat')).toBeVisible({ timeout: 30_000 });
    await startInlineChat(page);
    await askInline(page, a1GroundedQuestion, 1);
    expect(countActiveAssistantConversations(studentId, a1.id)).toBe(1);
    const a1Convs = getAssistantConversations(studentId, a1.id) as Array<{ id: string }>;
    expect(a1Convs).toHaveLength(1);
    const a1ConvId = a1Convs[0].id;

    // open the floating widget on the same lecture → it shows the SAME conversation + grounding basis
    await page.getByTestId('assistant-widget-button').click();
    await expect(page.getByTestId('assistant-widget-drawer')).toBeVisible();
    await expect(page.getByTestId('assistant-widget-context-pill')).toContainText(a1.title);
    await expect(page.locator('[data-testid="widget-basis"] summary').first()).toContainText(
      'Where did this come from?',
    );
    await expect(page.getByTestId('widget-messages').getByText(a1GroundedQuestion)).toBeVisible({
      timeout: 30_000,
    });

    // double-clicking send still creates exactly ONE user message (store-level idempotency guard)
    const widgetQuestion = 'Q-WIDGET double-click from the floating widget';
    await page.getByTestId('widget-input').fill(widgetQuestion);
    await page.getByTestId('widget-send').evaluate((button) => {
      button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      button.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    });
    await expect(page.getByTestId('widget-messages').getByText(widgetQuestion)).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.locator('[data-testid="widget-message-assistant"][data-state="completed"]')).toHaveCount(2, {
      timeout: 60_000,
    });
    expect(countUserMessagesWithContent(a1ConvId, widgetQuestion)).toBe(1);

    // two visible surfaces for the same conversation can race the same draft without duplicating it
    const twoSurfaceQuestion = 'Q-TWO-SURFACES same draft';
    await page.getByTestId('widget-input').fill(twoSurfaceQuestion);
    await expect(page.getByTestId('assistant-input')).toHaveValue(twoSurfaceQuestion);
    await page.evaluate(() => {
      document
        .querySelector('[data-testid="widget-send"]')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      document
        .querySelector('[data-testid="assistant-send"]')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    });
    await expect(page.getByTestId('widget-messages').getByText(twoSurfaceQuestion)).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.locator('[data-testid="widget-message-assistant"][data-state="completed"]')).toHaveCount(3, {
      timeout: 60_000,
    });
    expect(countUserMessagesWithContent(a1ConvId, twoSurfaceQuestion)).toBe(1);

    // retry after an accepted-but-timed-out send reuses the same idempotency key
    const retryQuestion = 'Q-RETRY after accepted timeout';
    await failNextAcceptedAssistantSend(page);
    await page.getByTestId('widget-input').fill(retryQuestion);
    await page.getByTestId('widget-send').click();
    await expect(page.getByTestId('assistant-widget-drawer').getByText('Couldn’t send your message — try again.')).toBeVisible({ timeout: 30_000 });
    await page.getByTestId('widget-send').click();
    await expect(page.getByTestId('widget-messages').getByText(retryQuestion)).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('[data-testid="widget-message-assistant"][data-state="completed"]')).toHaveCount(4, {
      timeout: 60_000,
    });
    expect(countUserMessagesWithContent(a1ConvId, retryQuestion)).toBe(1);

    // send from the widget → settles, and (shared store) the inline panel shows it too
    await page.getByTestId('assistant-widget-close').click();
    await expect(page.getByTestId('assistant-messages').getByText(retryQuestion)).toBeVisible();

    // exactly ONE active lecture_default conversation despite opening both entry points
    expect(countActiveAssistantConversations(studentId, a1.id)).toBe(1);

    // ── WORKSPACE: lists the chat, opens it, context pill + Open lecture ──
    // The persistent AppShell nav home (present on every student page, incl. this lecture page); the
    // dashboard's nav-assistant link only exists on /student.
    await page.getByTestId('shell-nav-assistant').click();
    await expect(page).toHaveURL(/\/student\/assistant$/);
    await expect(page.getByTestId('assistant-conversation-list')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('assistant-conversation-row').first()).toBeVisible({ timeout: 30_000 });
    await page.goto(`/student/assistant/${a1ConvId}`);
    await expect(page.getByTestId('assistant-context-pill')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('workspace-messages').getByText(a1GroundedQuestion)).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId('assistant-open-lecture')).toHaveAttribute(
      'href',
      await lectureUrl(a.moduleId, a1.id),
    );

    // ── RENAME: manual title persists across reload; titleSource flips to manual ──
    await page.getByTestId('assistant-rename').click();
    await page.getByTestId('assistant-rename-input').fill('My Renamed Exam Chat');
    await page.getByTestId('assistant-rename-save').click();
    await page.reload();
    await expect(page.getByText('My Renamed Exam Chat')).toBeVisible({ timeout: 30_000 });
    const lifecycle = getAssistantConversationLifecycle(a1ConvId) as { title: string; titleSource: string };
    expect(lifecycle.titleSource).toBe('manual');
    expect(lifecycle.title).toBe('My Renamed Exam Chat');

    // ── DELETE (on a2's chat): exact retention copy, no "permanently delete", drops + 404 ──
    await page.goto(await lectureUrl(a.moduleId, a2.id));
    await startInlineChat(page);
    await askInline(page, 'Q on lecture two', 1);
    const a2ConvId = (getAssistantConversations(studentId, a2.id) as Array<{ id: string }>)[0].id;
    await page.goto(`/student/assistant/${a2ConvId}`);
    await page.getByTestId('assistant-delete').click();
    const confirm = page.getByTestId('assistant-delete-confirm');
    await expect(confirm).toBeVisible();
    await expect(confirm).toContainText('this is not a permanent data purge');
    await expect(confirm).not.toContainText(/permanently delete/i);
    await page.getByTestId('assistant-delete-remove').click();
    await expect(page).toHaveURL(/\/student\/assistant$/, { timeout: 30_000 });
    expect(countActiveAssistantConversations(studentId, a2.id)).toBe(0);
    expect((getAssistantConversationLifecycle(a2ConvId) as { deletedAt: string | null }).deletedAt).not.toBeNull();
    // direct reopen of the deleted conversation → "no longer available"
    await page.goto(`/student/assistant/${a2ConvId}`);
    await expect(page.getByTestId('assistant-conversation-gone')).toBeVisible({ timeout: 30_000 });
    // reopen the LECTURE → a FRESH conversation (a new active row)
    await page.goto(await lectureUrl(a.moduleId, a2.id));
    await startInlineChat(page);
    expect(countActiveAssistantConversations(studentId, a2.id)).toBe(1);
    const a2Fresh = (getAssistantConversations(studentId, a2.id) as Array<{ id: string }>).filter(
      (c) => c.id !== a2ConvId,
    );
    expect(a2Fresh.length).toBe(1);

    // ── ISOLATION: a second student on the same lecture has their OWN chat; can't see student-1's ──
    const page2 = await signInPage(student2Context, STUDENT2_EMAIL, '/student');
    apiStudent2 = await createApiContext(await getAccessToken(page2));
    await page2.goto(await lectureUrl(a.moduleId, a1.id));
    await startInlineChat(page2);
    await expect(page2.getByTestId('assistant-empty')).toBeVisible(); // student-2's chat is empty + separate
    expect(countActiveAssistantConversations(student2Id, a1.id)).toBe(1);
    const s2Conv = (getAssistantConversations(student2Id, a1.id) as Array<{ id: string }>)[0];
    expect(s2Conv.id).not.toBe(a1ConvId);
    // student-2's workspace shows only their own chats (not student-1's renamed one)
    await page2.goto('/student/assistant');
    await expect(page2.getByText('My Renamed Exam Chat')).toHaveCount(0);
    // direct API access to student-1's conversation → 404 (don't reveal existence)
    const forbidden = await apiStudent2.get(`/student/assistant/conversations/${a1ConvId}`);
    expect(forbidden.status()).toBe(404);
  } finally {
    await apiStudent2?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
    await student2Context.close();
  }
});

test('8.4 access-revoked filtering + delete-while-pending + widget a11y', async ({ browser }) => {
  const runId = requireRunId();
  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();
  let apiStudent: APIRequestContext | null = null;

  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    const apiAdmin = await createApiContext(await getAccessToken(adminPage));
    const a = await createModule(runId, apiAdmin, `Stage 8.4 Revoke Module ${runId}`);
    await assignStudent(apiAdmin, a.moduleId, STUDENT_EMAIL);
    recordMany(runId, 'membershipIds', getMembershipsForModule(a.moduleId).map((m: { id: string }) => m.id));
    recordMany(runId, 'sectionIds', a.sections.map((s) => s.id));
    const s1 = nthSectionOfType(a.sections, 'lecture', 0);
    const s2 = nthSectionOfType(a.sections, 'lecture', 1);
    const s3 = nthSectionOfType(a.sections, 'lecture', 2);
    const unavailable = insertSection(a.moduleId, {
      type: 'lecture',
      title: `Unavailable assistant lecture ${runId}`,
      publishStatus: 'published',
    }) as SectionRow;
    recordManifestValue(runId, 'sectionIds', unavailable.id);

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    const apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    await uploadAndEmbed(runId, apiLecturer, a.moduleId, s1.id);
    await uploadAndEmbed(runId, apiLecturer, a.moduleId, s2.id);
    await publish(apiLecturer, a.moduleId, s1.id);
    await publish(apiLecturer, a.moduleId, s2.id);
    seedProcessingTranscriptForSection(s3.id, LECTURER_EMAIL);
    await publish(apiLecturer, a.moduleId, s3.id);

    const studentId = getAppUserByEmail(STUDENT_EMAIL).id;
    const page = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(page));

    // ── WIDGET READINESS GATE: processing/unavailable lectures do NOT create chats ──
    await page.goto(await lectureUrl(a.moduleId, s3.id));
    await page.getByTestId('assistant-widget-button').click();
    await expect(page.getByTestId('assistant-widget-readiness')).toContainText('still being prepared');
    expect(countActiveAssistantConversations(studentId, s3.id)).toBe(0);
    await page.getByTestId('assistant-widget-close').click();

    await page.goto(await lectureUrl(a.moduleId, unavailable.id));
    await page.getByTestId('assistant-widget-button').click();
    await expect(page.getByTestId('assistant-widget-readiness')).toContainText('isn’t available');
    expect(countActiveAssistantConversations(studentId, unavailable.id)).toBe(0);
    await page.getByTestId('assistant-widget-close').click();

    // start a chat on s1, then the lecturer unpublishes it → CURRENT ACCESS WINS
    await page.goto(await lectureUrl(a.moduleId, s1.id));
    await startInlineChat(page);
    await askInline(page, 'A question before the section is unpublished', 1);
    const s1ConvId = (getAssistantConversations(studentId, s1.id) as Array<{ id: string }>)[0].id;
    await unpublish(apiLecturer, a.moduleId, s1.id);

    await page.goto('/student/assistant');
    await expect(page.getByTestId('assistant-conversation-list').or(page.getByTestId('assistant-workspace-empty'))).toBeVisible({ timeout: 30_000 });
    // the unpublished section's chat is filtered out of the Workspace list
    await expect(page.getByText('A question before the section is unpublished')).toHaveCount(0);
    // direct open → no longer available (invariant C: 404, not 403)
    await page.goto(`/student/assistant/${s1ConvId}`);
    await expect(page.getByTestId('assistant-conversation-gone')).toBeVisible({ timeout: 30_000 });

    // ── DELETE WHILE PENDING (deterministic seeded pending turn; no worker resurrection) ──
    await page.goto(await lectureUrl(a.moduleId, s2.id));
    await startInlineChat(page);
    const s2ConvId = (getAssistantConversations(studentId, s2.id) as Array<{ id: string }>)[0].id;
    seedPendingAssistantTurn(s2ConvId, 'A pending question that will never complete');
    let delayedMessages = true;
    await page.route(`**/student/assistant/conversations/${s2ConvId}/messages**`, async (route) => {
      if (delayedMessages) {
        delayedMessages = false;
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      await route.continue();
    });
    await page.goto(`/student/assistant/${s2ConvId}`);
    await expect(page.getByTestId('workspace-send')).toBeDisabled();
    await expect(page.getByTestId('workspace-input')).toBeDisabled();
    await expect(page.getByTestId('workspace-messages').getByText('A pending question that will never complete')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('workspace-send')).toBeDisabled();
    await expect(page.getByTestId('workspace-input')).toBeDisabled();

    // A second open surface sees a 404 after external delete and transitions to gone instead of keeping stale pending UI.
    await page.goto(await lectureUrl(a.moduleId, s2.id));
    await startInlineChat(page);
    await page.getByTestId('assistant-widget-button').click();
    await expect(page.getByTestId('widget-messages').getByText('A pending question that will never complete')).toBeVisible({ timeout: 30_000 });
    const deleteResponse = await apiStudent!.delete(`/student/assistant/conversations/${s2ConvId}`);
    expect(deleteResponse.status()).toBe(204);
    await expect(page.getByTestId('widget-gone')).toBeVisible({ timeout: 30_000 });
    await page.goto(`/student/assistant/${s2ConvId}`);
    await expect(page.getByTestId('assistant-conversation-gone')).toBeVisible({ timeout: 30_000 });
    expect((getAssistantConversationLifecycle(s2ConvId) as { deletedAt: string | null }).deletedAt).not.toBeNull();

    // ── WIDGET a11y on a non-lecture page: drawer opens (recents), ESC closes + returns focus ──
    await page.goto('/student');
    const widgetButton = page.getByTestId('assistant-widget-button');
    await widgetButton.click();
    await expect(page.getByTestId('assistant-widget-drawer')).toBeVisible();
    await expect(page.getByTestId('assistant-widget-start-lecture')).toBeVisible();
    await expect(page.getByTestId('assistant-widget-open-workspace')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('assistant-widget-drawer')).toHaveCount(0);
    await expect(widgetButton).toBeFocused();
  } finally {
    await apiStudent?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
