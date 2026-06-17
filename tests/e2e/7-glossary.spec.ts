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
  insertSection,
  runPsqlJson,
  sqlLiteral,
  waitForSummariesSettled,
  waitForTranscriptEmbedded,
  getActiveTranscriptForSection,
} from './fixtures/db.mjs';

/**
 * Stage 7 browser gate — interactive glossary & practice (deterministic provider, §14 / rule 11 smoke
 * is separate).
 *
 * Arabic-preference student highlights a real summary → Save to glossary → entry appears, definition
 * fills in ASYNC and renders RTL (dir="rtl") → duplicate save rejected → manual add → delete (archive)
 * → practice scope chosen → Flashcards (keyboard + on-screen rating + progress) → Multiple-Choice
 * (4 deck-sampled options + "Don't know?" + ≥4-term minimum) → glossary_term_saved +
 * glossary_practice_completed events recorded → a SECOND (run-scoped) student cannot read the first's
 * entry (404).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? 'http://127.0.0.1:54321';
const SERVICE_ROLE = process.env.SUPABASE_SERVICE_ROLE_KEY ?? '';
const E2E_MODULE_ID = '20000000-0000-4000-8000-000000000001'; // seed.mjs fixtureIds.module
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const TRANSCRIPT_FILE = 'sentinel-lecture.vtt';
const HIGHLIGHT_TERM = 'definitions'; // present in the deterministic brief-summary fixture

test.setTimeout(240_000);
// Fail fast on a genuinely missing element (20s) instead of hanging to the full test timeout.
test.use({ actionTimeout: 20_000, navigationTimeout: 45_000 });

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; title: string; type: string; publishStatus: string };

// ── auth (mirrors 5d) ──
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
async function apiJson<T>(ctx: APIRequestContext, method: 'GET' | 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown): Promise<ApiResponse<T>> {
  const opts = body === undefined ? undefined : { data: body };
  const response =
    method === 'GET' ? await ctx.get(path)
    : method === 'POST' ? await ctx.post(path, opts)
    : method === 'PATCH' ? await ctx.patch(path, opts)
    : await ctx.delete(path);
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}
async function apiUpload<T>(ctx: APIRequestContext, path: string, fileName: string, buffer: Buffer, mimeType: string): Promise<ApiResponse<T>> {
  const response = await ctx.post(path, { multipart: { file: { name: fileName, mimeType, buffer } } });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

// ── manifest (run-scoped resources for teardown) ──
function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the Stage 7 gate');
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

// ── glossary DB assertions ──
function countActiveEntries(studentId: string): number {
  return runPsqlJson(`SELECT to_json(count(*)::int)::text FROM glossary_entries WHERE student_id = ${sqlLiteral(studentId)}::uuid AND status = 'active';`) as unknown as number;
}
function entryByNormalizedTerm(studentId: string, normalized: string): { id: string; definitionStatus: string; language: string } | null {
  return runPsqlJson(`SELECT json_build_object('id', id, 'definitionStatus', definition_status, 'language', language)::text FROM glossary_entries WHERE student_id = ${sqlLiteral(studentId)}::uuid AND normalized_term = ${sqlLiteral(normalized)} AND status = 'active' LIMIT 1;`) as unknown as { id: string; definitionStatus: string; language: string } | null;
}
function countGlossaryEvents(studentId: string, eventType: string): number {
  return runPsqlJson(`SELECT to_json(count(*)::int)::text FROM student_activity_events WHERE student_id = ${sqlLiteral(studentId)}::uuid AND event_type = ${sqlLiteral(eventType)};`) as unknown as number;
}

/** Select `substring` inside the element with `testId` and fire a bubbling mouseup so SaveToGlossary captures it. */
async function selectTextIn(page: Page, testId: string, substring: string) {
  const ok = await page.evaluate(({ testId, substring }) => {
    const root = document.querySelector(`[data-testid="${testId}"]`);
    if (!root) return false;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const idx = (node.textContent ?? '').indexOf(substring);
      if (idx >= 0) {
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + substring.length);
        const sel = window.getSelection()!;
        sel.removeAllRanges();
        sel.addRange(range);
        root.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
        return true;
      }
    }
    return false;
  }, { testId, substring });
  expect(ok, `selectable "${substring}" in ${testId}`).toBe(true);
}

