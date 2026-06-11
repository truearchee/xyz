import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, request as playwrightRequest, test, type APIRequestContext, type BrowserContext, type Locator, type Page } from '@playwright/test';

import {
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getMembershipsForModule,
  getSectionsForModule,
  getTranscriptEmbeddingVerification,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const UNASSIGNED_LECTURER_EMAIL = 'lecturer_unassigned_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const RAW_TEXT_MARKERS = [
  'Lab transcript notes for model evaluation',
  'Students compare a single decision tree',
];
const STUDENT_FORBIDDEN_TEXT = [
  'Embedding',
  'Embedded',
  'chunkCount',
  'embeddedChunkCount',
  'vector',
  'embedding_model',
  'embeddingModel',
  'modelRevision',
  'TranscriptProcessing',
  'safeFailureMessage',
];

type HookSessionResult = {
  data: {
    session: {
      access_token: string;
    } | null;
  };
};

type ApiResponse<T = unknown> = {
  body: T;
  status: number;
};

type SectionRow = {
  id: string;
  orderIndex: number;
  publishStatus: string;
  title: string;
  type: string;
};

type TranscriptProcessingProjection = {
  chunkCount: number;
  embeddedChunkCount: number;
  overallState: string;
  safeFailureMessage: string | null;
  steps: {
    embed: {
      status: string;
    };
  };
};

type RunManifest = {
  [key: string]: string[] | string;
  runId: string;
};

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

async function getSession(page: Page): Promise<HookSessionResult> {
  return page.evaluate(() => window.__xyzE2E!.getSession()) as Promise<HookSessionResult>;
}

async function getAccessToken(page: Page): Promise<string> {
  const session = await getSession(page);
  const token = session.data.session?.access_token;
  expect(token).toBeTruthy();
  return token as string;
}

async function createApiContext(token: string): Promise<APIRequestContext> {
  return playwrightRequest.newContext({
    baseURL: API_BASE_URL,
    extraHTTPHeaders: {
      Authorization: `Bearer ${token}`,
    },
  });
}

async function apiJson<T>(
  context: APIRequestContext,
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response =
    method === 'GET'
      ? await context.get(path)
      : await context.post(path, { data: body });
  const text = await response.text();
  return {
    body: text ? (JSON.parse(text) as T) : (null as T),
    status: response.status(),
  };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) {
    throw new Error('E2E_RUN_ID must be exported before running the 4.4 embedding gate');
  }
  return runId;
}

function manifestPathForRunId(runId: string): string {
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) {
    throw new Error(`Invalid E2E run id: ${runId}`);
  }
  return resolve('tests/e2e/.runs', `${runId}.json`);
}

function loadManifest(runId: string): RunManifest {
  return JSON.parse(readFileSync(manifestPathForRunId(runId), 'utf8')) as RunManifest;
}

function writeManifest(manifest: RunManifest) {
  writeFileSync(manifestPathForRunId(manifest.runId), `${JSON.stringify(manifest, null, 2)}\n`);
}

