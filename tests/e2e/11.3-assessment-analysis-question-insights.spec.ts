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
const UNASSIGNED_LECTURER_EMAIL = 'lecturer_unassigned_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const STUDENT_TWO_EMAIL = 'student2_e2e@example.test';

type ApiResponse<T = unknown> = { body: T; status: number; text: string };
type QuestionInsight = {
  questionKey: string;
  questionText: string;
  answerCount: number;
  correctCount: number;
  incorrectCount: number;
  correctRatePercent: string | null;
  smallCohort: boolean;
  smallCohortMessage: string | null;
  distractors: { optionText: string; selectedCount: number; selectedRatePercent: string | null }[];
};
type AssessmentInsights = {
  moduleId: string;
  questions: QuestionInsight[];
  mostMissedQuestions: QuestionInsight[];
  topicMastery: {
    available: boolean;
    unmappedAnswerCount: number;
    unmappedMessage: string | null;
    rows: {
      sourceSectionId: string;
      topicTitle: string;
      weekNumber: number | null;
      answerCount: number;
      correctCount: number;
      masteryPercent: string | null;
    }[];
  };
};
type SeededAssessmentGate = {
  moduleId: string;
  sectionId: string;
  studentIds: string[];
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
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const response = method === 'GET' ? await context.get(path) : await context.post(path, { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status(), text };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 11.3 gate');
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
DELETE FROM student_answers
WHERE quiz_attempt_id IN (
  SELECT qa.id
  FROM quiz_attempts qa
  JOIN quiz_definitions qd ON qd.id = qa.quiz_definition_id
  WHERE qd.module_id IN (
    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)}
  )
);

DELETE FROM answer_options
WHERE quiz_question_id IN (
  SELECT qq.id
  FROM quiz_questions qq
  JOIN quiz_attempts qa ON qa.id = qq.quiz_attempt_id
  JOIN quiz_definitions qd ON qd.id = qa.quiz_definition_id
  WHERE qd.module_id IN (
    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)}
  )
);

DELETE FROM quiz_questions
WHERE quiz_attempt_id IN (
  SELECT qa.id
  FROM quiz_attempts qa
  JOIN quiz_definitions qd ON qd.id = qa.quiz_definition_id
  WHERE qd.module_id IN (
    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)}
  )
);

DELETE FROM quiz_attempts
WHERE quiz_definition_id IN (
  SELECT id FROM quiz_definitions
  WHERE module_id IN (
    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)}
  )
);

DELETE FROM quiz_definitions
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)}
);

DELETE FROM module_sections
WHERE course_module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)}
);

DELETE FROM course_memberships
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)}
);

DELETE FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Assessment Gate ${runId}%`)};
`);
}

function seedAssessmentGate(runId: string): SeededAssessmentGate {
  cleanupPriorRunRows(runId);

  const lecturerId = getAppUserId(LECTURER_EMAIL);
  const studentIds = [getAppUserId(STUDENT_EMAIL), getAppUserId(STUDENT_TWO_EMAIL)];
  const moduleId = randomUUID();
  const sectionId = randomUUID();
  const definitionId = randomUUID();
  const membershipIds = [randomUUID(), randomUUID(), randomUUID()];
  const attemptSeeds = [
    { studentId: studentIds[0], attemptNumber: 1, q1: 'M phase', q2: 'Mitochondrion', q3: 'Alpha' },
    { studentId: studentIds[0], attemptNumber: 2, q1: 'M phase', q2: 'Mitochondrion', q3: 'Beta' },
    { studentId: studentIds[1], attemptNumber: 1, q1: 'G1 phase', q2: 'Ribosome', q3: null },
    { studentId: studentIds[1], attemptNumber: 2, q1: 'S phase', q2: 'Mitochondrion', q3: null },
  ];

  let sql = `
INSERT INTO course_modules (id, title, description, owner_id, timezone, starts_on, ends_on, is_active)
VALUES (
  ${sqlLiteral(moduleId)}::uuid,
  ${sqlLiteral(`Stage 11 Assessment Gate ${runId}`)},
  'Stage 11 assessment insight browser gate',
  ${sqlLiteral(lecturerId)}::uuid,
  'UTC',
  DATE '2026-01-12',
  DATE '2026-05-01',
  true
);

INSERT INTO course_memberships (id, user_id, module_id, role, status) VALUES
  (${sqlLiteral(membershipIds[0])}::uuid, ${sqlLiteral(lecturerId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'lecturer', 'active'),
  (${sqlLiteral(membershipIds[1])}::uuid, ${sqlLiteral(studentIds[0])}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active'),
  (${sqlLiteral(membershipIds[2])}::uuid, ${sqlLiteral(studentIds[1])}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active');

INSERT INTO module_sections (id, course_module_id, title, type, order_index, week_number, session_date, publish_status, status)
VALUES (
  ${sqlLiteral(sectionId)}::uuid,
  ${sqlLiteral(moduleId)}::uuid,
  'Cell Division',
  'lecture',
  1,
  2,
  DATE '2026-01-12',
  'published',
  'active'
);

INSERT INTO quiz_definitions (id, module_section_id, module_id, quiz_mode, source_scope)
VALUES (
  ${sqlLiteral(definitionId)}::uuid,
  ${sqlLiteral(sectionId)}::uuid,
  ${sqlLiteral(moduleId)}::uuid,
  'post_class',
  ${sqlLiteral(JSON.stringify({ sectionType: 'lecture', moduleSectionId: sectionId }))}::jsonb
);
`;

  for (const [index, seed] of attemptSeeds.entries()) {
    const attemptId = randomUUID();
    sql += `
INSERT INTO quiz_attempts (id, quiz_definition_id, student_id, attempt_number, status, completed_at)
VALUES (
  ${sqlLiteral(attemptId)}::uuid,
  ${sqlLiteral(definitionId)}::uuid,
  ${sqlLiteral(seed.studentId)}::uuid,
  ${seed.attemptNumber},
  'completed',
  ${sqlLiteral(`2026-06-20T08:0${index}:00Z`)}::timestamptz
);
`;
    sql += questionSql({
      attemptId,
      correctOption: 'S phase',
      displayOrder: 0,
      moduleId,
      options: ['S phase', 'M phase', 'G1 phase', 'Cytokinesis'],
      questionText: 'Which phase copies DNA?',
      sectionId,
      selectedOption: seed.q1,
    });
    sql += questionSql({
      attemptId,
      correctOption: 'Mitochondrion',
      displayOrder: 1,
      moduleId,
      options: ['Mitochondrion', 'Ribosome', 'Nucleus', 'Golgi apparatus'],
      questionText: 'Which organelle makes ATP?',
      sectionId,
      selectedOption: seed.q2,
    });
    if (seed.q3 !== null) {
      sql += questionSql({
        attemptId,
        correctOption: 'Alpha',
        displayOrder: 2,
        moduleId,
        options: ['Alpha', 'Beta', 'Gamma', 'Delta'],
        questionText: 'Which label belongs to the unproven tiny cohort?',
        sectionId: null,
        selectedOption: seed.q3,
      });
    }
  }

  runPsqlRows(sql);
  recordManifestValue(runId, 'moduleIds', moduleId);
  recordManifestValue(runId, 'sectionIds', sectionId);
  for (const membershipId of membershipIds) recordManifestValue(runId, 'membershipIds', membershipId);
  return { moduleId, sectionId, studentIds };
}

