import { expect, test, type Page } from '@playwright/test';

const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';

const USERS = {
  admin: { email: 'admin_e2e@example.test', home: '/admin', role: 'admin' },
  lecturer: {
    email: 'lecturer_e2e@example.test',
    home: '/lecturer',
    role: 'lecturer',
  },
  student: {
    email: 'student_e2e@example.test',
    home: '/student',
    role: 'student',
  },
} as const;

type Role = (typeof USERS)[keyof typeof USERS]['role'];

type CurrentUser = {
  role: Role;
};

type E2EApiResult<T = unknown> =
  | { ok: true; status: number; data: T }
  | { ok: false; status?: number; errorName: string; message?: string };

type HookSessionResult = {
  data: {
    session: {
      access_token: string;
    } | null;
  };
};

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
  const result = await getSession(page);
  const token = result.data.session?.access_token;
  expect(token).toBeTruthy();
  return token as string;
}

async function callMe(page: Page): Promise<E2EApiResult<CurrentUser>> {
  return page.evaluate(() => window.__xyzE2E!.callMe()) as Promise<
    E2EApiResult<CurrentUser>
  >;
}

async function callAdminUsers(page: Page): Promise<E2EApiResult> {
  return page.evaluate(() => window.__xyzE2E!.callAdminUsers()) as Promise<E2EApiResult>;
}

test('4.3.5b app shell role routing and auth recovery proof', async ({ browser }) => {
  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  try {
    await signIn(adminPage, USERS.admin.email, USERS.admin.home);
    const result = await callMe(adminPage);
    expect(result.ok).toBe(true);
    expect(result.status).toBe(200);
    if (!result.ok) {
      throw new Error('Expected admin /me call to succeed');
    }
    expect(result.data.role).toBe(USERS.admin.role);
  } finally {
    await adminContext.close();
  }

  const lecturerContext = await browser.newContext();
  const lecturerPage = await lecturerContext.newPage();
  try {
    await signIn(lecturerPage, USERS.lecturer.email, USERS.lecturer.home);
    const result = await callMe(lecturerPage);
    expect(result.ok).toBe(true);
    expect(result.status).toBe(200);
    if (!result.ok) {
      throw new Error('Expected lecturer /me call to succeed');
    }
    expect(result.data.role).toBe(USERS.lecturer.role);
  } finally {
    await lecturerContext.close();
  }

  const studentContext = await browser.newContext();
  const studentPage = await studentContext.newPage();
  try {
    await signIn(studentPage, USERS.student.email, USERS.student.home);
    const result = await callMe(studentPage);
    expect(result.ok).toBe(true);
    expect(result.status).toBe(200);
    if (!result.ok) {
      throw new Error('Expected student /me call to succeed');
    }
    expect(result.data.role).toBe(USERS.student.role);
  } finally {
    await studentContext.close();
  }

  const refreshContext = await browser.newContext();
  const refreshPage = await refreshContext.newPage();
  try {
    await signIn(refreshPage, USERS.lecturer.email, USERS.lecturer.home);
    const oldToken = await getAccessToken(refreshPage);
    await refreshPage.evaluate(() => window.__xyzE2E!.refreshSession());
    const newToken = await getAccessToken(refreshPage);
    expect(newToken).not.toBe(oldToken);

    const requestPromise = refreshPage.waitForRequest(
      (request) => request.url().includes('/me') && request.method() === 'GET',
    );
    const resultPromise = callMe(refreshPage);
    const request = await requestPromise;
    const result = await resultPromise;
    expect(request.headers().authorization).toBe(`Bearer ${newToken}`);
    expect(result.ok).toBe(true);
    expect(result.status).toBe(200);
  } finally {
    await refreshContext.close();
  }

  const recoveryContext = await browser.newContext();
  const recoveryPage = await recoveryContext.newPage();
  try {
    await signIn(recoveryPage, USERS.lecturer.email, USERS.lecturer.home);
    await recoveryPage.evaluate(() =>
      window.__xyzE2E!.forceNextBearerToken('malformed.jwt.token'),
    );

    const firstResult = await callMe(recoveryPage);
    expect(firstResult.ok).toBe(false);
    if (firstResult.ok) {
      throw new Error('Expected malformed token /me call to fail');
    }
    expect(firstResult.status).toBe(401);
    await expect(recoveryPage).toHaveURL(/\/login$/);
    await waitForHooks(recoveryPage);
    let session = await getSession(recoveryPage);
    expect(session.data.session).toBeNull();

    const secondResult = await callMe(recoveryPage);
    expect(secondResult.ok).toBe(false);
    if (secondResult.ok) {
      throw new Error('Expected signed-out /me call to fail');
    }
    expect(secondResult.status).toBe(401);
    await expect(recoveryPage).toHaveURL(/\/login$/);
    await waitForHooks(recoveryPage);
    session = await getSession(recoveryPage);
    expect(session.data.session).toBeNull();
  } finally {
    await recoveryContext.close();
  }

  const guardContext = await browser.newContext();
  const guardPage = await guardContext.newPage();
  try {
    await signIn(guardPage, USERS.student.email, USERS.student.home);
    await guardPage.goto('/admin');
    await expect(guardPage).toHaveURL(/\/unauthorized$/);
    await expect(guardPage.getByRole('heading', { name: 'Unauthorized' })).toBeVisible();
    expect(guardPage.url()).not.toContain('/login');
    const session = await getSession(guardPage);
    expect(session.data.session).not.toBeNull();
  } finally {
    await guardContext.close();
  }

  const forbiddenContext = await browser.newContext();
  const forbiddenPage = await forbiddenContext.newPage();
  try {
    await signIn(forbiddenPage, USERS.student.email, USERS.student.home);
    const result = await callAdminUsers(forbiddenPage);
    expect(result.ok).toBe(false);
    if (result.ok) {
      throw new Error('Expected student admin users call to fail');
    }
    expect(result.status).toBe(403);
    const session = await getSession(forbiddenPage);
    expect(session.data.session).not.toBeNull();
    expect(forbiddenPage.url()).not.toContain('/login');
  } finally {
    await forbiddenContext.close();
  }

  const logoutContext = await browser.newContext();
  const logoutPage = await logoutContext.newPage();
  try {
    await signIn(logoutPage, USERS.lecturer.email, USERS.lecturer.home);
    await logoutPage.getByRole('button', { name: 'Log out' }).click();
    await expect(logoutPage).toHaveURL(/\/login$/);
    await waitForHooks(logoutPage);
    let session = await getSession(logoutPage);
    expect(session.data.session).toBeNull();

    await logoutPage.goto('/lecturer');
    await expect(logoutPage).toHaveURL(/\/login$/);
    await waitForHooks(logoutPage);
    session = await getSession(logoutPage);
    expect(session.data.session).toBeNull();
  } finally {
    await logoutContext.close();
  }
});
