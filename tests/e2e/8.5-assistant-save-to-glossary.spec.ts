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
  getActiveTranscriptForSection,
  getAppUserByEmail,
  getMembershipsForModule,
  getSectionsForModule,
  runPsqlJson,
  sqlLiteral,
  waitForTranscriptEmbedded,
} from './fixtures/db.mjs';

/**
 * Stage 8.5 browser gate — save-to-glossary from the assistant (deterministic provider; rule 11 smoke is
 * not required — ADR-055 ships no new AI behavior).
 *
 * A student opens an enrolled, published lecture, chats with the assistant, and from a COMPLETED reply
 * highlights a term and saves it. The standard Stage 7 flow runs end to end: a personal entry appears in
 * THIS lecture's subject, the definition fills in async through the logged AI infra (background priority),
 * and the term is studyable. Saving the same term again creates no duplicate and attaches the chat as an
 * additional source idempotently. The glossary_term_saved event fires once. Negative assertions: the save
 * affordance never renders on the student's OWN message; an unbound conversation is rejected as a source;
 * another student cannot save against this conversation.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const PASSWORD = process.env.E2E_TEST_PASSWORD ?? 'LocalE2EPassword123!';
const ADMIN_EMAIL = 'admin_e2e@example.test';
const LECTURER_EMAIL = 'lecturer_e2e@example.test';
const STUDENT_EMAIL = 'student_e2e@example.test';
const STUDENT2_EMAIL = 'student2_e2e@example.test'; // seeded standing second student (cross-student gate)
const TRANSCRIPT_DIR = resolve('tests/e2e/fixtures/files/transcripts');
const TRANSCRIPT_FILE = 'sentinel-lecture.vtt';
// The deterministic provider's canned assistant answer (platform/llm/provider.py).
const ANSWER_MARKER = 'concise study-assistant answer';
const HIGHLIGHT_TERM = 'concise'; // present in the deterministic assistant answer

test.setTimeout(240_000);
test.use({ actionTimeout: 20_000, navigationTimeout: 45_000 });

type ApiResponse<T = unknown> = { body: T; status: number };
type SectionRow = { id: string; orderIndex: number; publishStatus: string; title: string; type: string };

// ── auth (mirrors 8.1) ──
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
async function apiUpload<T>(ctx: APIRequestContext, path: string, fileName: string, buffer: Buffer, mimeType: string): Promise<ApiResponse<T>> {
  const response = await ctx.post(path, { multipart: { file: { name: fileName, mimeType, buffer } } });
  const text = await response.text();
  return { body: text ? (JSON.parse(text) as T) : (null as T), status: response.status() };
}

// ── manifest (run-scoped resources for teardown) ──
function requireRunId(): string {
  const runId = process.env.E2E_RUN_ID;
  if (!runId) throw new Error('E2E_RUN_ID must be exported before running the Stage 8.5 gate');
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

// ── glossary / source DB assertions ──
function entryByNormalizedTerm(
  studentId: string,
  normalized: string,
  subjectId: string,
): { id: string; subjectId: string; definitionStatus: string } | null {
  return runPsqlJson(
    `SELECT json_build_object('id', id, 'subjectId', subject_id, 'definitionStatus', definition_status)::text FROM glossary_entries WHERE student_id = ${sqlLiteral(studentId)}::uuid AND normalized_term = ${sqlLiteral(normalized)} AND subject_id = ${sqlLiteral(subjectId)}::uuid AND status = 'active' LIMIT 1;`,
  ) as unknown as { id: string; subjectId: string; definitionStatus: string } | null;
}
function countActiveEntries(studentId: string, normalized: string, subjectId: string): number {
  return runPsqlJson(`SELECT to_json(count(*)::int)::text FROM glossary_entries WHERE student_id = ${sqlLiteral(studentId)}::uuid AND normalized_term = ${sqlLiteral(normalized)} AND subject_id = ${sqlLiteral(subjectId)}::uuid AND status = 'active';`) as unknown as number;
}
function countGlossaryEvents(studentId: string, eventType: string, sourceId: string): number {
  return runPsqlJson(`SELECT to_json(count(*)::int)::text FROM student_activity_events WHERE student_id = ${sqlLiteral(studentId)}::uuid AND event_type = ${sqlLiteral(eventType)} AND source_id = ${sqlLiteral(sourceId)}::uuid;`) as unknown as number;
}
function conversationSourcesForEntry(entryId: string): Array<{ conversationId: string | null; messageId: string | null; sectionId: string | null }> {
  return runPsqlJson(
    `SELECT coalesce(json_agg(json_build_object('conversationId', source_conversation_id, 'messageId', source_message_id, 'sectionId', module_section_id)), '[]')::text FROM glossary_source_references WHERE glossary_entry_id = ${sqlLiteral(entryId)}::uuid AND source_type = 'conversation';`,
  ) as unknown as Array<{ conversationId: string | null; messageId: string | null; sectionId: string | null }>;
}

// The lecture page renders summary SaveToGlossary wrappers AND the assistant chat's, all sharing the
// save-to-glossary testids — so every chat-save interaction must be scoped to the completed assistant
// reply, never page-wide.
const ASSISTANT_SAVE_CONTENT =
  '[data-testid="assistant-message-assistant"][data-state="completed"] [data-testid="save-to-glossary-content"]';

/** Select `substring` inside the element matching `selector` and fire a bubbling mouseup so SaveToGlossary captures it. */
async function selectTextIn(page: Page, selector: string, substring: string) {
  const ok = await page.evaluate(({ selector, substring }) => {
    const root = document.querySelector(selector);
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
  }, { selector, substring });
  expect(ok, `selectable "${substring}" in ${selector}`).toBe(true);
}

