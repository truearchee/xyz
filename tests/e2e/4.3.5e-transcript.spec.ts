import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, request as playwrightRequest, test, type APIRequestContext, type Locator, type Page } from '@playwright/test';

import {
  getActiveTranscriptCountForSection,
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getIngestionJobsForTranscript,
  getMembershipsForModule,
  getSectionsForModule,
  waitForTranscriptCompleted,
} from './fixtures/db.mjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const RAW_TEXT_MARKERS = [
  'Bagging trains learners on bootstrap samples',
  'Students compare a single decision tree',
];
const FORBIDDEN_TRANSCRIPT_FIELDS = [
  'text',
  'transcriptText',
  'rawText',
  'segments',
  'chunks',
  'normalizedText',
  'content',
  'segmentText',
  'chunkText',
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

type TranscriptArtifacts = Awaited<ReturnType<typeof waitForTranscriptCompleted>>;

type TranscriptProcessingProjection = {
  chunkCount: number;
  segmentCount: number;
  overallState: string;
  safeFailureMessage: string | null;
  steps: {
    parse: {
      status: string;
    };
    chunk: {
      status: string;
    };
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

async function apiMultipart(
  context: APIRequestContext,
  path: string,
  fileName: string,
  mimeType: string,
): Promise<ApiResponse> {
  const response = await context.post(path, {
    multipart: {
      file: {
        name: fileName,
        mimeType,
        buffer: readFileSync(resolve(TRANSCRIPT_DIR, fileName)),
      },
    },
  });
  const text = await response.text();
  return {
    body: text ? JSON.parse(text) : null,
    status: response.status(),
  };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) {
    throw new Error('E2E_RUN_ID must be exported before running the transcript gate');
  }
  return runId;
}

function recordMany(runId: string, field: string, values: string[]) {
  for (const value of values) {
    recordManifestValue(runId, field, value);
  }
}

function manifestPathForRunId(runId: string): string {
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) {
    throw new Error(`Invalid E2E run id: ${runId}`);
  }
  return resolve('tests/e2e/.runs', `${runId}.json`);
}

function loadManifest(runId: string): RunManifest {
  const path = manifestPathForRunId(runId);
  if (!existsSync(path)) {
    throw new Error(`Manifest not found: ${path}`);
  }
  return JSON.parse(readFileSync(path, 'utf8')) as RunManifest;
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

function recordStorageKey(runId: string, storageKey: string) {
  recordManifestValue(runId, 'storageKeys', storageKey);
}

function recordTranscriptId(runId: string, transcriptId: string) {
  recordManifestValue(runId, 'transcriptIds', transcriptId);
}

async function recordTranscriptArtifacts(
  runId: string,
  transcriptId: string,
  artifacts: TranscriptArtifacts,
) {
  recordTranscriptId(runId, transcriptId);
  if (artifacts.transcript?.storageKey) {
    recordStorageKey(runId, artifacts.transcript.storageKey);
  }
  recordMany(runId, 'ingestionJobIds', artifacts.jobs.map((job) => job.id));
  recordMany(runId, 'transcriptSegmentIds', artifacts.counts.segmentIds);
  recordMany(runId, 'transcriptChunkIds', artifacts.counts.chunkIds);
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
  assignment: SectionRow;
  lab: SectionRow;
  lecture: SectionRow;
  moduleId: string;
  moduleTitle: string;
  sections: SectionRow[];
}> {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) {
    throw new Error('Standing lecturer/student E2E users are required');
  }

  const moduleTitle = `Transcript Gate ${runId}`;
  const moduleCreate = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title: moduleTitle,
    description: `4.3.5e transcript browser gate ${runId}`,
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
  expect(sections.map((section) => section.title)).toEqual([
    'Lecture 1',
    'Lecture 2',
    'Lab 1',
    'Assignment 1',
  ]);
  recordMany(runId, 'sectionIds', sections.map((section) => section.id));

  return {
    assignment: sectionByTitle(sections, 'Assignment 1'),
    lab: sectionByTitle(sections, 'Lab 1'),
    lecture: sectionByTitle(sections, 'Lecture 1'),
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
  await expect(row.locator('[data-testid^="section-transcript-control-"]')).toBeVisible();
  const input = row.locator('[data-testid^="section-transcript-upload-"]');
  await expect(input).toBeVisible();
  await input.setInputFiles(resolve(TRANSCRIPT_DIR, fileName));
  await row.getByRole('button', { name: 'Upload transcript' }).click();
  const status = row.locator('[data-testid^="section-transcript-status-"]');
  await expect(status).toBeVisible();
  await expect(status).not.toContainText('No transcript uploaded yet.');
  await expect
    .poll(() => getActiveTranscriptForSection(section.id)?.id ?? null, { timeout: 10_000 })
    .not.toBeNull();
  return getActiveTranscriptForSection(section.id).id;
}

async function expectNoRawMarkers(page: Page) {
  for (const marker of RAW_TEXT_MARKERS) {
    await expect(page.getByText(marker)).toHaveCount(0);
  }
}

function assertNoForbiddenTranscriptFields(value: unknown) {
  const seen = new Set<string>();

  function visit(candidate: unknown) {
    if (Array.isArray(candidate)) {
      for (const item of candidate) {
        visit(item);
      }
      return;
    }
    if (!candidate || typeof candidate !== 'object') {
      return;
    }
    for (const [key, nested] of Object.entries(candidate)) {
      seen.add(key);
      visit(nested);
    }
  }

  visit(value);
  for (const field of FORBIDDEN_TRANSCRIPT_FIELDS) {
    expect(seen.has(field)).toBe(false);
  }
}

const CHUNK_COMPLETED_OVERALL_STATES = new Set(['chunked', 'embedding', 'embedded']);

async function waitForChunkCompletionProjectionResponse(
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
    return (
      typeof body?.overallState === 'string' &&
      CHUNK_COMPLETED_OVERALL_STATES.has(body.overallState) &&
      body.steps?.parse?.status === 'completed' &&
      body.steps?.chunk?.status === 'completed' &&
      typeof body.chunkCount === 'number' &&
      body.chunkCount > 0 &&
      typeof body.segmentCount === 'number' &&
      body.segmentCount > 0 &&
      body.safeFailureMessage === null
    );
  }, { timeout: 65_000 });
  return response.json() as Promise<TranscriptProcessingProjection>;
}

