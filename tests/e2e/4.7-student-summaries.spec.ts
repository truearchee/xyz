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
  countTranscriptSegmentsContaining,
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getGeneratedSummariesForTranscript,
  getMembershipsForModule,
  getSectionsForModule,
  getTranscriptArtifacts,
  seedDetailedSummaryGenerating,
  waitForSummariesSettled,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

// Stage 4.7 browser gate (G1–G7). A student READS both summaries in a real browser, while being unable
// to reach a raw transcript, an unpublished section, or content from a module they are not in. Fixtures
// are SEEDED/deterministic (§14): the demo uses the deterministic provider pipeline; G2 (brief-first) is
// a seeded transform; G7 (unavailable) uses a no-transcript published section (row 5). The security set
// (G3/G4/G5/G6) is asserted on real server payloads + the real rendered UI.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');

const BRIEF_MARKER = 'core ideas of the topic';
const DETAILED_OVERVIEW_MARKER = 'structured overview of the session';
const SENTINEL = 'RAW_TRANSCRIPT_SENTINEL_DO_NOT_SURFACE_4_7';
const SENTINEL_FILE = 'sentinel-lecture.vtt';

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };

test.setTimeout(180_000);

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

async function apiJson<T>(context: APIRequestContext, method: 'GET' | 'POST', path: string, body?: unknown): Promise<ApiResponse<T>> {
  const response = method === 'GET' ? await context.get(path) : await context.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

async function apiUpload<T>(context: APIRequestContext, path: string, fileName: string, buffer: Buffer, mimeType: string): Promise<ApiResponse<T>> {
  const response = await context.post(path, { multipart: { file: { name: fileName, mimeType, buffer } } });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 4.7 gate');
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

function sectionByTitle(sections: SectionRow[], title: string): SectionRow {
  const s = sections.find((c) => c.title === title);
  if (!s) throw new Error(`Missing generated section ${title}`);
  return s;
}

async function createModule(runId: string, adminContext: APIRequestContext, title: string, assignStudent: boolean) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) throw new Error('Standing lecturer/student E2E users are required');
  const create = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title,
    description: `4.7 gate ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    // Stage 5.5a: creation is schedule-driven (startsOn/endsOn replaced). Title-based section
    // selection below is reworked in 5.5e (full-suite pass after the 5.5d reseed).
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

test('4.7 student summaries browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();

  let apiAdmin: APIRequestContext | null = null;
  let apiLecturer: APIRequestContext | null = null;
  let apiStudent: APIRequestContext | null = null;

  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    apiAdmin = await createApiContext(await getAccessToken(adminPage));

    // Module A — student assigned. Module B — student NOT assigned (G5).
    const a = await createModule(runId, apiAdmin, `Stage 4.7 Module A ${runId}`, true);
    const b = await createModule(runId, apiAdmin, `Stage 4.7 Module B ${runId}`, false);

    const a1 = sectionByTitle(a.sections, 'Lecture 1'); // summarized → G1/G2/G3
    const a3 = sectionByTitle(a.sections, 'Lecture 2'); // published, no transcript → G7 (row 5)
    const a4 = sectionByTitle(a.sections, 'Lab 1'); // draft → G4
    const b1 = sectionByTitle(b.sections, 'Lecture 1'); // module B published → G5

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));

    // A1: upload the sentinel transcript (the deterministic provider summary ignores it), run the
    // pipeline to summaries, publish.
    const upload = await apiUpload<{ id: string }>(
      apiLecturer,
      `/modules/${a.moduleId}/sections/${a1.id}/transcript`,
      SENTINEL_FILE,
      readFileSync(resolve(TRANSCRIPT_DIR, SENTINEL_FILE)),
      'text/vtt',
    );
    expect(upload.status).toBe(201);
    const transcriptId = getActiveTranscriptForSection(a1.id).id;
    recordManifestValue(runId, 'transcriptIds', transcriptId);
    const artifacts = await waitForTranscriptEmbedded(transcriptId, 95_000);
    recordMany(runId, 'ingestionJobIds', artifacts.jobs.map((j: { id: string }) => j.id));
    recordMany(runId, 'transcriptChunkIds', artifacts.counts.chunkIds);
    recordMany(runId, 'transcriptSegmentIds', artifacts.counts.segmentIds);
    if (artifacts.transcript?.storageKey) recordManifestValue(runId, 'storageKeys', artifacts.transcript.storageKey);
    const settled = await waitForSummariesSettled(transcriptId, 120_000);
    expect(settled.generate_brief_summary).toBe('completed');
    expect(settled.generate_detailed_summary).toBe('completed');

    // CANARY VALIDITY (R1) — prove the sentinel actually rode the transcript backing G3's summary, so its
    // absence from the student surface is a live guarantee, not vacuous: (1) A1's active transcript IS the
    // sentinel file, (2) the sentinel is genuinely in that transcript's raw segments, (3) both summaries
    // the student reads were generated FROM that same transcript id.
    const a1Active = getActiveTranscriptForSection(a1.id);
    expect(a1Active.id).toBe(transcriptId);
    expect(a1Active.originalFileName).toBe(SENTINEL_FILE);
    expect(countTranscriptSegmentsContaining(transcriptId, SENTINEL)).toBeGreaterThan(0);
    const a1Summaries = getGeneratedSummariesForTranscript(transcriptId) as Array<{ summaryType: string }>;
    expect(a1Summaries.map((s) => s.summaryType).sort()).toEqual(['brief', 'detailed_study']);

    await publish(apiLecturer, a.moduleId, a1.id);
    await publish(apiLecturer, a.moduleId, a3.id); // Lecture 2 published, no transcript
    await publish(apiLecturer, b.moduleId, b1.id); // Module B Lecture 1 published
    // a4 (Lab 1) stays draft.

    // ---- Student browser + API contexts ----
    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(studentPage));

    // G1 — student reads brief + detailed in the browser.
    await studentPage.goto(`/student/modules/${a.moduleId}/sections/${a1.id}`);
    await expect(studentPage.getByTestId('student-section-detail')).toBeVisible();
    const brief = studentPage.getByTestId('student-summary-brief');
    const detailed = studentPage.getByTestId('student-summary-detailed');
    await expect(brief).toHaveAttribute('data-state', 'ready', { timeout: 30_000 });
    await expect(brief).toContainText(BRIEF_MARKER);
    await expect(detailed).toHaveAttribute('data-state', 'ready', { timeout: 30_000 });
    await expect(detailed).toContainText(DETAILED_OVERVIEW_MARKER);
    await expect(detailed).toContainText('Overview');

    // G3a — no raw-transcript affordance on the student page.
    const pageText = await studentPage.locator('body').innerText();
    expect(pageText).not.toContain(SENTINEL); // G3b — sentinel never rendered
    expect(pageText).not.toContain(SENTINEL_FILE); // raw transcript filename never rendered
    await expect(studentPage.getByText(/view transcript/i)).toHaveCount(0);

    // G3b — sentinel in NO student API response.
    for (const path of [
      `/student/modules/${a.moduleId}/sections`,
      `/student/sections/${a1.id}`,
      `/student/sections/${a1.id}/summaries`,
    ]) {
      const r = await apiStudent.get(path);
      expect(r.status()).toBe(200);
      expect(await r.text()).not.toContain(SENTINEL);
    }

    // G3c — every transcript text-bearing endpoint rejects the student token; no student transcript
    // signed-URL path exists (the student surface has no such route).
    for (const path of [
      `/modules/${a.moduleId}/sections/${a1.id}/transcript`,
      `/modules/${a.moduleId}/sections/${a1.id}/transcript-processing-status`,
      `/modules/${a.moduleId}/sections/${a1.id}/transcript-summaries`,
      `/modules/${a.moduleId}/sections/${a1.id}/transcript-active-summary-preview`,
    ]) {
      const r = await apiStudent.get(path);
      expect(r.status()).toBe(403);
    }

    // G2 — brief-first: seed detailed back to generating, reload, assert brief READY + detailed GENERATING.
    seedDetailedSummaryGenerating(transcriptId);
    await studentPage.reload();
    await expect(studentPage.getByTestId('student-summary-brief')).toHaveAttribute('data-state', 'ready', { timeout: 30_000 });
    await expect(studentPage.getByTestId('student-summary-detailed')).toHaveAttribute('data-state', 'generating', { timeout: 30_000 });
    await expect(studentPage.getByTestId('student-summary-detailed')).toContainText('being generated');

    // G7 — UNAVAILABLE renders for a published lecture with no transcript (row 5), no detail leaked.
    await studentPage.goto(`/student/modules/${a.moduleId}/sections/${a3.id}`);
    await expect(studentPage.getByTestId('student-summary-brief')).toHaveAttribute('data-state', 'unavailable', { timeout: 30_000 });
    await expect(studentPage.getByTestId('student-summary-brief')).toContainText('currently unavailable');

    // G4 — unpublished (draft) section → 404 (row D).
    const draftFetch = await apiJson<{ detail: string }>(apiStudent, 'GET', `/student/sections/${a4.id}/summaries`);
    expect(draftFetch.status).toBe(404);

    // G5 — unenrolled (module B) → existing published section → 404 (row P), body BYTE-IDENTICAL to G4.
    const otherModuleFetch = await apiJson<{ detail: string }>(apiStudent, 'GET', `/student/sections/${b1.id}/summaries`);
    expect(otherModuleFetch.status).toBe(404);
    expect(JSON.stringify(otherModuleFetch.body)).toBe(JSON.stringify(draftFetch.body));

    // G6 — non-student (lecturer) on the student endpoint → 403 (row R).
    const lecturerOnStudent = await apiJson(apiLecturer, 'GET', `/student/sections/${a1.id}/summaries`);
    expect(lecturerOnStudent.status).toBe(403);

    // session preserved throughout
    const me = await apiJson<{ role: string }>(apiStudent, 'GET', '/me');
    expect(me.body.role).toBe('student');
    expect(studentPage.url()).not.toContain('/login');
  } finally {
    await apiAdmin?.dispose();
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