function questionSql(input: {
  attemptId: string;
  correctOption: string;
  displayOrder: number;
  moduleId: string;
  options: string[];
  questionText: string;
  sectionId: string | null;
  selectedOption: string;
}) {
  const questionId = randomUUID();
  const optionIds = input.options.map(() => randomUUID());
  const selectedIndex = input.options.indexOf(input.selectedOption);
  if (selectedIndex === -1) throw new Error(`Selected option missing: ${input.selectedOption}`);
  const optionValues = input.options
    .map((option, index) => `(
      ${sqlLiteral(optionIds[index])}::uuid,
      ${sqlLiteral(questionId)}::uuid,
      ${sqlLiteral(option)},
      ${index},
      ${option === input.correctOption ? 'true' : 'false'}
    )`)
    .join(',\n');
  return `
INSERT INTO quiz_questions (
  id,
  quiz_attempt_id,
  question_text,
  display_order,
  source_type,
  source_module_id,
  source_section_id
)
VALUES (
  ${sqlLiteral(questionId)}::uuid,
  ${sqlLiteral(input.attemptId)}::uuid,
  ${sqlLiteral(input.questionText)},
  ${input.displayOrder},
  'new_generated',
  ${sqlLiteral(input.moduleId)}::uuid,
  ${input.sectionId === null ? 'NULL' : `${sqlLiteral(input.sectionId)}::uuid`}
);

INSERT INTO answer_options (id, quiz_question_id, text, display_order, is_correct)
VALUES
${optionValues};

INSERT INTO student_answers (id, quiz_attempt_id, quiz_question_id, selected_answer_option_id, is_correct)
VALUES (
  gen_random_uuid(),
  ${sqlLiteral(input.attemptId)}::uuid,
  ${sqlLiteral(questionId)}::uuid,
  ${sqlLiteral(optionIds[selectedIndex])}::uuid,
  ${input.selectedOption === input.correctOption ? 'true' : 'false'}
);
`;
}

function questionByText(body: AssessmentInsights, text: string): QuestionInsight {
  const question = body.questions.find((candidate) => candidate.questionText === text);
  if (!question) throw new Error(`Missing question insight: ${text}`);
  return question;
}