async function expectCompletedProof(
  runId: string,
  page: Page,
  moduleId: string,
  section: SectionRow,
  transcriptId: string,
) {
  const chunkCompletionProjectionPromise = waitForChunkCompletionProjectionResponse(
    page,
    moduleId,
    section.id,
  );
  const artifacts = await waitForTranscriptCompleted(transcriptId, 60_000);
  await recordTranscriptArtifacts(runId, transcriptId, artifacts);
  const projection = await chunkCompletionProjectionPromise;

  expect(artifacts.transcript.status).toBe('completed');
  expect(artifacts.counts.segmentCount).toBeGreaterThan(0);
  expect(artifacts.counts.chunkCount).toBeGreaterThan(0);
  expect(CHUNK_COMPLETED_OVERALL_STATES.has(projection.overallState)).toBe(true);
  expect(projection.steps.parse.status).toBe('completed');
  expect(projection.steps.chunk.status).toBe('completed');
  expect(projection.safeFailureMessage).toBeNull();
  expect(projection.segmentCount).toBeGreaterThan(0);
  expect(projection.chunkCount).toBeGreaterThan(0);

  const parseJob = artifacts.jobs.find((job) => job.jobType === 'parse');
  const chunkJob = artifacts.jobs.find((job) => job.jobType === 'chunk');
  expect(parseJob?.status).toBe('completed');
  expect(chunkJob?.status).toBe('completed');
  expect(Number(chunkJob?.resultMetadata?.chunk_count ?? 0)).toBeGreaterThan(0);

  await expect(rowForSection(page, section).locator('[data-testid^="section-transcript-status-"]')).toContainText(
    /Chunked|Embedding|Embedded|Generating summaries|Summaries ready/,
    { timeout: 65_000 },
  );
  await expectNoRawMarkers(page);
}

