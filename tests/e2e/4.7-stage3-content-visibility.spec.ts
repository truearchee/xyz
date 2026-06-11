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
  getSectionsForModule,
} from './fixtures/db.mjs';

// Stage 4.7 hard-prerequisite P1 — RESTORED Stage 3 content-visibility browser gate (rule 14).
//
// The original Stage 3 gate (session 4.3.5d Checkpoint E + supplemental E2) ran via a throwaway
// CommonJS runner that was never committed — "an archived spec is a dead spec." This re-authors its
// assertions as a live Playwright spec against the CURRENT auth/session/API contract. Every assertion
// below is traceable to a line in the 4.3.5d Checkpoint E / E2 reports (see knowledge/steps for the
// assertion → source-line mapping). The load-bearing guarantee — "students never see unpublished
// content" — is asserted on the SERVER PAYLOAD and the RENDERED UI, on bodies (not just status codes),
// with the session proven preserved.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';

// Minimal VALID pdf — the content validator only checks the `%PDF-` magic + non-empty (validators.py).
const PDF_BYTES = Buffer.from('%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n');
const NON_PDF_BYTES = Buffer.from('this is not a pdf at all');
const ORIGINAL_PDF = 'stage3-original.pdf';
const REPLACEMENT_PDF = 'stage3-replacement.pdf';
const NOTES = `Stage 3 restored gate notes ${process.env.E2E_RUN_ID ?? 'local'}`;

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

async function apiJson<T>(
  context: APIRequestContext,
  method: 'GET' | 'POST' | 'PATCH',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response =
    method === 'GET'
      ? await context.get(path)
      : method === 'PATCH'
        ? await context.patch(path, { data: body })
        : await context.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

async function apiUpload<T>(
  context: APIRequestContext,
  method: 'POST' | 'PUT',
  path: string,
  fileName: string,
  buffer: Buffer,
  mimeType: string,
): Promise<ApiResponse<T>> {
  const opts = { multipart: { file: { name: fileName, mimeType, buffer } } };
  const response = method === 'POST' ? await context.post(path, opts) : await context.put(path, opts);
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) {
    throw new Error('E2E_RUN_ID must be exported before running the Stage 3 restore gate');
  }
  return runId;
}

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

async function createRunModule(runId: string, adminContext: APIRequestContext) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) {
    throw new Error('Standing lecturer/student E2E users are required');
  }
  const moduleTitle = `Stage 3 Restored Gate ${runId}`;
  const moduleCreate = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title: moduleTitle,
    description: `Stage 3 content-visibility restore ${runId}`,
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
  return { moduleId, moduleTitle, sections };
}

