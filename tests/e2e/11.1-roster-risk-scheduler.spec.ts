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
const STUDENT_TWO_EMAIL = 'student2_e2e@example.test';

type ApiResponse<T = unknown> = { body: T; status: number };
type AgentRunRead = {
  id: string;
  status: string;
  snapshotCount: number;
};
type SeededRiskGate = {
  moduleId: string;
  riskStudentId: string;
  steadyStudentId: string;
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
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 11.1 gate');
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
	DELETE FROM student_risk_snapshots
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM agent_runs
	WHERE scope_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM student_activity_events
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM quiz_attempts
	WHERE quiz_definition_id IN (
	  SELECT id FROM quiz_definitions
	  WHERE module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	  )
	);

	DELETE FROM quiz_definitions
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM student_topic_mastery_snapshots
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM student_progress_snapshots
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM student_target_grade_goals
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM student_grade_records
	WHERE grade_component_id IN (
	  SELECT gc.id
	  FROM grade_components gc
	  JOIN course_grade_schemes cgs ON cgs.id = gc.scheme_id
	  WHERE cgs.module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	  )
	);

	DELETE FROM grade_boundaries
	WHERE scheme_id IN (
	  SELECT id FROM course_grade_schemes
	  WHERE module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	  )
	);

	DELETE FROM grade_components
	WHERE scheme_id IN (
	  SELECT id FROM course_grade_schemes
	  WHERE module_id IN (
	    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	  )
	);

	DELETE FROM course_grade_schemes
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM module_sections
	WHERE course_module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM course_memberships
	WHERE module_id IN (
	  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)}
	);

	DELETE FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Risk Gate ${runId}%`)};
	`);
}

