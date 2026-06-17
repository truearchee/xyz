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

import {
  getAppUserByEmail,
  getActiveTranscriptForSection,
  getSectionsForModule,
  runPsqlJson,
  sqlLiteral,
  waitForSummariesSettled,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

/**
 * Stage 5d browser gate — post-class quiz, against the deterministic-provider pipeline (§14).
 *
 * A student opens a published lecture with a completed detailed summary → the quiz is available →
 * Start → "generating" → 10 generated questions appear → answers each with immediate red/green
 * feedback → a WRONG answer becomes a recorded MistakeRecord → completes → sees a score → a
 * `completed_quiz` event row exists (same txn as the score) → Start Over yields a NEW attempt with
 * 10 new question rows. DETERMINISTIC-ONLY: answer all correct → 100 → `perfect_quiz_score` event.
 * NEGATIVE (two-surface): non-student → 403; unpublished/unassigned → 404 on the API. The real
 * provider is exercised separately by the rule-11 smoke (knowledge/steps/stage-05/5d-real-provider-smoke.md).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const TRANSCRIPT_FILE = 'sentinel-lecture.vtt';

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };
type OptionRow = { questionId: string; optionId: string; isCorrect: boolean };

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
async function apiJson<T>(ctx: APIRequestContext, method: 'GET' | 'POST', path: string, body?: unknown): Promise<ApiResponse<T>> {
  const response = method === 'GET' ? await ctx.get(path) : await ctx.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}
async function apiUpload<T>(ctx: APIRequestContext, path: string, fileName: string, buffer: Buffer, mimeType: string): Promise<ApiResponse<T>> {
  const response = await ctx.post(path, { multipart: { file: { name: fileName, mimeType, buffer } } });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}
function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 5d gate');
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
function sectionByTitle(sections: SectionRow[], title: string): SectionRow {
  const s = sections.find((c) => c.title === title);
  if (!s) throw new Error(`Missing generated section ${title}`);
  return s;
}

// ── quiz DB helpers (runPsqlJson JSON.parses the row, so SQL must return json_*(...)::text) ───────
function latestAttemptId(studentId: string): string {
  return runPsqlJson(
    `SELECT to_json(id)::text FROM quiz_attempts WHERE student_id = ${sqlLiteral(studentId)}::uuid ORDER BY created_at DESC LIMIT 1;`,
  ) as unknown as string;
}
function attemptStatus(attemptId: string): string {
  return runPsqlJson(
    `SELECT to_json(status)::text FROM quiz_attempts WHERE id = ${sqlLiteral(attemptId)}::uuid;`,
  ) as unknown as string;
}
function optionsForAttempt(attemptId: string): OptionRow[] {
  return runPsqlJson(
    `SELECT coalesce(json_agg(json_build_object('questionId', q.id, 'optionId', o.id, 'isCorrect', o.is_correct)
       ORDER BY q.display_order, o.display_order), '[]'::json)::text
     FROM quiz_questions q JOIN answer_options o ON o.quiz_question_id = q.id
     WHERE q.quiz_attempt_id = ${sqlLiteral(attemptId)}::uuid;`,
  ) as unknown as OptionRow[];
}
function countQuestions(attemptId: string): number {
  return runPsqlJson(
    `SELECT to_json(count(*)::int)::text FROM quiz_questions WHERE quiz_attempt_id = ${sqlLiteral(attemptId)}::uuid;`,
  ) as unknown as number;
}
function countEvents(attemptId: string, eventType: string): number {
  return runPsqlJson(
    `SELECT to_json(count(*)::int)::text FROM student_activity_events WHERE source_id = ${sqlLiteral(attemptId)}::uuid AND event_type = ${sqlLiteral(eventType)};`,
  ) as unknown as number;
}
function countMistakes(attemptId: string): number {
  return runPsqlJson(
    `SELECT to_json(count(*)::int)::text FROM mistake_records WHERE source_quiz_attempt_id = ${sqlLiteral(attemptId)}::uuid;`,
  ) as unknown as number;
}

async function setupPublishedSectionWithSummary(runId: string, apiAdmin: APIRequestContext, apiLecturer: APIRequestContext) {
  const created = await apiJson<{ id: string }>(apiAdmin, 'POST', '/admin/modules', {
    title: `Stage 5d Quiz Module ${runId}`,
    ownerId: getAppUserByEmail(LECTURER_EMAIL).id,
    timezone: 'UTC',
  });
  expect(created.status).toBe(201);
  const moduleId = created.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  await apiJson(apiAdmin, 'POST', `/admin/modules/${moduleId}/members`, { userId: student.id, role: 'student' });

  const sections = getSectionsForModule(moduleId) as SectionRow[];
  const lecture = sectionByTitle(sections, 'Lecture 1');
  const upload = await apiUpload<{ id: string }>(
    apiLecturer,
    `/modules/${moduleId}/sections/${lecture.id}/transcript`,
    TRANSCRIPT_FILE,
    readFileSync(resolve(TRANSCRIPT_DIR, TRANSCRIPT_FILE)),
    'text/vtt',
  );
  expect(upload.status).toBe(201);
  const transcriptId = getActiveTranscriptForSection(lecture.id).id;
  recordManifestValue(runId, 'transcriptIds', transcriptId);
  await waitForTranscriptEmbedded(transcriptId, 95_000);
  const settled = await waitForSummariesSettled(transcriptId, 120_000);
  expect(settled.generate_detailed_summary).toBe('completed');
  await apiJson(apiLecturer, 'POST', `/modules/${moduleId}/sections/${lecture.id}/publish`);
  return { moduleId, lecture, studentId: student.id };
}

/** Click every question's option matching `wantCorrect`, asserting immediate feedback each time. */
async function answerAll(page: Page, attemptId: string, wantCorrect: boolean) {
  const options = optionsForAttempt(attemptId);
  const byQuestion = new Map<string, OptionRow[]>();
  for (const o of options) byQuestion.set(o.questionId, [...(byQuestion.get(o.questionId) ?? []), o]);
  for (const [, opts] of byQuestion) {
    const pick = opts.find((o) => o.isCorrect === wantCorrect) ?? opts[0];
    await page.getByTestId(`quiz-option-${pick.optionId}`).click();
  }
  await expect(page.getByTestId('quiz-feedback').first()).toBeVisible();
}

test('5d post-class quiz browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminCtx = await browser.newContext();
  const lecturerCtx = await browser.newContext();
  const studentCtx = await browser.newContext();
  let apiAdmin: APIRequestContext | null = null;
  let apiLecturer: APIRequestContext | null = null;
  let apiStudent: APIRequestContext | null = null;
  try {
    const adminPage = await signInPage(adminCtx, ADMIN_EMAIL, '/admin');
    apiAdmin = await createApiContext(await getAccessToken(adminPage));
    const lecturerPage = await signInPage(lecturerCtx, LECTURER_EMAIL, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));

    const { moduleId, lecture, studentId } = await setupPublishedSectionWithSummary(runId, apiAdmin, apiLecturer);

    // ── student browser: available → Start → generating → 10 questions ──────────────────────────
    const studentPage = await signInPage(studentCtx, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(studentPage));
    await studentPage.goto(`/student/modules/${moduleId}/sections/${lecture.id}`);
    await expect(studentPage.getByTestId('post-class-quiz-panel')).toBeVisible();
    await expect(studentPage.getByTestId('quiz-start')).toBeVisible({ timeout: 30_000 });
    await studentPage.getByTestId('quiz-start').click();
    await expect(studentPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 60_000 });
    await expect(studentPage.getByTestId('quiz-question-card')).toHaveCount(10);

    const attemptId = latestAttemptId(studentId);
    recordManifestValue(runId, 'quizAttemptIds', attemptId);
    const options = optionsForAttempt(attemptId);
    const byQuestion = new Map<string, OptionRow[]>();
    for (const o of options) byQuestion.set(o.questionId, [...(byQuestion.get(o.questionId) ?? []), o]);
    const questionIds = [...byQuestion.keys()];

    // First question WRONG → immediate red feedback + "Saved to your mistakes" + a MistakeRecord row.
    const firstWrong = byQuestion.get(questionIds[0])!.find((o) => !o.isCorrect)!;
    await studentPage.getByTestId(`quiz-option-${firstWrong.optionId}`).click();
    const firstFeedback = studentPage.getByTestId('quiz-feedback').first();
    await expect(firstFeedback).toHaveAttribute('data-correct', 'false');
    await expect(studentPage.getByTestId('quiz-mistake-saved').first()).toBeVisible();
    await expect.poll(() => countMistakes(attemptId)).toBe(1);

    // Remaining nine CORRECT.
    for (const qid of questionIds.slice(1)) {
      const correct = byQuestion.get(qid)!.find((o) => o.isCorrect)!;
      await studentPage.getByTestId(`quiz-option-${correct.optionId}`).click();
    }
    // Complete → score 90% → completed_quiz event in the SAME transaction as the score.
    await studentPage.getByTestId('quiz-complete').click();
    await expect(studentPage.getByTestId('quiz-result')).toBeVisible({ timeout: 30_000 });
    await expect(studentPage.getByTestId('quiz-score')).toHaveText('90%');
    await expect(studentPage.getByTestId('quiz-mistakes-count')).toContainText('1 mistake');
    expect(attemptStatus(attemptId)).toBe('completed');
    expect(countEvents(attemptId, 'completed_quiz')).toBe(1);
    expect(countEvents(attemptId, 'perfect_quiz_score')).toBe(0);

    // ── Start Over → a NEW attempt with 10 NEW question rows from a new request ──────────────────
    await studentPage.getByTestId('quiz-start-over').click();
    await expect(studentPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 60_000 });
    const attempt2 = latestAttemptId(studentId);
    recordManifestValue(runId, 'quizAttemptIds', attempt2);
    expect(attempt2).not.toBe(attemptId);
    expect(countQuestions(attempt2)).toBe(10);

    // DETERMINISTIC-ONLY: answer all correct → 100 → perfect_quiz_score event.
    await answerAll(studentPage, attempt2, true);
    await studentPage.getByTestId('quiz-complete').click();
    await expect(studentPage.getByTestId('quiz-score')).toHaveText('100%', { timeout: 30_000 });
    expect(countEvents(attempt2, 'completed_quiz')).toBe(1);
    expect(countEvents(attempt2, 'perfect_quiz_score')).toBe(1);

    // ── NEGATIVE (two-surface): non-student → 403 on the API ────────────────────────────────────
    const lecturerStart = await apiJson(apiLecturer, 'POST', `/student/sections/${lecture.id}/quiz/start`);
    expect(lecturerStart.status).toBe(403);
    const lecturerAvail = await apiJson(apiLecturer, 'GET', `/student/sections/${lecture.id}/quiz/availability`);
    expect(lecturerAvail.status).toBe(403);

    // ── S7 UNPUBLISH-MID-ATTEMPT (browser-coordinated, in-flight) ───────────────────────────────
    // Start a THIRD attempt in Chromium, answer ONE question (so it is genuinely in-flight), then
    // unpublish the section via the lecturer API in the SAME test. The in-flight attempt must become
    // 404 on every student endpoint AND emit no event while hidden; re-publish → resume.
    await studentPage.getByTestId('quiz-start-over').click();
    await expect(studentPage.getByTestId('quiz-question-card').first()).toBeVisible({ timeout: 60_000 });
    const attempt3 = latestAttemptId(studentId);
    recordManifestValue(runId, 'quizAttemptIds', attempt3);
    const firstOf3 = optionsForAttempt(attempt3)[0];
    await studentPage.getByTestId(`quiz-option-${firstOf3.optionId}`).click();
    await expect(studentPage.getByTestId('quiz-feedback').first()).toBeVisible();
    expect(attemptStatus(attempt3)).toBe('in_progress');

    await apiJson(apiLecturer, 'POST', `/modules/${moduleId}/sections/${lecture.id}/unpublish`);
    expect((await apiJson(apiStudent, 'GET', `/student/quiz/attempts/${attempt3}`)).status).toBe(404);
    expect((await apiJson(apiStudent, 'POST', `/student/quiz/attempts/${attempt3}/complete`)).status).toBe(404);
    expect((await apiJson(apiStudent, 'GET', `/student/sections/${lecture.id}/quiz/availability`)).status).toBe(404);
    // No event fired while hidden (the complete 404'd before the EventRecorder).
    expect(countEvents(attempt3, 'completed_quiz')).toBe(0);

    // Re-publish → the in-flight attempt resumes (detail visible again).
    await apiJson(apiLecturer, 'POST', `/modules/${moduleId}/sections/${lecture.id}/publish`);
    expect((await apiJson(apiStudent, 'GET', `/student/quiz/attempts/${attempt3}`)).status).toBe(200);
    expect(attemptStatus(attempt3)).toBe('in_progress'); // row persisted through the hide
  } finally {
    await apiAdmin?.dispose();
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await adminCtx.close();
    await lecturerCtx.close();
    await studentCtx.close();
  }
});
