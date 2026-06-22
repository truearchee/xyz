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

import { runPsqlRows, sqlLiteral } from './fixtures/db.mjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const STUDENT_TWO_EMAIL = 'student2_e2e@example.test';
const RUNS_DIR = resolve('tests/e2e/.runs');

type CalendarEvent = Record<string, string>;
type SeededCalendarGate = {
  moduleId: string;
  planId: string;
  itemId: string;
  deadlineSectionId: string;
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

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the 11.5 gate');
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
  const rows = runPsqlRows(`
SELECT id::text
FROM app_users
WHERE email = ${sqlLiteral(email)}
LIMIT 1;
`);
  const id = rows.at(-1);
  if (!id) throw new Error(`Missing E2E app user ${email}; run tests/e2e/fixtures/seed.mjs first`);
  return id;
}

function cleanupPriorRunRows(runId: string) {
  runPsqlRows(`
DELETE FROM workload_plan_items
WHERE workload_plan_id IN (
  SELECT id FROM workload_plans
  WHERE module_id IN (
    SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Calendar Gate ${runId}%`)}
  )
);

DELETE FROM workload_plans
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Calendar Gate ${runId}%`)}
);

DELETE FROM module_sections
WHERE course_module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Calendar Gate ${runId}%`)}
);

DELETE FROM course_memberships
WHERE module_id IN (
  SELECT id FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Calendar Gate ${runId}%`)}
);

DELETE FROM course_modules WHERE title LIKE ${sqlLiteral(`Stage 11 Calendar Gate ${runId}%`)};
`);
}

function seedCalendarGate(runId: string): SeededCalendarGate {
  cleanupPriorRunRows(runId);

  const lecturerId = getAppUserId(LECTURER_EMAIL);
  const studentId = getAppUserId(STUDENT_EMAIL);
  const studentTwoId = getAppUserId(STUDENT_TWO_EMAIL);
  const moduleId = randomUUID();
  const planId = randomUUID();
  const itemId = randomUUID();
  const deadlineSectionId = randomUUID();
  const membershipIds = [randomUUID(), randomUUID(), randomUUID()];

  runPsqlRows(`
INSERT INTO course_modules (id, title, description, owner_id, timezone, starts_on, ends_on, is_active)
VALUES (
  ${sqlLiteral(moduleId)}::uuid,
  ${sqlLiteral(`Stage 11 Calendar Gate ${runId}`)},
  'Stage 11 calendar export browser gate',
  ${sqlLiteral(lecturerId)}::uuid,
  'Europe/London',
  DATE '2026-03-01',
  DATE '2026-04-30',
  true
);

INSERT INTO course_memberships (id, user_id, module_id, role, status) VALUES
  (${sqlLiteral(membershipIds[0])}::uuid, ${sqlLiteral(lecturerId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'lecturer', 'active'),
  (${sqlLiteral(membershipIds[1])}::uuid, ${sqlLiteral(studentId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active'),
  (${sqlLiteral(membershipIds[2])}::uuid, ${sqlLiteral(studentTwoId)}::uuid, ${sqlLiteral(moduleId)}::uuid, 'student', 'active');

INSERT INTO module_sections (id, course_module_id, title, type, order_index, week_number, session_date, due_at, publish_status, status)
VALUES (
  ${sqlLiteral(deadlineSectionId)}::uuid,
  ${sqlLiteral(moduleId)}::uuid,
  'DST deadline',
  'assignment',
  1,
  1,
  DATE '2026-03-29',
  TIMESTAMPTZ '2026-03-29T20:00:00Z',
  'published',
  'active'
);

INSERT INTO workload_plans (
  id, student_id, module_id, algorithm_version, input_hash, availability_version,
  source_cutoff_at, is_active, provenance
)
VALUES (
  ${sqlLiteral(planId)}::uuid,
  ${sqlLiteral(studentId)}::uuid,
  ${sqlLiteral(moduleId)}::uuid,
  'workload-v1',
  ${sqlLiteral(`calendar-${runId}`)},
  1,
  TIMESTAMPTZ '2026-03-29T00:00:00Z',
  true,
  ${sqlLiteral(JSON.stringify({ timezone: 'Europe/London', snapshot: true }))}::jsonb
);

INSERT INTO workload_plan_items (
  id, workload_plan_id, source_section_id, task_key, scheduled_date, "window",
  scheduled_start_at, scheduled_end_at, label, estimate_minutes, reason,
  source_reason_code, source_metadata, tight, sort_index
)
VALUES (
  ${sqlLiteral(itemId)}::uuid,
  ${sqlLiteral(planId)}::uuid,
  ${sqlLiteral(deadlineSectionId)}::uuid,
  ${sqlLiteral(`deadline:${deadlineSectionId}`)},
  DATE '2026-03-29',
  'evening',
  TIMESTAMPTZ '2026-03-29T17:00:00Z',
  TIMESTAMPTZ '2026-03-29T18:00:00Z',
  'DST Focus Block',
  60,
  'deadline',
  NULL,
  '{}'::jsonb,
  false,
  0
);
`);

  recordManifestValue(runId, 'moduleIds', moduleId);
  recordManifestValue(runId, 'sectionIds', deadlineSectionId);
  for (const membershipId of membershipIds) recordManifestValue(runId, 'membershipIds', membershipId);

  return { moduleId, planId, itemId, deadlineSectionId };
}

