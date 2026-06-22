import { expect, request as playwrightRequest, test, type APIRequestContext, type Browser, type Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

import { runPsqlJson, runPsqlRows, sqlLiteral } from './fixtures/db.mjs';

// Stage 10 gamification browser gate (Scenarios A/B/C). All schedule/engagement dates are RELATIVE,
// computed by the DATABASE via now() arithmetic (COURSE_TIMEZONE=UTC in .env.e2e), so the host and the
// container can never disagree on "today" — no hardcoded calendar dates, no time-travel (rule 9).

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const E2E_ACTOR_DOMAIN = 'xyz-lms-e2e.dev';
const RUNS_DIR = resolve('tests/e2e/.runs');

type SeededUser = { key: string; email: string; appId: string };

test.setTimeout(180_000);

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the Stage 10 gate');
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) throw new Error(`Invalid E2E run id: ${runId}`);
  const manifestPath = manifestPathForRunId(runId);
  if (!existsSync(manifestPath)) {
    mkdirSync(RUNS_DIR, { recursive: true });
    writeFileSync(
      manifestPath,
      `${JSON.stringify(
        { runId, authUserIds: [], appUserIds: [], moduleIds: [], sectionIds: [], membershipIds: [], createdAt: new Date().toISOString() },
        null,
        2,
      )}\n`,
    );
  }
  return runId;
}

function manifestPathForRunId(runId: string): string {
  return resolve(RUNS_DIR, `${runId}.json`);
}

function recordValue(runId: string, field: string, value: string) {
  const manifestPath = manifestPathForRunId(runId);
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as Record<string, unknown>;
  const values = Array.isArray(manifest[field]) ? (manifest[field] as string[]) : [];
  manifest[field] = [...new Set([...values, value])];
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
}

function loadE2EEnv(): Record<string, string> {
  const path = '.env.e2e';
  if (!existsSync(path)) throw new Error('.env.e2e is required for the Stage 10 browser gate');
  const parsed: Record<string, string> = {};
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const separator = trimmed.indexOf('=');
    if (separator === -1) continue;
    parsed[trimmed.slice(0, separator)] = trimmed.slice(separator + 1).replace(/^"(.*)"$/, '$1');
  }
  const env = { ...parsed, ...process.env };
  for (const key of ['NEXT_PUBLIC_SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'E2E_TEST_PASSWORD']) {
    if (!env[key]) throw new Error(`${key} is required for the Stage 10 browser gate`);
  }
  return env;
}

function e2ePassword(): string {
  return process.env.E2E_TEST_PASSWORD ?? loadE2EEnv().E2E_TEST_PASSWORD;
}

