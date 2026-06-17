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
  getAppUserByEmail,
  getMembershipsForModule,
  runPsqlJson,
  sqlLiteral,
} from './fixtures/db.mjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const PDF_NAME = 'stage-55e-lab.pdf';
const NOTEBOOK_NAME = 'stage-55e-lab.ipynb';
const PDF_BYTES = Buffer.from('%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n');
const NOTEBOOK_BYTES = Buffer.from(
  JSON.stringify({
    cells: [
      {
        cell_type: 'markdown',
        metadata: {},
        source: ['# Stage 5.5e notebook gate'],
      },
    ],
    metadata: {},
    nbformat: 4,
    nbformat_minor: 5,
  }),
);

const REFERENCE_SCHEDULE = {
  courseStartDate: '2026-05-11',
  courseEndDate: '2026-06-26',
  weekStartDay: 'monday',
  sessionPattern: [
    { weekday: 'monday', sectionType: 'lecture' },
    { weekday: 'tuesday', sectionType: 'lecture' },
    { weekday: 'wednesday', sectionType: 'lecture' },
    { weekday: 'thursday', sectionType: 'lab' },
  ],
  quizDay: 'friday',
};

type ApiResponse<T = unknown> = { body: T; status: number };
type ModuleRow = { id: string; ownerId: string; title: string };
type SectionWeekRow = {
  dueAt: string | null;
  id: string;
  orderIndex: number;
  publishStatus: string;
  sessionDate: string | null;
  title: string;
  type: string;
  weekNumber: number | null;
};
type AssetRow = {
  assetKind: string;
  fileName: string;
  id: string;
  mimeType: string;
  processingStatus: string;
};
type RunManifest = { [key: string]: string[] | string; runId: string };

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

async function apiJson<T>(
  context: APIRequestContext,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response =
    method === 'GET'
      ? await context.get(path)
      : method === 'PATCH'
        ? await context.patch(path, { data: body })
        : method === 'DELETE'
          ? await context.delete(path)
          : await context.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) {
    throw new Error('E2E_RUN_ID must be exported before running the 5.5e browser gate');
  }
  return runId;
}

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

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

function getSectionAssets(sectionId: string): AssetRow[] {
  return runPsqlJson(`
SELECT coalesce(json_agg(
  json_build_object(
    'id', id,
    'fileName', file_name,
    'mimeType', mime_type,
    'assetKind', asset_kind,
    'processingStatus', processing_status
  )
  ORDER BY file_name
), '[]'::json)::text
FROM section_assets
WHERE module_section_id = ${sqlLiteral(sectionId)}::uuid;
`) as AssetRow[];
}

async function assertNoSectionMutationEndpoints(apiLecturer: APIRequestContext, moduleId: string, sectionId: string) {
  const createSection = await apiJson(apiLecturer, 'POST', `/modules/${moduleId}/sections`, {
    title: 'Forbidden extra section',
    type: 'lecture',
  });
  expect([404, 405]).toContain(createSection.status);

  const deleteSection = await apiJson(apiLecturer, 'DELETE', `/modules/${moduleId}/sections/${sectionId}`);
  expect([404, 405]).toContain(deleteSection.status);
}