function unfoldLines(content: string): string[] {
  expect(content).toContain('\r\n');
  const rawLines = content.split('\r\n');
  expect(rawLines.at(-1)).toBe('');
  const lines: string[] = [];
  for (const line of rawLines.slice(0, -1)) {
    if (line.startsWith(' ')) {
      lines[lines.length - 1] += line.slice(1);
    } else {
      lines.push(line);
    }
  }
  return lines;
}

function parseCalendar(content: string): { properties: Record<string, string>; events: CalendarEvent[] } {
  const lines = unfoldLines(content);
  expect(lines[0]).toBe('BEGIN:VCALENDAR');
  expect(lines.at(-1)).toBe('END:VCALENDAR');
  const properties: Record<string, string> = {};
  const events: CalendarEvent[] = [];
  let current: CalendarEvent | null = null;
  for (const line of lines.slice(1, -1)) {
    if (line === 'BEGIN:VEVENT') {
      expect(current).toBeNull();
      current = {};
      continue;
    }
    if (line === 'END:VEVENT') {
      expect(current).not.toBeNull();
      events.push(current!);
      current = null;
      continue;
    }
    expect(line).toContain(':');
    const index = line.indexOf(':');
    const name = line.slice(0, index);
    const value = line.slice(index + 1);
    if (current) {
      current[name] = value;
    } else {
      properties[name] = value;
    }
  }
  expect(current).toBeNull();
  return { properties, events };
}

function parseUtc(value: string): Date {
  const match = value.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  if (!match) throw new Error(`Invalid UTC iCalendar datetime: ${value}`);
  return new Date(Date.UTC(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    Number(match[4]),
    Number(match[5]),
    Number(match[6]),
  ));
}

function timeParts(value: Date, timeZone: string): Record<string, string> {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(value);
  return Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]));
}

test('Stage 11.5 calendar export gate', async ({ browser }) => {
  const runId = requireRunId();
  const seeded = seedCalendarGate(runId);

  const studentContext = await browser.newContext();
  const studentTwoContext = await browser.newContext();
  let studentTwoApi: APIRequestContext | null = null;

  try {
    const studentPage = await signInPage(studentContext, STUDENT_EMAIL, '/student');
    await studentPage.goto(`/student/modules/${seeded.moduleId}`);
    const planner = studentPage.getByTestId('student-workload-planner');
    await expect(planner).toBeVisible();
    await expect(planner.getByTestId('workload-plan-list')).toBeVisible();
    await expect(planner).toContainText('DST Focus Block');

    const firstDownloadPromise = studentPage.waitForEvent('download');
    await planner.getByTestId('workload-export-calendar').click();
    const firstDownload = await firstDownloadPromise;
    expect(firstDownload.suggestedFilename()).toContain(`${seeded.planId}.ics`);
    const firstPath = await firstDownload.path();
    expect(firstPath).toBeTruthy();
    const firstContent = readFileSync(firstPath!, 'utf8');
    const { properties, events } = parseCalendar(firstContent);
    expect(properties.PRODID).toBe('XYZ LMS');
    expect(properties['X-WR-TIMEZONE']).toBe('Europe/London');

    const studyEvent = events.find((event) => event.UID === `workload-plan-item-${seeded.itemId}@xyz-lms`);
    expect(studyEvent).toBeTruthy();
    expect(studyEvent!.SUMMARY).toBe('Study: DST Focus Block');
    expect(studyEvent!.DESCRIPTION).toContain('Reason: deadline\\nEstimate: 60 minutes');
    expect(studyEvent!.DTSTART).toBe('20260329T170000Z');
    expect(studyEvent!.DTEND).toBe('20260329T180000Z');
    const studyStart = parseUtc(studyEvent!.DTSTART);
    expect(studyStart.toISOString()).toBe('2026-03-29T17:00:00.000Z');
    expect(timeParts(studyStart, 'Europe/London')).toMatchObject({ hour: '18', minute: '00' });
    expect(timeParts(studyStart, 'Asia/Dubai')).toMatchObject({ hour: '21', minute: '00' });
    expect(timeParts(studyStart, 'Asia/Dubai').hour).not.toBe('18');

    const deadlineEvent = events.find((event) => event.UID === `module-deadline-${seeded.deadlineSectionId}@xyz-lms`);
    expect(deadlineEvent).toBeTruthy();
    expect(deadlineEvent!.SUMMARY).toBe('Deadline: DST deadline');
    expect(deadlineEvent!.DTSTART).toBe('20260329T200000Z');

    const secondDownloadPromise = studentPage.waitForEvent('download');
    await planner.getByTestId('workload-export-calendar').click();
    const secondDownload = await secondDownloadPromise;
    const secondPath = await secondDownload.path();
    expect(secondPath).toBeTruthy();
    const secondContent = readFileSync(secondPath!, 'utf8');
    const secondParsed = parseCalendar(secondContent);
    expect(events.map((event) => event.UID).sort()).toEqual(secondParsed.events.map((event) => event.UID).sort());

    const studentTwoPage = await signInPage(studentTwoContext, STUDENT_TWO_EMAIL, '/student');
    studentTwoApi = await createApiContext(await getAccessToken(studentTwoPage));
    const forbidden = await studentTwoApi.get(`/student/workload/plans/${seeded.planId}/calendar.ics`);
    expect(forbidden.status()).toBe(403);
    expect(await forbidden.text()).not.toBe('');
  } finally {
    await studentTwoApi?.dispose();
    await studentContext.close();
    await studentTwoContext.close();
  }
});