async function supabaseAdminFetch(env: Record<string, string>, path: string, init: RequestInit = {}) {
  const response = await fetch(`${env.NEXT_PUBLIC_SUPABASE_URL}${path}`, {
    ...init,
    headers: {
      apikey: env.SUPABASE_SERVICE_ROLE_KEY,
      authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
      'content-type': 'application/json',
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

async function ensureAuthUser(runId: string, key: string, role: 'student' | 'lecturer'): Promise<SeededUser> {
  const env = loadE2EEnv();
  const email = `stage10-${key}-${runId}@${E2E_ACTOR_DOMAIN}`;
  const usersBody = await supabaseAdminFetch(env, '/auth/v1/admin/users?per_page=1000&page=1');
  const existing = Array.isArray(usersBody?.users)
    ? usersBody.users.find((candidate: { email?: string }) => candidate.email === email)
    : null;
  const payload = {
    email,
    password: env.E2E_TEST_PASSWORD,
    email_confirm: true,
    user_metadata: { full_name: `Stage 10 ${key}`, e2e_fixture: '10' },
  };
  const authBody = existing?.id
    ? await supabaseAdminFetch(env, `/auth/v1/admin/users/${existing.id}`, { method: 'PUT', body: JSON.stringify(payload) })
    : await supabaseAdminFetch(env, '/auth/v1/admin/users', { method: 'POST', body: JSON.stringify(payload) });
  const authUser = authBody?.user ?? authBody;
  recordValue(runId, 'authUserIds', authUser.id);
  const appId = randomUUID();
  const persistedAppId = runPsqlJson(`
WITH upserted AS (
  INSERT INTO app_users (id, auth_provider_id, email, full_name, role, is_active, timezone)
  VALUES (${sqlLiteral(appId)}::uuid, ${sqlLiteral(authUser.id)}, ${sqlLiteral(email)}, ${sqlLiteral(`Stage 10 ${key}`)}, ${sqlLiteral(role)}, true, 'UTC')
  ON CONFLICT (auth_provider_id) DO UPDATE
  SET email = EXCLUDED.email, full_name = EXCLUDED.full_name, role = ${sqlLiteral(role)}, is_active = true, timezone = 'UTC'
  RETURNING id
)
SELECT to_json(id)::text FROM upserted;
`) as unknown as string;
  recordValue(runId, 'appUserIds', persistedAppId);
  return { key, email, appId: persistedAppId };
}

function insertModule(runId: string, title: string, ownerId: string): string {
  const id = randomUUID();
  runPsqlRows(`
INSERT INTO course_modules (id, title, description, owner_id, timezone, is_active)
VALUES (${sqlLiteral(id)}::uuid, ${sqlLiteral(title)}, 'Stage 10 gamification E2E module', ${sqlLiteral(ownerId)}::uuid, 'UTC', true);
`);
  recordValue(runId, 'moduleIds', id);
  return id;
}

function insertMembership(runId: string, userId: string, moduleId: string, role: 'student' | 'lecturer') {
  const id = randomUUID();
  runPsqlRows(`
INSERT INTO course_memberships (id, user_id, module_id, role, status)
VALUES (${sqlLiteral(id)}::uuid, ${sqlLiteral(userId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(role)}, 'active');
`);
  recordValue(runId, 'membershipIds', id);
}

// Section scheduled RELATIVE to the DB's current UTC date (dayOffset days from today; <=0 = past/today).
// publishStatus defaults to 'published' — pass 'unpublished' to exercise the visibility-leak negative case.
function insertSection(
  runId: string,
  moduleId: string,
  title: string,
  dayOffset: number,
  orderIndex: number,
  publishStatus: 'published' | 'unpublished' = 'published',
): string {
  const id = randomUUID();
  runPsqlRows(`
INSERT INTO module_sections (id, course_module_id, title, type, order_index, week_number, session_date, publish_status, status)
VALUES (${sqlLiteral(id)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(title)}, 'lecture', ${orderIndex}, 1,
        (now() AT TIME ZONE 'UTC')::date + (${dayOffset}), ${sqlLiteral(publishStatus)}, 'active');
`);
  recordValue(runId, 'sectionIds', id);
  return id;
}

// A top-tier ('strong') Stage 9 topic-mastery snapshot for a section — the input the topic_mastered
// badge keys off. Used to prove the badge is NOT awarded when the section is not student-visible.
function insertMasterySnapshot(studentId: string, moduleId: string, sectionId: string) {
  runPsqlRows(`
INSERT INTO student_topic_mastery_snapshots (id, student_id, module_id, module_section_id, mastery_percentage, status_label)
VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(sectionId)}::uuid, 95, 'strong');
`);
}

// completed_quiz event RELATIVE to now() (occurred_at = now() + dayOffset days; UTC date = today+offset).
function insertCompletedQuiz(studentId: string, moduleId: string, dayOffset: number, sectionId?: string) {
  const defId = randomUUID();
  const meta = sectionId
    ? `'{"quizMode":"post_class","quizDefinitionId":"${defId}","moduleSectionId":"${sectionId}"}'`
    : `'{"quizMode":"post_class","quizDefinitionId":"${defId}"}'`;
  runPsqlRows(`
INSERT INTO student_activity_events (id, student_id, module_id, event_type, source_id, occurred_at, metadata)
VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'completed_quiz',
        gen_random_uuid(), now() + INTERVAL '${dayOffset} days', ${meta}::jsonb);
`);
}

function studiedSectionCount(studentId: string, sectionId: string): number {
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text FROM student_activity_events
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND event_type = 'studied_section'
  AND metadata->>'sectionId' = ${sqlLiteral(sectionId)};
`) as unknown as number;
}

async function waitForHooks(page: Page) {
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
}

async function signIn(page: Page, email: string, expectedPath = '/student') {
  await page.goto('/login');
  await waitForHooks(page);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(e2ePassword());
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(new RegExp(`${expectedPath}$`));
  await waitForHooks(page);
}

async function tokenFor(browser: Browser, email: string): Promise<string> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, email);
  const session = (await page.evaluate(() => window.__xyzE2E!.getSession())) as {
    data: { session: { access_token: string } | null };
  };
  await page.close();
  await context.close();
  const token = session.data.session?.access_token;
  if (!token) throw new Error(`No session token for ${email}`);
  return token;
}

async function apiContext(token: string): Promise<APIRequestContext> {
  return playwrightRequest.newContext({
    baseURL: API_BASE_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
}

async function openSection(page: Page, moduleId: string, sectionId: string) {
  // Navigating to the student section page fires GET /student/modules/{m}/sections/{s}, which the
  // content domain uses to record the studied_section engagement event (the REAL serving path).
  await page.goto(`/student/modules/${moduleId}/sections/${sectionId}`);
  await waitForHooks(page);
}

test('Stage 10 gamification gate — Scenario A: earn + extend, idempotent', async ({ browser }) => {
  const runId = requireRunId();
  const lecturer = await ensureAuthUser(runId, 'a-lect', 'lecturer');
  const student = await ensureAuthUser(runId, 'a-stu', 'student');
  const moduleId = insertModule(runId, `Stage 10 A ${runId}`, lecturer.appId);
  insertMembership(runId, lecturer.appId, moduleId, 'lecturer');
  insertMembership(runId, student.appId, moduleId, 'student');
  const sectionToday = insertSection(runId, moduleId, 'Today lecture', 0, 3);
  insertSection(runId, moduleId, 'Yesterday lecture', -1, 2);
  insertSection(runId, moduleId, 'Two days ago lecture', -2, 1);
  // 2-day streak (engaged on -2 and -1) + 10 DISTINCT completed quizzes split across those two days.
  for (let i = 0; i < 5; i += 1) insertCompletedQuiz(student.appId, moduleId, -2);
  for (let i = 0; i < 5; i += 1) insertCompletedQuiz(student.appId, moduleId, -1);

  // Real in-browser engaging action TODAY: open today's published summary → studied_section recorded.
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, student.email);
  await openSection(page, moduleId, sectionToday);

  // First on-read evaluation (API): today now engaged → streak 3, and streak_3 + quizzes_10 awarded NEW.
  const token = await tokenFor(browser, student.email);
  const api = await apiContext(token);
  const first = await api.get('/student/gamification');
  expect(first.status()).toBe(200);
  const firstBody = JSON.parse(await first.text());
  expect(firstBody.currentStreak).toBe(3);
  expect(firstBody.streakStatus).toBe('active');
  const firstEarned = new Set((firstBody.earnedBadges as Array<{ badgeKey: string }>).map((b) => b.badgeKey));
  expect(firstEarned.has('streak_3')).toBe(true);
  expect(firstEarned.has('quizzes_10')).toBe(true);
  expect(firstBody.newBadgeIds).toEqual(expect.arrayContaining(['streak_3', 'quizzes_10']));

  // Reload awards nothing new (idempotency).
  const second = await api.get('/student/gamification');
  const secondBody = JSON.parse(await second.text());
  expect(secondBody.newBadgeIds).toEqual([]);
  const secondEarned = new Set((secondBody.earnedBadges as Array<{ badgeKey: string }>).map((b) => b.badgeKey));
  expect(secondEarned.has('streak_3')).toBe(true);
  expect(secondEarned.has('quizzes_10')).toBe(true);
  await api.dispose();

  // The UI shows the streak + earned badges in My Progress.
  await page.goto('/student/progress');
  await expect(page.getByTestId('progress-dashboard')).toBeVisible();
  await page.getByTestId(`progress-module-card-${moduleId}`).click();
  await expect(page.getByTestId('gamification-placeholder')).toBeVisible();
  await expect(page.getByTestId('streak-current')).toContainText('3');
  await expect(page.getByTestId('badge-earned-streak_3')).toBeVisible();
  await expect(page.getByTestId('badge-earned-quizzes_10')).toBeVisible();
  await context.close();
});

test('Stage 10 gamification gate — Scenario B: reset after a missed scheduled day', async ({ browser }) => {
  const runId = requireRunId();
  const lecturer = await ensureAuthUser(runId, 'b-lect', 'lecturer');
  const student = await ensureAuthUser(runId, 'b-stu', 'student');
  const moduleId = insertModule(runId, `Stage 10 B ${runId}`, lecturer.appId);
  insertMembership(runId, lecturer.appId, moduleId, 'lecturer');
  insertMembership(runId, student.appId, moduleId, 'student');
  // Scheduled days -5..0; a 3-day streak through -3, then -2 and -1 MISSED, today scheduled.
  const sectionToday = insertSection(runId, moduleId, 'Today', 0, 6);
  insertSection(runId, moduleId, 'D-1', -1, 5);
  insertSection(runId, moduleId, 'D-2', -2, 4);
  insertSection(runId, moduleId, 'D-3', -3, 3);
  insertSection(runId, moduleId, 'D-4', -4, 2);
  insertSection(runId, moduleId, 'D-5', -5, 1);
  for (const off of [-5, -4, -3]) insertCompletedQuiz(student.appId, moduleId, off);

  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, student.email);
  await openSection(page, moduleId, sectionToday); // any qualifying activity today

  const token = await tokenFor(browser, student.email);
  const api = await apiContext(token);
  const body = JSON.parse(await (await api.get('/student/gamification')).text());
  expect(body.currentStreak).toBe(1); // reset by the gap — NOT 4
  expect(body.longestStreak).toBeGreaterThanOrEqual(3); // monotonic longest preserved
  expect(body.streakStatus).toBe('active');
  await api.dispose();

  await page.goto('/student/progress');
  await page.getByTestId(`progress-module-card-${moduleId}`).click();
  await expect(page.getByTestId('streak-current')).toContainText('1');
  await context.close();
});

test('Stage 10 gamification gate — Scenario C: studied_section recorded once per day', async ({ browser }) => {
  const runId = requireRunId();
  const lecturer = await ensureAuthUser(runId, 'c-lect', 'lecturer');
  const student = await ensureAuthUser(runId, 'c-stu', 'student');
  const moduleId = insertModule(runId, `Stage 10 C ${runId}`, lecturer.appId);
  insertMembership(runId, lecturer.appId, moduleId, 'lecturer');
  insertMembership(runId, student.appId, moduleId, 'student');
  const section = insertSection(runId, moduleId, 'Studied lecture', 0, 1);
  const other = insertSection(runId, moduleId, 'Other lecture', 0, 2);

  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, student.email);

  await openSection(page, moduleId, section);
  await expect.poll(() => studiedSectionCount(student.appId, section)).toBe(1);
  // Re-opening the SAME section the same local day creates NO second event (uuid5 dedup).
  await openSection(page, moduleId, section);
  await expect.poll(() => studiedSectionCount(student.appId, section)).toBe(1);
  // A different section adds its own single event.
  await openSection(page, moduleId, other);
  await expect.poll(() => studiedSectionCount(student.appId, other)).toBe(1);

  // The engagement keeps the streak alive on this scheduled day.
  const token = await tokenFor(browser, student.email);
  const api = await apiContext(token);
  const body = JSON.parse(await (await api.get('/student/gamification')).text());
  expect(body.todaySatisfied).toBe(true);
  expect(body.streakStatus).toBe('active');
  await api.dispose();
  await context.close();
});

test('Stage 10 gamification gate — Scenario D: topic_mastered respects section visibility', async ({ browser }) => {
  // Security negative case (the leak the all-published fixtures never exercised): a topic mastered on an
  // UNPUBLISHED section must NOT grant topic_mastered — otherwise the badge leaks that hidden content
  // exists. Then publishing it (a visible mastered topic) earns the badge — guards against over-correction.
  const runId = requireRunId();
  const lecturer = await ensureAuthUser(runId, 'd-lect', 'lecturer');
  const student = await ensureAuthUser(runId, 'd-stu', 'student');
  const moduleId = insertModule(runId, `Stage 10 D ${runId}`, lecturer.appId);
  insertMembership(runId, lecturer.appId, moduleId, 'lecturer');
  insertMembership(runId, student.appId, moduleId, 'student');
  const hiddenSection = insertSection(runId, moduleId, 'Hidden lecture', 0, 1, 'unpublished');
  insertMasterySnapshot(student.appId, moduleId, hiddenSection);

  const token = await tokenFor(browser, student.email);
  const api = await apiContext(token);
  const before = JSON.parse(await (await api.get('/student/gamification')).text());
  const earnedBefore = new Set((before.earnedBadges as Array<{ badgeKey: string }>).map((b) => b.badgeKey));
  expect(earnedBefore.has('topic_mastered')).toBe(false); // mastery on an unpublished section must not leak

  // Now master a topic on a PUBLISHED (visible) section → the badge legitimately unlocks.
  const visibleSection = insertSection(runId, moduleId, 'Visible lecture', 0, 2, 'published');
  insertMasterySnapshot(student.appId, moduleId, visibleSection);
  const after = JSON.parse(await (await api.get('/student/gamification')).text());
  const earnedAfter = new Set((after.earnedBadges as Array<{ badgeKey: string }>).map((b) => b.badgeKey));
  expect(earnedAfter.has('topic_mastered')).toBe(true);
  await api.dispose();
});