async function createModule(runId: string, adminContext: APIRequestContext, title: string) {
  const owner = getAppUserByEmail(LECTURER_EMAIL);
  const student = getAppUserByEmail(STUDENT_EMAIL);
  if (!owner?.id || !student?.id) throw new Error('Standing lecturer/student E2E users are required');
  const create = await apiJson<{ id: string }>(adminContext, 'POST', '/admin/modules', {
    title,
    description: `8.5 gate ${runId}`,
    ownerId: owner.id,
    timezone: 'UTC',
    schedule: {
      courseStartDate: '2026-01-12',
      courseEndDate: '2026-05-01',
      weekStartDay: 'monday',
      sessionPattern: [{ weekday: 'monday', sectionType: 'lecture' }],
      quizDay: 'friday',
    },
  });
  expect(create.status).toBe(201);
  const moduleId = create.body.id;
  recordManifestValue(runId, 'moduleIds', moduleId);
  const assign = await apiJson<{ id: string }>(adminContext, 'POST', `/admin/modules/${moduleId}/members`, { userId: student.id, role: 'student' });
  expect(assign.status).toBe(201);
  recordMany(runId, 'membershipIds', getMembershipsForModule(moduleId).map((m: { id: string }) => m.id));
  const sections = getSectionsForModule(moduleId) as SectionRow[];
  recordMany(runId, 'sectionIds', sections.map((s) => s.id));
  return { moduleId, section: sections.filter((s) => s.type === 'lecture')[0] };
}

async function publishAndEmbed(runId: string, apiLecturer: APIRequestContext, moduleId: string, sectionId: string) {
  const upload = await apiUpload<{ id: string }>(apiLecturer, `/modules/${moduleId}/sections/${sectionId}/transcript`, TRANSCRIPT_FILE, readFileSync(resolve(TRANSCRIPT_DIR, TRANSCRIPT_FILE)), 'text/vtt');
  expect(upload.status).toBe(201);
  const transcriptId = getActiveTranscriptForSection(sectionId).id as string;
  recordManifestValue(runId, 'transcriptIds', transcriptId);
  const artifacts = await waitForTranscriptEmbedded(transcriptId, 120_000);
  recordMany(runId, 'ingestionJobIds', artifacts.jobs.map((j: { id: string }) => j.id));
  recordMany(runId, 'transcriptChunkIds', artifacts.counts.chunkIds);
  recordMany(runId, 'transcriptSegmentIds', artifacts.counts.segmentIds);
  if (artifacts.transcript?.storageKey) recordManifestValue(runId, 'storageKeys', artifacts.transcript.storageKey);
  const publish = await apiJson(apiLecturer, 'POST', `/modules/${moduleId}/sections/${sectionId}/publish`);
  expect(publish.status).toBe(200);
}