async function createRunScopedUser(runId: string, role: 'lecturer' | 'student', label: string): Promise<{ email: string; appUserId: string }> {
  const email = `glossary-${label}-${runId}-${Date.now().toString(36)}@xyz-lms-e2e.dev`;
  const resp = await fetch(`${SUPABASE_URL}/auth/v1/admin/users`, {
    method: 'POST',
    headers: { apikey: SERVICE_ROLE, authorization: `Bearer ${SERVICE_ROLE}`, 'content-type': 'application/json' },
    body: JSON.stringify({ email, password: PASSWORD, email_confirm: true }),
  });
  const user = (await resp.json()) as { id?: string; user?: { id: string } };
  const authId = user.id ?? user.user?.id;
  expect(authId, `${role} auth id`).toBeTruthy();
  recordManifestValue(runId, 'authUserIds', authId as string);
  const appUserId = runPsqlJson(`WITH ins AS (INSERT INTO app_users (id, auth_provider_id, email, full_name, role, is_active, timezone) VALUES (gen_random_uuid(), ${sqlLiteral(authId)}, ${sqlLiteral(email)}, ${sqlLiteral(`Glossary ${label}`)}, ${sqlLiteral(role)}, true, 'UTC') RETURNING id) SELECT to_json(id)::text FROM ins;`) as unknown as string;
  recordManifestValue(runId, 'appUserIds', appUserId);
  const membershipId = runPsqlJson(`WITH ins AS (INSERT INTO course_memberships (id, user_id, module_id, role, status) VALUES (gen_random_uuid(), ${sqlLiteral(appUserId)}::uuid, ${sqlLiteral(E2E_MODULE_ID)}::uuid, ${sqlLiteral(role)}, 'active') RETURNING id) SELECT to_json(id)::text FROM ins;`) as unknown as string;
  recordManifestValue(runId, 'membershipIds', membershipId);
  return { email, appUserId };
}

