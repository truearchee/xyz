import { execSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  expect,
  request as playwrightRequest,
  test,
  type APIRequestContext,
  type Page,
} from '@playwright/test';

import {
  getActiveTranscriptForSection,
  getAiRequestLogsForTranscript,
  getAppUserByEmail,
  getGeneratedSummariesForTranscript,
  getMembershipsForModule,
  getSectionsForModule,
  waitForSummaryFailure,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

// Stage 4.5d Gate 2 — forced-fault browser coverage (deterministic provider, NO key). The
// LLM-transport fault is a global ai_worker env value, so the spec recreates ai_worker with the
// matching fault before each test and restores it afterwards. This keeps the full active suite
// runnable without a manual --grep + worker-recreate preamble.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; title: string; type: string };

// Stage 5.5: generated titles are now "Lecture — Week N (...)" / "Lab — Week N (...)". Select by
// type + ordinal; getSectionsForModule returns rows ordered by order_index, so index 0 = first.
// (Replaces the old `find(title==='Lab 1')!` which silently produced undefined → TypeError on miss.)
function nthSectionOfType(sections: SectionRow[], type: 'lecture' | 'lab', index = 0): SectionRow {
  const matches = sections.filter((candidate) => candidate.type === type);
  const section = matches[index];
  if (!section) {
    throw new Error(`Missing generated ${type} section #${index} (have ${matches.length})`);
  }
  return section;
}

test.setTimeout(600_000);

function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before the 4.5d fault gate');
  return runId;
}

function manifestPath(runId: string): string {
  if (!/^e2e-[a-z0-9][a-z0-9-]{5,80}$/.test(runId)) throw new Error(`Invalid E2E run id: ${runId}`);
  return resolve('tests/e2e/.runs', `${runId}.json`);
}

function record(runId: string, field: string, value: string) {
  const m = JSON.parse(readFileSync(manifestPath(runId), 'utf8'));
  m[field] = [...new Set([...(Array.isArray(m[field]) ? m[field] : []), value])];
  writeFileSync(manifestPath(runId), `${JSON.stringify(m, null, 2)}\n`);
}

function composeCommand(): string {
  return process.env.E2E_COMPOSE_FILES
    ? `docker compose ${process.env.E2E_COMPOSE_FILES}`
    : 'docker compose -f docker-compose.yml -f docker-compose.fault.yml';
}

function recreateAiWorker(fault: 'invalid_output' | 'invalid_input' | null) {
  const env = {
    ...process.env,
    LLM_FAULT_INJECTION: fault ?? '',
    PIPELINE_FAULT_INJECTION_ENABLED: '',
    PIPELINE_FAULT_INJECTION: '',
  };
  const compose = composeCommand();
  execSync(`${compose} up -d --force-recreate ai_worker`, { env, stdio: 'inherit' });
  const deadline = Date.now() + 60_000;
  for (;;) {
    const logs = execSync(`${compose} logs --tail=40 ai_worker`, { env }).toString();
    if (logs.includes('Listening on ai')) return;
    if (Date.now() > deadline) {
      throw new Error('ai_worker did not become ready within 60s after recreate');
    }
    execSync('sleep 1');
  }
}

async function signIn(page: Page, email: string, expectedPath: string) {
  await page.goto('/login');
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(new RegExp(`${expectedPath}$`));
  await page.waitForFunction(() => typeof window.__xyzE2E !== 'undefined');
}

async function apiContextFor(page: Page): Promise<APIRequestContext> {
  const session = (await page.evaluate(() => window.__xyzE2E!.getSession())) as {
    data: { session: { access_token: string } | null };
  };
  const token = session.data.session?.access_token;
  expect(token).toBeTruthy();
  return playwrightRequest.newContext({
    baseURL: API_BASE_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token as string}` },
  });
}

async function apiJson<T>(ctx: APIRequestContext, method: 'GET' | 'POST', path: string, body?: unknown): Promise<ApiResponse<T>> {
  const res = method === 'GET' ? await ctx.get(path) : await ctx.post(path, { data: body });
  const text = await res.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: res.status() };
}

function rowForSection(page: Page, section: SectionRow) {
  return page.locator('[data-testid^="lecturer-section-row-"]').filter({ hasText: section.title });
}

async function setupModuleAndUpload(page: Page, adminCtx: APIRequestContext, runId: string, label: string) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  const created = await apiJson<{ id: string }>(adminCtx, 'POST', '/admin/modules', {
    title: `Stage 4.5d Fault ${label} ${runId}`,
    description: `4.5d fault gate ${label} ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    // Stage 5.5a: creation is schedule-driven (startsOn/endsOn replaced). Title-based section
    // selection below is reworked in 5.5e (full-suite pass after the 5.5d reseed).
    schedule: {
      courseStartDate: '2026-01-12',
      courseEndDate: '2026-05-01',
      weekStartDay: 'monday',
      sessionPattern: [
        { weekday: 'monday', sectionType: 'lecture' },
        { weekday: 'tuesday', sectionType: 'lecture' },
        { weekday: 'wednesday', sectionType: 'lecture' },
        { weekday: 'thursday', sectionType: 'lab' },
      ],
      quizDay: 'friday',
    },
  });
  expect(created.status).toBe(201);
  const moduleId = created.body.id;
  record(runId, 'moduleIds', moduleId);
  const assign = await apiJson<{ id: string }>(adminCtx, 'POST', `/admin/modules/${moduleId}/members`, {
    userId: student.id,
    role: 'student',
  });
  expect(assign.status).toBe(201);
  record(runId, 'membershipIds', assign.body.id);
  for (const m of getMembershipsForModule(moduleId)) record(runId, 'membershipIds', m.id);
  const sections = getSectionsForModule(moduleId) as SectionRow[];
  for (const s of sections) record(runId, 'sectionIds', s.id);
  const lab = nthSectionOfType(sections, 'lab', 0);

  await page.goto(`/lecturer/modules/${moduleId}`);
  const row = rowForSection(page, lab);
  const input = row.locator('[data-testid^="section-transcript-upload-"]');
  await expect(input).toBeVisible();
  await input.setInputFiles(resolve(TRANSCRIPT_DIR, 'lab-notes.txt'));
  await row.getByRole('button', { name: 'Upload transcript' }).click();
  await expect.poll(() => getActiveTranscriptForSection(lab.id)?.id ?? null, { timeout: 10_000 }).not.toBeNull();
  const transcriptId = getActiveTranscriptForSection(lab.id).id;
  record(runId, 'transcriptIds', transcriptId);
  const artifacts = await waitForTranscriptEmbedded(transcriptId, 95_000);
  for (const j of artifacts.jobs) record(runId, 'ingestionJobIds', j.id);
  for (const id of artifacts.counts.chunkIds) record(runId, 'transcriptChunkIds', id);
  for (const id of artifacts.counts.segmentIds) record(runId, 'transcriptSegmentIds', id);
  if (artifacts.transcript?.storageKey) record(runId, 'storageKeys', artifacts.transcript.storageKey);
  return { moduleId, lab, transcriptId };
}

