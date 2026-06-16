import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

import { expect, test, type Page } from '@playwright/test';

const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const E2E_ACTOR_DOMAIN = 'xyz-lms-e2e.dev';

type HookSessionResult = {
  data: {
    session: {
      access_token: string;
    } | null;
  };
};

type E2EApiResult<T = unknown> =
  | { ok: true; status: number; data: T }
  | { ok: false; status?: number; errorName: string; message?: string };

function loadE2eEnv() {
  return Object.fromEntries(
    readFileSync('.env.e2e', 'utf8')
      .split(/\r?\n/)
      .filter((line) => line.trim() && !line.trim().startsWith('#'))
      .map((line) => line.split(/=(.*)/s).slice(0, 2)),
  );
}

function assertAllowedSupabaseUrl(env: Record<string, string>) {
  const supabaseUrl = new URL(env.NEXT_PUBLIC_SUPABASE_URL);
  const allowedUrl = new URL(env.E2E_SUPABASE_ALLOWED_URL);

  if (supabaseUrl.href !== allowedUrl.href) {
    throw new Error('NEXT_PUBLIC_SUPABASE_URL must exactly match E2E_SUPABASE_ALLOWED_URL');
  }

  const isLocal =
    ['localhost', '127.0.0.1'].includes(supabaseUrl.hostname) &&
    supabaseUrl.port === '54321';
  const isDedicatedE2E =
    supabaseUrl.protocol === 'https:' &&
    supabaseUrl.hostname.endsWith('.supabase.co');

  if (!isLocal && !isDedicatedE2E) {
    throw new Error('E2E Supabase URL must be local Supabase or an exact dedicated Supabase project URL');
  }
}

function adminHeaders(env: Record<string, string>) {
  return {
    apikey: env.SUPABASE_SERVICE_ROLE_KEY,
    authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    'content-type': 'application/json',
  };
}

