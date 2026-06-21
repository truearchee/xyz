import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  getAppUserByEmail,
  getMembershipsForModule,
  getSectionsForModule,
  runPsqlJson,
  runPsqlRows,
  sqlLiteral,
} from './fixtures/db.mjs';

/**
 * Stage 8.6c browser gate — Time-management mode. The mode is conversational only: no saved plan,
 * calendar, .ics, or Stage 11 planner artifact. It grounds on structured deadline/progress refs for the
 * current student only, not retrieval. This gate seeds another student's sentinel deadline and proves it
 * never reaches the UI or context snapshot.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const STUDENT2_EMAIL = 'student2_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const ANSWER_MARKER = 'concise study-assistant answer';
const OTHER_STUDENT_SENTINEL = 'OTHER_STUDENT_DEADLINE_SENTINEL_86C';

test.setTimeout(240_000);
test.use({ actionTimeout: 20_000, navigationTimeout: 45_000 });

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };

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
  const response = method === 'GET' ? await ctx.get(path) : await ctx.post(path, body === undefined ? undefined : { data: body });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the Stage 8.6c gate');
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
function recordMany(runId: string, field: string, values: string[]) {
  for (const value of values) recordManifestValue(runId, field, value);
}

function conversationKind(conversationId: string): string | null {
  return runPsqlJson(`SELECT to_json(conversation_kind)::text FROM assistant_conversations WHERE id = ${sqlLiteral(conversationId)}::uuid;`) as unknown as string | null;
}
function timeManagementConversationCount(studentId: string): number {
  return runPsqlJson(
    `SELECT to_json(count(*)::int)::text
     FROM assistant_conversations
     WHERE student_id = ${sqlLiteral(studentId)}::uuid
       AND conversation_kind = 'time_management'
       AND deleted_at IS NULL;`,
  ) as unknown as number;
}
function latestTimeManagementSnapshot(conversationId: string): Record<string, unknown> {
  return runPsqlJson(
    `SELECT context_snapshot::text
     FROM assistant_messages
     WHERE conversation_id = ${sqlLiteral(conversationId)}::uuid
       AND role = 'assistant' AND status = 'completed'
     ORDER BY generated_at DESC NULLS LAST, created_at DESC, id DESC LIMIT 1;`,
  ) as unknown as Record<string, unknown>;
}
function completedAssistantCount(conversationId: string): number {
  return runPsqlJson(
    `SELECT to_json(count(*)::int)::text
     FROM assistant_messages WHERE conversation_id = ${sqlLiteral(conversationId)}::uuid
       AND role = 'assistant' AND status = 'completed';`,
  ) as unknown as number;
}
function completedGroundings(conversationId: string): string[] {
  return runPsqlJson(
    `SELECT coalesce(json_agg(grounding_status ORDER BY generated_at, created_at, id), '[]')::text
     FROM assistant_messages WHERE conversation_id = ${sqlLiteral(conversationId)}::uuid
       AND role = 'assistant' AND status = 'completed';`,
  ) as unknown as string[];
}
function assistantLogFeatures(conversationId: string): string[] {
  return runPsqlJson(
    `SELECT coalesce(json_agg(DISTINCT l.feature), '[]')::text
     FROM assistant_messages m JOIN ai_request_logs l ON l.id = m.ai_request_log_id
     WHERE m.conversation_id = ${sqlLiteral(conversationId)}::uuid;`,
  ) as unknown as string[];
}
function tableExists(table: string): boolean {
  return runPsqlJson(`SELECT to_json(to_regclass('public.${table}') IS NOT NULL)::text;`) as unknown as boolean;
}
function countRows(table: string): number {
  if (!/^[a-z_]+$/.test(table)) throw new Error(`bad table name: ${table}`);
  if (!tableExists(table)) return 0;
  return runPsqlJson(`SELECT to_json(count(*)::int)::text FROM ${table};`) as unknown as number;
}
function calendarAssetCount(): number {
  return runPsqlJson(
    `SELECT to_json(count(*)::int)::text FROM section_assets
     WHERE lower(file_name) LIKE '%.ics' OR lower(mime_type) IN ('text/calendar', 'application/ics');`,
  ) as unknown as number;
}
function assertNoAssistantPlannerImports() {
  let output = '';
  try {
    output = execFileSync(
      'rg',
      [
        '-n',
        'from app\\.domains\\.(analytics|planner)|from app\\.platform\\.query\\.(analytics|planner)|import .*WorkloadPlan|import .*InternalCalendarEvent',
        'backend/app/domains/assistant',
        'backend/app/platform/query/time_management_read.py',
      ],
      { encoding: 'utf8' },
    );
  } catch (error) {
    const status = typeof error === 'object' && error && 'status' in error ? (error as { status?: number }).status : null;
    if (status !== 1) throw error;
  }
  expect(output.trim()).toBe('');
}

async function createModule(runId: string, adminContext: APIRequestContext, title: string, studentEmail: string) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(studentEmail);
  if (!owner?.id || !student?.id) throw new Error('Standing lecturer/student E2E users are required');
  const create = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title,
    description: `8.6c gate ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    schedule: {
      courseStartDate: '2026-06-15',
      courseEndDate: '2026-07-31',
      weekStartDay: 'monday',
      sessionPattern: [{ weekday: 'monday', sectionType: 'lecture' }],
      quizDay: 'friday',
    },
  });
  expect(create.status).toBe(201);
  const moduleId = create.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);
  const assign = await apiJson(adminContext, 'POST', `/admin/modules/${moduleId}/members`, { userId: student.id, role: 'student' });
  expect(assign.status).toBe(201);
  recordMany(runId, 'membershipIds', getMembershipsForModule(moduleId).map((m: { id: string }) => m.id));
  const sections = getSectionsForModule(moduleId) as SectionRow[];
  recordMany(runId, 'sectionIds', sections.map((s) => s.id));
  return { moduleId, section: sections.filter((s) => s.type === 'lecture')[0], studentId: student.id as string };
}

function seedTimeManagementRows(moduleId: string, sectionId: string, studentId: string, sectionTitle: string) {
  runPsqlRows(`
WITH scheme AS (
  INSERT INTO course_grade_schemes (id, module_id, name, on_track_max, at_risk_max, benchmark_min_cohort)
  VALUES (gen_random_uuid(), ${sqlLiteral(moduleId)}::uuid, 'E2E', 70, 85, 5)
  RETURNING id
),
component AS (
  INSERT INTO grade_components (id, scheme_id, name, weight, sort_order, component_kind, module_section_id)
  SELECT gen_random_uuid(), scheme.id, 'Coursework', 0.5, 1, 'assignment', ${sqlLiteral(sectionId)}::uuid
  FROM scheme
  RETURNING id, scheme_id
),
boundaries AS (
  INSERT INTO grade_boundaries (id, scheme_id, letter_grade, lower_bound, sort_order)
  SELECT gen_random_uuid(), component.scheme_id, 'A', 80, 1 FROM component
  UNION ALL
  SELECT gen_random_uuid(), component.scheme_id, 'B', 70, 2 FROM component
  UNION ALL
  SELECT gen_random_uuid(), component.scheme_id, 'C', 60, 3 FROM component
),
grade_record AS (
  INSERT INTO student_grade_records (id, student_id, grade_component_id, percentage_score, source)
  SELECT gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, component.id, 62, 'e2e' FROM component
)
INSERT INTO student_progress_snapshots (id, student_id, module_id, week_number, snapshot_date, standing_points, source_metrics)
VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 1, current_date, 62, '{"source":"8.6c"}'::jsonb);

INSERT INTO student_target_grade_goals (id, student_id, module_id, target_letter_grade, status)
VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'B', 'active');

UPDATE module_sections
SET title = ${sqlLiteral(sectionTitle)},
    publish_status = 'published',
    status = 'active',
    week_number = 1,
    session_date = current_date + interval '2 days',
    due_at = now() + interval '3 days'
WHERE id = ${sqlLiteral(sectionId)}::uuid;

INSERT INTO student_topic_mastery_snapshots (id, student_id, module_id, module_section_id, mastery_percentage, status_label, source_metrics)
VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, ${sqlLiteral(sectionId)}::uuid, 48, 'needs_attention', '{"source":"8.6c"}'::jsonb);
`);
}

function seedOtherStudentSentinel(moduleId: string, sectionId: string) {
  runPsqlRows(`
UPDATE module_sections
SET title = ${sqlLiteral(OTHER_STUDENT_SENTINEL)},
    publish_status = 'published',
    status = 'active',
    week_number = 1,
    session_date = current_date + interval '1 day',
    due_at = now() + interval '1 day'
WHERE id = ${sqlLiteral(sectionId)}::uuid;
`);
}

async function ask(page: Page, text: string, expectedCompleted: number) {
  await page.getByTestId('workspace-input').fill(text);
  await page.getByTestId('workspace-send').click();
  await expect(page.locator('[data-testid="workspace-message-assistant"][data-state="completed"]')).toHaveCount(expectedCompleted, { timeout: 60_000 });
}

test('8.6c time-management browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminCtx = await browser.newContext();
  const studentCtx = await browser.newContext();

  try {
    const adminPage = await signInPage(adminCtx, ADMIN_EMAIL, '/admin');
    const apiAdmin = await createApiContext(await getAccessToken(adminPage));
    const main = await createModule(runId, apiAdmin, `Stage 8.6c Time ${runId}-${Date.now()}`, STUDENT_EMAIL);
    const other = await createModule(runId, apiAdmin, `Stage 8.6c Other ${runId}-${Date.now()}`, STUDENT2_EMAIL);
    seedTimeManagementRows(main.moduleId, main.section.id, main.studentId, `Stage 8.6c Deadline ${runId}`);
    seedOtherStudentSentinel(other.moduleId, other.section.id);
    const artifactCountsBefore = {
      workloadPlans: countRows('workload_plans'),
      workloadPlanItems: countRows('workload_plan_items'),
      internalCalendarEvents: countRows('internal_calendar_events'),
      calendarAssets: calendarAssetCount(),
    };

    const page = await signInPage(studentCtx, STUDENT_EMAIL, '/student');

    await page.goto('/student/assistant');
    await expect(page.getByTestId('assistant-workspace')).toBeVisible();
    await page.getByTestId('assistant-new-time-management').click();
    await expect(page).toHaveURL(/\/student\/assistant\/[0-9a-f-]+$/);
    const conversationId = page.url().split('/').pop() as string;
    await expect(page.getByTestId('assistant-mode-label')).toHaveText('Time management');
    await expect(page.getByTestId('assistant-context-pill')).toContainText('Your deadlines and progress');
    const completedBefore = completedAssistantCount(conversationId);
    if (completedBefore === 0) {
      await expect(page.getByTestId('workspace-time-management-starters')).toBeVisible();
    }
    await expect(page.locator('select')).toHaveCount(0);

    await ask(page, 'What should I prioritize today?', completedBefore + 1);
    const reply = page.locator('[data-testid="workspace-message-assistant"][data-state="completed"]').last();
    await expect(reply).toContainText(ANSWER_MARKER);
    await expect(reply.getByTestId('workspace-basis-text')).toContainText('deadlines and progress');
    await expect(page.getByText(OTHER_STUDENT_SENTINEL)).toHaveCount(0);

    expect(conversationKind(conversationId)).toBe('time_management');
    expect(timeManagementConversationCount(main.studentId)).toBe(1);
    expect(completedGroundings(conversationId).at(-1)).toBe('lecture_grounded');
    expect(assistantLogFeatures(conversationId)).toEqual(['assistant']);
    const snapshot = latestTimeManagementSnapshot(conversationId);
    expect(snapshot.mode).toBe('time_management');
    expect(snapshot.retrievalScope).toBe('structured_schedule_progress');
    expect(JSON.stringify(snapshot)).toContain(main.section.id);
    expect(JSON.stringify(snapshot)).not.toContain(other.section.id);
    expect(JSON.stringify(snapshot)).not.toContain(OTHER_STUDENT_SENTINEL);

    expect(countRows('workload_plans')).toBe(artifactCountsBefore.workloadPlans);
    expect(countRows('workload_plan_items')).toBe(artifactCountsBefore.workloadPlanItems);
    expect(countRows('internal_calendar_events')).toBe(artifactCountsBefore.internalCalendarEvents);
    expect(calendarAssetCount()).toBe(artifactCountsBefore.calendarAssets);
    assertNoAssistantPlannerImports();
  } finally {
    await adminCtx.close();
    await studentCtx.close();
  }
});