test('4.7 P1 — Stage 3 content-visibility (restored)', async ({ browser }) => {
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

    const lecture1 = sectionByTitle(setup.sections, 'Lecture 1');
    const lecture2 = sectionByTitle(setup.sections, 'Lecture 2');

    // --- Lecturer setup through the real backend (product path) ---
    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));

    // Upload a valid PDF to Lecture 1, then replace it by asset id (filename changes).
    const upload = await apiUpload<{ id: string; fileName: string; processingStatus: string }>(
      apiLecturer,
      'POST',
      `/modules/${setup.moduleId}/sections/${lecture1.id}/assets`,
      ORIGINAL_PDF,
      PDF_BYTES,
      'application/pdf',
    );
    expect(upload.status).toBe(201);
    expect(upload.body.fileName).toBe(ORIGINAL_PDF);
    expect(upload.body.processingStatus).toBeTruthy();
    const assetId = upload.body.id;
    recordManifestValue(runId, 'assetIds', assetId);

    const replace = await apiUpload<{ id: string; fileName: string }>(
      apiLecturer,
      'PUT',
      `/modules/${setup.moduleId}/sections/${lecture1.id}/assets/${assetId}`,
      REPLACEMENT_PDF,
      PDF_BYTES,
      'application/pdf',
    );
    expect(replace.status).toBe(200);
    expect(replace.body.id).toBe(assetId); // same asset row — replaced by id
    expect(replace.body.fileName).toBe(REPLACEMENT_PDF);

    // Non-PDF upload to Lecture 2 is rejected (422) and creates no asset.
    const badUpload = await apiUpload<{ detail: string }>(
      apiLecturer,
      'POST',
      `/modules/${setup.moduleId}/sections/${lecture2.id}/assets`,
      'notes.txt',
      NON_PDF_BYTES,
      'text/plain',
    );
    expect(badUpload.status).toBe(422);
    const lecture2Assets = await apiJson<{ assets: unknown[] }>(
      apiLecturer,
      'GET',
      `/modules/${setup.moduleId}/sections/${lecture2.id}/assets`,
    );
    expect(lecture2Assets.body.assets).toHaveLength(0);

    // Notes on Lecture 1, then publish Lecture 1 only (Lecture 2 / Lab 1 / Assignment 1 stay draft).
    const notes = await apiJson(apiLecturer, 'PATCH', `/modules/${setup.moduleId}/sections/${lecture1.id}/notes`, {
      lecturerNotes: NOTES,
    });
    expect(notes.status).toBe(200);
    const publish = await apiJson<{ publishStatus: string }>(
      apiLecturer,
      'POST',
      `/modules/${setup.moduleId}/sections/${lecture1.id}/publish`,
    );
    expect(publish.status).toBe(200);
    expect(publish.body.publishStatus).toBe('published');

    // --- Student: server payload shows ONLY the published section ---
    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(studentPage));

    const studentSections = await apiJson<Array<{ id: string; title: string }>>(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections`,
    );
    expect(studentSections.status).toBe(200);
    expect(studentSections.body.map((s) => s.title)).toEqual(['Lecture 1']); // EXACT — not "includes"
    expect(studentSections.body.map((s) => s.id)).toEqual([lecture1.id]);

    const studentDetail = await apiJson<{ lecturerNotes: string; assets: Array<{ fileName: string }> }>(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections/${lecture1.id}`,
    );
    expect(studentDetail.status).toBe(200);
    expect(studentDetail.body.lecturerNotes).toBe(NOTES);
    expect(studentDetail.body.assets.map((a) => a.fileName)).toContain(REPLACEMENT_PDF);

    // Draft section direct fetch → 404 SECTION_NOT_FOUND (unpublished is indistinguishable from absent).
    const draftFetch = await apiJson<{ detail: string }>(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections/${lecture2.id}`,
    );
    expect(draftFetch.status).toBe(404);
    expect(draftFetch.body).toMatchObject({ detail: 'SECTION_NOT_FOUND' });

    // Signed URL for the published asset → 200 with a url.
    const signed = await apiJson<{ url: string }>(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections/${lecture1.id}/assets/${assetId}/download-url`,
    );
    expect(signed.status).toBe(200);
    expect(signed.body.url).toBeTruthy();

    // Authenticated student upload attempt → 403 CONTENT_FORBIDDEN, session preserved.
    const studentUpload = await apiUpload<{ detail: string }>(
      apiStudent,
      'POST',
      `/modules/${setup.moduleId}/sections/${lecture1.id}/assets`,
      ORIGINAL_PDF,
      PDF_BYTES,
      'application/pdf',
    );
    expect(studentUpload.status).toBe(403);
    expect(studentUpload.body).toMatchObject({ detail: 'CONTENT_FORBIDDEN' });
    const meAfter403 = await apiJson<{ role: string }>(apiStudent, 'GET', '/me');
    expect(meAfter403.status).toBe(200);
    expect(meAfter403.body.role).toBe('student');

    // --- Student UI shows ONLY the published section ---
    await studentPage.goto(`/student/modules/${setup.moduleId}`);
    await expect(studentPage.locator('[data-testid="student-section-list"]')).toBeVisible();
    await expect(studentPage.getByRole('heading', { name: 'Lecture 1', exact: true })).toBeVisible();
    for (const hidden of ['Lecture 2', 'Lab 1', 'Assignment 1']) {
      await expect(studentPage.getByRole('heading', { name: hidden, exact: true })).toHaveCount(0);
    }
    await expect(studentPage.getByText(NOTES)).toBeVisible();
    await expect(studentPage.getByText(REPLACEMENT_PDF)).toBeVisible();
    expect(studentPage.url()).not.toContain('/login');

    // --- Revocation: unpublish removes the section from the student surface AND revokes minting ---
    const unpublish = await apiJson<{ publishStatus: string }>(
      apiLecturer,
      'POST',
      `/modules/${setup.moduleId}/sections/${lecture1.id}/unpublish`,
    );
    expect(unpublish.status).toBe(200);
    expect(unpublish.body.publishStatus).toBe('unpublished');

    const afterUnpublishSections = await apiJson<unknown[]>(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections`,
    );
    expect(afterUnpublishSections.status).toBe(200);
    expect(afterUnpublishSections.body).toEqual([]); // student now sees nothing
    const meAfterUnpublish = await apiJson<{ role: string }>(apiStudent, 'GET', '/me');
    expect(meAfterUnpublish.body.role).toBe('student'); // session preserved

    // Fresh signed-URL request for the now-unpublished asset → 403 CONTENT_FORBIDDEN (NOT 404). The
    // E2-B1 contract: revocation blocks FUTURE minting; an authorized actor gets 403, never an
    // existence-hiding 404.
    const revokedSigned = await apiJson<{ detail: string }>(
      apiStudent,
      'GET',
      `/modules/${setup.moduleId}/sections/${lecture1.id}/assets/${assetId}/download-url`,
    );
    expect(revokedSigned.status).toBe(403);
    expect(revokedSigned.body).toMatchObject({ detail: 'CONTENT_FORBIDDEN' });
    expect(revokedSigned.status).not.toBe(404);

    // Student UI reload → the section is gone.
    await studentPage.reload();
    await expect(studentPage.getByRole('heading', { name: 'Lecture 1', exact: true })).toHaveCount(0);
  } finally {
    await apiAdmin?.dispose();
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
