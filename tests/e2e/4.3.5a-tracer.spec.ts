import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

import { expect, test, type Page } from '@playwright/test';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const MODULE_TITLE = 'e2e_module';
const DRAFT_SECTION_TITLE = 'lecture_section';
const PUBLISHED_SECTION_TITLE = 'published_section';
const PDF_BYTES = '%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n';

type ApiResult<T = unknown> = {
  body: T;
  headers: Record<string, string>;
  status: number;
  url: string;
};

type CurrentUserResponse = {
  role: string;
  activeModuleMemberships: Array<{ moduleId: string; role: string }>;
};

type ModuleSummary = {
  id: string;
  title: string;
};

type SectionListItem = {
  id: string;
  title: string;
};

type SectionAssetResponse = {
  id: string;
};

type AssetDownloadUrl = {
  url: string;
};

function loadE2eEnv() {
  return Object.fromEntries(
    readFileSync('.env.e2e', 'utf8')
      .split(/\r?\n/)
      .filter((line) => line && !line.startsWith('#'))
      .map((line) => line.split(/=(.*)/s).slice(0, 2)),
  );
}

async function signIn(page: Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByText('Session status: authenticated')).toBeVisible();
  const token = await page.evaluate(async () => {
    const key = Object.keys(window.localStorage).find(
      (candidate) =>
        candidate.startsWith('sb-') && candidate.endsWith('-auth-token'),
    );
    if (!key) {
      return null;
    }
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw).access_token as string | null;
  });
  expect(token).toBeTruthy();
  return token as string;
}