test('4.5d fault gate — invalid_output is rejected, retried, logged; no summary stored', async ({ browser }) => {
  const runId = requireRunId();
  const lecturerCtx = await browser.newContext();
  const adminCtx = await browser.newContext();
  let api: APIRequestContext | null = null;
  try {
    recreateAiWorker('invalid_output');
    const adminPage = await adminCtx.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    api = await apiContextFor(adminPage);

    const lecturerPage = await lecturerCtx.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    const { lab, transcriptId } = await setupModuleAndUpload(lecturerPage, api, runId, 'output');

    // Rejected + RETRYABLE: the job fails with the retryable failure_category=invalid_output (the
    // bounded RQ retry is scheduled). NB the AI worker runs without an RQ scheduler, so the delayed
    // retry does not execute here — proving the *retryable classification* (vs terminal invalid_input)
    // is the meaningful, reliable distinction; actual re-drive is a Stage 4.6 / infra concern.
    await waitForSummaryFailure(transcriptId, 'invalid_output', 90_000);
    // Logged: an AIRequestLog row with status=invalid_output (chatter never stored).
    const logs = getAiRequestLogsForTranscript(transcriptId) as Array<{ status: string }>;
    expect(logs.some((l) => l.status === 'invalid_output')).toBe(true);
    // Not stored: no malformed summary persisted.
    expect(getGeneratedSummariesForTranscript(transcriptId)).toEqual([]);

    // Badge/panel shows the retry-available category copy (no stack trace).
    await lecturerPage.reload();
    const row = rowForSection(lecturerPage, lab);
    await expect(row.locator('[data-testid^="section-summary-brief-status-"]')).toContainText(
      'Retry available',
      { timeout: 95_000 },
    );
  } finally {
    recreateAiWorker(null);
    await api?.dispose();
    await lecturerCtx.close();
    await adminCtx.close();
  }
});

test('4.5d fault gate — invalid_input is terminal, non-retryable; no summary row', async ({ browser }) => {
  const runId = requireRunId();
  const lecturerCtx = await browser.newContext();
  const adminCtx = await browser.newContext();
  let api: APIRequestContext | null = null;
  try {
    recreateAiWorker('invalid_input');
    const adminPage = await adminCtx.newPage();
    await signIn(adminPage, ADMIN_EMAIL, '/admin');
    api = await apiContextFor(adminPage);

    const lecturerPage = await lecturerCtx.newPage();
    await signIn(lecturerPage, LECTURER_EMAIL, '/lecturer');
    const { lab, transcriptId } = await setupModuleAndUpload(lecturerPage, api, runId, 'input');

    // Terminal: the job fails invalid_input and is NOT retried.
    await waitForSummaryFailure(transcriptId, 'invalid_input', 90_000);
    const logs = getAiRequestLogsForTranscript(transcriptId) as Array<{ status: string; attemptNumber: number }>;
    expect(logs.some((l) => l.status === 'invalid_input')).toBe(true);
    expect(Math.max(...logs.map((l) => l.attemptNumber))).toBe(1); // no RQ retry
    expect(getGeneratedSummariesForTranscript(transcriptId)).toEqual([]);

    // Badge/panel shows the non-retryable copy (too long), no detail leaked.
    await lecturerPage.reload();
    const row = rowForSection(lecturerPage, lab);
    await expect(row.locator('[data-testid^="section-summary-brief-status-"]')).toContainText(
      'too long',
      { timeout: 95_000 },
    );
  } finally {
    recreateAiWorker(null);
    await api?.dispose();
    await lecturerCtx.close();
    await adminCtx.close();
  }
});