test('Stage 7 glossary browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const lecturerCtx = await browser.newContext();
  const studentCtx = await browser.newContext();
  const student2Ctx = await browser.newContext();
  let apiLecturer: APIRequestContext | null = null;
  let apiStudent: APIRequestContext | null = null;
  let apiStudent2: APIRequestContext | null = null;
  const lecturer = await createRunScopedUser(runId, 'lecturer', 'lecturer');
  const student = await createRunScopedUser(runId, 'student', 'student');
  const studentId = student.appUserId;

  try {
    // ── setup: a fresh published lecture in the seeded module, with a ready summary ──
    const lecturerPage = await signInPage(lecturerCtx, lecturer.email, '/lecturer');
    apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    const section = insertSection(E2E_MODULE_ID, { type: 'lecture', title: `Glossary Lecture ${runId}`, publishStatus: 'published' }) as SectionRow;
    recordManifestValue(runId, 'sectionIds', section.id);
    const upload = await apiUpload<{ id: string }>(apiLecturer, `/modules/${E2E_MODULE_ID}/sections/${section.id}/transcript`, TRANSCRIPT_FILE, readFileSync(resolve(TRANSCRIPT_DIR, TRANSCRIPT_FILE)), 'text/vtt');
    expect(upload.status).toBe(201);
    const transcriptId = getActiveTranscriptForSection(section.id).id as string;
    recordManifestValue(runId, 'transcriptIds', transcriptId);
    await waitForTranscriptEmbedded(transcriptId, 120_000);
    const settled = await waitForSummariesSettled(transcriptId, 120_000);
    expect(settled.generate_brief_summary).toBe('completed');

    // ── student: Arabic preference, open the section ──
    const studentPage = await signInPage(studentCtx, student.email, '/student');
    apiStudent = await createApiContext(await getAccessToken(studentPage));
    expect((await apiJson(apiStudent, 'PATCH', '/me/preferences', { preferredLanguage: 'ar' })).status).toBe(200);

    await studentPage.goto(`/student/modules/${E2E_MODULE_ID}/sections/${section.id}`);
    const brief = studentPage.getByTestId('student-summary-brief-content');
    await expect(brief).toBeVisible({ timeout: 30_000 });

    // ── Phase 1: highlight → save → async fill-in → Arabic RTL ──
    await selectTextIn(studentPage, 'student-summary-brief-content', HIGHLIGHT_TERM);
    await expect(studentPage.getByTestId('save-to-glossary')).toBeEnabled();
    await studentPage.getByTestId('save-to-glossary').click();
    await expect(studentPage.getByTestId('save-to-glossary-status')).toHaveAttribute('data-status', 'saved');
    await expect.poll(() => entryByNormalizedTerm(studentId, HIGHLIGHT_TERM)?.language ?? null, { timeout: 15_000 }).toBe('ar');
    await expect.poll(() => entryByNormalizedTerm(studentId, HIGHLIGHT_TERM)?.definitionStatus ?? null, { timeout: 30_000 }).toBe('generated');
    const highlightEntryId = entryByNormalizedTerm(studentId, HIGHLIGHT_TERM)!.id;
    expect(countGlossaryEvents(studentId, 'glossary_term_saved')).toBe(1);

    // glossary page → detail renders the definition RTL (dir="rtl")
    await studentPage.goto('/student/glossary');
    await expect(studentPage.getByTestId('glossary-page')).toBeVisible();
    await studentPage.getByTestId(`glossary-entry-${highlightEntryId}`).click();
    await expect(studentPage.getByTestId('glossary-detail')).toBeVisible();
    await expect.poll(() => studentPage.getByTestId('glossary-detail-definition').getAttribute('dir'), { timeout: 15_000 }).toBe('rtl');

    // ── Phase 2: duplicate save rejected (no second entry) ──
    await studentPage.goto(`/student/modules/${E2E_MODULE_ID}/sections/${section.id}`);
    await expect(studentPage.getByTestId('student-summary-brief-content')).toBeVisible({ timeout: 30_000 });
    await selectTextIn(studentPage, 'student-summary-brief-content', HIGHLIGHT_TERM);
    await studentPage.getByTestId('save-to-glossary').click();
    await expect(studentPage.getByTestId('save-to-glossary-status')).toHaveAttribute('data-status', 'duplicate');
    expect(countActiveEntries(studentId)).toBe(1); // still exactly one

    // ── Phase 3: manual add (UI once) + API (deck to ≥4 for MCQ) ──
    await studentPage.goto('/student/glossary');
    await studentPage.getByTestId('glossary-add-term').click();
    await expect(studentPage.getByTestId('manual-entry-modal')).toBeVisible();
    await studentPage.getByTestId('manual-entry-course').selectOption(E2E_MODULE_ID);
    await studentPage.getByTestId('manual-entry-term').fill('Mitochondria');
    await studentPage.getByTestId('manual-entry-save').click();
    await expect(studentPage.getByTestId('manual-entry-modal')).toBeHidden();
    for (const term of ['Ribosome', 'Nucleus', 'Cytoplasm', 'Enzyme']) {
      expect((await apiJson(apiStudent, 'POST', '/student/glossary/entries', { subjectId: E2E_MODULE_ID, term })).status).toBe(200);
    }
    // all entries reach 'generated' (deck of 6: highlight + 5 manual)
    await expect.poll(() => runPsqlJson(`SELECT to_json(count(*)::int)::text FROM glossary_entries WHERE student_id = ${sqlLiteral(studentId)}::uuid AND status='active' AND definition_status='generated';`) as unknown as number, { timeout: 30_000 }).toBe(6);

    // ── Phase 4: delete (archive) — disappears from views, count drops ──
    const ribosome = entryByNormalizedTerm(studentId, 'ribosome')!;
    expect((await apiJson(apiStudent, 'DELETE', `/student/glossary/entries/${ribosome.id}`)).status).toBe(204);
    await studentPage.goto('/student/glossary');
    await expect(studentPage.getByTestId(`glossary-entry-${ribosome.id}`)).toHaveCount(0);
    expect(countActiveEntries(studentId)).toBe(5);

    // ── Phase 5: Flashcards (keyboard + on-screen rating + progress) ──
    await studentPage.goto('/student/glossary/practice');
    await studentPage.getByTestId('practice-mode-flashcard').check(); // scope defaults to "all my saved terms"
    await expect(studentPage.getByTestId('practice-start')).toBeEnabled();
    await studentPage.getByTestId('practice-start').click();
    await expect(studentPage.getByTestId('glossary-flashcards-session')).toBeVisible();
    const progress = studentPage.getByTestId('glossary-flashcards-progress');
    await expect(progress).toHaveText(/0 \/ 5/);
    await studentPage.getByTestId('glossary-flashcard').click(); // flip (UX)
    await studentPage.getByTestId('flashcard-know').click(); // on-screen rating
    await expect(progress).toHaveText(/1 \/ 5/);
    await studentPage.keyboard.press('ArrowRight'); // keyboard "I know this"
    await expect(progress).toHaveText(/2 \/ 5/);
    await studentPage.keyboard.press('ArrowLeft'); // "study again" re-queues (still counts as answered)
    await expect(progress).toHaveText(/3 \/ 5/);
    await studentPage.keyboard.press('ArrowRight');
    await expect(progress).toHaveText(/4 \/ 5/);
    await studentPage.keyboard.press('ArrowRight');
    await expect(progress).toHaveText(/5 \/ 5/);
    await studentPage.keyboard.press('ArrowRight'); // re-queued (already answered) card → complete
    await expect(studentPage.getByTestId('glossary-practice-result')).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => countGlossaryEvents(studentId, 'glossary_practice_completed')).toBe(1);

    // ── Phase 6: Multiple-Choice (≥4 options, deck-sampled, "Don't know?") ──
    const avail = await apiJson<{ available: boolean; termCount: number }>(apiStudent, 'GET', `/student/glossary/practice/availability?mode=multiple_choice&scope=course&subjectId=${E2E_MODULE_ID}`);
    expect(avail.body.available).toBe(true);
    expect(avail.body.termCount).toBeGreaterThanOrEqual(4);
    await studentPage.goto('/student/glossary/practice');
    await studentPage.getByText('A specific course').click(); // scope = a specific course
    await studentPage.getByTestId('practice-course').selectOption(E2E_MODULE_ID);
    await studentPage.getByTestId('practice-mode-mcq').check();
    await expect(studentPage.getByTestId('practice-start')).toBeEnabled();
    await studentPage.getByTestId('practice-start').click();
    await expect(studentPage.getByTestId('glossary-mcq-session')).toBeVisible();
    await expect(studentPage.getByTestId('quiz-question-card')).toBeVisible();
    await expect(studentPage.locator('[data-testid^="quiz-option-"]')).toHaveCount(4); // 4 deck-sampled
    const MCQ_DECK = 5; // exactly the 5 active generated terms in scope
    for (let q = 0; q < MCQ_DECK; q += 1) {
      // wait for the (new) question's options to be answerable before clicking — avoids the transition race
      await expect(studentPage.locator('[data-testid^="quiz-option-"]').first()).toBeEnabled();
      if (q === 1) {
        await studentPage.getByTestId('glossary-mcq-dontknow').click(); // "Don't know?" → records not-known
      } else {
        await studentPage.locator('[data-testid^="quiz-option-"]').first().click();
      }
      await expect(studentPage.getByTestId('quiz-feedback')).toBeVisible();
      await studentPage.getByTestId('glossary-mcq-next').click(); // q==4 → finish
    }
    await expect(studentPage.getByTestId('glossary-practice-result')).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => countGlossaryEvents(studentId, 'glossary_practice_completed')).toBe(2);

    // ── Phase 7: a second (run-scoped) student cannot read the first's entry (404) ──
    const second = await createRunScopedUser(runId, 'student', 'second-student');
    const student2Page = await signInPage(student2Ctx, second.email, '/student');
    apiStudent2 = await createApiContext(await getAccessToken(student2Page));
    expect((await apiJson(apiStudent2, 'GET', `/student/glossary/entries/${highlightEntryId}`)).status).toBe(404);
    const ownList = await apiJson<{ items: unknown[] }>(apiStudent2, 'GET', '/student/glossary/entries');
    expect(ownList.body.items.length).toBe(0); // second student sees none of the first's entries
  } finally {
    await apiLecturer?.dispose();
    await apiStudent?.dispose();
    await apiStudent2?.dispose();
    await lecturerCtx.close();
    await studentCtx.close();
    await student2Ctx.close();
  }
});
