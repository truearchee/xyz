import { expect, request as playwrightRequest, test, type APIRequestContext, type Browser, type Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

import { runPsqlJson, runPsqlRows, sqlLiteral } from './fixtures/db.mjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const E2E_ACTOR_DOMAIN = 'xyz-lms-e2e.dev';
const RUNS_DIR = resolve('tests/e2e/.runs');

type SeededStudent = { key: string; email: string; appId: string };
type SeededProgress = {
  moduleOneId: string;
  moduleTwoId: string;
  foreignModuleId: string;
  students: Record<string, SeededStudent>;
};
type BenchmarkPrivacy = {
  callerAverage: string;
  forbiddenAverages: string[];
};

const MODULE_ONE_BENCHMARK_SCORES: Record<string, string> = {
  a: '12.34',
  b: '23.45',
  c: '34.56',
  d: '45.67',
  e: '56.78',
  f: '67.89',
};
const MODULE_TWO_BENCHMARK_SCORES: Record<string, string> = {
  a: '11.12',
  b: '22.23',
  c: '33.34',
  d: '44.45',
  e: '55.56',
  f: '66.67',
};

test.setTimeout(180_000);

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the Stage 9 gate');
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) throw new Error(`Invalid E2E run id: ${runId}`);
  const manifestPath = manifestPathForRunId(runId);
  if (!existsSync(manifestPath)) {
    mkdirSync(RUNS_DIR, { recursive: true });
    writeFileSync(
      manifestPath,
      `${JSON.stringify(
        {
          runId,
          authUserIds: [],
          appUserIds: [],
          moduleIds: [],
          sectionIds: [],
          membershipIds: [],
          assetIds: [],
          transcriptIds: [],
          transcriptSegmentIds: [],
          transcriptChunkIds: [],
          ingestionJobIds: [],
          aiRequestLogIds: [],
          storageKeys: [],
          createdAt: new Date().toISOString(),
        },
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
  if (!existsSync(path)) throw new Error('.env.e2e is required for the Stage 9 browser gate');
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
    if (!env[key]) throw new Error(`${key} is required for the Stage 9 browser gate`);
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

async function ensureAuthStudent(runId: string, key: string): Promise<SeededStudent> {
  const env = loadE2EEnv();
  const email = `stage9-${key}-${runId}@${E2E_ACTOR_DOMAIN}`;
  const usersBody = await supabaseAdminFetch(env, '/auth/v1/admin/users?per_page=1000&page=1');
  const existing = Array.isArray(usersBody?.users)
    ? usersBody.users.find((candidate: { email?: string }) => candidate.email === email)
    : null;
  const payload = {
    email,
    password: env.E2E_TEST_PASSWORD,
    email_confirm: true,
    user_metadata: { full_name: `Stage 9 Student ${key.toUpperCase()}`, e2e_fixture: '9' },
  };
  const authBody = existing?.id
    ? await supabaseAdminFetch(env, `/auth/v1/admin/users/${existing.id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
    : await supabaseAdminFetch(env, '/auth/v1/admin/users', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
  const authUser = authBody?.user ?? authBody;
  recordValue(runId, 'authUserIds', authUser.id);
  const appId = randomUUID();
  const persistedAppId = runPsqlJson(`
WITH upserted AS (
  INSERT INTO app_users (id, auth_provider_id, email, full_name, role, is_active, timezone)
  VALUES (${sqlLiteral(appId)}::uuid, ${sqlLiteral(authUser.id)}, ${sqlLiteral(email)}, ${sqlLiteral(`Stage 9 Student ${key.toUpperCase()}`)}, 'student', true, 'UTC')
  ON CONFLICT (auth_provider_id) DO UPDATE
  SET email = EXCLUDED.email,
      full_name = EXCLUDED.full_name,
      role = 'student',
      is_active = true,
      timezone = 'UTC'
  RETURNING id
)
SELECT to_json(id)::text FROM upserted;
`) as unknown as string;
  recordValue(runId, 'appUserIds', persistedAppId);
  return { key, email, appId: persistedAppId };
}

function insertMembership(runId: string, userId: string, moduleId: string, role: 'student' | 'lecturer') {
  const id = randomUUID();
  runPsqlRows(`
INSERT INTO course_memberships (id, user_id, module_id, role, status)
VALUES (${sqlLiteral(id)}::uuid, ${sqlLiteral(userId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(role)}, 'active');
`);
  recordValue(runId, 'membershipIds', id);
}

function insertModule(runId: string, title: string, ownerId: string): string {
  const id = randomUUID();
  runPsqlRows(`
INSERT INTO course_modules (id, title, description, owner_id, timezone, starts_on, ends_on, is_active)
VALUES (${sqlLiteral(id)}::uuid, ${sqlLiteral(title)}, 'Stage 9 progress E2E module', ${sqlLiteral(ownerId)}::uuid, 'UTC', DATE '2026-01-12', DATE '2026-05-01', true);
`);
  recordValue(runId, 'moduleIds', id);
  return id;
}

function insertSection(runId: string, moduleId: string, title: string, type: 'lecture' | 'lab', orderIndex: number): string {
  const id = randomUUID();
  runPsqlRows(`
INSERT INTO module_sections (id, course_module_id, title, type, order_index, week_number, session_date, publish_status, status)
VALUES (${sqlLiteral(id)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(title)}, ${sqlLiteral(type)}, ${orderIndex}, 1, DATE '2026-01-12', 'published', 'active');
`);
  recordValue(runId, 'sectionIds', id);
  return id;
}

function insertScheme(moduleId: string, sectionIds: string[]): string[] {
  const schemeId = randomUUID();
  runPsqlRows(`
INSERT INTO course_grade_schemes (id, module_id, name, on_track_max, at_risk_max, benchmark_min_cohort)
VALUES (${sqlLiteral(schemeId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Stage 9 E2E scheme', 70, 85, 5);
INSERT INTO grade_boundaries (id, scheme_id, letter_grade, lower_bound, sort_order) VALUES
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A', 93, 1),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A-', 87, 2),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B+', 84, 3),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B', 80, 4),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'C', 70, 5),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'F', 0, 6);
`);
  const componentIds = [randomUUID(), randomUUID(), randomUUID(), randomUUID(), randomUUID()];
  runPsqlRows(`
INSERT INTO grade_components (id, scheme_id, name, weight, sort_order, component_kind, module_section_id) VALUES
  (${sqlLiteral(componentIds[0])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Quiz average', 0.20, 1, 'quiz', ${sqlLiteral(sectionIds[0])}::uuid),
  (${sqlLiteral(componentIds[1])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Lab portfolio', 0.20, 2, 'lab', ${sqlLiteral(sectionIds[1])}::uuid),
  (${sqlLiteral(componentIds[2])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Project', 0.25, 3, 'assignment', NULL),
  (${sqlLiteral(componentIds[3])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Midterm', 0.25, 4, 'exam', NULL),
  (${sqlLiteral(componentIds[4])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Final exam', 0.10, 5, 'exam', NULL);
`);
  return componentIds;
}

function grade(studentId: string, componentIds: string[], score: string, count: number) {
  const values = componentIds
    .slice(0, count)
    .map(
      (componentId) =>
        `(gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(componentId)}::uuid, ${score}, 'e2e')`,
    )
    .join(', ');
  runPsqlRows(`
INSERT INTO student_grade_records (id, student_id, grade_component_id, percentage_score, source)
VALUES ${values};
`);
}

function target(studentId: string, moduleId: string, letter: string) {
  runPsqlRows(`
INSERT INTO student_target_grade_goals (id, student_id, module_id, target_letter_grade, status)
VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(letter)}, 'active');
`);
}

function snapshots(studentId: string, moduleId: string, sectionIds: string[], latest: number) {
  runPsqlRows(`
INSERT INTO student_progress_snapshots (id, student_id, module_id, week_number, snapshot_date, standing_points, source_metrics)
VALUES
  (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 1, DATE '2026-01-12', ${latest - 8}, '{"seed":"stage9-e2e"}'::jsonb),
  (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 2, DATE '2026-01-19', ${latest - 4}, '{"seed":"stage9-e2e"}'::jsonb),
  (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 3, DATE '2026-01-26', ${latest}, '{"seed":"stage9-e2e"}'::jsonb);
INSERT INTO student_topic_mastery_snapshots (id, student_id, module_id, module_section_id, mastery_percentage, status_label, source_metrics)
VALUES
  (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(sectionIds[0])}::uuid, ${latest - 5}, 'on_track', '{"seed":"stage9-e2e"}'::jsonb),
  (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(sectionIds[1])}::uuid, ${latest - 12}, 'needs_attention', '{"seed":"stage9-e2e"}'::jsonb);
`);
}

function benchmark(moduleId: string, sectionId: string, students: SeededStudent[], scores: number[]) {
  const definitionId = randomUUID();
  runPsqlRows(`
INSERT INTO quiz_definitions (id, module_section_id, module_id, quiz_mode, source_scope)
VALUES (${sqlLiteral(definitionId)}::uuid, ${sqlLiteral(sectionId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'post_class', '{"sectionIds":[]}'::jsonb);
`);
  for (const [index, student] of students.entries()) {
    const score = scores[index % scores.length];
    const correct = Math.floor(score / 10);
    runPsqlRows(`
INSERT INTO quiz_attempts (
  id, quiz_definition_id, student_id, attempt_number, status, total_questions,
  new_question_count, mistake_review_question_count, correct_count, incorrect_count,
  score_percentage, started_at, completed_at
)
VALUES (
  gen_random_uuid(), ${sqlLiteral(definitionId)}::uuid, ${sqlLiteral(student.appId)}::uuid, 1,
  'completed', 10, 10, 0, ${correct}, ${10 - correct}, ${score}, now(), now()
);
`);
  }
}

function assertPrivacyPayload(raw: string, seeded: SeededProgress, benchmarkPrivacy?: BenchmarkPrivacy) {
  for (const student of Object.values(seeded.students)) {
    expect(raw).not.toContain(student.email);
    expect(raw).not.toContain(student.appId);
  }
  expect(raw).not.toContain('Stage 9 Student');
  expect(raw).not.toContain('studentId');
  expect(raw).not.toContain('student_id');
  expect(raw).not.toContain('gradeRecords');
  expect(raw).not.toContain('grade_records');
  expect(raw).not.toContain('componentScores');
  expect(raw).not.toContain('component_scores');
  expect(raw).not.toContain('percentageScore');
  expect(raw).not.toContain('percentage_score');
  expect(raw).not.toContain('perStudent');
  expect(raw).not.toContain('individualStanding');
  if (!benchmarkPrivacy) return;

  const body = JSON.parse(raw) as { benchmark?: { studentAverage?: string | null; suppressed?: boolean } };
  expect(body.benchmark).toBeTruthy();
  expect(body.benchmark?.suppressed).toBe(false);
  expect(Number(body.benchmark?.studentAverage)).toBeCloseTo(Number(benchmarkPrivacy.callerAverage), 2);
  for (const average of benchmarkPrivacy.forbiddenAverages) {
    expect(Number(body.benchmark?.studentAverage)).not.toBeCloseTo(Number(average), 2);
    expect(raw).not.toContain(average);
  }
}

async function captureForecastPanel(page: Page, state: string) {
  const screenshotDir = process.env.STAGE9_SCREENSHOT_DIR;
  if (!screenshotDir) return;
  mkdirSync(screenshotDir, { recursive: true });
  await page.getByTestId('forecast-panel').screenshot({
    path: resolve(screenshotDir, `forecast-${state}.png`),
  });
}

async function seedProgress(runId: string): Promise<SeededProgress> {
  const lecturer = await ensureAuthStudent(runId, 'lecturer');
  runPsqlRows(`UPDATE app_users SET role = 'lecturer' WHERE id = ${sqlLiteral(lecturer.appId)}::uuid;`);
  const students = Object.fromEntries(
    await Promise.all(['a', 'b', 'c', 'd', 'e', 'f'].map(async (key) => [key, await ensureAuthStudent(runId, key)])),
  ) as Record<string, SeededStudent>;
  const studentList = Object.values(students);

  const moduleOneId = insertModule(runId, `Stage 9 Progress Module 1 ${runId}`, lecturer.appId);
  const moduleTwoId = insertModule(runId, `Stage 9 Progress Module 2 ${runId}`, lecturer.appId);
  const foreignModuleId = insertModule(runId, `Stage 9 Other Student Module ${runId}`, lecturer.appId);
  insertMembership(runId, lecturer.appId, moduleOneId, 'lecturer');
  insertMembership(runId, lecturer.appId, moduleTwoId, 'lecturer');
  insertMembership(runId, lecturer.appId, foreignModuleId, 'lecturer');
  insertMembership(runId, students.a.appId, foreignModuleId, 'student');
  for (const student of studentList) {
    insertMembership(runId, student.appId, moduleOneId, 'student');
    insertMembership(runId, student.appId, moduleTwoId, 'student');
  }

  const moduleOneSections = [
    insertSection(runId, moduleOneId, 'Financial Modelling', 'lecture', 1),
    insertSection(runId, moduleOneId, 'Applied Lab', 'lab', 2),
  ];
  const moduleTwoSections = [
    insertSection(runId, moduleTwoId, 'Forecasting Lecture', 'lecture', 1),
    insertSection(runId, moduleTwoId, 'Forecasting Lab', 'lab', 2),
  ];
  const moduleOneComponents = insertScheme(moduleOneId, moduleOneSections);
  const moduleTwoComponents = insertScheme(moduleTwoId, moduleTwoSections);

  // Module 1 states: A on_track, B at_risk, E achieved, F final_no_remaining.
  grade(students.a.appId, moduleOneComponents, '89.44', 4);
  grade(students.b.appId, moduleOneComponents, '94.44', 4);
  grade(students.e.appId, moduleOneComponents, '91.11', 4);
  grade(students.f.appId, moduleOneComponents, '85.00', 5);
  target(students.a.appId, moduleOneId, 'A-');
  target(students.b.appId, moduleOneId, 'A');
  target(students.e.appId, moduleOneId, 'B');
  target(students.f.appId, moduleOneId, 'A');

  // Module 2 states: C requires_high_score, D impossible with B+ best reachable.
  grade(students.c.appId, moduleTwoComponents, '92.50', 4);
  grade(students.d.appId, moduleTwoComponents, '82.50', 4);
  target(students.c.appId, moduleTwoId, 'A');
  target(students.d.appId, moduleTwoId, 'A');

  for (const [index, student] of studentList.entries()) {
    snapshots(student.appId, moduleOneId, moduleOneSections, 78 + index);
    snapshots(student.appId, moduleTwoId, moduleTwoSections, 72 + index);
  }
  benchmark(moduleOneId, moduleOneSections[0], studentList, Object.values(MODULE_ONE_BENCHMARK_SCORES).map(Number));
  benchmark(moduleTwoId, moduleTwoSections[0], studentList, Object.values(MODULE_TWO_BENCHMARK_SCORES).map(Number));
  return { moduleOneId, moduleTwoId, foreignModuleId, students };
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

async function tokenFor(browser: Browser, email: string, expectedPath = '/student'): Promise<string> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, email, expectedPath);
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

// The My Progress dashboard is a pure read: it must issue NO LLM request of its own (no AI log). We prove
// that by an id-set diff rather than a global count, deliberately EXCLUDING async transcript-ingestion
// worker logs (ingestion_job_id NOT NULL — e.g. summary_brief/summary_detailed) that other specs' jobs
// can drain into this window. Those are background work, not the progress read, and a global count made
// the assertion flake on test ordering. A regression where the progress path itself called the LLM would
// log a row with ingestion_job_id IS NULL (it is not an ingestion job) and is still caught here.
function aiLogIds(): string[] {
  return runPsqlRows(`SELECT id::text FROM ai_request_logs`);
}

function newSynchronousAiLogCount(beforeIds: string[]): number {
  const exclusion = beforeIds.length
    ? `AND id NOT IN (${beforeIds.map((id) => sqlLiteral(id)).join(', ')})`
    : '';
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text
FROM ai_request_logs
WHERE ingestion_job_id IS NULL
${exclusion}
`) as unknown as number;
}

test('Stage 9 My Progress dashboard gate', async ({ browser }) => {
  const runId = requireRunId();
  const seeded = await seedProgress(runId);
  const context = await browser.newContext();
  const beforeAiIds = aiLogIds();

  const states: Array<[string, string, string, string, string]> = [
    ['a', seeded.moduleOneId, 'on_track', 'On track', 'OK'],
    ['b', seeded.moduleOneId, 'at_risk', 'At risk', '!'],
    ['c', seeded.moduleTwoId, 'requires_high_score', 'Requires high score', '!'],
    ['d', seeded.moduleTwoId, 'impossible', 'Impossible', 'X'],
    ['e', seeded.moduleOneId, 'achieved', 'Achieved', 'OK'],
    ['f', seeded.moduleOneId, 'final_no_remaining', 'Final grade', '='],
  ];
  const benchmarkScoresByModule: Record<string, Record<string, string>> = {
    [seeded.moduleOneId]: MODULE_ONE_BENCHMARK_SCORES,
    [seeded.moduleTwoId]: MODULE_TWO_BENCHMARK_SCORES,
  };
  for (const [key, moduleId, expectedState] of states) {
    const token = await tokenFor(browser, seeded.students[key].email);
    const api = await apiContext(token);
    const dashboardResponse = await api.get('/student/progress');
    expect(dashboardResponse.status()).toBe(200);
    assertPrivacyPayload(await dashboardResponse.text(), seeded);
    const response = await api.get(`/student/modules/${moduleId}/progress`);
    expect(response.status()).toBe(200);
    const raw = await response.text();
    const moduleBenchmarkScores = benchmarkScoresByModule[moduleId];
    assertPrivacyPayload(raw, seeded, {
      callerAverage: moduleBenchmarkScores[key],
      forbiddenAverages: Object.entries(moduleBenchmarkScores)
        .filter(([otherKey]) => otherKey !== key)
        .map(([, average]) => average),
    });
    const body = JSON.parse(raw);
    expect(body.forecast.state).toBe(expectedState);
    if (expectedState === 'final_no_remaining') {
      expect(body.forecast.requiredRemainingAverage).toBeNull();
    }
    await api.dispose();
  }

  const studentDToken = await tokenFor(browser, seeded.students.d.email);
  const studentDApi = await apiContext(studentDToken);
  const foreignResponse = await studentDApi.get(`/student/modules/${seeded.foreignModuleId}/progress`);
  expect(foreignResponse.status()).toBe(404);
  await studentDApi.dispose();

  const lecturerToken = await tokenFor(browser, `stage9-lecturer-${runId}@${E2E_ACTOR_DOMAIN}`, '/lecturer');
  const lecturerApi = await apiContext(lecturerToken);
  expect((await lecturerApi.get('/student/progress')).status()).toBe(403);
  expect((await lecturerApi.get(`/student/modules/${seeded.moduleOneId}/progress`)).status()).toBe(403);
  await lecturerApi.dispose();

  for (const [key, moduleId, state, label, icon] of states) {
    const stateContext = await browser.newContext();
    const statePage = await stateContext.newPage();
    await signIn(statePage, seeded.students[key].email);
    await statePage.goto('/student/progress');
    await expect(statePage.getByTestId('progress-dashboard')).toBeVisible();
    await statePage.getByTestId(`progress-module-card-${moduleId}`).click();
    await expect(statePage.getByTestId('forecast-state')).toContainText(label);
    await expect(statePage.getByTestId('forecast-state-icon')).toHaveText(icon);
    await captureForecastPanel(statePage, state);
    if (state === 'final_no_remaining') {
      await expect(statePage.getByTestId('forecast-panel')).toContainText('Final grade:');
      await expect(statePage.getByTestId('forecast-panel')).toContainText('no remaining work');
      await expect(statePage.getByTestId('forecast-panel')).not.toContainText('Need ');
    }
    await stateContext.close();
  }

  const page = await context.newPage();
  await signIn(page, seeded.students.d.email);
  await page.goto('/student/progress');
  await expect(page.getByTestId('progress-dashboard')).toBeVisible();
  await page.getByTestId(`progress-module-card-${seeded.moduleTwoId}`).click();
  await expect(page.getByTestId('forecast-state')).toContainText('Impossible');
  await expect(page.getByTestId('impossible-headline')).toHaveText('Best grade still reachable: B+');
  await expect(page.getByTestId('benchmark-card')).toContainText('Cohort 6');
  await expect(page.getByTestId('trend-text-fallback')).toContainText('Week 1');
  await expect(page.getByTestId('trend-text-fallback')).toContainText('Week 3');
  await expect(page.getByTestId('mastery-row').first()).toBeVisible();
  await expect(page.getByTestId('mastery-row').first()).toContainText('Forecasting Lecture');
  await expect(page.getByTestId('mastery-row').nth(1)).toContainText('Forecasting Lab');
  await expect(page.getByTestId('gamification-placeholder')).toBeVisible();
  await page.getByText('How this is calculated').click();
  await expect(page.getByTestId('forecast-panel')).toContainText('To reach A');
  await expect(page.getByTestId('forecast-panel')).toContainText('on remaining work');

  await expect(page.getByRole('button', { name: /save/i })).toHaveCount(0);
  await page.getByTestId('target-grade-select').selectOption('B+');
  await expect(page.getByTestId('target-save-status')).toHaveText('Saved');
  await expect(page.getByTestId('forecast-state')).toContainText('Requires high score');
  await expect(page.getByTestId('forecast-state-icon')).toHaveText('!');

  const token = await tokenFor(browser, seeded.students.d.email);
  const api = await apiContext(token);
  const progressResponse = await api.get(`/student/modules/${seeded.moduleTwoId}/progress`);
  const raw = await progressResponse.text();
  expect(progressResponse.status()).toBe(200);
  assertPrivacyPayload(raw, seeded);
  await api.dispose();

  expect(newSynchronousAiLogCount(beforeAiIds)).toBe(0);
  await context.close();
});