async function apiRequest<T>(
  page: Page,
  method: string,
  path: string,
  init: { body?: unknown; headers?: Record<string, string> } = {},
): Promise<ApiResult<T>> {
  return page.evaluate(
    async ({ apiBaseUrl, body, headers, method, path }) => {
      const key = Object.keys(window.localStorage).find(
        (candidate) =>
          candidate.startsWith('sb-') && candidate.endsWith('-auth-token'),
      );
      const raw = key ? window.localStorage.getItem(key) : null;
      const token = raw ? JSON.parse(raw).access_token : null;
      const response = await fetch(`${apiBaseUrl}${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body === undefined ? {} : { 'content-type': 'application/json' }),
          ...headers,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await response.text();
      let parsed: unknown = text;
      try {
        parsed = text ? JSON.parse(text) : null;
      } catch {
        parsed = text;
      }
      return {
        body: parsed,
        headers: Object.fromEntries(response.headers.entries()),
        status: response.status,
        url: response.url,
      };
    },
    { apiBaseUrl: API_BASE_URL, body: init.body, headers: init.headers, method, path },
  ) as Promise<ApiResult<T>>;
}

async function uploadFile(
  page: Page,
  moduleId: string,
  sectionId: string,
  fileName: string,
  mimeType: string,
  contents: string,
) {
  const chooserPromise = page.waitForEvent('filechooser');
  await page
    .getByLabel(fileName.endsWith('.pdf') ? 'PDF file' : 'Non-PDF file', {
      exact: true,
    })
    .click();
  const chooser = await chooserPromise;
  await chooser.setFiles({
    name: fileName,
    mimeType,
    buffer: Buffer.from(contents),
  });
  await page
    .getByRole('button', {
      name: fileName.endsWith('.pdf') ? 'upload PDF' : 'upload non-PDF',
    })
    .click();
  await expect(page.getByText(`Last action: upload ${fileName.endsWith('.pdf') ? 'PDF' : 'non-PDF'}`)).toBeVisible();
  await expect(page.locator('section').filter({ hasText: 'Raw Result' })).toContainText(
    '"ok"',
  );
  const raw = await page.locator('section').filter({ hasText: 'Raw Result' }).locator('pre').innerText();
  return JSON.parse(raw) as { ok: boolean; data?: SectionAssetResponse; status?: number };
}

async function selectTracerModuleAndSection(
  page: Page,
  sectionId: string,
) {
  await expect(page.getByText(`Selected module title: ${MODULE_TITLE}`)).toBeVisible();
  await page.getByLabel('Section ID override', { exact: true }).fill(sectionId);
}

function storageKeyForAsset(assetId: string) {
  return execFileSync(
    'docker',
    [
      'compose',
      'exec',
      '-T',
      'db',
      'psql',
      '-U',
      'postgres',
      '-d',
      'xyz_lms',
      '-tA',
      '-c',
      `select storage_key from section_assets where id='${assetId}'::uuid;`,
    ],
    { encoding: 'utf8' },
  ).trim();
}

async function cleanupExactStorageKey(key: string) {
  if (!key || key.includes('*') || key.endsWith('/')) {
    throw new Error(`Refusing broad storage cleanup key: ${key}`);
  }
  const env = loadE2eEnv();
  const response = await fetch(
    `${env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/object/${env.SUPABASE_STORAGE_BUCKET}`,
    {
      method: 'DELETE',
      headers: {
        apikey: env.SUPABASE_SERVICE_ROLE_KEY,
        authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ prefixes: [key] }),
    },
  );
  expect(response.ok).toBe(true);
}

function cleanupExactAssetRow(assetId: string) {
  if (!/^[0-9a-f-]{36}$/i.test(assetId)) {
    throw new Error(`Refusing asset cleanup for invalid id: ${assetId}`);
  }
  execFileSync(
    'docker',
    [
      'compose',
      'exec',
      '-T',
      'db',
      'psql',
      '-U',
      'postgres',
      '-d',
      'xyz_lms',
      '-c',
      `delete from section_assets where id='${assetId}'::uuid;`,
    ],
    { encoding: 'utf8' },
  );
}

test('4.3.5a tracer proves browser to API to storage spine', async ({ browser }) => {
  const corsErrors: string[] = [];
  const preflights: Array<{ headers: Record<string, string>; status: number }> = [];
  let lecturerToken = '';
  let studentToken = '';
  let moduleId = '';
  let draftSectionId = '';
  let publishedSectionId = '';
  let assetId = '';
  let storageKey = '';
  let signedUrl = '';

  const lecturerContext = await browser.newContext();
  const lecturerPage = await lecturerContext.newPage();
  lecturerPage.on('console', (message) => {
    const text = message.text();
    if (text.toLowerCase().includes('cors')) {
      corsErrors.push(text);
    }
  });
  lecturerPage.on('response', (response) => {
    if (response.request().method() === 'OPTIONS') {
      preflights.push({
        status: response.status(),
        headers: response.headers(),
      });
    }
  });

  try {
    lecturerToken = await signIn(lecturerPage, LECTURER_EMAIL);
    await lecturerPage.goto('/tracer');
    await expect(lecturerPage.getByText('Status: logged in')).toBeVisible();

    await lecturerPage.getByRole('button', { name: 'GET /me' }).click();
    await expect(lecturerPage.getByText('Role: lecturer')).toBeVisible();
    const lecturerMe = await apiRequest<CurrentUserResponse>(lecturerPage, 'GET', '/me');
    expect(lecturerMe.status).toBe(200);
    expect(lecturerMe.body.role).toBe('lecturer');
    expect(lecturerMe.body.activeModuleMemberships.length).toBeGreaterThan(0);

    await lecturerPage.getByRole('button', { name: 'GET /modules' }).click();
    const lecturerModules = await apiRequest<Array<ModuleSummary>>(
      lecturerPage,
      'GET',
      `/modules?tracer=${Date.now()}`,
    );
    expect(lecturerModules.status).toBe(200);
    expect(lecturerModules.body).toHaveLength(1);
    expect(lecturerModules.body[0].title).toBe(MODULE_TITLE);
    moduleId = lecturerModules.body[0].id;
    expect(corsErrors).toEqual([]);
    for (const preflight of preflights) {
      expect(preflight.status).toBeLessThan(400);
      expect(preflight.headers['access-control-allow-origin']).toBe('http://localhost:3000');
    }

    const sections = await apiRequest<Array<SectionListItem>>(
      lecturerPage,
      'GET',
      `/modules/${moduleId}/sections`,
    );
    expect(sections.status).toBe(200);
    draftSectionId = sections.body.find((section) => section.title === DRAFT_SECTION_TITLE)?.id ?? '';
    publishedSectionId =
      sections.body.find((section) => section.title === PUBLISHED_SECTION_TITLE)?.id ?? '';
    expect(draftSectionId).toBeTruthy();
    expect(publishedSectionId).toBeTruthy();
    await selectTracerModuleAndSection(lecturerPage, publishedSectionId);

    const upload = await uploadFile(
      lecturerPage,
      moduleId,
      publishedSectionId,
      'lecture.pdf',
      'application/pdf',
      PDF_BYTES,
    );
    expect(upload.ok).toBe(true);
    expect(upload.data?.id).toBeTruthy();
    assetId = upload.data?.id ?? '';
    storageKey = storageKeyForAsset(assetId);
    expect(storageKey).toContain(`/assets/${assetId}/`);

    const nonPdf = await uploadFile(
      lecturerPage,
      moduleId,
      publishedSectionId,
      'not-a-pdf.txt',
      'text/plain',
      'plain text',
    );
    expect(nonPdf.ok).toBe(false);
    expect(nonPdf.status).toBeGreaterThanOrEqual(400);
    expect(nonPdf.status).toBeLessThan(500);

    await lecturerPage.getByRole('button', { name: 'publish section' }).click();
    const publish = await apiRequest<{ publishStatus?: string }>(
      lecturerPage,
      'POST',
      `/modules/${moduleId}/sections/${publishedSectionId}/publish`,
    );
    expect(publish.status).toBe(200);
    expect(publish.body.publishStatus).toBe('published');
  } finally {
    await lecturerContext.close();
  }

  const studentContext = await browser.newContext();
  const studentPage = await studentContext.newPage();
  try {
    studentToken = await signIn(studentPage, STUDENT_EMAIL);
    expect(studentToken).not.toBe(lecturerToken);
    await studentPage.goto('/tracer');
    await expect(studentPage.getByText('Status: logged in')).toBeVisible();

    await studentPage.getByRole('button', { name: 'GET /me' }).click();
    await expect(studentPage.getByText('Role: student')).toBeVisible();
    const studentMe = await apiRequest<CurrentUserResponse>(studentPage, 'GET', '/me');
    expect(studentMe.status).toBe(200);
    expect(studentMe.body.role).toBe('student');

    const studentSections = await apiRequest<Array<SectionListItem>>(
      studentPage,
      'GET',
      `/modules/${moduleId}/sections`,
    );
    expect(studentSections.status).toBe(200);
    expect(studentSections.body.some((section) => section.id === publishedSectionId)).toBe(true);

    await studentPage.getByRole('button', { name: 'GET /modules' }).click();
    await selectTracerModuleAndSection(studentPage, draftSectionId);
    await studentPage.getByRole('button', { name: 'GET selected section' }).click();
    await expect(
      studentPage.locator('section').filter({ hasText: 'Unauthorized State' }),
    ).toContainText(/"status": (403|404)/);
    expect(studentPage.url()).toContain('/tracer');
    const draftResponse = await apiRequest(
      studentPage,
      'GET',
      `/modules/${moduleId}/sections/${draftSectionId}`,
    );
    expect([403, 404]).toContain(draftResponse.status);
    await selectTracerModuleAndSection(studentPage, publishedSectionId);
    await studentPage.getByLabel('Asset ID', { exact: true }).fill(assetId);
    await studentPage.getByRole('button', { name: 'request signed URL' }).click();
    await expect(studentPage.locator('section').filter({ hasText: 'Raw Result' })).toContainText('"ok": true');
    expect(studentPage.url()).toContain('/tracer');

    const download = await apiRequest<AssetDownloadUrl>(
      studentPage,
      'GET',
      `/modules/${moduleId}/sections/${publishedSectionId}/assets/${assetId}/download-url`,
    );
    expect(download.status).toBe(200);
    expect(download.body.url).toBeTruthy();
    signedUrl = download.body.url;
    expect(download.headers['cache-control']).toBe('no-store');

    const signedResponse = await studentContext.request.get(signedUrl, {
      headers: { Authorization: '' },
    });
    expect(signedResponse.status()).toBe(200);
    const signedBytes = await signedResponse.body();
    expect(signedBytes.toString()).toContain('%PDF-1.4');

    await selectTracerModuleAndSection(studentPage, publishedSectionId);
    const chooserPromise = studentPage.waitForEvent('filechooser');
    await studentPage.getByLabel('PDF file', { exact: true }).click();
    const chooser = await chooserPromise;
    await chooser.setFiles({
      name: 'student-upload.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(PDF_BYTES),
    });
    await studentPage
      .getByRole('button', { name: 'attempt upload as current user for student 403' })
      .click();
    await expect(
      studentPage.locator('section').filter({ hasText: 'Unauthorized State' }),
    ).toContainText('"status": 403');
    await expect(
      studentPage.locator('section').filter({ hasText: 'Unauthorized State' }),
    ).toContainText('session still present');
    expect(studentPage.url()).toContain('/tracer');
    const keptSessionToken = await studentPage.evaluate(() => {
      const key = Object.keys(window.localStorage).find(
        (candidate) =>
          candidate.startsWith('sb-') && candidate.endsWith('-auth-token'),
      );
      const raw = key ? window.localStorage.getItem(key) : null;
      return raw ? JSON.parse(raw).access_token : null;
    });
    expect(keptSessionToken).toBe(studentToken);
  } finally {
    await studentContext.close();
    if (storageKey) {
      await cleanupExactStorageKey(storageKey);
    }
    if (assetId) {
      cleanupExactAssetRow(assetId);
    }
  }
});
