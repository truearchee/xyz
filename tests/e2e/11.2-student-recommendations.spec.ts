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
import { randomUUID } from 'node:crypto';

import { runPsqlJson, runPsqlRows, sqlLiteral } from './fixtures/db.mjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';

type ApiResponse<T = unknown> = { body: T; status: number };
type AgentRunRead = {
  id: string;
  status: string;
  snapshotCount: number;
  recommendationCount: number;
};
type SeededRecommendationGate = {
  moduleId: string;
  riskStudentId: string;
  scheduledFor: string;
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
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response = method === 'GET' ? await context.get(path) : await context.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 11.2 gate');
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) throw new Error(`Invalid E2E run id: ${runId}`);
  return runId;
}

type RunManifest = { [key: string]: string[] | string; runId: string };
function manifestPathForRunId(runId: string): string {
  return resolve('tests/e2e/.runs', `${runId}.json`);
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
	DELETE FROM recommendations
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM student_risk_snapshots
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM agent_runs
	WHERE scope_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM student_activity_events
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM quiz_attempts
	WHERE quiz_definition_id IN (
	  SELECT id FROM quiz_definitions
	  WHERE module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	  )
	);

	DELETE FROM quiz_definitions
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM student_topic_mastery_snapshots
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM student_progress_snapshots
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM student_target_grade_goals
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM student_grade_records
	WHERE grade_component_id IN (
	  SELECT gc.id
	  FROM grade_components gc
	  JOIN course_grade_schemes cgs ON cgs.id = gc.scheme_id
	  WHERE cgs.module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	  )
	);

	DELETE FROM grade_boundaries
	WHERE scheme_id IN (
	  SELECT id FROM course_grade_schemes
	  WHERE module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	  )
	);

	DELETE FROM grade_components
	WHERE scheme_id IN (
	  SELECT id FROM course_grade_schemes
	  WHERE module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	  )
	);

	DELETE FROM course_grade_schemes
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM module_sections
	WHERE course_module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM course_memberships
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)}
	);

	DELETE FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}%`)};
	`);
}

function seedRecommendationGate(runId: string): SeededRecommendationGate {
  cleanupPriorRunRows(runId);

  const lecturerId = getAppUserId(LECTURER_EMAIL);
  const riskStudentId = getAppUserId(STUDENT_EMAIL);
  const moduleId = randomUUID();
  const lectureId = randomUUID();
  const lecturerMembershipId = randomUUID();
  const riskMembershipId = randomUUID();
  const schemeId = randomUUID();
  const componentIds = [randomUUID(), randomUUID(), randomUUID(), randomUUID(), randomUUID()];

  runPsqlRows(`
INSERT INTO course_modules (id, title, description, owner_id, timezone, starts_on, ends_on, is_active)
VALUES (
  ${sqlLiteral(moduleId)}::uuid,
  ${sqlLiteral(`Stage 11 Recommendation Gate ${runId}`)},
  'Stage 11 recommendation browser gate',
  ${sqlLiteral(lecturerId)}::uuid,
  'UTC',
  DATE '2026-01-12',
  DATE '2026-05-01',
  true
);

INSERT INTO course_memberships (id, user_id, module_id, role, status) VALUES
  (${sqlLiteral(lecturerMembershipId)}::uuid, ${sqlLiteral(lecturerId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'lecturer', 'active'),
  (${sqlLiteral(riskMembershipId)}::uuid, ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active');

INSERT INTO module_sections (id, course_module_id, title, type, order_index, week_number, session_date, publish_status, status)
VALUES (
  ${sqlLiteral(lectureId)}::uuid,
  ${sqlLiteral(moduleId)}::uuid,
  'Recommendation Signal Lecture',
  'lecture',
  1,
  1,
  DATE '2026-01-12',
  'published',
  'active'
);

INSERT INTO course_grade_schemes (id, module_id, name, on_track_max, at_risk_max, benchmark_min_cohort)
VALUES (${sqlLiteral(schemeId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Stage 11 recommendation gate scheme', 70, 85, 2);

INSERT INTO grade_boundaries (id, scheme_id, letter_grade, lower_bound, sort_order) VALUES
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A', 93, 1),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A-', 87, 2),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B+', 84, 3),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B', 80, 4),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'C', 70, 5),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'F', 0, 6);

INSERT INTO grade_components (id, scheme_id, name, weight, sort_order, component_kind, module_section_id) VALUES
  (${sqlLiteral(componentIds[0])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Quiz average', 0.20, 1, 'quiz', ${sqlLiteral(lectureId)}::uuid),
  (${sqlLiteral(componentIds[1])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Lab portfolio', 0.20, 2, 'lab', NULL),
  (${sqlLiteral(componentIds[2])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Project', 0.20, 3, 'assignment', NULL),
  (${sqlLiteral(componentIds[3])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Midterm', 0.20, 4, 'exam', NULL),
  (${sqlLiteral(componentIds[4])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Final exam', 0.20, 5, 'exam', NULL);

INSERT INTO student_grade_records (id, student_id, grade_component_id, percentage_score, source)
VALUES
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[0])}::uuid, 82.50, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[1])}::uuid, 82.50, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[2])}::uuid, 82.50, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[3])}::uuid, 82.50, 'e2e');

INSERT INTO student_target_grade_goals (id, student_id, module_id, target_letter_grade, status)
VALUES (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'A', 'active');

INSERT INTO student_progress_snapshots (id, student_id, module_id, week_number, snapshot_date, standing_points, source_metrics)
VALUES (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 1, DATE '2026-01-12', 72.00, '{"seed":"stage11.2-e2e"}'::jsonb);
`);

  for (const id of [moduleId]) recordManifestValue(runId, 'moduleIds', id);
  for (const id of [lectureId]) recordManifestValue(runId, 'sectionIds', id);
  for (const id of [lecturerMembershipId, riskMembershipId]) recordManifestValue(runId, 'membershipIds', id);

  return {
    moduleId,
    riskStudentId,
    scheduledFor: new Date(Date.now() + 1000).toISOString(),
  };
}

