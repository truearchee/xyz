import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';

import {
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getGeneratedSummariesForTranscript,
  getMembershipsForModule,
  getSectionsForModule,
  waitForSummariesSettled,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

// Stage 4.5d browser gate (Half 1, deterministic provider). Proves the lecturer SEES the brief then
// the detailed (by-section) summary in a real browser, the badge reaches "Summaries ready", the
// routing split landed in provenance (brief=cerebras, detailed=nvidia), and the read surface is
// two-surface authorized (student 403 + UI absence; unassigned lecturer 404).
//
// Forced-fault paths (invalid_output retried/logged; invalid_input terminal) are covered by a
// fault-configured stack run (LLM_FAULT_INJECTION on the ai_worker) — global worker env can't mix
// success + fault in one stack, so they are a dedicated run, not this success-path gate.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const UNASSIGNED_LECTURER_EMAIL = 'lecturer_unassigned_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');

// Deterministic provider canned output (provider.py _render_output) — what the lecturer must see.
const BRIEF_MARKER = 'core ideas of the topic';
const DETAILED_OVERVIEW_MARKER = 'structured overview of the session';

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

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) {
    throw new Error('E2E_RUN_ID must be exported before running the 4.5d summary gate');
  }
  return runId;
}

// Manifest recording so the harness teardown removes every run-created row (codebase teardown
// convention; deleting transcripts cascades summaries + AIRequestLogs).
type RunManifest = { [key: string]: string[] | string; runId: string };

function manifestPathForRunId(runId: string): string {
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) {
    throw new Error(`Invalid E2E run id: ${runId}`);
  }
  return resolve('tests/e2e/.runs', `${runId}.json`);
}

function recordManifestValue(runId: string, field: string, value: string) {
  const manifest = JSON.parse(readFileSync(manifestPathForRunId(runId), 'utf8')) as RunManifest;
  const current = Array.isArray(manifest[field]) ? manifest[field] : [];
  manifest[field] = [...new Set([...current, value])];
  writeFileSync(manifestPathForRunId(runId), `${JSON.stringify(manifest, null, 2)}\n`);
}

function recordMany(runId: string, field: string, values: string[]) {
  for (const value of values) {
    recordManifestValue(runId, field, value);
  }
}

function sectionByTitle(sections: SectionRow[], title: string): SectionRow {
  const section = sections.find((candidate) => candidate.title === title);
  if (!section) {
    throw new Error(`Missing generated section ${title}`);
  }
  return section;
}

function rowForSection(page: Page, section: SectionRow) {
  return page.locator('[data-testid^="lecturer-section-row-"]').filter({ hasText: section.title });
}

