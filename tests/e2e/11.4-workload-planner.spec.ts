import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

import { runPsqlJson, runPsqlRows, sqlLiteral } from './fixtures/db.mjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const STUDENT_TWO_EMAIL = 'student2_e2e@example.test';
const RUNS_DIR = resolve('tests/e2e/.runs');

type ApiResponse<T = unknown> = { body: T; status: number; text: string };
type WorkloadPlanItem = {
  taskKey: string;
  scheduledDate: string | null;
  scheduledEndAt: string | null;
  label: string;
  estimateMinutes: number;
  reason: string;
  tight: boolean;
  tightMessage: string | null;
  sortIndex: number;
};
type WorkloadPlan = {
  id: string;
  inputHash: string;
  items: WorkloadPlanItem[];
};
type SeededWorkloadGate = {
  moduleId: string;
  studentId: string;
  studentTwoId: string;
  sameDaySectionId: string;
  closeASectionId: string;
  closeBSectionId: string;
  laterSectionId: string;
  dueByTaskKey: Record<string, string>;
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
  await expect(page).toHaveURL(new RegExp(`${expectedPath}$`), { timeout: 30_000 });
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
  method: 'GET' | 'POST' | 'PUT',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response =
    method === 'GET'
      ? await context.get(path)
      : method === 'POST'
        ? await context.post(path, { data: body })
        : await context.put(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status(), text };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 11.4 gate');
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

type RunManifest = { [key: string]: string[] | string; runId: string };
function manifestPathForRunId(runId: string): string {
  return resolve(RUNS_DIR, `${runId}.json`);
}

function recordManifestValue(runId: string, field: string, value: string) {
  const manifest = JSON.parse(readFileSync(manifestPathForRunId(runId), 'utf8')) as RunManifest;
  const current = Array.isArray(manifest[field]) ? manifest[field] : [];
  manifest[field] = [...new Set([...current, value])];
  writeFileSync(manifestPathForRunId(runId), `${JSON.stringify(manifest, null, 2)}\n`);
}

function getAppUserId(email: string): string {
  const userId = runPsqlJson(`
SELECT to_json(id)::text
FROM app_users
WHERE email = ${sqlLiteral(email)}
LIMIT 1;
`) as unknown as string | null;
  if (!userId) throw new Error(`Missing E2E app user ${email}; run tests/e2e/fixtures/seed.mjs first`);
  return userId;
}

function cleanupPriorRunRows(runId: string) {
  runPsqlRows(`
DELETE FROM workload_plan_items
WHERE workload_plan_id IN (
  SELECT id FROM workload_plans
  WHERE module_id IN (
    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)}
  )
);

DELETE FROM workload_plans
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)}
);

DELETE FROM student_availability
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)}
);

DELETE FROM student_risk_snapshots
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)}
);

DELETE FROM agent_runs
WHERE scope_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)}
);

DELETE FROM module_sections
WHERE course_module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)}
);

DELETE FROM course_memberships
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)}
);

DELETE FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Workload Gate ${runId}%`)};
`);
}

function dateAtUtc(daysFromToday: number, hour: number, minute = 0): Date {
  const now = new Date();
  const value = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hour, minute, 0, 0));
  value.setUTCDate(value.getUTCDate() + daysFromToday);
  return value;
}

function sameDayDue(): Date {
  const now = new Date();
  const due = dateAtUtc(0, 23, 45);
  if (due > now) return due;
  return new Date(now.getTime() + 60 * 60 * 1000);
}

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function seedWorkloadGate(runId: string): SeededWorkloadGate {
  cleanupPriorRunRows(runId);

  const lecturerId = getAppUserId(LECTURER_EMAIL);
  const studentId = getAppUserId(STUDENT_EMAIL);
  const studentTwoId = getAppUserId(STUDENT_TWO_EMAIL);
  const moduleId = randomUUID();
  const sameDaySectionId = randomUUID();
  const [closeASectionId, closeBSectionId] = [randomUUID(), randomUUID()].sort();
  const laterSectionId = randomUUID();
  const membershipIds = [randomUUID(), randomUUID(), randomUUID()];
  const agentRunId = randomUUID();
  const sameDue = sameDayDue();
  const closeDue = dateAtUtc(1, 21);
  const laterDue = dateAtUtc(2, 21);
  const courseEnd = dateAtUtc(30, 23);
  const riskReason = JSON.stringify([
    {
      code: 'topic_deadline_gap',
      severity: 'needs_support',
      metricKeys: ['topicGapDueInHours', 'topicTitle'],
      lecturerText: 'Portfolio Review needs attention before an upcoming deadline',
      studentText: 'Portfolio Review could use a little extra time before the deadline.',
      supportingMetrics: { topicGapDueInHours: 36, topicTitle: 'Portfolio Review' },
    },
  ]);

  runPsqlRows(`
INSERT INTO course_modules (id, title, description, owner_id, timezone, starts_on, ends_on, is_active)
VALUES (
  ${sqlLiteral(moduleId)}::uuid,
  ${sqlLiteral(`Stage 11 Workload Gate ${runId}`)},
  'Stage 11 workload planner browser gate',
  ${sqlLiteral(lecturerId)}::uuid,
  'UTC',
  CURRENT_DATE,
  DATE ${sqlLiteral(isoDate(courseEnd))},
  true
);

INSERT INTO course_memberships (id, user_id, module_id, role, status) VALUES
  (${sqlLiteral(membershipIds[0])}::uuid, ${sqlLiteral(lecturerId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'lecturer', 'active'),
  (${sqlLiteral(membershipIds[1])}::uuid, ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active'),
  (${sqlLiteral(membershipIds[2])}::uuid, ${sqlLiteral(studentTwoId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active');

INSERT INTO module_sections (id, course_module_id, title, type, order_index, week_number, session_date, due_at, publish_status, status)
VALUES
  (${sqlLiteral(sameDaySectionId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Same-day check', 'assignment', 1, 1, CURRENT_DATE, ${sqlLiteral(sameDue.toISOString())}::timestamptz, 'published', 'active'),
  (${sqlLiteral(closeASectionId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Close A', 'assignment', 2, 1, CURRENT_DATE + INTERVAL '1 day', ${sqlLiteral(closeDue.toISOString())}::timestamptz, 'published', 'active'),
  (${sqlLiteral(closeBSectionId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Close B', 'assignment', 3, 1, CURRENT_DATE + INTERVAL '1 day', ${sqlLiteral(closeDue.toISOString())}::timestamptz, 'published', 'active'),
  (${sqlLiteral(laterSectionId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Later review', 'assignment', 4, 1, CURRENT_DATE + INTERVAL '2 days', ${sqlLiteral(laterDue.toISOString())}::timestamptz, 'published', 'active');

INSERT INTO agent_runs (
  id, trigger_type, scope_type, scope_id, scheduled_for, algorithm_version, status, completed_at,
  snapshot_count, recommendation_count, plan_count, idempotency_key
)
VALUES (
  ${sqlLiteral(agentRunId)}::uuid,
  'manual_admin',
  'module',
  ${sqlLiteral(moduleId)}::uuid,
  now(),
  'risk-v1',
  'completed',
  now(),
  2,
  0,
  0,
  ${sqlLiteral(`workload-${runId}`)}
);

INSERT INTO student_risk_snapshots (
  id, agent_run_id, student_id, module_id, risk_tier, risk_reasons, algorithm_version, input_hash, source_cutoff_at, computed_at
)
VALUES
  (gen_random_uuid(), ${sqlLiteral(agentRunId)}::uuid, ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'needs_support', ${sqlLiteral(riskReason)}::jsonb, 'risk-v1', 'risk-student-one', now(), now()),
  (gen_random_uuid(), ${sqlLiteral(agentRunId)}::uuid, ${sqlLiteral(studentTwoId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'needs_support', ${sqlLiteral(riskReason)}::jsonb, 'risk-v1', 'risk-student-two', now(), now());
`);

  recordManifestValue(runId, 'moduleIds', moduleId);
  for (const sectionId of [sameDaySectionId, closeASectionId, closeBSectionId, laterSectionId]) {
    recordManifestValue(runId, 'sectionIds', sectionId);
  }
  for (const membershipId of membershipIds) recordManifestValue(runId, 'membershipIds', membershipId);

  return {
    moduleId,
    studentId,
    studentTwoId,
    sameDaySectionId,
    closeASectionId,
    closeBSectionId,
    laterSectionId,
    dueByTaskKey: {
      [`deadline:${sameDaySectionId}`]: sameDue.toISOString(),
      [`deadline:${closeASectionId}`]: closeDue.toISOString(),
      [`deadline:${closeBSectionId}`]: closeDue.toISOString(),
      [`deadline:${laterSectionId}`]: laterDue.toISOString(),
    },
  };
}

function sumByTask(items: WorkloadPlanItem[], taskKey: string): number {
  return items.filter((item) => item.taskKey === taskKey).reduce((total, item) => total + item.estimateMinutes, 0);
}

function scheduledTotalsByDate(items: WorkloadPlanItem[]): Map<string, number> {
  const totals = new Map<string, number>();
  for (const item of items) {
    if (!item.scheduledDate) continue;
    totals.set(item.scheduledDate, (totals.get(item.scheduledDate) ?? 0) + item.estimateMinutes);
  }
  return totals;
}

function firstIndex(items: WorkloadPlanItem[], label: string): number {
  const index = items.findIndex((item) => item.label === label);
  if (index < 0) throw new Error(`Missing plan item label: ${label}`);
  return index;
}

test('Stage 11.4 workload planner gate', async ({ browser }) => {
  const runId = requireRunId();
  const seeded = seedWorkloadGate(runId);

  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();
  const studentTwoContext = await browser.newContext();
  let studentApi: APIRequestContext | null = null;
  let studentTwoApi: APIRequestContext | null = null;
  let adminApi: APIRequestContext | null = null;
  let lecturerApi: APIRequestContext | null = null;

  try {
    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    studentApi = await createApiContext(await getAccessToken(studentPage));

    await studentPage.goto(`/student/modules/${seeded.moduleId}`);
    const planner = studentPage.getByTestId('student-workload-planner');
    await expect(planner).toBeVisible();
    for (const day of ['tuesday', 'thursday', 'saturday', 'sunday']) {
      const checkbox = planner.getByTestId(`workload-day-${day}`);
      if (!(await checkbox.isChecked())) await checkbox.check();
    }
    await planner.getByTestId('workload-window').selectOption('no_preference');
    await planner.getByTestId('workload-max-minutes').fill('100');
    await planner.getByTestId('workload-generate').click();
    await expect(planner.getByTestId('workload-status')).toHaveText('Plan updated');
    await expect(planner.getByTestId('workload-plan-list')).toBeVisible();
    await expect(planner).toContainText('Prepare for Same-day check');
    await expect(planner).toContainText('Prepare for Close A');
    await expect(planner).toContainText('Prepare for Close B');
    await expect(planner).toContainText('Portfolio Review');
    await expect(planner.getByRole('button', { name: /edit|done|accept|reject/i })).toHaveCount(0);
    await expect(planner.locator('[draggable="true"]')).toHaveCount(0);

    const planResponse = await apiJson<WorkloadPlan>(
      studentApi,
      'GET',
      `/student/modules/${seeded.moduleId}/workload/plan`,
    );
    expect(planResponse.status).toBe(200);
    const plan = planResponse.body;
    expect(planResponse.text).not.toContain(seeded.studentTwoId);
    expect(planResponse.text).not.toContain(STUDENT_TWO_EMAIL);

    expect(firstIndex(plan.items, 'Prepare for Same-day check')).toBeLessThan(
      firstIndex(plan.items, 'Prepare for Close A'),
    );
    expect(firstIndex(plan.items, 'Prepare for Close A')).toBeLessThan(
      firstIndex(plan.items, 'Prepare for Close B'),
    );
    expect(firstIndex(plan.items, 'Prepare for Close B')).toBeLessThan(
      firstIndex(plan.items, 'Prepare for Later review'),
    );
    expect(firstIndex(plan.items, 'Prepare for Later review')).toBeLessThan(
      firstIndex(plan.items, 'Reinforce Portfolio Review'),
    );

    for (const [taskKey, dueAt] of Object.entries(seeded.dueByTaskKey)) {
      const taskItems = plan.items.filter((item) => item.taskKey === taskKey);
      expect(taskItems.length).toBeGreaterThan(0);
      expect(sumByTask(plan.items, taskKey)).toBe(90);
      for (const item of taskItems) {
        if (item.scheduledEndAt) expect(Date.parse(item.scheduledEndAt)).toBeLessThanOrEqual(Date.parse(dueAt));
      }
    }

    const totals = scheduledTotalsByDate(plan.items);
    expect(Math.max(...totals.values())).toBeLessThanOrEqual(125);
    expect([...totals.values()].some((total) => total - 100 === 25)).toBe(true);
    const tightItems = plan.items.filter((item) => item.tight);
    expect(tightItems.length).toBeGreaterThan(0);
    expect(tightItems.every((item) => item.tightMessage?.includes('Plan may not fully fit'))).toBe(true);

    const studentTwoPage = await signInPage(studentTwoContext, STUDENT_TWO_EMAIL, '/student');
    studentTwoApi = await createApiContext(await getAccessToken(studentTwoPage));
    const studentTwoMissing = await apiJson(
      studentTwoApi,
      'GET',
      `/student/modules/${seeded.moduleId}/workload/plan`,
    );
    expect(studentTwoMissing.status).toBe(404);
    const studentTwoGenerated = await apiJson<WorkloadPlan>(
      studentTwoApi,
      'POST',
      `/student/modules/${seeded.moduleId}/workload/plan:generate`,
    );
    expect(studentTwoGenerated.status).toBe(200);
    expect(studentTwoGenerated.body.id).not.toBe(plan.id);
    expect(studentTwoGenerated.text).not.toContain(seeded.studentId);
    expect(studentTwoGenerated.text).not.toContain(STUDENT_EMAIL);

    const adminPage = await signInPage(adminContext, ADMIN_EMAIL, '/admin');
    adminApi = await createApiContext(await getAccessToken(adminPage));
    expect(
      (await apiJson(adminApi, 'GET', `/student/modules/${seeded.moduleId}/workload/plan`)).status,
    ).toBe(403);

    const lecturerPage = await signInPage(lecturerContext, LECTURER_EMAIL, '/lecturer');
    lecturerApi = await createApiContext(await getAccessToken(lecturerPage));
    expect(
      (await apiJson(lecturerApi, 'GET', `/student/modules/${seeded.moduleId}/workload/plan`)).status,
    ).toBe(403);

    const updatedAvailability = await apiJson(
      studentApi,
      'PUT',
      `/student/modules/${seeded.moduleId}/workload/availability`,
      {
        studyDays: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
        preferredWindow: 'no_preference',
        maxStudyMinutesPerDay: 180,
      },
    );
    expect(updatedAvailability.status).toBe(200);
    const regenerated = await apiJson<WorkloadPlan>(
      studentApi,
      'POST',
      `/student/modules/${seeded.moduleId}/workload/plan:generate`,
    );
    expect(regenerated.status).toBe(200);
    expect(regenerated.body.id).not.toBe(plan.id);
    expect(regenerated.body.inputHash).not.toBe(plan.inputHash);
    const oldSuperseded = runPsqlJson(`
SELECT to_json((NOT is_active) AND superseded_at IS NOT NULL)::text
FROM workload_plans
WHERE id = ${sqlLiteral(plan.id)}::uuid;
`) as unknown as boolean;
    expect(oldSuperseded).toBe(true);
    const activePlanCount = runPsqlJson(`
SELECT to_json(count(*)::int)::text
FROM workload_plans
WHERE student_id = ${sqlLiteral(seeded.studentId)}::uuid
  AND module_id = ${sqlLiteral(seeded.moduleId)}::uuid
  AND is_active;
`) as unknown as number;
    expect(activePlanCount).toBe(1);
  } finally {
    await studentApi?.dispose();
    await studentTwoApi?.dispose();
    await adminApi?.dispose();
    await lecturerApi?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
    await studentTwoContext.close();
  }
});
