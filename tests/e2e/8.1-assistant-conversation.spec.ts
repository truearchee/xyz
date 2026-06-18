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
  countAssistantConversations,
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getAssistantConversations,
  getAssistantRequestLogFeatures,
  getMembershipsForModule,
  getSectionsForModule,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

// Stage 8.1 browser gate. From a lecture page a student starts a conversation attached to that lecture,
// asks questions, sees real (deterministic-provider) answers through the gateway, and they persist +
// reload. A different lecture's chat is a SEPARATE conversation. "Start chat" in two tabs at once never
// creates two lecture_default conversations. Every assistant turn writes an AIRequestLog feature=assistant
// row. Deterministic provider at the boundary; the FULL gateway path runs (rule 11). No streaming (8.3),
// no grounding (8.2).

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const TRANSCRIPT_FILE = 'sentinel-lecture.vtt';
// The deterministic provider's canned assistant answer (platform/llm/provider.py).
const ANSWER_MARKER = 'concise study-assistant answer';

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };

test.setTimeout(240_000);

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
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 8.1 gate');
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

async function createModule(runId: string, adminContext: APIRequestContext, title: string, assignStudent: boolean) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) throw new Error('Standing lecturer/student E2E users are required');
  const create = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title,
    description: `8.1 gate ${runId}`,
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
        { weekday: 'thursday', sectionType: 'lab' },
      ],
      quizDay: 'friday',
    },
  });
  expect(create.status).toBe(201);
  const moduleId = create.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);
  if (assignStudent) {
    const assign = await apiJson<{ id: string }>(adminContext, 'POST', `/admin/modules/${moduleId}/members`, {
      userId: student.id,
      role: 'student',
    });
    expect(assign.status).toBe(201);
  }
  recordMany(runId, 'membershipIds', getMembershipsForModule(moduleId).map((m: { id: string }) => m.id));
  const sections = getSectionsForModule(moduleId) as SectionRow[];
  recordMany(runId, 'sectionIds', sections.map((s) => s.id));
  return { moduleId, sections };
}

async function publish(api: APIRequestContext, moduleId: string, sectionId: string) {
  const r = await apiJson(api, 'POST', `/modules/${moduleId}/sections/${sectionId}/publish`);
  expect(r.status).toBe(200);
}

async function uploadAndEmbed(
  runId: string,
  apiLecturer: APIRequestContext,
  moduleId: string,
  sectionId: string,
) {
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
  if (artifacts.transcript?.storageKey) recordManifestValue(runId, 'storageKeys', artifacts.transcript.storageKey);
}

// Wait until the chat shows exactly `n` completed assistant answers (the pending bubble flips on poll).
async function waitForAnswers(page: Page, n: number) {
  await expect(
    page.locator('[data-testid="assistant-message-assistant"][data-state="completed"]'),
  ).toHaveCount(n, { timeout: 60_000 });
}

async function startChat(page: Page) {
  await page.getByTestId('assistant-start-chat').click();
  await expect(page.getByTestId('assistant-messages')).toBeVisible();
}

async function ask(page: Page, text: string, expectedAnswers: number) {
  await page.getByTestId('assistant-input').fill(text);
  await page.getByTestId('assistant-send').click();
  await waitForAnswers(page, expectedAnswers);
}

async function expectNoHorizontalScrollAt375(page: Page) {
  await page.setViewportSize({ width: 375, height: 812 });
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const root = document.documentElement;
          const body = document.body;
          return Math.max(root.scrollWidth, body?.scrollWidth ?? 0) <= root.clientWidth;
        }),
      { timeout: 5_000 },
    )
    .toBe(true);
}