test('5.5e schedule UI, resolver by-week, lab attachments, and student downloads', async ({ browser }) => {
  const runId = requireRunId();
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) {
    throw new Error('Standing lecturer/student E2E users are required');
  }

  const moduleTitle = `Stage 5.5e Browser Gate ${runId}`;
  const adminContext = await browser.newContext({ acceptDownloads: true });
  const lecturerContext = await browser.newContext({ acceptDownloads: true });
  const studentContext = await browser.newContext({ acceptDownloads: true });

  let apiAdmin: APIRequestContext | null = null;
  let apiLecturer: APIRequestContext | null = null;
  let apiStudent: APIRequestContext | null = null;

  try {
    const adminPage = await signInPage(adminContext, ADMIN_EMAIL, '/admin');
    apiAdmin = await createApiContext(await getAccessToken(adminPage));

    const apiPreview = await apiJson<{
      fridaySectionCount: number;
      labCount: number;
      lectureCount: number;
      sections: Array<{ title: string; type: string; weekNumber: number }>;
      totalSections: number;
      weekCount: number;
    }>(apiAdmin, 'POST', '/admin/modules/preview-sections', REFERENCE_SCHEDULE);
    expect(apiPreview.status).toBe(200);
    expect(apiPreview.body).toMatchObject({
      fridaySectionCount: 0,
      labCount: 7,
      lectureCount: 21,
      totalSections: 28,
      weekCount: 7,
    });
    expect(apiPreview.body.sections).toHaveLength(28);

    const missingSchedule = await apiJson(apiAdmin, 'POST', '/admin/modules', {
      title: `${moduleTitle} invalid`,
      description: null,
      ownerId: owner.id,
      timezone: 'UTC',
    });
    expect(missingSchedule.status).toBe(422);

    const createForm = adminPage.getByTestId('create-module-form');
    await createForm.getByLabel('Module title').fill(moduleTitle);
    await createForm.getByLabel('Module owner lecturer').selectOption({
      label: `Lecturer E2E (${LECTURER_EMAIL})`,
    });
    await createForm.getByLabel('Module description').fill(`5.5e browser gate ${runId}`);
    await createForm.getByLabel('Course starts on').fill(REFERENCE_SCHEDULE.courseStartDate);
    await createForm.getByLabel('Course ends on').fill(REFERENCE_SCHEDULE.courseEndDate);

    const uiPreviewResponsePromise = adminPage.waitForResponse(
      (response) =>
        response.url().endsWith('/admin/modules/preview-sections') &&
        response.request().method() === 'POST',
    );
    await createForm.getByRole('button', { name: 'Preview sections' }).click();
    const uiPreviewResponse = await uiPreviewResponsePromise;
    expect(uiPreviewResponse.status()).toBe(200);
    const uiPreview = (await uiPreviewResponse.json()) as { totalSections: number };
    expect(uiPreview.totalSections).toBe(28);
    await expect(adminPage.getByTestId('module-schedule-preview')).toContainText('28 total sections');

    await createForm.getByRole('button', { name: 'Create module' }).click();
    await expect(adminPage.getByTestId(`admin-module-row-${slugify(moduleTitle)}`)).toBeVisible();

    const moduleList = await apiJson<ModuleRow[]>(apiAdmin, 'GET', '/admin/modules');
    expect(moduleList.status).toBe(200);
    const module = moduleList.body.find((candidate) => candidate.title === moduleTitle);
    expect(module).toBeTruthy();
    const moduleId = module!.id;
    recordManifestValue(runId, 'moduleIds', moduleId);

    const studentAssign = await apiJson<{ id: string }>(apiAdmin, 'POST', `/admin/modules/${moduleId}/members`, {
      role: 'student',
      userId: student.id,
    });
    expect(studentAssign.status).toBe(201);
    recordManifestValue(runId, 'membershipIds', studentAssign.body.id);

    const sections = await apiJson<SectionWeekRow[]>(
      apiAdmin,
      'GET',
      `/admin/modules/${moduleId}/sections/by-week?includeUnstamped=true`,
    );
    expect(sections.status).toBe(200);
    expect(sections.body).toHaveLength(28);
    expect(sections.body.filter((section) => section.type === 'lecture')).toHaveLength(21);
    expect(sections.body.filter((section) => section.type === 'lab')).toHaveLength(7);
    recordMany(runId, 'sectionIds', sections.body.map((section) => section.id));
    recordMany(runId, 'membershipIds', getMembershipsForModule(moduleId).map((m: { id: string }) => m.id));

    const week1 = await apiJson<SectionWeekRow[]>(
      apiAdmin,
      'GET',
      `/admin/modules/${moduleId}/sections/by-week?coveredWeeks=1&includeUnstamped=false`,
    );
    expect(week1.status).toBe(200);
    expect(week1.body).toHaveLength(4);

    await adminPage.getByLabel('Managed module').selectOption({ label: moduleTitle });
    await expect(adminPage.getByTestId('admin-by-week-view')).toBeVisible();
    await expect(adminPage.locator('[data-testid^="admin-by-week-row-"]')).toHaveCount(28);

    const lecturerPage = await signInPage(lecturerContext, LECTURER_EMAIL, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    await lecturerPage.goto(`/lecturer/modules/${moduleId}`);
    await expect(lecturerPage.getByTestId('lecturer-by-week-view')).toBeVisible();
    await expect(lecturerPage.locator('[data-testid^="lecturer-by-week-row-"]')).toHaveCount(28);
    await expect(lecturerPage.getByRole('button', { name: /add section/i })).toHaveCount(0);
    await expect(lecturerPage.getByRole('button', { name: /delete section/i })).toHaveCount(0);
    await expect(lecturerPage.getByRole('button', { name: /reorder|move up|move down/i })).toHaveCount(0);

    const firstLecture = sections.body.find((section) => section.type === 'lecture' && section.weekNumber === 1);
    const firstLab = sections.body.find((section) => section.type === 'lab' && section.weekNumber === 1);
    expect(firstLecture).toBeTruthy();
    expect(firstLab).toBeTruthy();
    await assertNoSectionMutationEndpoints(apiLecturer, moduleId, firstLecture!.id);

    const lectureMetadata = lecturerPage.getByTestId(`section-metadata-editor-${slugify(firstLecture!.title)}`);
    await lectureMetadata.getByLabel(`Session date for ${firstLecture!.title}`).fill('2026-05-19');
    await lectureMetadata.getByRole('button', { name: 'Save date' }).click();
    await expect(lecturerPage.getByTestId(`section-metadata-current-${slugify(firstLecture!.title)}`)).toContainText(
      'Week 2',
    );
    const recomputed = await apiJson<SectionWeekRow[]>(
      apiLecturer,
      'GET',
      `/modules/${moduleId}/sections/by-week?coveredWeeks=2&includeUnstamped=true`,
    );
    expect(recomputed.status).toBe(200);
    expect(recomputed.body.find((section) => section.id === firstLecture!.id)).toMatchObject({
      sessionDate: '2026-05-19',
      weekNumber: 2,
    });

    const labCard = lecturerPage.locator('article').filter({ hasText: firstLab!.title }).first();
    const uploadControl = labCard.locator('[data-testid^="section-upload-control-"]');
    await uploadControl.locator('input[type="file"]').setInputFiles({
      buffer: PDF_BYTES,
      mimeType: 'application/pdf',
      name: PDF_NAME,
    });
    await uploadControl.getByRole('button', { name: 'Upload' }).click();
    await expect(labCard.getByText(PDF_NAME)).toBeVisible();

    await uploadControl.getByLabel('Due').fill('2026-05-14T17:30');
    await uploadControl.locator('input[type="file"]').setInputFiles({
      buffer: NOTEBOOK_BYTES,
      mimeType: 'application/x-ipynb+json',
      name: NOTEBOOK_NAME,
    });
    await uploadControl.getByRole('button', { name: 'Upload' }).click();
    await expect(labCard.getByText(NOTEBOOK_NAME)).toBeVisible();

    const assets = getSectionAssets(firstLab!.id);
    expect(assets).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ assetKind: 'attachment', fileName: NOTEBOOK_NAME, processingStatus: 'completed' }),
        expect.objectContaining({ assetKind: 'processable', fileName: PDF_NAME }),
      ]),
    );
    recordMany(runId, 'assetIds', assets.map((asset) => asset.id));
    const pdfAsset = assets.find((asset) => asset.fileName === PDF_NAME);
    const notebookAsset = assets.find((asset) => asset.fileName === NOTEBOOK_NAME);
    expect(pdfAsset).toBeTruthy();
    expect(notebookAsset).toBeTruthy();

    await labCard.getByRole('button', { name: `Publish ${firstLab!.title}` }).click();
    await expect(labCard.getByText('Section visibility: Published')).toBeVisible();

    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(studentPage));
    await studentPage.goto(`/student/modules/${moduleId}`);
    await expect(studentPage.getByTestId('student-section-list')).toBeVisible();
    await expect(studentPage.getByRole('heading', { name: firstLab!.title, exact: true })).toBeVisible();
    await expect(studentPage.getByTestId(`student-section-due-at-${firstLab!.id}`)).not.toContainText('No deadline set');
    await expect(studentPage.getByText(PDF_NAME)).toBeVisible();
    await expect(studentPage.getByText(NOTEBOOK_NAME)).toBeVisible();

    const pdfSignedUrl = await apiJson<{ url: string }>(
      apiStudent,
      'GET',
      `/modules/${moduleId}/sections/${firstLab!.id}/assets/${pdfAsset!.id}/download-url`,
    );
    expect(pdfSignedUrl.status).toBe(200);
    expect(pdfSignedUrl.body.url).toBeTruthy();

    const attachmentSignedUrl = await apiJson<{ detail: string }>(
      apiStudent,
      'GET',
      `/modules/${moduleId}/sections/${firstLab!.id}/assets/${notebookAsset!.id}/download-url`,
    );
    expect(attachmentSignedUrl.status).toBe(404);
    expect(attachmentSignedUrl.body).toMatchObject({ detail: 'SECTION_NOT_FOUND' });

    const attachmentResponse = await apiStudent.get(
      `/modules/${moduleId}/sections/${firstLab!.id}/assets/${notebookAsset!.id}/download`,
    );
    expect(attachmentResponse.status()).toBe(200);
    expect(attachmentResponse.headers()['content-disposition']).toContain('attachment');
    expect(attachmentResponse.headers()['x-content-type-options']).toBe('nosniff');

    const downloadPromise = studentPage.waitForEvent('download');
    await studentPage
      .getByTestId(`student-section-asset-row-${notebookAsset!.id}`)
      .getByRole('button', { name: `Open file ${NOTEBOOK_NAME}` })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(NOTEBOOK_NAME);
  } finally {
    await apiAdmin?.dispose();
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