function seedRiskGate(runId: string): SeededRiskGate {
  cleanupPriorRunRows(runId);

  const lecturerId = getAppUserId(LECTURER_EMAIL);
  const riskStudentId = getAppUserId(STUDENT_EMAIL);
  const steadyStudentId = getAppUserId(STUDENT_TWO_EMAIL);
  const moduleId = randomUUID();
  const lectureId = randomUUID();
  const labId = randomUUID();
  const lecturerMembershipId = randomUUID();
  const riskMembershipId = randomUUID();
  const steadyMembershipId = randomUUID();
  const schemeId = randomUUID();
  const componentIds = [randomUUID(), randomUUID(), randomUUID(), randomUUID(), randomUUID()];
  const quizDefinitionId = randomUUID();
  const riskAttemptId = randomUUID();
  const steadyAttemptId = randomUUID();
  const eventTime = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

  runPsqlRows(`
INSERT INTO course_modules (id, title, description, owner_id, timezone, starts_on, ends_on, is_active)
VALUES (
  ${sqlLiteral(moduleId)}::uuid,
  ${sqlLiteral(`Stage 11 Risk Gate ${runId}`)},
  'Stage 11 roster risk browser gate',
  ${sqlLiteral(lecturerId)}::uuid,
  'UTC',
  DATE '2026-01-12',
  DATE '2026-05-01',
  true
);

INSERT INTO course_memberships (id, user_id, module_id, role, status) VALUES
  (${sqlLiteral(lecturerMembershipId)}::uuid, ${sqlLiteral(lecturerId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'lecturer', 'active'),
  (${sqlLiteral(riskMembershipId)}::uuid, ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active'),
  (${sqlLiteral(steadyMembershipId)}::uuid, ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active');

INSERT INTO module_sections (id, course_module_id, title, type, order_index, week_number, session_date, publish_status, status)
VALUES
  (${sqlLiteral(lectureId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Risk Signal Lecture', 'lecture', 1, 1, DATE '2026-01-12', 'published', 'active'),
  (${sqlLiteral(labId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Risk Signal Lab', 'lab', 2, 1, DATE '2026-01-13', 'published', 'active');

INSERT INTO course_grade_schemes (id, module_id, name, on_track_max, at_risk_max, benchmark_min_cohort)
VALUES (${sqlLiteral(schemeId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Stage 11 risk gate scheme', 70, 85, 2);

INSERT INTO grade_boundaries (id, scheme_id, letter_grade, lower_bound, sort_order) VALUES
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A', 93, 1),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A-', 87, 2),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B+', 84, 3),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B', 80, 4),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'C', 70, 5),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'F', 0, 6);

INSERT INTO grade_components (id, scheme_id, name, weight, sort_order, component_kind, module_section_id) VALUES
  (${sqlLiteral(componentIds[0])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Quiz average', 0.20, 1, 'quiz', ${sqlLiteral(lectureId)}::uuid),
  (${sqlLiteral(componentIds[1])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Lab portfolio', 0.20, 2, 'lab', ${sqlLiteral(labId)}::uuid),
  (${sqlLiteral(componentIds[2])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Project', 0.20, 3, 'assignment', NULL),
  (${sqlLiteral(componentIds[3])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Midterm', 0.20, 4, 'exam', NULL),
  (${sqlLiteral(componentIds[4])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Final exam', 0.20, 5, 'exam', NULL);

INSERT INTO student_grade_records (id, student_id, grade_component_id, percentage_score, source)
VALUES
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[0])}::uuid, 82.50, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[1])}::uuid, 82.50, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[2])}::uuid, 82.50, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(componentIds[3])}::uuid, 82.50, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(componentIds[0])}::uuid, 92.00, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(componentIds[1])}::uuid, 92.00, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(componentIds[2])}::uuid, 92.00, 'e2e'),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(componentIds[3])}::uuid, 92.00, 'e2e');

INSERT INTO student_target_grade_goals (id, student_id, module_id, target_letter_grade, status)
VALUES
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'A', 'active'),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'B', 'active');

INSERT INTO student_progress_snapshots (id, student_id, module_id, week_number, snapshot_date, standing_points, source_metrics)
VALUES
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 1, DATE '2026-01-12', 72.00, '{"seed":"stage11-e2e"}'::jsonb),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 1, DATE '2026-01-12', 88.00, '{"seed":"stage11-e2e"}'::jsonb);

INSERT INTO student_topic_mastery_snapshots (id, student_id, module_id, module_section_id, mastery_percentage, status_label, source_metrics)
VALUES
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(lectureId)}::uuid, 74.00, 'on_track', '{"seed":"stage11-e2e"}'::jsonb),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(lectureId)}::uuid, 91.00, 'strong', '{"seed":"stage11-e2e"}'::jsonb);

INSERT INTO quiz_definitions (id, module_section_id, module_id, quiz_mode, source_scope, created_at)
VALUES (
  ${sqlLiteral(quizDefinitionId)}::uuid,
  ${sqlLiteral(lectureId)}::uuid,
  ${sqlLiteral(moduleId)}::uuid,
  'post_class',
  ${sqlLiteral(JSON.stringify({ sectionIds: [lectureId] }))}::jsonb,
  ${sqlLiteral(eventTime)}::timestamptz
);

INSERT INTO quiz_attempts (
  id, quiz_definition_id, student_id, attempt_number, status, total_questions,
  new_question_count, mistake_review_question_count, correct_count, incorrect_count,
  score_percentage, started_at, completed_at
)
VALUES
  (${sqlLiteral(riskAttemptId)}::uuid, ${sqlLiteral(quizDefinitionId)}::uuid, ${sqlLiteral(riskStudentId)}::uuid, 1, 'completed', 10, 10, 0, 9, 1, 90.00, ${sqlLiteral(eventTime)}::timestamptz, ${sqlLiteral(eventTime)}::timestamptz),
  (${sqlLiteral(steadyAttemptId)}::uuid, ${sqlLiteral(quizDefinitionId)}::uuid, ${sqlLiteral(steadyStudentId)}::uuid, 1, 'completed', 10, 10, 0, 9, 1, 90.00, ${sqlLiteral(eventTime)}::timestamptz, ${sqlLiteral(eventTime)}::timestamptz);

INSERT INTO student_activity_events (id, student_id, module_id, event_type, source_id, occurred_at, metadata)
VALUES
  (gen_random_uuid(), ${sqlLiteral(riskStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'completed_quiz', ${sqlLiteral(riskAttemptId)}::uuid, ${sqlLiteral(eventTime)}::timestamptz, '{"seed":"stage11-e2e"}'::jsonb),
  (gen_random_uuid(), ${sqlLiteral(steadyStudentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'completed_quiz', ${sqlLiteral(steadyAttemptId)}::uuid, ${sqlLiteral(eventTime)}::timestamptz, '{"seed":"stage11-e2e"}'::jsonb);
`);

  for (const id of [moduleId]) recordManifestValue(runId, 'moduleIds', id);
  for (const id of [lectureId, labId]) recordManifestValue(runId, 'sectionIds', id);
  for (const id of [lecturerMembershipId, riskMembershipId, steadyMembershipId]) {
    recordManifestValue(runId, 'membershipIds', id);
  }

  return {
    moduleId,
    riskStudentId,
    steadyStudentId,
    scheduledFor: new Date(Date.now() + 1000).toISOString(),
  };
}