function recordManifestValue(runId: string, field: string, value: string) {
  const manifest = loadManifest(runId);
  const current = Array.isArray(manifest[field]) ? manifest[field] : [];
  manifest[field] = [...new Set([...current, value])];
  writeManifest(manifest);
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

function rowForSection(page: Page, section: SectionRow): Locator {
  return page.locator('[data-testid^="lecturer-section-row-"]').filter({
    hasText: section.title,
  });
}

async function createRunModule(
  runId: string,
  adminContext: APIRequestContext,
): Promise<{
  lab: SectionRow;
  moduleId: string;
  moduleTitle: string;
  sections: SectionRow[];
}> {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) {
    throw new Error('Standing lecturer/student E2E users are required');
  }

  const moduleTitle = `Stage 4.4 Gate ${runId}`;
  const moduleCreate = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title: moduleTitle,
    description: `4.4 embedding browser gate ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    startsOn: '2026-01-12',
    endsOn: '2026-05-01',
  });
  expect(moduleCreate.status).toBe(201);
  const moduleId = moduleCreate.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);

  const studentAssign = await apiJson<{ id: string }>(
    adminContext,
    'POST',
    `/admin/modules/${moduleId}/members`,
    {
      userId: student.id,
      role: 'student',
    },
  );
  expect(studentAssign.status).toBe(201);
  recordManifestValue(runId, 'membershipIds', studentAssign.body.id);

  const memberships = getMembershipsForModule(moduleId);
  recordMany(runId, 'membershipIds', memberships.map((membership: { id: string }) => membership.id));

  const sections = getSectionsForModule(moduleId) as SectionRow[];
  recordMany(runId, 'sectionIds', sections.map((section) => section.id));

  return {
    lab: sectionByTitle(sections, 'Lab 1'),
    moduleId,
    moduleTitle,
    sections,
  };
}

async function publishSections(context: APIRequestContext, moduleId: string, sections: SectionRow[]) {
  for (const section of sections) {
    const response = await apiJson(context, 'POST', `/modules/${moduleId}/sections/${section.id}/publish`);
    expect(response.status).toBe(200);
  }
}

async function uploadTranscriptThroughUi(
  page: Page,
  section: SectionRow,
  fileName: string,
): Promise<string> {
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

async function waitForEmbeddedProjectionResponse(
  page: Page,
  moduleId: string,
  sectionId: string,
): Promise<TranscriptProcessingProjection> {
  const response = await page.waitForResponse(async (candidate) => {
    if (
      candidate.request().method() !== 'GET' ||
      candidate.status() !== 200 ||
      new URL(candidate.url()).pathname !==
        `/modules/${moduleId}/sections/${sectionId}/transcript-processing-status`
    ) {
      return false;
    }

    const body = (await candidate.json().catch(() => null)) as
      | Partial<TranscriptProcessingProjection>
      | null;
    // Embed completion is the signal. Since 4.5a the summary pipeline runs after embed, so the
    // projection moves embedded → summarizing → summarized; we key off the embed STEP, not the
    // overallState, which no longer rests at 'embedded'.
    return (
      body?.steps?.embed?.status === 'completed' &&
      typeof body.chunkCount === 'number' &&
      body.chunkCount > 0 &&
      body.embeddedChunkCount === body.chunkCount &&
      body.safeFailureMessage === null
    );
  }, { timeout: 95_000 });
  return response.json() as Promise<TranscriptProcessingProjection>;
}

async function expectStudentNoEmbeddingInternals(page: Page) {
  for (const marker of [...RAW_TEXT_MARKERS, ...STUDENT_FORBIDDEN_TEXT]) {
    await expect(page.getByText(marker)).toHaveCount(0);
  }
  await expect(page.locator('[data-testid^="section-transcript-control-"]')).toHaveCount(0);
  await expect(page.locator('[data-testid^="section-transcript-upload-"]')).toHaveCount(0);
}

test('4.4 transcript embedding browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();
  const unassignedLecturerContext = await browser.newContext();

  let apiAdmin: APIRequestContext | null = null;
  let apiLecturer: APIRequestContext | null = null;
  let apiStudent: APIRequestContext | null = null;
  let apiUnassignedLecturer: APIRequestContext | null = null;

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
    const labRow = rowForSection(lecturerPage, setup.lab);
    const status = labRow.locator('[data-testid^="section-transcript-status-"]');

    const embeddedProjectionPromise = waitForEmbeddedProjectionResponse(
      lecturerPage,
      setup.moduleId,
      setup.lab.id,
    );
    const labTranscriptId = await uploadTranscriptThroughUi(
      lecturerPage,
      setup.lab,
      'lab-notes.txt',
    );
    const embeddingWasVisible = await status
      .filter({ hasText: 'Embedding' })
      .waitFor({ state: 'visible', timeout: 2_000 })
      .then(() => true)
      .catch(() => false);

    const artifacts = await waitForTranscriptEmbedded(labTranscriptId, 95_000);
    const projection = await embeddedProjectionPromise;

    recordManifestValue(runId, 'transcriptIds', labTranscriptId);
    recordMany(runId, 'ingestionJobIds', artifacts.jobs.map((job) => job.id));
    recordMany(runId, 'transcriptChunkIds', artifacts.counts.chunkIds);
    recordMany(runId, 'transcriptSegmentIds', artifacts.counts.segmentIds);
    if (artifacts.transcript?.storageKey) {
      recordManifestValue(runId, 'storageKeys', artifacts.transcript.storageKey);
    }

    // 'embedded' or any later (summary) state — the embed step is what this gate proves.
    expect(['embedded', 'summarizing', 'summarized']).toContain(projection.overallState);
    expect(projection.steps.embed.status).toBe('completed');
    expect(projection.embeddedChunkCount).toBe(projection.chunkCount);
    expect(projection.safeFailureMessage).toBeNull();

    // The badge passes through "Embedded" then on to the summary states; accept any of them.
    await expect(status).toContainText(/Embedded|Generating summaries|Summaries ready/, {
      timeout: 95_000,
    });

    const verification = getTranscriptEmbeddingVerification(labTranscriptId);
    expect(verification.embedJobStatus).toBe('completed');
    expect(verification.chunkCount).toBeGreaterThan(0);
    expect(verification.embeddedChunkCount).toBe(verification.chunkCount);
    expect(verification.provenanceCompleteCount).toBe(verification.chunkCount);
    expect(verification.vectorDimensions).toEqual([384]);
    expect(verification.embeddingModels).toEqual(['sentence-transformers/all-MiniLM-L6-v2']);
    expect(verification.embeddingModelRevisions).toEqual([
      '1110a243fdf4706b3f48f1d95db1a4f5529b4d41',
    ]);
    expect(verification.embeddingDimensions).toEqual([384]);
    expect(verification.embeddingNormalizations).toEqual(['l2']);
    expect(verification.embeddingVersions.length).toBe(1);
    expect(verification.chunkingVersions).toEqual(['chunk-v1-no-overlap-180w']);
    expect(verification.activeEmbedJobCount).toBe(0);

    const studentPage = await signInAndReturnPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(studentPage));
    const studentProjection = await apiJson(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections/${setup.lab.id}/transcript-processing-status`,
    );
    expect(studentProjection.status).toBe(403);
    expect(studentProjection.body).toMatchObject({ detail: 'TRANSCRIPT_FORBIDDEN' });

    const studentSession = await getSession(studentPage);
    expect(studentSession.data.session).not.toBeNull();
    expect(studentPage.url()).not.toContain('/login');
    await studentPage.goto(`/student/modules/${setup.moduleId}`);
    await expect(studentPage.getByRole('heading', { name: setup.moduleTitle })).toBeVisible();
    await expectStudentNoEmbeddingInternals(studentPage);

    const unassignedPage = await signInAndReturnPage(
      unassignedLecturerContext,
      UNASSIGNED_LECTURER_EMAIL,
      '/lecturer',
    );
    apiUnassignedLecturer = await createApiContext(await getAccessToken(unassignedPage));
    const unassignedProjection = await apiJson(
      apiUnassignedLecturer,
      'GET',
      `/modules/${setup.moduleId}/sections/${setup.lab.id}/transcript-processing-status`,
    );
    expect(unassignedProjection.status).toBe(404);
    expect(unassignedProjection.body).toMatchObject({ detail: 'SECTION_NOT_FOUND' });

    test.info().annotations.push({
      type: 'embedding-visible',
      description: embeddingWasVisible ? 'observed' : 'not observed; pipeline completed before browser sampled it',
    });
  } finally {
    await apiAdmin?.dispose();
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await apiUnassignedLecturer?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
    await unassignedLecturerContext.close();
  }
});

async function signInAndReturnPage(
  context: BrowserContext,
  email: string,
  expectedPath: string,
): Promise<Page> {
  const page = await context.newPage();
  await signIn(page, email, expectedPath);
  return page;
}