test('4.3.5e Stage 4.1-4.3 transcript browser gate', async ({ browser }) => {
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

    const setup = await createRunModule(runId, apiAdmin);

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    await publishSections(apiLecturer, setup.moduleId, setup.sections);

    await lecturerPage.goto(`/lecturer/modules/${setup.moduleId}`);
    await expect(lecturerPage.getByRole('heading', { name: setup.moduleTitle })).toBeVisible();
    await expect(lecturerPage.getByTestId('lecturer-section-list')).toBeVisible();

    const lectureRow = rowForSection(lecturerPage, setup.lecture);
    const labRow = rowForSection(lecturerPage, setup.lab);
    const assignmentRow = rowForSection(lecturerPage, setup.assignment);

    await expect(lectureRow.locator('[data-testid^="section-transcript-control-"]')).toBeVisible();
    await expect(labRow.locator('[data-testid^="section-transcript-control-"]')).toBeVisible();
    await expect(assignmentRow.locator('[data-testid^="section-transcript-control-"]')).toHaveCount(0);
    await expect(assignmentRow.locator('[data-testid^="section-transcript-upload-"]')).toHaveCount(0);

    await lectureRow
      .locator('[data-testid^="section-transcript-upload-"]')
      .setInputFiles(resolve(TRANSCRIPT_DIR, 'invalid-transcript.pdf'));
    await expect(lectureRow.locator('[data-testid^="section-transcript-error-"]')).toContainText(
      'Transcript upload accepts .vtt or .txt files.',
    );

    const lectureTranscriptId = await uploadTranscriptThroughUi(
      lecturerPage,
      setup.lecture,
      'ensemble-methods.vtt',
    );
    await expectCompletedProof(
      runId,
      lecturerPage,
      setup.moduleId,
      setup.lecture,
      lectureTranscriptId,
    );

    await lecturerPage.reload();
    await expect(lecturerPage.getByRole('heading', { name: setup.moduleTitle })).toBeVisible();
    const reloadedLectureRow = rowForSection(lecturerPage, setup.lecture);
    await expect(reloadedLectureRow.getByText('ensemble-methods.vtt')).toBeVisible();
    await expect(reloadedLectureRow.locator('[data-testid^="section-transcript-status-"]')).toContainText(
      /Chunked|Embedding|Embedded|Generating summaries|Summaries ready/,
    );
    await expect(reloadedLectureRow.locator('[data-testid^="section-transcript-upload-"]')).toHaveCount(0);
    await expectNoRawMarkers(lecturerPage);

    const duplicate = await apiMultipart(
      apiLecturer,
      `/modules/${setup.moduleId}/sections/${setup.lecture.id}/transcript`,
      'ensemble-methods.vtt',
      'text/vtt',
    );
    expect(duplicate.status).toBe(409);
    expect(duplicate.body).toMatchObject({ detail: 'TRANSCRIPT_ALREADY_EXISTS' });
    expect(getActiveTranscriptForSection(setup.lecture.id)?.id).toBe(lectureTranscriptId);
    expect(getActiveTranscriptCountForSection(setup.lecture.id)).toBe(1);

    const labTranscriptId = await uploadTranscriptThroughUi(
      lecturerPage,
      setup.lab,
      'lab-notes.txt',
    );
    await expectCompletedProof(
      runId,
      lecturerPage,
      setup.moduleId,
      setup.lab,
      labTranscriptId,
    );

    const assignmentUpload = await apiMultipart(
      apiLecturer,
      `/modules/${setup.moduleId}/sections/${setup.assignment.id}/transcript`,
      'ensemble-methods.vtt',
      'text/vtt',
    );
    expect(assignmentUpload.status).toBe(422);
    expect(assignmentUpload.body).toMatchObject({ detail: 'SECTION_TYPE_UNSUPPORTED' });

    const studentPage = await studentContext.newPage();
    await signIn(studentPage, STUDENT_EMAIL, '/student');
    await studentPage.goto(`/student/modules/${setup.moduleId}`);
    await expect(studentPage.getByRole('heading', { name: setup.moduleTitle })).toBeVisible();
    await expect(studentPage.locator('[data-testid^="section-transcript-control-"]')).toHaveCount(0);
    await expect(studentPage.locator('[data-testid^="section-transcript-upload-"]')).toHaveCount(0);
    await expectNoRawMarkers(studentPage);

    apiStudent = await createApiContext(await getAccessToken(studentPage));
    const studentUpload = await apiMultipart(
      apiStudent,
      `/modules/${setup.moduleId}/sections/${setup.lecture.id}/transcript`,
      'ensemble-methods.vtt',
      'text/vtt',
    );
    expect(studentUpload.status).toBe(403);
    expect(studentUpload.body).toMatchObject({ detail: 'TRANSCRIPT_FORBIDDEN' });
    const studentSession = await getSession(studentPage);
    expect(studentSession.data.session).not.toBeNull();
    expect(studentPage.url()).not.toContain('/login');

    const meResponse = await apiJson<{ role: string }>(apiStudent, 'GET', '/me');
    expect(meResponse.status).toBe(200);
    expect(meResponse.body.role).toBe('student');

    const studentRead = await apiJson(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections/${setup.lecture.id}/transcript`,
    );
    expect(studentRead.status).toBe(403);
    assertNoForbiddenTranscriptFields(studentRead.body);

    const jobs = getIngestionJobsForTranscript(lectureTranscriptId);
    expect(jobs.find((job: { jobType: string }) => job.jobType === 'parse')?.status).toBe('completed');
    expect(jobs.find((job: { jobType: string }) => job.jobType === 'chunk')?.status).toBe('completed');
  } finally {
    await apiAdmin?.dispose();
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