function promoteRiskStudent(moduleId: string, studentId: string) {
  runPsqlRows(`
UPDATE student_grade_records
SET percentage_score = 100.00
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND grade_component_id IN (
    SELECT gc.id
    FROM grade_components gc
    JOIN course_grade_schemes cgs ON cgs.id = gc.scheme_id
    WHERE cgs.module_id = ${sqlLiteral(moduleId)}::uuid
  );
`);
}

function snapshotCount(runId: string): number {
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text
FROM student_risk_snapshots
WHERE agent_run_id = ${sqlLiteral(runId)}::uuid;
`) as unknown as number;
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

test('Stage 11.1 roster risk scheduler gate', async ({ browser }) => {
  const runId = requireRunId();
  const seeded = seedRiskGate(runId);

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
    expect(completed.snapshotCount).toBe(2);
    expect(snapshotCount(firstRun.body.id)).toBe(2);

    const lecturerPage = await signInPage(lecturerContext, LECTURER_EMAIL, '/lecturer');
    await lecturerPage.goto(`/lecturer/modules/${seeded.moduleId}`);
    await expect(lecturerPage.getByTestId('lecturer-roster-risk')).toBeVisible();
    await expect(lecturerPage.getByTestId('needs-support-count')).toHaveText('Needs support: 1');
    await expect(lecturerPage.getByTestId(`lecturer-risk-row-${seeded.riskStudentId}`)).toContainText('Needs support');
    await expect(lecturerPage.getByTestId('lecturer-risk-reason-forecast_impossible')).toContainText(
      'forecastState: impossible',
    );

    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    await studentPage.goto(`/student/modules/${seeded.moduleId}`);
    const studentRiskCard = studentPage.getByTestId('student-risk-card');
    await expect(studentRiskCard).toBeVisible();
    await expect(studentRiskCard).toContainText('Your target may need a different path from here');
    await expect(studentRiskCard).not.toContainText(/Needs support|Watch|peer|other students/i);

    promoteRiskStudent(seeded.moduleId, seeded.riskStudentId);
    await lecturerPage.reload();
    await expect(lecturerPage.getByTestId('lecturer-roster-risk')).toBeVisible();
    await expect(lecturerPage.getByTestId('needs-support-count')).toHaveText('Needs support: 0');
    await expect(lecturerPage.getByTestId(`lecturer-risk-row-${seeded.riskStudentId}`)).not.toContainText(
      'forecastState: impossible',
    );
    await studentPage.reload();
    await expect(studentRiskCard).toContainText('Your recent activity looks steady for this module.');
    await expect(snapshotCount(firstRun.body.id)).toBe(2);

    const duplicateRun = await apiJson<AgentRunRead>(adminApi, 'POST', '/admin/analytics/agent-runs', {
      triggerType: 'manual_admin',
      scopeType: 'module',
      scopeId: seeded.moduleId,
      scheduledFor: seeded.scheduledFor,
    });
    expect(duplicateRun.status).toBe(202);
    expect(duplicateRun.body.id).toBe(firstRun.body.id);
    expect(duplicateRun.body.snapshotCount).toBe(2);
    expect(snapshotCount(firstRun.body.id)).toBe(2);
  } finally {
    await adminApi?.dispose();
    await adminContext.close();
    await lecturerContext.close();
    await studentContext.close();
  }
});