async function startChat(page: Page) {
  await page.getByTestId('assistant-start-chat').click();
  await expect(page.getByTestId('assistant-messages')).toBeVisible();
}
async function ask(page: Page, text: string, expectedAnswers: number) {
  await page.getByTestId('assistant-input').fill(text);
  await page.getByTestId('assistant-send').click();
  await expect(page.locator('[data-testid="assistant-message-assistant"][data-state="completed"]')).toHaveCount(expectedAnswers, { timeout: 60_000 });
}

test('8.5 assistant save-to-glossary browser gate', async ({ browser }) => {
  const runId = requireRunId();
  const adminCtx = await browser.newContext();
  const lecturerCtx = await browser.newContext();
  const studentCtx = await browser.newContext();
  const student2Ctx = await browser.newContext();
  let apiStudent: APIRequestContext | null = null;
  let apiStudent2: APIRequestContext | null = null;

  try {
    const adminPage = await signInPage(adminCtx, ADMIN_EMAIL, '/admin');
    const apiAdmin = await createApiContext(await getAccessToken(adminPage));
    const { moduleId, section } = await createModule(runId, apiAdmin, `Stage 8.5 Module ${runId}`);

    const lecturerPage = await signInPage(lecturerCtx, LECTURER_EMAIL, '/lecturer');
    const apiLecturer = await createApiContext(await getAccessToken(lecturerPage));
    await publishAndEmbed(runId, apiLecturer, moduleId, section.id);
    const studentId = getAppUserByEmail(STUDENT_EMAIL).id as string;

    // ── student opens the lecture → chats → completed reply ──
    const page = await signInPage(studentCtx, STUDENT_EMAIL, '/student');
    apiStudent = await createApiContext(await getAccessToken(page));
    await page.goto(`/student/modules/${moduleId}/sections/${section.id}`);
    await expect(page.getByTestId('assistant-start-chat')).toBeVisible({ timeout: 30_000 });
    await startChat(page);
    await ask(page, 'What is this lecture about?', 1);
    const answer = page.locator('[data-testid="assistant-message-assistant"][data-state="completed"]').first();
    await expect(answer).toContainText(ANSWER_MARKER);

    // ── negative (browser): the student's OWN message has NO save affordance ──
    await expect(page.getByTestId('assistant-message-user').locator('[data-testid="save-to-glossary"]')).toHaveCount(0);
    // a completed assistant reply DOES carry exactly one save affordance
    await expect(answer.locator('[data-testid="save-to-glossary"]')).toHaveCount(1);

    // ── highlight a term in the assistant reply → save (scoped to THIS reply, not the summary's) ──
    await selectTextIn(page, ASSISTANT_SAVE_CONTENT, HIGHLIGHT_TERM);
    await expect(answer.getByTestId('save-to-glossary')).toBeEnabled();
    await answer.getByTestId('save-to-glossary').click();
    await expect(answer.getByTestId('save-to-glossary-status')).toHaveAttribute('data-status', 'saved');

    // ── entry appears in the student's glossary, subject = THIS lecture; definition fills in async ──
    await expect.poll(() => entryByNormalizedTerm(studentId, HIGHLIGHT_TERM, moduleId)?.subjectId ?? null, { timeout: 15_000 }).toBe(moduleId);
    const entry = entryByNormalizedTerm(studentId, HIGHLIGHT_TERM, moduleId)!;
    await expect.poll(() => entryByNormalizedTerm(studentId, HIGHLIGHT_TERM, moduleId)?.definitionStatus ?? null, { timeout: 30_000 }).toBe('generated');
    expect(countGlossaryEvents(studentId, 'glossary_term_saved', entry.id)).toBe(1);
    // the source records THIS conversation + message, bound to the lecture section
    const sources = conversationSourcesForEntry(entry.id);
    expect(sources).toHaveLength(1);
    expect(sources[0].conversationId).toBeTruthy();
    expect(sources[0].messageId).toBeTruthy();
    expect(sources[0].sectionId).toBe(section.id);
    const sourceConversationId = sources[0].conversationId as string;
    const sourceMessageId = sources[0].messageId as string;

    // ── studyable: it shows in the glossary and is practiseable (flashcard session starts) ──
    await page.goto('/student/glossary');
    await expect(page.getByTestId('glossary-page')).toBeVisible();
    await expect(page.getByTestId(`glossary-entry-${entry.id}`)).toBeVisible();
    await page.goto('/student/glossary/practice');
    await page.getByTestId('practice-mode-flashcard').check();
    await expect(page.getByTestId('practice-start')).toBeEnabled();
    await page.getByTestId('practice-start').click();
    await expect(page.getByTestId('glossary-flashcards-session')).toBeVisible();

    // ── duplicate save: same term + same chat → "already saved", no second entry, source attached once ──
    await page.goto(`/student/modules/${moduleId}/sections/${section.id}`);
    await startChat(page);
    const answer2 = page.locator('[data-testid="assistant-message-assistant"][data-state="completed"]').first();
    await expect(answer2).toContainText(ANSWER_MARKER);
    await selectTextIn(page, ASSISTANT_SAVE_CONTENT, HIGHLIGHT_TERM);
    await answer2.getByTestId('save-to-glossary').click();
    await expect(answer2.getByTestId('save-to-glossary-status')).toHaveAttribute('data-status', 'duplicate');
    expect(countActiveEntries(studentId, HIGHLIGHT_TERM, moduleId)).toBe(1);
    expect(conversationSourcesForEntry(entry.id)).toHaveLength(1); // idempotent — chat not attached twice

    // ── negative (API): an UNBOUND conversation is rejected as a save source (404) ──
    // No UI surface reaches an unbound conversation after 8.4, so this is driven through the API. The
    // affordance is also hidden client-side when a conversation has no bound section (saveSectionId null).
    const unboundConversationId = runPsqlJson(
      `WITH ins AS (INSERT INTO assistant_conversations (id, student_id, conversation_kind, attached_section_id, created_at, updated_at) VALUES (gen_random_uuid(), ${sqlLiteral(studentId)}::uuid, 'workspace', NULL, now(), now()) RETURNING id) SELECT to_json(id)::text FROM ins;`,
    ) as unknown as string;
    const unboundMessageId = runPsqlJson(
      `WITH ins AS (INSERT INTO assistant_messages (id, conversation_id, role, status, content, created_at, updated_at) VALUES (gen_random_uuid(), ${sqlLiteral(unboundConversationId)}::uuid, 'assistant', 'completed', 'A concise unbound reply.', now(), now()) RETURNING id) SELECT to_json(id)::text FROM ins;`,
    ) as unknown as string;
    try {
      const unbound = await apiJson(apiStudent, 'POST', '/student/glossary/highlight', {
        conversation: { conversationId: unboundConversationId, messageId: unboundMessageId },
        term: HIGHLIGHT_TERM,
        selectedText: HIGHLIGHT_TERM,
      });
      expect(unbound.status).toBe(404);
    } finally {
      runPsqlJson(`WITH del AS (DELETE FROM assistant_conversations WHERE id = ${sqlLiteral(unboundConversationId)}::uuid RETURNING 1) SELECT to_json(count(*)::int)::text FROM del;`);
    }

    // ── negative (API): another student cannot save against THIS conversation (404, never 403) ──
    const student2Id = getAppUserByEmail(STUDENT2_EMAIL).id as string;
    const student2Page = await signInPage(student2Ctx, STUDENT2_EMAIL, '/student');
    apiStudent2 = await createApiContext(await getAccessToken(student2Page));
    const crossStudent = await apiJson(apiStudent2, 'POST', '/student/glossary/highlight', {
      conversation: { conversationId: sourceConversationId, messageId: sourceMessageId },
      term: HIGHLIGHT_TERM,
      selectedText: HIGHLIGHT_TERM,
    });
    expect(crossStudent.status).toBe(404);
    expect(entryByNormalizedTerm(student2Id, HIGHLIGHT_TERM, moduleId)).toBeNull(); // no leak into student-2's glossary
  } finally {
    await apiStudent?.dispose();
    await apiStudent2?.dispose();
    await adminCtx.close();
    await lecturerCtx.close();
    await studentCtx.close();
    await student2Ctx.close();
  }
});
