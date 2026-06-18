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

import {
  getAppUserByEmail,
  runPsqlJson,
  runPsqlRows,
  sqlLiteral,
} from './fixtures/db.mjs';

/**
 * Stage 6d browser gate — complete quiz modes + security set.
 *
 * This gate intentionally mixes browser actions with DB-backed assertions:
 * browser proves the shipped surfaces, while DB assertions prove scope sampling, pool reuse,
 * own-student-only mistakes, and 404/403 semantics without trusting rendered text alone.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_A_EMAIL = 'student_e2e@example.test';
const E2E_ACTOR_DOMAIN = 'xyz-lms-e2e.dev';
const SCREENSHOT_DIR = resolve('knowledge/steps/stage-06/screenshots');

type ApiResponse<T = unknown> = { body: T; status: number };
type OptionRow = { questionId: string; optionId: string; isCorrect: boolean };
type SeededSection = { id: string; title: string; type: string; weekNumber: number; publishStatus: string };
type MistakeState = { id: string; retakeCorrectCount: number; showInRetakePrefix: boolean };
type EventRow = { eventType: string; metadata: Record<string, unknown> };
type SeededModule = {
  moduleId: string;
  studentAId: string;
  studentBId: string;
  studentBEmail: string;
  studentCId: string;
  studentCEmail: string;
  lectureW1: SeededSection;
  labW1: SeededSection;
  lectureW2: SeededSection;
  hiddenW1: SeededSection;
};

test.setTimeout(420_000);

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
  ctx: APIRequestContext,
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response = method === 'GET' ? await ctx.get(path) : await ctx.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 6d gate');
  return runId;
}

function manifestPathForRunId(runId: string): string {
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) throw new Error(`Invalid E2E run id: ${runId}`);
  return resolve('tests/e2e/.runs', `${runId}.json`);
}

function recordManifestValue(runId: string, field: string, value: string) {
  const manifest = JSON.parse(readFileSync(manifestPathForRunId(runId), 'utf8')) as Record<string, string[] | string>;
  const current = Array.isArray(manifest[field]) ? (manifest[field] as string[]) : [];
  manifest[field] = [...new Set([...current, value])];
  writeFileSync(manifestPathForRunId(runId), `${JSON.stringify(manifest, null, 2)}\n`);
}

function loadE2EEnv(): Record<string, string> {
  const path = resolve('.env.e2e');
  if (!existsSync(path)) {
    throw new Error('.env.e2e is required for the 6d browser gate');
  }
  const parsed: Record<string, string> = {};
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const separator = trimmed.indexOf('=');
    if (separator === -1) continue;
    parsed[trimmed.slice(0, separator)] = trimmed.slice(separator + 1).replace(/^"(.*)"$/, '$1');
  }
  return { ...parsed, ...process.env } as Record<string, string>;
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

async function ensureRunScopedAuthStudent(runId: string, key: string): Promise<{ authId: string; appId: string; email: string }> {
  const env = loadE2EEnv();
  const safeRunId = runId.replaceAll('_', '-');
  const email = `${key}-${safeRunId}@${E2E_ACTOR_DOMAIN}`;
  const appId = randomUUID();
  const usersBody = await supabaseAdminFetch(env, '/auth/v1/admin/users?per_page=1000&page=1');
  const existing = Array.isArray(usersBody?.users)
    ? usersBody.users.find((candidate: { email?: string }) => candidate.email === email)
    : null;
  const payload = {
    email,
    password: env.E2E_TEST_PASSWORD,
    email_confirm: true,
    user_metadata: { full_name: `Stage 6d ${key}`, e2e_fixture: '6d' },
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
  if (!authUser?.id) {
    throw new Error(`Supabase auth user was not created for ${email}`);
  }
  recordManifestValue(runId, 'authUserIds', authUser.id);
  const persistedAppId = runPsqlJson(`
WITH upserted AS (
  INSERT INTO app_users (id, auth_provider_id, email, full_name, role, is_active, timezone)
  VALUES (${sqlLiteral(appId)}::uuid, ${sqlLiteral(authUser.id)}, ${sqlLiteral(email)}, ${sqlLiteral(`Stage 6d ${key}`)}, 'student', true, 'UTC')
  ON CONFLICT (auth_provider_id) DO UPDATE
  SET email = EXCLUDED.email,
      full_name = EXCLUDED.full_name,
      role = EXCLUDED.role,
      is_active = true,
      timezone = EXCLUDED.timezone
  RETURNING id
)
SELECT to_json(id)::text FROM upserted;
`) as unknown as string;
  recordManifestValue(runId, 'appUserIds', persistedAppId);
  return { authId: authUser.id, appId: persistedAppId, email };
}

function insertMembership(runId: string, userId: string, moduleId: string, role: 'lecturer' | 'student') {
  const id = runPsqlJson(`
WITH inserted AS (
  INSERT INTO course_memberships (id, user_id, module_id, role, status)
  VALUES (gen_random_uuid(), ${sqlLiteral(userId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(role)}, 'active')
  RETURNING id
)
SELECT to_json(id)::text FROM inserted;
`) as unknown as string;
  recordManifestValue(runId, 'membershipIds', id);
}

function insertReadySection(runId: string, moduleId: string, lecturerId: string, input: {
  title: string;
  type: 'lecture' | 'lab';
  orderIndex: number;
  weekNumber: number;
  sessionDate: string;
  publishStatus: 'published' | 'unpublished';
}): SeededSection {
  const row = runPsqlJson(`
WITH section AS (
  INSERT INTO module_sections (
    id, course_module_id, title, type, order_index, week_number, session_date, publish_status, status
  )
  VALUES (
    gen_random_uuid(), ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(input.title)}, ${sqlLiteral(input.type)},
    ${input.orderIndex}, ${input.weekNumber}, DATE ${sqlLiteral(input.sessionDate)},
    ${sqlLiteral(input.publishStatus)}, 'active'
  )
  RETURNING id, title, type, week_number, publish_status
),
transcript AS (
  INSERT INTO transcripts (
    id, module_section_id, source_type, original_file_name, storage_key, mime_type, file_size,
    checksum, status, uploaded_by_user_id, lifecycle_state
  )
  SELECT gen_random_uuid(), id, 'manual_upload', ${sqlLiteral(`${input.title}.vtt`)},
         ${sqlLiteral(`modules/${moduleId}/sections/${input.orderIndex}/${randomUUID()}.vtt`)},
         'text/vtt', 100,
         encode(sha256(${sqlLiteral(`${runId}:${input.title}`)}::bytea), 'hex'),
         'completed', ${sqlLiteral(lecturerId)}::uuid, 'active'
  FROM section
  RETURNING id, module_section_id, checksum
),
job AS (
  INSERT INTO ingestion_jobs (id, transcript_id, job_type, status, attempts, idempotency_key, completed_at)
  SELECT gen_random_uuid(), id, 'generate_detailed_summary', 'completed', 1,
         ${sqlLiteral(`6d-summary:${runId}:${input.orderIndex}:${randomUUID()}`)}, now()
  FROM transcript
  RETURNING id, transcript_id
),
log AS (
  INSERT INTO ai_request_logs (
    id, ingestion_job_id, feature, model_id, prompt_version, prompt_content_hash, rendered_prompt_hash,
    input_content_hash, status, request_completed_at
  )
  SELECT gen_random_uuid(), id, 'summary_detailed', 'deterministic-e2e', 'detailed-v1', 'h', 'rh', 'ih',
         'succeeded', now()
  FROM job
  RETURNING id, ingestion_job_id
),
summary AS (
  INSERT INTO generated_lecture_summaries (
    id, transcript_id, module_section_id, summary_type, content_json, content_schema_version,
    model_id, prompt_version, prompt_content_hash, backend_used, source_transcript_checksum,
    input_hash, ai_request_log_id, created_by_ingestion_job_id
  )
  SELECT gen_random_uuid(), t.id, t.module_section_id, 'detailed_study',
         jsonb_build_object(
           'overview', ${sqlLiteral(`Stage 6d ${input.title} overview`)},
           'keyConcepts', jsonb_build_array(${sqlLiteral(`${input.title} concept`)}),
           'importantDefinitions', jsonb_build_array(jsonb_build_object('term', ${sqlLiteral(input.title)}, 'definition', 'Definition')),
           'mainExplanations', jsonb_build_array('Main explanation'),
           'examples', jsonb_build_array('Worked example'),
           'examRelevantPoints', jsonb_build_array(${sqlLiteral(`Exam point ${input.weekNumber}`)})
         ),
         'detailed-v1', 'deterministic-e2e', 'detailed-v1', 'h', 'nvidia', t.checksum, 'ih',
         l.id, j.id
  FROM transcript t
  JOIN job j ON j.transcript_id = t.id
  JOIN log l ON l.ingestion_job_id = j.id
  RETURNING id
)
SELECT json_build_object(
  'id', s.id,
  'title', s.title,
  'type', s.type,
  'weekNumber', s.week_number,
  'publishStatus', s.publish_status,
  'transcriptId', t.id,
  'ingestionJobId', j.id,
  'aiRequestLogId', l.id
)::text
FROM section s
JOIN transcript t ON t.module_section_id = s.id
JOIN job j ON j.transcript_id = t.id
JOIN log l ON l.ingestion_job_id = j.id;
`) as unknown as SeededSection & { transcriptId: string; ingestionJobId: string; aiRequestLogId: string };
  recordManifestValue(runId, 'sectionIds', row.id);
  recordManifestValue(runId, 'transcriptIds', row.transcriptId);
  recordManifestValue(runId, 'ingestionJobIds', row.ingestionJobId);
  recordManifestValue(runId, 'aiRequestLogIds', row.aiRequestLogId);
  return row;
}

async function seedModule(runId: string): Promise<SeededModule> {
  const lecturer = getAppUserByEmail(LECTURER_EMAIL);
  const studentA = getAppUserByEmail(STUDENT_A_EMAIL);
  const studentB = await ensureRunScopedAuthStudent(runId, 'student-b');
  const studentC = await ensureRunScopedAuthStudent(runId, 'student-c');
  const moduleId = runPsqlJson(`
WITH inserted AS (
  INSERT INTO course_modules (id, title, owner_id, timezone, starts_on, ends_on, is_active)
  VALUES (
    gen_random_uuid(), ${sqlLiteral(`Stage 6d Quiz Modes ${runId}`)}, ${sqlLiteral(lecturer.id)}::uuid,
    'UTC', DATE '2026-01-05', DATE '2026-02-28', true
  )
  RETURNING id
)
SELECT to_json(id)::text FROM inserted;
`) as unknown as string;
  recordManifestValue(runId, 'moduleIds', moduleId);
  insertMembership(runId, lecturer.id, moduleId, 'lecturer');
  insertMembership(runId, studentA.id, moduleId, 'student');
  insertMembership(runId, studentB.appId, moduleId, 'student');

  return {
    moduleId,
    studentAId: studentA.id,
    studentBId: studentB.appId,
    studentBEmail: studentB.email,
    studentCId: studentC.appId,
    studentCEmail: studentC.email,
    lectureW1: insertReadySection(runId, moduleId, lecturer.id, {
      title: 'Stage 6d Lecture W1',
      type: 'lecture',
      orderIndex: 1,
      weekNumber: 1,
      sessionDate: '2026-01-06',
      publishStatus: 'published',
    }),
    labW1: insertReadySection(runId, moduleId, lecturer.id, {
      title: 'Stage 6d Lab W1',
      type: 'lab',
      orderIndex: 2,
      weekNumber: 1,
      sessionDate: '2026-01-07',
      publishStatus: 'published',
    }),
    lectureW2: insertReadySection(runId, moduleId, lecturer.id, {
      title: 'Stage 6d Lecture W2',
      type: 'lecture',
      orderIndex: 3,
      weekNumber: 2,
      sessionDate: '2026-01-13',
      publishStatus: 'published',
    }),
    hiddenW1: insertReadySection(runId, moduleId, lecturer.id, {
      title: 'Stage 6d Hidden W1',
      type: 'lecture',
      orderIndex: 4,
      weekNumber: 1,
      sessionDate: '2026-01-08',
      publishStatus: 'unpublished',
    }),
  };
}

function latestAttemptId(studentId: string): string {
  return runPsqlJson(`
SELECT to_json(id)::text
FROM quiz_attempts
WHERE student_id = ${sqlLiteral(studentId)}::uuid
ORDER BY created_at DESC
LIMIT 1;
`) as unknown as string;
}

function optionsForAttempt(attemptId: string): OptionRow[] {
  return runPsqlJson(`
SELECT coalesce(json_agg(json_build_object('questionId', q.id, 'optionId', o.id, 'isCorrect', o.is_correct)
  ORDER BY q.display_order, o.display_order), '[]'::json)::text
FROM quiz_questions q
JOIN answer_options o ON o.quiz_question_id = q.id
WHERE q.quiz_attempt_id = ${sqlLiteral(attemptId)}::uuid;
`) as unknown as OptionRow[];
}

function questionSourceSectionIds(attemptId: string): string[] {
  return runPsqlJson(`
SELECT coalesce(json_agg(DISTINCT source_section_id), '[]'::json)::text
FROM quiz_questions
WHERE quiz_attempt_id = ${sqlLiteral(attemptId)}::uuid
  AND source_section_id IS NOT NULL;
`) as unknown as string[];
}

function mistakeBankCount(studentId: string, moduleId: string): number {
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text
FROM mistake_records
WHERE student_id = ${sqlLiteral(studentId)}::uuid
  AND module_id = ${sqlLiteral(moduleId)}::uuid;
	`) as unknown as number;
}

function mistakeForSourceQuestion(questionId: string): MistakeState {
  return runPsqlJson(`
SELECT json_build_object(
  'id', id,
  'retakeCorrectCount', retake_correct_count,
  'showInRetakePrefix', show_in_retake_prefix
)::text
FROM mistake_records
WHERE source_question_id = ${sqlLiteral(questionId)}::uuid;
`) as unknown as MistakeState;
}

function retakePrefixQuestionId(attemptId: string, mistakeId: string): string {
  return runPsqlJson(`
SELECT to_json(id)::text
FROM quiz_questions
WHERE quiz_attempt_id = ${sqlLiteral(attemptId)}::uuid
  AND source_mistake_record_id = ${sqlLiteral(mistakeId)}::uuid
  AND source_type = 'mistake_review'
ORDER BY display_order ASC
LIMIT 1;
`) as unknown as string;
}

function prefixMistakeCount(attemptId: string): number {
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text
FROM quiz_questions
WHERE quiz_attempt_id = ${sqlLiteral(attemptId)}::uuid
  AND source_type = 'mistake_review';
`) as unknown as number;
}

function quizPoolLogCount(moduleId: string): number {
  return runPsqlJson(`
SELECT to_json(count(*)::int)::text
FROM ai_request_logs arl
JOIN section_question_pools sqp ON sqp.ai_request_log_id = arl.id
JOIN module_sections ms ON ms.id = sqp.module_section_id
WHERE arl.feature = 'quiz_pool'
  AND ms.course_module_id = ${sqlLiteral(moduleId)}::uuid;
	`) as unknown as number;
}

function forceFailedPoolForSection(runId: string, sectionId: string): string {
  const poolId = runPsqlJson(`
WITH existing_key AS (
  SELECT model, prompt_version
  FROM section_question_pools
  ORDER BY created_at DESC
  LIMIT 1
),
summary AS (
  SELECT id
  FROM generated_lecture_summaries
  WHERE module_section_id = ${sqlLiteral(sectionId)}::uuid
    AND summary_type = 'detailed_study'
  ORDER BY created_at DESC
  LIMIT 1
),
inserted AS (
  INSERT INTO section_question_pools (
    id, module_section_id, model, prompt_version, source_summary_id,
    source_summary_content_hash, status, failure_category, failure_message_sanitized
  )
  SELECT gen_random_uuid(), ${sqlLiteral(sectionId)}::uuid, existing_key.model, existing_key.prompt_version,
         summary.id, ${sqlLiteral(`forced-failure:${runId}:${sectionId}`)}, 'failed', 'provider_error',
         'forced browser-gate failure'
  FROM existing_key, summary
  RETURNING id
)
SELECT to_json(id)::text FROM inserted;
`) as unknown as string;
  recordManifestValue(runId, 'sectionQuestionPoolIds', poolId);
  return poolId;
}

function eventRowsForAttempt(attemptId: string): EventRow[] {
  return runPsqlJson(`
SELECT coalesce(json_agg(json_build_object('eventType', event_type, 'metadata', metadata) ORDER BY event_type), '[]'::json)::text
FROM student_activity_events
WHERE source_id = ${sqlLiteral(attemptId)}::uuid;
`) as unknown as EventRow[];
}

function recordPoolLogIds(runId: string, moduleId: string) {
  const rows = runPsqlRows(`
SELECT arl.id
FROM ai_request_logs arl
JOIN section_question_pools sqp ON sqp.ai_request_log_id = arl.id
JOIN module_sections ms ON ms.id = sqp.module_section_id
WHERE arl.feature = 'quiz_pool'
  AND ms.course_module_id = ${sqlLiteral(moduleId)}::uuid;
`);
  for (const id of rows) recordManifestValue(runId, 'aiRequestLogIds', id);
}

async function answerAll(page: Page, attemptId: string, wantCorrect: boolean, skipQuestionIds = new Set<string>()) {
  const options = optionsForAttempt(attemptId);
  const byQuestion = new Map<string, OptionRow[]>();
  for (const option of options) byQuestion.set(option.questionId, [...(byQuestion.get(option.questionId) ?? []), option]);
  for (const [, choices] of byQuestion) {
    if (skipQuestionIds.has(choices[0].questionId)) continue;
    const pick = choices.find((option) => option.isCorrect === wantCorrect) ?? choices[0];
    await page.getByTestId(`quiz-option-${pick.optionId}`).click();
  }
  await expect(page.getByTestId('quiz-feedback').first()).toBeVisible();
}

async function answerQuestion(page: Page, attemptId: string, questionId: string, wantCorrect: boolean) {
  const pick = optionsForAttempt(attemptId)
    .filter((option) => option.questionId === questionId)
    .find((option) => option.isCorrect === wantCorrect);
  if (!pick) throw new Error(`Attempt ${attemptId} has no ${wantCorrect ? 'correct' : 'wrong'} option for question ${questionId}`);
  await page.getByTestId(`quiz-option-${pick.optionId}`).click();
  await expect(page.getByTestId('quiz-feedback').first()).toHaveAttribute('data-correct', String(wantCorrect));
}

async function answerOneWrong(page: Page, attemptId: string): Promise<string> {
  const wrong = optionsForAttempt(attemptId).find((option) => !option.isCorrect);
  if (!wrong) throw new Error(`Attempt ${attemptId} has no wrong option`);
  await page.getByTestId(`quiz-option-${wrong.optionId}`).click();
  await expect(page.getByTestId('quiz-feedback').first()).toHaveAttribute('data-correct', 'false');
  return wrong.questionId;
}

function expectOnlyInScope(actual: string[], allowed: string[], forbidden: string[]) {
  expect(new Set(actual)).toEqual(new Set(allowed));
  for (const sectionId of forbidden) expect(actual).not.toContain(sectionId);
}

async function captureSurface(page: Page, name: string) {
  mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: resolve(SCREENSHOT_DIR, `${name}-desktop.png`), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: resolve(SCREENSHOT_DIR, `${name}-mobile.png`), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
}

async function startRecapFromModal(page: Page, moduleId: string, weeks = '1') {
  await page.goto(`/student/modules/${moduleId}`);
  await expect(page.getByTestId('quiz-mode-selector')).toBeVisible();
  await page.getByTestId('quiz-mode-recap').getByRole('button', { name: 'Choose scope' }).click();
  await expect(page.getByTestId('quiz-recap-scope-modal')).toBeVisible();
  await page.getByLabel('Weeks').fill(weeks);
  await page.getByRole('button', { name: 'Check' }).click();
  await expect(page.getByText(/Ready: [1-9]/)).toBeVisible();
  await page.getByRole('button', { name: 'Start recap' }).click();
}

test('6d quiz modes browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const seeded = await seedModule(runId);
  const adminCtx = await browser.newContext();
  const lecturerCtx = await browser.newContext();
  const studentACtx = await browser.newContext();
  const studentBCtx = await browser.newContext();
  const studentCCtx = await browser.newContext();
  let apiLecturer: APIRequestContext | null = null;
  let apiStudentA: APIRequestContext | null = null;
  let apiStudentB: APIRequestContext | null = null;
  let apiStudentC: APIRequestContext | null = null;
  try {
    await signInPage(adminCtx, ADMIN_EMAIL, '/admin');
    const lecturerPage = await signInPage(lecturerCtx, LECTURER_EMAIL, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    const studentPage = await signInPage(studentACtx, STUDENT_A_EMAIL, '/student');
    apiStudentA = await createApiContext(await getAccessToken(studentPage));

    // Lecturer AssessmentScope surface: create + list only.
    await lecturerPage.goto(`/lecturer/modules/${seeded.moduleId}`);
    await expect(lecturerPage.getByTestId('assessment-scope-panel')).toBeVisible();
    await lecturerPage.getByLabel('Name').fill('Stage 6d Midterm');
    await lecturerPage.getByLabel('Covered weeks').fill('1');
    await captureSurface(lecturerPage, 'assessment-scope-form');
    await lecturerPage.getByRole('button', { name: 'Create scope' }).click();
    await expect(lecturerPage.getByTestId('assessment-scope-table')).toContainText('Stage 6d Midterm');
    await captureSurface(lecturerPage, 'assessment-scope-list');

    // Student module mode selector + recap scope modal.
    await studentPage.goto(`/student/modules/${seeded.moduleId}`);
    await expect(studentPage.getByTestId('quiz-mode-selector')).toBeVisible();
    await captureSurface(studentPage, 'mode-selector');
    await studentPage.getByTestId('quiz-mode-recap').getByRole('button', { name: 'Choose scope' }).click();
    await expect(studentPage.getByTestId('quiz-recap-scope-modal')).toBeVisible();
    await studentPage.getByLabel('Weeks').fill('1');
    await studentPage.getByRole('button', { name: 'Check' }).click();
    await expect(studentPage.getByText(/Ready: 2/)).toBeVisible();
    await captureSurface(studentPage, 'recap-scope-modal');
    await studentPage.getByRole('button', { name: 'Start recap' }).click();
    await expect(studentPage.getByTestId('quiz-generating')).toBeVisible({ timeout: 10_000 });
    await captureSurface(studentPage, 'generating-state');
    await expect(studentPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 90_000 });
    await expect(studentPage.getByTestId('quiz-question-card')).toHaveCount(10);
    const recapAttempt = latestAttemptId(seeded.studentAId);
    recordManifestValue(runId, 'quizAttemptIds', recapAttempt);
    expectOnlyInScope(
      questionSourceSectionIds(recapAttempt),
      [seeded.lectureW1.id, seeded.labW1.id],
      [seeded.hiddenW1.id, seeded.lectureW2.id],
    );
    recordPoolLogIds(runId, seeded.moduleId);

    // Cross-mode bank coverage starts with a recap-origin mistake.
    const wrongQuestionId = await answerOneWrong(studentPage, recapAttempt);
    await answerAll(studentPage, recapAttempt, true, new Set([wrongQuestionId]));
    await studentPage.getByTestId('quiz-complete').click();
    await expect(studentPage.getByTestId('quiz-result')).toBeVisible({ timeout: 30_000 });
    await expect.poll(() => mistakeBankCount(seeded.studentAId, seeded.moduleId)).toBe(1);
    const mistake = mistakeForSourceQuestion(wrongQuestionId);
    expect(mistake.showInRetakePrefix).toBe(true);
    expect(mistake.retakeCorrectCount).toBe(0);

    // Full retake obligation: prefix appears, two correct source-quiz retakes clear it, and no pool log is
    // created by retake sampling.
    const logsBeforeRetakes = quizPoolLogCount(seeded.moduleId);
    await studentPage.getByTestId('quiz-start-over').click();
    await expect(studentPage.getByTestId('quiz-retake-prefix-banner')).toContainText('1 missed question', {
      timeout: 90_000,
    });
    await captureSurface(studentPage, 'retake-prefix-banner');
    const firstRetakeAttempt = latestAttemptId(seeded.studentAId);
    recordManifestValue(runId, 'quizAttemptIds', firstRetakeAttempt);
    expect(prefixMistakeCount(firstRetakeAttempt)).toBe(1);
    const firstPrefixQuestion = retakePrefixQuestionId(firstRetakeAttempt, mistake.id);
    await answerQuestion(studentPage, firstRetakeAttempt, firstPrefixQuestion, true);
    await answerAll(studentPage, firstRetakeAttempt, true, new Set([firstPrefixQuestion]));
    await studentPage.getByTestId('quiz-complete').click();
    await expect(studentPage.getByTestId('quiz-result')).toBeVisible({ timeout: 30_000 });
    expect(mistakeForSourceQuestion(wrongQuestionId)).toMatchObject({
      retakeCorrectCount: 1,
      showInRetakePrefix: true,
    });

    await studentPage.getByTestId('quiz-start-over').click();
    await expect(studentPage.getByTestId('quiz-retake-prefix-banner')).toContainText('1 missed question', {
      timeout: 90_000,
    });
    const secondRetakeAttempt = latestAttemptId(seeded.studentAId);
    recordManifestValue(runId, 'quizAttemptIds', secondRetakeAttempt);
    expect(prefixMistakeCount(secondRetakeAttempt)).toBe(1);
    const secondPrefixQuestion = retakePrefixQuestionId(secondRetakeAttempt, mistake.id);
    await answerQuestion(studentPage, secondRetakeAttempt, secondPrefixQuestion, true);
    await answerAll(studentPage, secondRetakeAttempt, true, new Set([secondPrefixQuestion]));
    await studentPage.getByTestId('quiz-complete').click();
    await expect(studentPage.getByTestId('quiz-result')).toBeVisible({ timeout: 30_000 });
    expect(mistakeForSourceQuestion(wrongQuestionId)).toMatchObject({
      retakeCorrectCount: 2,
      showInRetakePrefix: false,
    });

    await studentPage.getByTestId('quiz-start-over').click();
    await expect(studentPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 90_000 });
    await expect(studentPage.getByTestId('quiz-retake-prefix-banner')).toHaveCount(0);
    const noPrefixRetakeAttempt = latestAttemptId(seeded.studentAId);
    recordManifestValue(runId, 'quizAttemptIds', noPrefixRetakeAttempt);
    expect(prefixMistakeCount(noPrefixRetakeAttempt)).toBe(0);
    expect(quizPoolLogCount(seeded.moduleId)).toBe(logsBeforeRetakes);

    // Mistakes bank list, persistence after prefix drop, and start.
    await studentPage.goto(`/student/modules/${seeded.moduleId}`);
    await studentPage.getByTestId('quiz-mode-bank').getByRole('button', { name: 'Open bank' }).click();
    await expect(studentPage.getByTestId('quiz-mistakes-bank-modal')).toBeVisible();
    await expect(studentPage.getByTestId('quiz-mistakes-bank-count')).toContainText('1 saved mistake');
    await captureSurface(studentPage, 'mistakes-bank');
    await studentPage.getByRole('button', { name: 'Start mistakes bank' }).click();
    await expect(studentPage.getByTestId('quiz-question-card')).toHaveCount(1);
    const bankAttemptA = latestAttemptId(seeded.studentAId);
    recordManifestValue(runId, 'quizAttemptIds', bankAttemptA);
    await expect(studentPage.getByTestId('quiz-retake-prefix-banner')).toContainText('1 missed question');

    // Exam-prep modal + scope correctness.
    await studentPage.goto(`/student/modules/${seeded.moduleId}`);
    await studentPage.getByTestId('quiz-mode-exam-prep').getByRole('button', { name: 'Choose scope' }).click();
    await expect(studentPage.getByTestId('quiz-exam-scope-modal')).toBeVisible();
    await expect(studentPage.getByText('Stage 6d Midterm')).toBeVisible();
    await captureSurface(studentPage, 'exam-prep-scope-modal');
    await studentPage.getByTestId('quiz-exam-scope-modal').getByRole('button', { name: 'Start' }).click();
    await expect(studentPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 90_000 });
    const examAttempt = latestAttemptId(seeded.studentAId);
    recordManifestValue(runId, 'quizAttemptIds', examAttempt);
    expectOnlyInScope(
      questionSourceSectionIds(examAttempt),
      [seeded.lectureW1.id, seeded.labW1.id],
      [seeded.hiddenW1.id, seeded.lectureW2.id],
    );
    await answerAll(studentPage, examAttempt, true);
    await studentPage.getByTestId('quiz-complete').click();
    await expect(studentPage.getByTestId('quiz-result')).toBeVisible({ timeout: 30_000 });
    const examEvents = eventRowsForAttempt(examAttempt);
    expect(examEvents.map((event) => event.eventType).sort()).toEqual(['completed_quiz', 'perfect_quiz_score']);
    for (const event of examEvents) {
      expect(event.metadata).toMatchObject({
        quizMode: 'exam_prep',
        assessmentScopeId: expect.any(String),
        moduleSectionIds: expect.arrayContaining([seeded.lectureW1.id, seeded.labW1.id]),
      });
    }

    // Failure + retry proof: force a section pool into terminal failure, retry from the failed browser state,
    // then complete the recovered attempt.
    forceFailedPoolForSection(runId, seeded.lectureW2.id);
    await startRecapFromModal(studentPage, seeded.moduleId, '2');
    await expect(studentPage.getByTestId('quiz-retry-failed')).toBeVisible({ timeout: 90_000 });
    await studentPage.getByTestId('quiz-retry-failed').click();
    await expect(studentPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 120_000 });
    const retriedAttempt = latestAttemptId(seeded.studentAId);
    recordManifestValue(runId, 'quizAttemptIds', retriedAttempt);
    expectOnlyInScope(questionSourceSectionIds(retriedAttempt), [seeded.lectureW2.id], [seeded.lectureW1.id, seeded.labW1.id, seeded.hiddenW1.id]);
    await answerAll(studentPage, retriedAttempt, true);
    await studentPage.getByTestId('quiz-complete').click();
    await expect(studentPage.getByTestId('quiz-result')).toBeVisible({ timeout: 30_000 });

    // In-browser pool reuse: second assigned student starts same recap; ready questions, no new pool log.
    const logsBeforeB = quizPoolLogCount(seeded.moduleId);
    const studentBPage = await signInPage(studentBCtx, seeded.studentBEmail, '/student');
    apiStudentB = await createApiContext(await getAccessToken(studentBPage));
    await startRecapFromModal(studentBPage, seeded.moduleId);
    await expect(studentBPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 30_000 });
    const recapAttemptB = latestAttemptId(seeded.studentBId);
    recordManifestValue(runId, 'quizAttemptIds', recapAttemptB);
    expect(quizPoolLogCount(seeded.moduleId)).toBe(logsBeforeB);
    expectOnlyInScope(
      questionSourceSectionIds(recapAttemptB),
      [seeded.lectureW1.id, seeded.labW1.id],
      [seeded.hiddenW1.id, seeded.lectureW2.id],
    );

    // Authorization set: student B owns no student A mistakes; unassigned student sees 404; non-student 403.
    expect((await apiJson(apiStudentB, 'GET', `/student/modules/${seeded.moduleId}/mistakes-bank`)).body).toMatchObject({
      pagination: { total: 0 },
    });
    expect((await apiJson(apiStudentB, 'POST', `/student/modules/${seeded.moduleId}/mistakes-bank/start`)).status).toBe(409);
    expect((await apiJson(apiStudentB, 'GET', `/student/quiz/attempts/${bankAttemptA}`)).status).toBe(404);

    const studentCPage = await signInPage(studentCCtx, seeded.studentCEmail, '/student');
    apiStudentC = await createApiContext(await getAccessToken(studentCPage));
    expect((await apiJson(apiStudentC, 'GET', `/student/modules/${seeded.moduleId}/mistakes-bank`)).status).toBe(404);
    expect((await apiJson(apiStudentC, 'POST', `/student/modules/${seeded.moduleId}/recap-quiz/start`, { weeks: [1] })).status).toBe(404);

    expect((await apiJson(apiLecturer, 'GET', `/student/modules/${seeded.moduleId}/mistakes-bank`)).status).toBe(403);
    await expect(lecturerPage).toHaveURL(/\/lecturer/);
    expect((await apiJson(apiStudentA, 'POST', `/student/modules/${seeded.moduleId}/recap-quiz/availability`, { weeks: [1] })).body)
      .toMatchObject({ available: true, readySectionCount: 2 });
  } finally {
    await apiLecturer?.dispose();
    await apiStudentA?.dispose();
    await apiStudentB?.dispose();
    await apiStudentC?.dispose();
    await adminCtx.close();
    await lecturerCtx.close();
    await studentACtx.close();
    await studentBCtx.close();
    await studentCCtx.close();
  }
});