test.describe('Stage 11.3 assessment analysis + question insights', () => {
  test('shows exact aggregate question insights and enforces aggregate-only authz', async ({ browser }) => {
    const runId = requireRunId();
    const seeded = seedAssessmentGate(runId);

    const lecturerContext = await browser.newContext();
    const lecturerPage = await signInPage(lecturerContext, LECTURER_EMAIL, '/lecturer');
    const lecturerToken = await getAccessToken(lecturerPage);
    const lecturerApi = await createApiContext(lecturerToken);

    const apiResult = await apiJson<AssessmentInsights>(
      lecturerApi,
      'GET',
      `/lecturer/modules/${seeded.moduleId}/analytics/assessment-insights`,
    );
    expect(apiResult.status).toBe(200);
    const body = apiResult.body;
    expect(body.moduleId).toBe(seeded.moduleId);
    for (const studentId of seeded.studentIds) expect(apiResult.text).not.toContain(studentId);
    expect(apiResult.text).not.toContain(STUDENT_EMAIL);
    expect(apiResult.text).not.toContain(STUDENT_TWO_EMAIL);

    const dna = questionByText(body, 'Which phase copies DNA?');
    expect(dna.answerCount).toBe(4);
    expect(dna.correctCount).toBe(1);
    expect(dna.incorrectCount).toBe(3);
    expect(dna.correctRatePercent).toBe('25.00');
    expect(dna.distractors.map((d) => [d.optionText, d.selectedCount, d.selectedRatePercent])).toEqual([
      ['M phase', 2, '50.00'],
      ['G1 phase', 1, '25.00'],
    ]);

    const atp = questionByText(body, 'Which organelle makes ATP?');
    expect(atp.correctRatePercent).toBe('75.00');
    expect(body.mostMissedQuestions.map((question) => question.questionText)).toEqual([
      'Which phase copies DNA?',
      'Which organelle makes ATP?',
    ]);

    const tiny = questionByText(body, 'Which label belongs to the unproven tiny cohort?');
    expect(tiny.answerCount).toBe(2);
    expect(tiny.correctRatePercent).toBeNull();
    expect(tiny.smallCohortMessage).toBe('Not enough submissions for an aggregate insight');
    expect(body.topicMastery.rows).toHaveLength(1);
    expect(body.topicMastery.rows[0]).toMatchObject({
      sourceSectionId: seeded.sectionId,
      topicTitle: 'Cell Division',
      weekNumber: 2,
      answerCount: 8,
      correctCount: 4,
      masteryPercent: '50.00',
    });
    expect(body.topicMastery.unmappedAnswerCount).toBe(2);
    expect(body.topicMastery.unmappedMessage).toBe(
      'Topic mastery unavailable for 2 submissions without question provenance.',
    );

    const unassignedContext = await browser.newContext();
    const unassignedPage = await signInPage(unassignedContext, UNASSIGNED_LECTURER_EMAIL, '/lecturer');
    const unassignedApi = await createApiContext(await getAccessToken(unassignedPage));
    expect(
      (
        await apiJson(
          unassignedApi,
          'GET',
          `/lecturer/modules/${seeded.moduleId}/analytics/assessment-insights`,
        )
      ).status,
    ).toBe(403);

    const studentContext = await browser.newContext();
    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    const studentApi = await createApiContext(await getAccessToken(studentPage));
    expect(
      (
        await apiJson(
          studentApi,
          'GET',
          `/lecturer/modules/${seeded.moduleId}/analytics/assessment-insights`,
        )
      ).status,
    ).toBe(403);

    await lecturerPage.goto(`/lecturer/modules/${seeded.moduleId}`);
    await expect(lecturerPage.getByTestId('lecturer-assessment-insights')).toBeVisible();
    await expect(lecturerPage.getByTestId('assessment-question-count')).toHaveText('Questions: 3');
    await expect(lecturerPage.getByTestId(`assessment-question-rate-${dna.questionKey}`)).toHaveText('25.00%');
    await expect(lecturerPage.getByTestId(`assessment-question-rate-${atp.questionKey}`)).toHaveText('75.00%');
    await expect(lecturerPage.getByTestId(`assessment-question-rate-${tiny.questionKey}`)).toHaveText(
      'Not enough submissions for an aggregate insight',
    );
    await expect(lecturerPage.getByTestId(`most-missed-${dna.questionKey}`)).toContainText(
      'Which phase copies DNA? · 3 missed · 25.00% correct',
    );
    await expect(lecturerPage.getByTestId(`most-missed-${atp.questionKey}`)).toContainText(
      'Which organelle makes ATP? · 1 missed · 75.00% correct',
    );
    const dnaDistractors = lecturerPage.getByTestId(new RegExp(`assessment-distractor-${dna.questionKey}-`));
    await expect(dnaDistractors.nth(0)).toHaveText('M phase: 2 (50.00%)');
    await expect(dnaDistractors.nth(1)).toHaveText('G1 phase: 1 (25.00%)');
    await expect(lecturerPage.getByTestId('topic-mastery-unavailable')).toHaveText(
      'Topic mastery unavailable for 2 submissions without question provenance.',
    );
    await expect(lecturerPage.getByTestId(`topic-mastery-percent-${seeded.sectionId}`)).toHaveText('50.00%');
    const assessmentPanel = lecturerPage.getByTestId('lecturer-assessment-insights');
    await expect(assessmentPanel.getByText(STUDENT_EMAIL)).toHaveCount(0);
    await expect(assessmentPanel.getByText(STUDENT_TWO_EMAIL)).toHaveCount(0);
  });
});