function promoteRiskStudent(moduleId: string, studentId: string) {
  runPsqlRows(`
DELETE FROM student_grade_records
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND grade_component_id IN (
    SELECT gc.id
    FROM grade_components gc
    JOIN course_grade_schemes cgs ON cgs.id = gc.scheme_id
    WHERE cgs.module_id = ${sqlLiteral(moduleId)}::uuid
  );

INSERT INTO student_grade_records (id, student_id, grade_component_id, percentage_score, source)
SELECT gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, gc.id, 100.00, 'e2e'
FROM grade_components gc
JOIN course_grade_schemes cgs ON cgs.id = gc.scheme_id
WHERE cgs.module_id = ${sqlLiteral(moduleId)}::uuid;
`);
}

function activeRecommendationCount(moduleId: string): number {
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text
FROM recommendations
WHERE module_id = ${sqlLiteral(moduleId)}::uuid
  AND status = 'active';
`) as unknown as number;
}

function closeOtherStudentRecommendations(moduleId: string, studentId: string) {
  runPsqlRows(`
UPDATE recommendations
SET status = 'closed',
    close_reason = 'superseded',
    closed_at = now(),
    updated_at = now()
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND module_id <> ${sqlLiteral(moduleId)}::uuid
  AND status = 'active';
`);
}

async function pollRun(api: APIRequestContext, runId: string): Promise<AgentRunRead> {
  let last: AgentRunRead | null = null;
  await expect
    .poll(
      async () => {
        const response = await apiJson<AgentRunRead>(api, 'GET', `/admin/analytics/agent-runs/${runId}`);
        expect(response.status).toBe(200);
        last = response.body;
        return response.body.status;
      },
      { intervals: [500, 1000, 2000], timeout: 60_000 },
    )
    .toBe('completed');
  return last as AgentRunRead;
}

test('Stage 11.2 student detail recommendations gate', async ({ browser }) => {
  const runId = requireRunId();
  const seeded = seedRecommendationGate(runId);

  const adminContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  const studentContext = await browser.newContext();
  let adminApi: APIRequestContext | null = null;

  try {
    const adminPage = await signInPage(adminContext, ADMIN_EMAIL, '/admin');
    adminApi = await createApiContext(await getAccessToken(adminPage));

    const firstRun = await apiJson<AgentRunRead>(adminApi, 'POST', '/admin/analytics/agent-runs', {
      triggerType: 'manual_admin',
      scopeType: 'module',
      scopeId: seeded.moduleId,
      scheduledFor: seeded.scheduledFor,
    });
    expect(firstRun.status).toBe(202);

    const completed = await pollRun(adminApi, firstRun.body.id);
    expect(completed.snapshotCount).toBe(1);
    expect(completed.recommendationCount).toBe(1);
    expect(activeRecommendationCount(seeded.moduleId)).toBe(1);
    closeOtherStudentRecommendations(seeded.moduleId, seeded.riskStudentId);

    const lecturerPage = await signInPage(lecturerContext, LECTURER_EMAIL, '/lecturer');
    await lecturerPage.goto(`/lecturer/modules/${seeded.moduleId}`);
    await expect(lecturerPage.getByTestId('lecturer-roster-risk')).toBeVisible();
    await expect(lecturerPage.getByTestId('needs-support-count')).toHaveText('Needs support: 1');
    await expect(lecturerPage.getByTestId(`lecturer-risk-row-${seeded.riskStudentId}`)).toContainText('Needs support');
    await expect(lecturerPage.getByTestId('lecturer-risk-reason-forecast_impossible')).toContainText(
      'forecastState: impossible',
    );

    await lecturerPage.getByTestId(`lecturer-risk-row-${seeded.riskStudentId}`).getByRole('button', { name: 'Review' }).click();
    const modal = lecturerPage.getByRole('dialog');
    await expect(modal.getByTestId('lecturer-recommendation-modal')).toBeVisible();
    await expect(modal).toContainText('Suggested manual follow-up');
    await expect(modal).toContainText('Student preview');
    await expect(modal).toContainText('Your target may need a different path from here');
    await expect(modal.getByRole('button', { name: 'Copy draft' })).toBeVisible();
    await expect(modal.getByRole('button', { name: 'Mark acted' })).toBeVisible();
    await expect(modal.getByRole('button', { name: 'Dismiss' })).toBeVisible();
    await expect(modal.getByRole('button', { name: /send/i })).toHaveCount(0);

    await modal.getByRole('button', { name: 'Dismiss' }).click();
    await expect(modal).toContainText('No current recommendation for this student.');

    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    await expect(studentPage.getByTestId('student-recommendation-banner')).toBeVisible();
    await expect(studentPage.getByTestId('student-recommendation-banner')).toContainText(
      'Your target may need a different path from here',
    );
    await expect(studentPage.getByTestId('student-recommendation-banner')).toContainText(
      'Focus on the strongest remaining course opportunities',
    );
    await expect(studentPage.getByTestId('student-recommendation-banner')).not.toContainText(
      /Needs support|Watch|peer|other students/i,
    );

    await studentPage.goto(`/student/modules/${seeded.moduleId}`);
    const studentRiskCard = studentPage.getByTestId('student-risk-card');
    await expect(studentRiskCard).toBeVisible();
    await expect(studentPage.getByTestId('student-recommendation-nudge')).toBeVisible();
    await expect(studentRiskCard).toContainText('Your target may need a different path from here');
    await expect(studentRiskCard).not.toContainText(/Needs support|Watch|peer|other students/i);

    promoteRiskStudent(seeded.moduleId, seeded.riskStudentId);
    await studentPage.reload();
    await expect(studentRiskCard).toContainText('Your recent activity looks steady for this module.');
    await expect(studentPage.getByTestId('student-recommendation-nudge')).toHaveCount(0);

    await lecturerPage.reload();
    await expect(lecturerPage.getByTestId('lecturer-roster-risk')).toBeVisible();
    await expect(lecturerPage.getByTestId('needs-support-count')).toHaveText('Needs support: 0');
    await expect(lecturerPage.getByTestId(`lecturer-risk-row-${seeded.riskStudentId}`)).not.toContainText(
      'forecastState: impossible',
    );

    const duplicateRun = await apiJson<AgentRunRead>(adminApi, 'POST', '/admin/analytics/agent-runs', {
      triggerType: 'manual_admin',
      scopeType: 'module',
      scopeId: seeded.moduleId,
      scheduledFor: seeded.scheduledFor,
    });
    expect(duplicateRun.status).toBe(202);
    expect(duplicateRun.body.id).toBe(firstRun.body.id);
    expect(duplicateRun.body.recommendationCount).toBe(1);
    expect(activeRecommendationCount(seeded.moduleId)).toBe(1);
  } finally {
    await adminApi?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