async function supabaseAdminFetch(
  env: Record<string, string>,
  path: string,
  init: RequestInit = {},
) {
  const response = await fetch(`${env.NEXT_PUBLIC_SUPABASE_URL}${path}`, {
    ...init,
    headers: {
      ...adminHeaders(env),
      ...(init.headers ?? {}),
    },
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message = body?.msg ?? body?.message ?? body?.error ?? response.statusText;
    throw new Error(`Supabase Admin API ${init.method ?? 'GET'} ${path} failed: ${message}`);
  }

  return body;
}

async function cleanupAuthUsers(emails: string[]) {
  const env = loadE2eEnv();
  assertAllowedSupabaseUrl(env);
  const body = await supabaseAdminFetch(env, '/auth/v1/admin/users?per_page=1000&page=1');
  const users = Array.isArray(body?.users) ? body.users : [];

  for (const email of emails) {
    if (!email.endsWith(`@${E2E_ACTOR_DOMAIN}`)) {
      throw new Error(`Refusing cleanup for non-E2E email: ${email}`);
    }
    const authUser = users.find((candidate: { email?: string }) => candidate.email === email);
    if (authUser?.id) {
      await supabaseAdminFetch(env, `/auth/v1/admin/users/${authUser.id}`, {
        method: 'DELETE',
      });
    }
  }
}

function sqlLiteral(value: string) {
  return `'${value.replaceAll("'", "''")}'`;
}

function runPsql(sql: string) {
  execFileSync(
    'docker',
    [
      'compose',
      'exec',
      '-T',
      'db',
      'psql',
      '-v',
      'ON_ERROR_STOP=1',
      '-U',
      'postgres',
      '-d',
      'xyz_lms',
    ],
    { encoding: 'utf8', input: sql },
  );
}

function cleanupAppRows(emails: string[], moduleTitles: string[]) {
  if (emails.some((email) => !email.endsWith(`@${E2E_ACTOR_DOMAIN}`))) {
    throw new Error('Refusing cleanup for non-E2E email');
  }
  if (moduleTitles.some((title) => !title.startsWith('Module '))) {
    throw new Error('Refusing cleanup for non-E2E module title');
  }

  runPsql(`
BEGIN;
WITH target_users AS (
  SELECT id FROM app_users WHERE email IN (${emails.map(sqlLiteral).join(', ')})
),
target_modules AS (
  SELECT id FROM course_modules WHERE title IN (${moduleTitles.map(sqlLiteral).join(', ')})
)
DELETE FROM course_memberships
WHERE user_id IN (SELECT id FROM target_users)
   OR module_id IN (SELECT id FROM target_modules);

WITH target_modules AS (
  SELECT id FROM course_modules WHERE title IN (${moduleTitles.map(sqlLiteral).join(', ')})
)
DELETE FROM module_sections
WHERE course_module_id IN (SELECT id FROM target_modules);

DELETE FROM course_modules
WHERE title IN (${moduleTitles.map(sqlLiteral).join(', ')});

DELETE FROM app_users
WHERE email IN (${emails.map(sqlLiteral).join(', ')});
COMMIT;
`);
}

async function cleanupRun(emails: string[], moduleTitles: string[]) {
  cleanupAppRows(emails, moduleTitles);
  await cleanupAuthUsers(emails);
}

async function waitForHooks(page: Page) {
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
}

async function signIn(
  page: Page,
  email: string,
  password: string,
  expectedPath?: string,
) {
  await page.goto('/login');
  await waitForHooks(page);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  if (expectedPath) {
    await expect(page).toHaveURL(new RegExp(`${expectedPath}$`));
    await waitForHooks(page);
  }
}

async function getSession(page: Page): Promise<HookSessionResult> {
  return page.evaluate(() => window.__xyzE2E!.getSession()) as Promise<HookSessionResult>;
}

async function callAdminUsers(page: Page): Promise<E2EApiResult> {
  return page.evaluate(() => window.__xyzE2E!.callAdminUsers()) as Promise<E2EApiResult>;
}

async function createUser(
  page: Page,
  role: 'lecturer' | 'student',
  email: string,
  fullName: string,
) {
  const form = page.getByTestId(`create-${role}-form`);
  await form.getByLabel(`${role} email`).fill(email);
  await form.getByLabel(`${role} full name`).fill(fullName);
  await form.getByLabel(`${role} password`).fill(PASSWORD);
  await form.getByRole('button', { name: `Create ${role}` }).click();
  await expect(page.getByTestId(`admin-user-row-${email.split('@')[0].replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase()}`)).toBeVisible();
}

async function createModule(
  page: Page,
  title: string,
  ownerFullName: string,
  ownerEmail: string,
) {
  const form = page.getByTestId('create-module-form');
  await form.getByLabel('Module title').fill(title);
  await form.getByLabel('Module owner lecturer').selectOption({
    label: `${ownerFullName} (${ownerEmail})`,
  });
  await form.getByLabel('Module description').fill(`${title} E2E proof`);
  // Stage 5.5a: module creation is schedule-driven; the form now requires course start/end dates
  // (the weekly pattern is a fixed default pending the 5.5e picker). Without these the browser blocks
  // submit client-side, so creation never reaches the backend.
  await form.getByLabel('Course starts on').fill('2026-05-11');
  await form.getByLabel('Course ends on').fill('2026-06-26');
  await form.getByRole('button', { name: 'Create module' }).click();
  await expect(page.getByTestId(`admin-module-row-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`)).toBeVisible();
}

async function selectManagedModule(page: Page, title: string) {
  await page.getByLabel('Managed module').selectOption({ label: title });
  await expect(page.getByRole('heading', { name: `${title} members` })).toBeVisible();
}

async function assignMember(
  page: Page,
  moduleTitle: string,
  role: 'lecturer' | 'student',
  fullName: string,
  email: string,
) {
  const form = page.getByTestId('assign-member-form');
  await form.getByLabel('Assignment module').selectOption({ label: moduleTitle });
  await form.getByLabel('Assignment role').selectOption({ label: role === 'lecturer' ? 'Lecturer' : 'Student' });
  await form.getByLabel('Assignment user').selectOption({ label: `${fullName} (${email})` });
  await form.getByRole('button', { name: 'Assign member' }).click();
  await selectManagedModule(page, moduleTitle);
  await expect(page.getByRole('region', { name: 'Module members' }).getByText(email)).toBeVisible();
}

test('4.3.5c Stage 2 admin UI browser gate', async ({ browser }) => {
  const runId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const ownerA = {
    email: `owner_a_${runId}@${E2E_ACTOR_DOMAIN}`,
    fullName: `Owner A ${runId}`,
  };
  const ownerB = {
    email: `owner_b_${runId}@${E2E_ACTOR_DOMAIN}`,
    fullName: `Owner B ${runId}`,
  };
  const mainLecturer = {
    email: `main_lecturer_${runId}@${E2E_ACTOR_DOMAIN}`,
    fullName: `Main Lecturer ${runId}`,
  };
  const student = {
    email: `student_${runId}@${E2E_ACTOR_DOMAIN}`,
    fullName: `Student ${runId}`,
  };
  const moduleA = `Module A ${runId}`;
  const moduleB = `Module B ${runId}`;
  const emails = [ownerA.email, ownerB.email, mainLecturer.email, student.email];
  const moduleTitles = [moduleA, moduleB];

  await cleanupRun(emails, moduleTitles);

  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();
  const freshInactiveContext = await browser.newContext();

  try {
    const adminPage = await adminContext.newPage();
    await signIn(adminPage, ADMIN_EMAIL, PASSWORD, '/admin');

    await createUser(adminPage, 'lecturer', ownerA.email, ownerA.fullName);
    await createUser(adminPage, 'lecturer', ownerB.email, ownerB.fullName);
    await createUser(adminPage, 'lecturer', mainLecturer.email, mainLecturer.fullName);
    await createUser(adminPage, 'student', student.email, student.fullName);

    await adminPage.reload();
    await expect(adminPage).toHaveURL(/\/admin$/);
    await waitForHooks(adminPage);

    await createModule(adminPage, moduleA, ownerA.fullName, ownerA.email);
    await createModule(adminPage, moduleB, ownerB.fullName, ownerB.email);

    await assignMember(adminPage, moduleA, 'lecturer', mainLecturer.fullName, mainLecturer.email);
    await assignMember(adminPage, moduleA, 'student', student.fullName, student.email);

    const memberRegion = adminPage.getByRole('region', { name: 'Module members' });
    await selectManagedModule(adminPage, moduleB);
    await expect(memberRegion.getByText(mainLecturer.email)).toHaveCount(0);
    await expect(memberRegion.getByText(student.email)).toHaveCount(0);
    await expect(adminPage.getByLabel('Assignment user')).not.toContainText(ADMIN_EMAIL);

    await assignMember(adminPage, moduleB, 'student', student.fullName, student.email);
    await selectManagedModule(adminPage, moduleB);
    const studentModuleBRow = memberRegion.locator('tr').filter({ hasText: student.email });
    await expect(studentModuleBRow).toBeVisible();
    await studentModuleBRow.getByRole('button', { name: 'Remove membership' }).click();
    await expect(studentModuleBRow).toHaveCount(0);

    const lecturerPage = await lecturerContext.newPage();
    await signIn(lecturerPage, mainLecturer.email, PASSWORD, '/lecturer');
    await expect(lecturerPage.getByText(moduleA)).toBeVisible();
    await expect(lecturerPage.getByText(moduleB)).toHaveCount(0);

    const studentPage = await studentContext.newPage();
    await signIn(studentPage, student.email, PASSWORD, '/student');
    await expect(studentPage.getByText(moduleA)).toBeVisible();
    await expect(studentPage.getByText(moduleB)).toHaveCount(0);

    const lecturerRow = adminPage.getByTestId(`admin-user-row-${mainLecturer.email.split('@')[0].replace(/[^a-zA-Z0-9]+/g, '-').toLowerCase()}`);
    await lecturerRow.getByRole('button', { name: 'Deactivate' }).click();
    await expect(lecturerRow).toContainText('Inactive');

    const freshInactivePage = await freshInactiveContext.newPage();
    await signIn(freshInactivePage, mainLecturer.email, PASSWORD);
    await expect(freshInactivePage.getByRole('heading', { name: 'Access denied' })).toBeVisible();

    await lecturerPage.reload();
    await expect(lecturerPage.getByRole('heading', { name: 'Access denied' })).toBeVisible();

    const forbiddenResult = await callAdminUsers(studentPage);
    expect(forbiddenResult.ok).toBe(false);
    if (forbiddenResult.ok) {
      throw new Error('Expected student admin call to fail');
    }
    expect(forbiddenResult.status).toBe(403);
    const session = await getSession(studentPage);
    expect(session.data.session).not.toBeNull();
    expect(studentPage.url()).not.toContain('/login');
  } finally {
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
    await freshInactiveContext.close();
    await cleanupRun(emails, moduleTitles);
  }
});
