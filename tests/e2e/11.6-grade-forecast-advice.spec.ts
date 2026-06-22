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
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';

type ApiResponse<T = unknown> = { body: T; status: number };
type SeededAdviceGate = {
  impossibleModuleId: string;
  reachableModuleId: string;
  studentId: string;
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

async function apiJson<T>(context: APIRequestContext, method: 'GET', path: string): Promise<ApiResponse<T>> {
  const response = await context.get(path);
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 11.6 gate');
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
SELECT to_json(id)::text FROM app_users WHERE email = ${sqlLiteral(email)} LIMIT 1;
`) as unknown as string | null;
  if (!userId) throw new Error(`Missing E2E app user ${email}; run tests/e2e/fixtures/seed.mjs first`);
  return userId;
}

function cleanupPriorRunRows(runId: string) {
  const like = sqlLiteral(`Stage 11 Forecast Advice ${runId}%`);
  runPsqlRows(`
DELETE FROM student_forecast_advice
WHERE module_id IN (SELECT id FROM course_modules WHERE title LIKE ${like});

DELETE FROM student_target_grade_goals
WHERE module_id IN (SELECT id FROM course_modules WHERE title LIKE ${like});

DELETE FROM student_grade_records
WHERE grade_component_id IN (
  SELECT gc.id FROM grade_components gc
  JOIN course_grade_schemes cgs ON cgs.id = gc.scheme_id
  WHERE cgs.module_id IN (SELECT id FROM course_modules WHERE title LIKE ${like})
);

DELETE FROM grade_boundaries
WHERE scheme_id IN (
  SELECT id FROM course_grade_schemes
  WHERE module_id IN (SELECT id FROM course_modules WHERE title LIKE ${like})
);

DELETE FROM grade_components
WHERE scheme_id IN (
  SELECT id FROM course_grade_schemes
  WHERE module_id IN (SELECT id FROM course_modules WHERE title LIKE ${like})
);

DELETE FROM course_grade_schemes
WHERE module_id IN (SELECT id FROM course_modules WHERE title LIKE ${like});

DELETE FROM course_memberships
WHERE module_id IN (SELECT id FROM course_modules WHERE title LIKE ${like});

DELETE FROM course_modules WHERE title LIKE ${like};
`);
}

function seedModule(args: {
  runId: string;
  suffix: string;
  lecturerId: string;
  studentId: string;
  targetGrade: string;
  gradedScore: number;
  gradedCount: number;
}): string {
  const { runId, suffix, lecturerId, studentId, targetGrade, gradedScore, gradedCount } = args;
  const moduleId = randomUUID();
  const schemeId = randomUUID();
  const lecturerMembershipId = randomUUID();
  const studentMembershipId = randomUUID();
  const componentIds = [randomUUID(), randomUUID(), randomUUID(), randomUUID(), randomUUID()];
  const gradeRows = componentIds
    .slice(0, gradedCount)
    .map(
      (cid) =>
        `(gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(cid)}::uuid, ${gradedScore.toFixed(2)}, 'e2e')`,
    )
    .join(',\n  ');

  runPsqlRows(`
INSERT INTO course_modules (id, title, description, owner_id, timezone, starts_on, ends_on, is_active)
VALUES (
  ${sqlLiteral(moduleId)}::uuid,
  ${sqlLiteral(`Stage 11 Forecast Advice ${runId} ${suffix}`)},
  'Stage 11.6 grade-forecast advice browser gate',
  ${sqlLiteral(lecturerId)}::uuid,
  'UTC', DATE '2026-01-12', DATE '2026-05-01', true
);

INSERT INTO course_memberships (id, user_id, module_id, role, status) VALUES
  (${sqlLiteral(lecturerMembershipId)}::uuid, ${sqlLiteral(lecturerId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'lecturer', 'active'),
  (${sqlLiteral(studentMembershipId)}::uuid, ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active');

INSERT INTO course_grade_schemes (id, module_id, name, on_track_max, at_risk_max, benchmark_min_cohort)
VALUES (${sqlLiteral(schemeId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'Stage 11.6 advice scheme', 70, 85, 2);

INSERT INTO grade_boundaries (id, scheme_id, letter_grade, lower_bound, sort_order) VALUES
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A', 93, 1),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'A-', 87, 2),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B+', 84, 3),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'B', 80, 4),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'C', 70, 5),
  (gen_random_uuid(), ${sqlLiteral(schemeId)}::uuid, 'F', 0, 6);

INSERT INTO grade_components (id, scheme_id, name, weight, sort_order, component_kind) VALUES
  (${sqlLiteral(componentIds[0])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Quiz average', 0.20, 1, 'quiz'),
  (${sqlLiteral(componentIds[1])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Lab portfolio', 0.20, 2, 'lab'),
  (${sqlLiteral(componentIds[2])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Project', 0.20, 3, 'assignment'),
  (${sqlLiteral(componentIds[3])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Midterm', 0.20, 4, 'exam'),
  (${sqlLiteral(componentIds[4])}::uuid, ${sqlLiteral(schemeId)}::uuid, 'Final exam', 0.20, 5, 'exam');

INSERT INTO student_grade_records (id, student_id, grade_component_id, percentage_score, source) VALUES
  ${gradeRows};

INSERT INTO student_target_grade_goals (id, student_id, module_id, target_letter_grade, status)
VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(targetGrade)}, 'active');
`);

  recordManifestValue(runId, 'moduleIds', moduleId);
  recordManifestValue(runId, 'membershipIds', lecturerMembershipId);
  recordManifestValue(runId, 'membershipIds', studentMembershipId);
  return moduleId;
}

function seedAdviceGate(runId: string): SeededAdviceGate {
  cleanupPriorRunRows(runId);
  const lecturerId = getAppUserId(LECTURER_EMAIL);
  const studentId = getAppUserId(STUDENT_EMAIL);
  // Impossible: 4/5 components @ 82.50, target A → max reachable 86 < 93 → impossible, best B+.
  const impossibleModuleId = seedModule({
    runId, suffix: 'Impossible', lecturerId, studentId,
    targetGrade: 'A', gradedScore: 82.5, gradedCount: 4,
  });
  // Reachable: 4/5 components @ 93.75, target A → required remaining average 90 → requires_high_score.
  const reachableModuleId = seedModule({
    runId, suffix: 'Reachable', lecturerId, studentId,
    targetGrade: 'A', gradedScore: 93.75, gradedCount: 4,
  });
  return { impossibleModuleId, reachableModuleId, studentId };
}

function adviceProvenance(moduleId: string, studentId: string): Record<string, string | null> {
  return runPsqlJson(`
SELECT to_json(t)::text FROM (
  SELECT ai_status, ai_model_id, ai_prompt_version, ai_input_hash,
         (ai_generated_at IS NOT NULL) AS has_generated_at,
         (ai_input_hash = input_hash) AS hash_matches
  FROM student_forecast_advice
  WHERE module_id = ${sqlLiteral(moduleId)}::uuid AND student_id = ${sqlLiteral(studentId)}::uuid
  LIMIT 1
) t;
`) as unknown as Record<string, string | null>;
}

function aiRequestLogCount(): number {
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text FROM ai_request_logs WHERE feature = 'grade_forecast_advice';
`) as unknown as number;
}

function forceTemplateFallback(moduleId: string, studentId: string) {
  runPsqlRows(`
UPDATE student_forecast_advice
SET ai_status = 'template_fallback', ai_text = NULL, ai_input_hash = input_hash, updated_at = now()
WHERE module_id = ${sqlLiteral(moduleId)}::uuid AND student_id = ${sqlLiteral(studentId)}::uuid;
`);
}

const BANNED = /failing|at risk|behind the class|other students|give up|too late|hopeless|fallen|peer/i;

test('Stage 11.6 grade-forecast advice gate', async ({ browser }) => {
  const runId = requireRunId();
  const seeded = seedAdviceGate(runId);

  const studentContext = await browser.newContext();
  const lecturerContext = await browser.newContext();
  let lecturerApi: APIRequestContext | null = null;

  try {
    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');

    // ── Impossible case: template renders immediately, AI swaps in, honest + constructive ──────────
    // The advice card lives on the My-Progress dashboard alongside the forecast; select the module there.
    await studentPage.goto('/student/progress');
    await studentPage.getByTestId(`progress-module-card-${seeded.impossibleModuleId}`).click();
    const impossibleCard = studentPage.getByTestId('forecast-advice-card');
    await expect(impossibleCard).toBeVisible();
    await expect(impossibleCard).toHaveAttribute('data-forecast-state', 'impossible');
    // Deterministic/template advice is present immediately (non-empty before the AI resolves).
    await expect(studentPage.getByTestId('forecast-advice-text')).not.toBeEmpty();

    // AI swaps in via the gateway (deterministic E2E provider → validators pass → source=ai).
    await expect(impossibleCard).toHaveAttribute('data-source', 'ai', { timeout: 60_000 });
    await expect(impossibleCard).toHaveAttribute('data-ai-status', 'succeeded');

    // Honest + constructive: names the best reachable grade and the unreachable framing; no shaming.
    const impossibleText = (await studentPage.getByTestId('forecast-advice-text').textContent()) ?? '';
    expect(impossibleText).toContain('B+');
    expect(impossibleText.toLowerCase()).toContain('more than the remaining');
    expect(impossibleText).not.toMatch(BANNED);

    // AIRequestLog + provenance recorded for the advice feature.
    expect(aiRequestLogCount()).toBeGreaterThan(0);
    const prov = adviceProvenance(seeded.impossibleModuleId, seeded.studentId);
    expect(prov.ai_status).toBe('succeeded');
    expect(prov.ai_model_id).toBeTruthy();
    expect(prov.ai_prompt_version).toBe('v1');
    expect(prov.has_generated_at).toBe(true);
    expect(prov.hash_matches).toBe(true);

    // ── Reachable case: advice references the deterministic numbers, invents none ─────────────────
    await studentPage.getByTestId(`progress-module-card-${seeded.reachableModuleId}`).click();
    const reachableCard = studentPage.getByTestId('forecast-advice-card');
    await expect(reachableCard).toBeVisible();
    await expect(reachableCard).toHaveAttribute('data-forecast-state', 'requires_high_score', {
      timeout: 60_000,
    });
    await expect(reachableCard).toHaveAttribute('data-source', 'ai', { timeout: 60_000 });
    const reachableText = (await studentPage.getByTestId('forecast-advice-text').textContent()) ?? '';
    expect(reachableText).toContain('90%'); // required remaining average (1-dp), the deterministic number
    expect(reachableText).toContain('A'); // target grade
    expect(reachableText).not.toMatch(BANNED);

    // ── Forced AI-unavailable → template fallback renders (no broken/empty card) ──────────────────
    forceTemplateFallback(seeded.impossibleModuleId, seeded.studentId);
    await studentPage.goto('/student/progress');
    await studentPage.getByTestId(`progress-module-card-${seeded.impossibleModuleId}`).click();
    const fallbackCard = studentPage.getByTestId('forecast-advice-card');
    await expect(fallbackCard).toBeVisible();
    await expect(fallbackCard).toHaveAttribute('data-ai-status', 'template_fallback', { timeout: 60_000 });
    await expect(fallbackCard).toHaveAttribute('data-source', 'template');
    const fallbackText = (await studentPage.getByTestId('forecast-advice-text').textContent()) ?? '';
    expect(fallbackText).toContain('B+'); // honest template still renders
    expect(fallbackText).not.toMatch(BANNED);

    // ── Gamification block on the same page is untouched ──────────────────────────────────────────
    await expect(studentPage.getByTestId('gamification-placeholder')).toBeVisible();

    // ── Student-self only: a non-student role gets 403 on the advice endpoint ─────────────────────
    const lecturerPage = await signInPage(lecturerContext, LECTURER_EMAIL, '/lecturer');
    lecturerApi = await createApiContext(await getAccessToken(lecturerPage));
    const forbidden = await apiJson(
      lecturerApi,
      'GET',
      `/student/modules/${seeded.impossibleModuleId}/forecast-advice`,
    );
    expect(forbidden.status).toBe(403);
  } finally {
    await lecturerApi?.dispose();
    await studentContext.close();
    await lecturerContext.close();
  }
});
