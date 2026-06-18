import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Locator,
  type Page,
} from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getAssistantConversations,
  getAssistantMessageGrounding,
  getFirstTranscriptChunkText,
  getMembershipsForModule,
  getSectionsForModule,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

// Stage 8.2 browser gate — server-side single-lecture grounding. A student asks a lecture's own chunk
// text verbatim and gets a GROUNDED answer with a safe "Where did this come from?" basis; a different
// study question is honestly flagged "Not from this lecture"; an unrelated question is redirected with no
// label; a LAB section grounds too; and an unassigned section is 404. groundingStatus is asserted at the
// DB layer (backend-derived, never parsed from prose). Deterministic embedding encoder (identical text →
// distance 0) + deterministic LLM provider; the FULL retrieval + gateway path runs (rules 9/11).

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const TRANSCRIPT_FILE = 'sentinel-lecture.vtt';

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };
type GroundingRow = { role: string; status: string; groundingStatus: string | null };

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
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 8.2 gate');
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
    description: `8.2 gate ${runId}`,
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

// Upload + embed a transcript and return the active transcript id (so the gate can read a chunk verbatim).
async function uploadAndEmbed(
  runId: string,
  apiLecturer: APIRequestContext,
  moduleId: string,
  sectionId: string,
): Promise<string> {
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
  return transcriptId;
}

async function startChat(page: Page) {
  await page.getByTestId('assistant-start-chat').click();
  await expect(page.getByTestId('assistant-messages')).toBeVisible();
}

// Wait until exactly `n` completed assistant answers are shown, then return the nth (0-based) bubble.
async function ask(page: Page, text: string, expectedAnswers: number): Promise<Locator> {
  await page.getByTestId('assistant-input').fill(text);
  await page.getByTestId('assistant-send').click();
  const completed = page.locator('[data-testid="assistant-message-assistant"][data-state="completed"]');
  await expect(completed).toHaveCount(expectedAnswers, { timeout: 60_000 });
  return completed.nth(expectedAnswers - 1);
}

async function expectGrounded(bubble: Locator, basisContains: string) {
  await expect(bubble.getByTestId('assistant-not-from-lecture')).toHaveCount(0); // grounded → no label
  const basis = bubble.getByTestId('assistant-basis');
  await expect(basis.getByText('Where did this come from?')).toBeVisible();
  await basis.getByText('Where did this come from?').click(); // expand the collapsed disclosure
  const text = bubble.getByTestId('assistant-basis-text');
  await expect(text).toBeVisible();
  await expect(text).toContainText(basisContains);
}

async function expectGeneral(bubble: Locator) {
  await expect(bubble.getByTestId('assistant-not-from-lecture')).toBeVisible();
  await expect(bubble.getByTestId('assistant-not-from-lecture')).toHaveText('Not from this lecture');
  const basis = bubble.getByTestId('assistant-basis');
  await basis.getByText('Where did this come from?').click();
  await expect(bubble.getByTestId('assistant-basis-text')).toContainText('No relevant lecture context');
}

async function expectRedirect(bubble: Locator) {
  await expect(bubble.getByTestId('assistant-not-from-lecture')).toHaveCount(0); // no label
  await expect(bubble.getByTestId('assistant-basis')).toHaveCount(0); // no basis line for a redirect
}

function groundingStatuses(conversationId: string): Array<string | null> {
  const rows = getAssistantMessageGrounding(conversationId) as GroundingRow[];
  return rows.filter((r) => r.role === 'assistant').map((r) => r.groundingStatus);
}

test('8.2 assistant grounding browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();

  let apiStudent: APIRequestContext | null = null;
  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    const apiAdmin = await createApiContext(await getAccessToken(adminPage));

    // Module A — student assigned (a lecture + a lab). Module B — student NOT assigned (unassigned 404).
    const a = await createModule(runId, apiAdmin, `Stage 8.2 Module A ${runId}`, true);
    const b = await createModule(runId, apiAdmin, `Stage 8.2 Module B ${runId}`, false);
    const lecture = nthSectionOfType(a.sections, 'lecture', 0);
    const lab = nthSectionOfType(a.sections, 'lab', 0);
    const bSection = nthSectionOfType(b.sections, 'lecture', 0);

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    const apiLecturer = await createApiContext(await getAccessToken(lecturerPage));

    const lectureTranscriptId = await uploadAndEmbed(runId, apiLecturer, a.moduleId, lecture.id);
    const labTranscriptId = await uploadAndEmbed(runId, apiLecturer, a.moduleId, lab.id);
    await uploadAndEmbed(runId, apiLecturer, b.moduleId, bSection.id);
    await publish(apiLecturer, a.moduleId, lecture.id);
    await publish(apiLecturer, a.moduleId, lab.id);
    await publish(apiLecturer, b.moduleId, bSection.id);

    const studentId = getAppUserByEmail(STUDENT_EMAIL).id;
    // The exact normalized chunk text — asked verbatim → deterministic distance 0 → grounded.
    const lectureChunk = getFirstTranscriptChunkText(lectureTranscriptId);
    const labChunk = getFirstTranscriptChunkText(labTranscriptId);

    const page = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(page));

    // ── LECTURE: grounded → general → redirect, all in one conversation ──────────────────────────
    await page.goto(`/student/modules/${a.moduleId}/sections/${lecture.id}`);
    await expect(page.getByTestId('assistant-start-chat')).toBeVisible({ timeout: 30_000 });
    await startChat(page);

    const grounded = await ask(page, lectureChunk, 1);
    await expectGrounded(grounded, 'Based on this lecture');
    await expect(grounded.getByTestId('assistant-basis-text')).toContainText(lecture.title);

    const general = await ask(page, 'Explain the Riemann hypothesis in one short paragraph.', 2);
    await expectGeneral(general);

    const redirect = await ask(page, 'What movie should I watch this weekend?', 3);
    await expectRedirect(redirect);

    // DB truth (decision 3): grounding is backend-derived, in order.
    const lectureConv = (getAssistantConversations(studentId, lecture.id) as Array<{ id: string }>)[0];
    expect(groundingStatuses(lectureConv.id)).toEqual([
      'lecture_grounded',
      'general_not_from_lecture',
      'educational_redirect',
    ]);

    // ── LAB: the assistant grounds on labs too, with a "this lab's context" basis ────────────────
    await page.goto(`/student/modules/${a.moduleId}/sections/${lab.id}`);
    await expect(page.getByTestId('assistant-start-chat')).toBeVisible({ timeout: 30_000 });
    await startChat(page);
    const labGrounded = await ask(page, labChunk, 1);
    await expectGrounded(labGrounded, 'Based on this lab');
    await expect(labGrounded.getByTestId('assistant-basis-text')).toContainText(lab.title);
    const labConv = (getAssistantConversations(studentId, lab.id) as Array<{ id: string }>)[0];
    expect(groundingStatuses(labConv.id)).toEqual(['lecture_grounded']);

    // ── unassigned student → module B section is 404 (not 403), never grounded ───────────────────
    const unassigned = await apiStudent.get(`/student/sections/${bSection.id}/assistant/availability`);
    expect(unassigned.status()).toBe(404);
  } finally {
    await apiStudent?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