async function createRunModule(runId: string, adminContext: APIRequestContext) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) {
    throw new Error('Standing lecturer/student E2E users are required');
  }

  const moduleTitle = `Stage 4.5d Gate ${runId}`;
  const moduleCreate = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title: moduleTitle,
    description: `4.5d summary browser gate ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    startsOn: '2026-01-12',
    endsOn: '2026-05-01',
  });
  expect(moduleCreate.status).toBe(201);
  const moduleId = moduleCreate.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);

  const studentAssign = await apiJson<{ id: string }>(adminContext, 'POST', `/admin/modules/${moduleId}/members`, {
    userId: student.id,
    role: 'student',
  });
  expect(studentAssign.status).toBe(201);
  recordManifestValue(runId, 'membershipIds', studentAssign.body.id);
  recordMany(runId, 'membershipIds', getMembershipsForModule(moduleId).map((m: { id: string }) => m.id));

  const sections = getSectionsForModule(moduleId) as SectionRow[];
  recordMany(runId, 'sectionIds', sections.map((section) => section.id));
  return { lab: sectionByTitle(sections, 'Lab 1'), moduleId, moduleTitle, sections };
}

async function publishSections(context: APIRequestContext, moduleId: string, sections: SectionRow[]) {
  for (const section of sections) {
    const response = await apiJson(context, 'POST', `/modules/${moduleId}/sections/${section.id}/publish`);
    expect(response.status).toBe(200);
  }
}

async function uploadTranscriptThroughUi(page: Page, section: SectionRow, fileName: string): Promise<string> {
  const row = rowForSection(page, section);
  const input = row.locator('[data-testid^="section-transcript-upload-"]');
  await expect(input).toBeVisible();
  await input.setInputFiles(resolve(TRANSCRIPT_DIR, fileName));
  await row.getByRole('button', { name: 'Upload transcript' }).click();
  await expect
    .poll(() => getActiveTranscriptForSection(section.id)?.id ?? null, { timeout: 10_000 })
    .not.toBeNull();
  return getActiveTranscriptForSection(section.id).id;
}

test('4.5d lecturer summary browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();
  const unassignedContext = await browser.newContext();

  let apiAdmin: APIRequestContext | null = null;
  let apiLecturer: APIRequestContext | null = null;
  let apiStudent: APIRequestContext | null = null;
  let apiUnassigned: APIRequestContext | null = null;

  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    apiAdmin = await createApiContext(await getAccessToken(adminPage));

    const setup = await createRunModule(runId, apiAdmin);

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    await publishSections(apiLecturer, setup.moduleId, setup.sections);

    await lecturerPage.goto(`/lecturer/modules/${setup.moduleId}`);
    await expect(lecturerPage.getByRole('heading', { name: setup.moduleTitle })).toBeVisible();

    // Upload → embed → both summaries generate (deterministic provider).
    const transcriptId = await uploadTranscriptThroughUi(lecturerPage, setup.lab, 'lab-notes.txt');
    recordManifestValue(runId, 'transcriptIds', transcriptId);
    const artifacts = await waitForTranscriptEmbedded(transcriptId, 95_000);
    recordMany(runId, 'ingestionJobIds', artifacts.jobs.map((job: { id: string }) => job.id));
    recordMany(runId, 'transcriptChunkIds', artifacts.counts.chunkIds);
    recordMany(runId, 'transcriptSegmentIds', artifacts.counts.segmentIds);
    if (artifacts.transcript?.storageKey) {
      recordManifestValue(runId, 'storageKeys', artifacts.transcript.storageKey);
    }
    const jobStatuses = await waitForSummariesSettled(transcriptId, 120_000);
    expect(jobStatuses.generate_brief_summary).toBe('completed');
    expect(jobStatuses.generate_detailed_summary).toBe('completed');

    // Provenance proof: the routing split landed (brief=cerebras, detailed=nvidia), each with an
    // AIRequestLog row.
    const summaries = getGeneratedSummariesForTranscript(transcriptId) as Array<{
      summaryType: string;
      backendUsed: string;
      aiRequestLogId: string;
    }>;
    const byType = Object.fromEntries(summaries.map((s) => [s.summaryType, s]));
    expect(byType.brief?.backendUsed).toBe('cerebras');
    expect(byType.detailed_study?.backendUsed).toBe('nvidia');
    expect(byType.brief?.aiRequestLogId).toBeTruthy();
    expect(byType.detailed_study?.aiRequestLogId).toBeTruthy();

    // The lecturer SEES the brief then the detailed (by section) and a "Summaries ready" badge.
    await lecturerPage.reload();
    const labRow = rowForSection(lecturerPage, setup.lab);
    await expect(labRow.locator('[data-testid^="section-summary-brief-"]')).toContainText(BRIEF_MARKER, {
      timeout: 95_000,
    });
    const detailedPanel = labRow.locator('[data-testid^="section-summary-detailed-"]');
    await expect(detailedPanel).toContainText(DETAILED_OVERVIEW_MARKER, { timeout: 95_000 });
    await expect(detailedPanel).toContainText('Overview');
    await expect(detailedPanel).toContainText('Key concepts');
    await expect(detailedPanel).toContainText('Lab notes');
    await expect(labRow.locator('[data-testid^="section-transcript-status-"]')).toContainText('Summaries ready', {
      timeout: 95_000,
    });

    // Authz two-surface — student: API 403 + UI has no summary panel.
    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(studentPage));
    const studentRead = await apiJson(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections/${setup.lab.id}/transcript-summaries`,
    );
    expect(studentRead.status).toBe(403);
    expect(studentRead.body).toMatchObject({ detail: 'TRANSCRIPT_FORBIDDEN' });
    await studentPage.goto(`/student/modules/${setup.moduleId}`);
    await expect(studentPage.getByRole('heading', { name: setup.moduleTitle })).toBeVisible();
    await expect(studentPage.locator('[data-testid^="section-summary-panel-"]')).toHaveCount(0);
    await expect(studentPage.getByText(BRIEF_MARKER)).toHaveCount(0);
    expect(studentPage.url()).not.toContain('/login');

    // Authz two-surface — unassigned lecturer: API 404 (existence-leak prevention).
    const unassignedPage = await signInPage(unassignedContext, UNASSIGNED_LECTURER_EMAIL, '/lecturer');
    apiUnassigned = await createApiContext(await getAccessToken(unassignedPage));
    const unassignedRead = await apiJson(
      apiUnassigned,
      'GET',
      `/modules/${setup.moduleId}/sections/${setup.lab.id}/transcript-summaries`,
    );
    expect(unassignedRead.status).toBe(404);
    expect(unassignedRead.body).toMatchObject({ detail: 'SECTION_NOT_FOUND' });
  } finally {
    await apiAdmin?.dispose();
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await apiUnassigned?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
    await unassignedContext.close();
  }
});