test('8.1 assistant conversation foundation browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();

  let apiStudent: APIRequestContext | null = null;
  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    const apiAdmin = await createApiContext(await getAccessToken(adminPage));

    // Module A — student assigned (two lectures). Module B — student NOT assigned (unassigned 404).
    const a = await createModule(runId, apiAdmin, `Stage 8.1 Module A ${runId}`, true);
    const b = await createModule(runId, apiAdmin, `Stage 8.1 Module B ${runId}`, false);
    const a1 = nthSectionOfType(a.sections, 'lecture', 0); // Lecture A
    const a2 = nthSectionOfType(a.sections, 'lecture', 1); // Lecture B (separate conversation)
    const b1 = nthSectionOfType(b.sections, 'lecture', 0); // module B (unassigned)

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    const apiLecturer = await createApiContext(await getAccessToken(lecturerPage));

    // Make all three lectures retrieval-ready (chunks + embeddings) and published.
    await uploadAndEmbed(runId, apiLecturer, a.moduleId, a1.id);
    await uploadAndEmbed(runId, apiLecturer, a.moduleId, a2.id);
    await uploadAndEmbed(runId, apiLecturer, b.moduleId, b1.id);
    await publish(apiLecturer, a.moduleId, a1.id);
    await publish(apiLecturer, a.moduleId, a2.id);
    await publish(apiLecturer, b.moduleId, b1.id);

    const studentId = getAppUserByEmail(STUDENT_EMAIL).id;

    // ── two-tab race on Lecture A: both press "Start chat" → exactly one lecture_default conversation
    const racePage1 = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(racePage1));
    const racePage2 = await studentContext.newPage();
    await racePage1.goto(`/student/modules/${a.moduleId}/sections/${a1.id}`);
    await racePage2.goto(`/student/modules/${a.moduleId}/sections/${a1.id}`);
    await expect(racePage1.getByTestId('assistant-start-chat')).toBeVisible({ timeout: 30_000 });
    await expect(racePage2.getByTestId('assistant-start-chat')).toBeVisible({ timeout: 30_000 });
    await Promise.all([startChat(racePage1), startChat(racePage2)]);
    expect(countAssistantConversations(studentId, a1.id)).toBe(1);
    await racePage2.close();

    // ── Lecture A: ask two questions; both Q&A persist
    const page = racePage1;
    await ask(page, 'Q1: What is this lecture about?', 1);
    await ask(page, 'Q2: Can you explain that more simply?', 2);
    await expect(page.getByTestId('assistant-message-user')).toHaveCount(2);
    await expect(page.getByText('Q1: What is this lecture about?')).toBeVisible();
    await expect(page.getByText('Q2: Can you explain that more simply?')).toBeVisible();
    await expect(
      page.locator('[data-testid="assistant-message-assistant"][data-state="completed"]').first(),
    ).toContainText(ANSWER_MARKER);

    // ── reload → re-open chat → both Q&A still shown (persistence)
    await page.reload();
    await startChat(page);
    await expect(page.getByText('Q1: What is this lecture about?')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Q2: Can you explain that more simply?')).toBeVisible();
    await waitForAnswers(page, 2);

    // ── Lecture B (a2): separate conversation — does NOT show Lecture A's messages
    await page.goto(`/student/modules/${a.moduleId}/sections/${a2.id}`);
    await startChat(page);
    await expect(page.getByTestId('assistant-empty')).toBeVisible();
    await expect(page.getByText('Q1: What is this lecture about?')).toHaveCount(0);
    await ask(page, 'Different lecture question', 1);

    // ── back to Lecture A: its conversation is intact
    await page.goto(`/student/modules/${a.moduleId}/sections/${a1.id}`);
    await startChat(page);
    await expect(page.getByText('Q1: What is this lecture about?')).toBeVisible({ timeout: 30_000 });
    await waitForAnswers(page, 2);
    await expectNoHorizontalScrollAt375(page);

    // ── DB: the conversation carries kind + attached lecture; every assistant turn wrote feature=assistant
    const convs = getAssistantConversations(studentId, a1.id) as Array<{
      id: string;
      conversationKind: string;
      attachedSectionId: string;
    }>;
    expect(convs).toHaveLength(1);
    expect(convs[0].conversationKind).toBe('lecture_default');
    expect(convs[0].attachedSectionId).toBe(a1.id);
    const features = getAssistantRequestLogFeatures(convs[0].id) as string[];
    expect(features.length).toBeGreaterThanOrEqual(2);
    expect(features.every((f) => f === 'assistant')).toBe(true);

    // ── unassigned student → no assistant access to module B's lecture (404, not 403)
    const unassigned = await apiStudent.get(`/student/sections/${b1.id}/assistant/availability`);
    expect(unassigned.status()).toBe(404);
  } finally {
    await apiStudent?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
