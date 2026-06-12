import {
  expect,
  test,
  type APIRequestContext,
  type Browser,
} from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import {
  apiContextFor,
  identity,
  seedBrowserSession,
  signIn,
  stagingEnv,
  type Session,
  type StagingEnv,
} from "./fixtures/staging-smoke/staging-auth";

// Stage 4.8d — the HOOK-FREE staging smoke (umbrella §2/§9). The LOAD-BEARING part is the
// membership+publish state machine with negative controls FIRST (spec §1): a green here must mean the
// student sees content ONLY because (active member of THIS module) AND (section published) — never weak
// auth. NC1≡NC2 (byte-identical 404) is the existence-leak proof. NC4 is three independent surfaces.

const SENTINEL = "RAW_TRANSCRIPT_SENTINEL_4_8D_DO_NOT_SURFACE";
const FIXTURE = resolve("tests/e2e/fixtures/staging-smoke/sentinel-lecture.vtt");
const BUDGET_MS = 15 * 60_000; // §3: 15-min hard cap, enforced here (not the Playwright timeout)
const POLL_MS = 10_000; // §3: ≤10 s backoff

type ApiResult = { status: number; body: any; text: string };

async function getJson(api: APIRequestContext, path: string): Promise<ApiResult> {
  const r = await api.get(path);
  const text = await r.text();
  return { status: r.status(), body: text ? JSON.parse(text) : null, text };
}
async function postJson(api: APIRequestContext, path: string, data?: unknown): Promise<ApiResult> {
  const r = await api.post(path, data === undefined ? undefined : { data });
  const text = await r.text();
  return { status: r.status(), body: text ? JSON.parse(text) : null, text };
}

async function appUserIdByEmail(adminApi: APIRequestContext, email: string): Promise<string> {
  const r = await getJson(adminApi, "/admin/users?limit=200&offset=0");
  expect(r.status, "GET /admin/users").toBe(200);
  const user = (r.body as Array<{ id: string; email: string }>).find((u) => u.email === email);
  if (!user) throw new Error(`AppUser not found for ${email} (was the 4.8b bootstrap run?)`);
  return user.id;
}

async function pollUntil(label: string, predicate: () => Promise<boolean>): Promise<void> {
  const start = Date.now();
  for (;;) {
    if (await predicate()) return;
    if (Date.now() - start >= BUDGET_MS) {
      throw new Error(`[budget] ${label} did not complete within ${BUDGET_MS / 60_000} min — FAIL LOUD`);
    }
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

function extractModelIds(body: unknown): string[] {
  const found = new Set<string>();
  const walk = (node: unknown) => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (node && typeof node === "object") {
      for (const [k, v] of Object.entries(node)) {
        if (typeof v === "string" && /model/i.test(k)) found.add(v);
        else walk(v);
      }
    }
  };
  walk(body);
  return [...found];
}

// Measure SSE progressive delivery from a REAL browser over the D1 cross-origin transport — Playwright's
// APIRequestContext buffers the whole body, so chunk-arrival timing must be read in-page via fetch+reader.
async function measureSseProbe(browser: Browser, env: StagingEnv, adminSession: Session) {
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await page.goto(env.baseURL);
    return await page.evaluate(
      async ({ apiURL, token }) => {
        const res = await fetch(`${apiURL}/internal/sse-probe`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok || !res.body) return { ok: false, chunks: 0, maxDeltaMs: 0, status: res.status };
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        const times: number[] = [];
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          const events = decoder.decode(value).split("\n\n").filter((b) => b.startsWith("data:"));
          for (let i = 0; i < events.length; i++) times.push(performance.now());
        }
        let maxDeltaMs = 0;
        for (let i = 1; i < times.length; i++) maxDeltaMs = Math.max(maxDeltaMs, times[i] - times[i - 1]);
        return { ok: true, chunks: times.length, maxDeltaMs, status: res.status };
      },
      { apiURL: env.apiURL, token: adminSession.access_token },
    );
  } finally {
    await context.close();
  }
}

test("4.8d staging smoke — membership+publish visibility gate (hook-free)", async ({ browser }) => {
  const env = stagingEnv();
  const adminId = identity("BOOTSTRAP_ADMIN");
  const lecturerId = identity("BOOTSTRAP_LECTURER");
  const studentId = identity("BOOTSTRAP_STUDENT");
  const runId = `e2e-${Date.now().toString(36)}-r48d`;

  // Real, hook-free logins (real user JWTs — not service-role, not __xyzE2E).
  const adminSession = await signIn(env, adminId);
  const lecturerSession = await signIn(env, lecturerId);
  const studentSession = await signIn(env, studentId);
  const adminApi = await apiContextFor(env, adminSession);
  const lecturerApi = await apiContextFor(env, lecturerSession);
  const studentApi = await apiContextFor(env, studentSession);

  const artifact: Record<string, unknown> = { runId, startedAt: new Date().toISOString() };

  try {
    // Roles are real + correct (the student token is genuinely a student).
    expect((await getJson(adminApi, "/me")).body.role).toBe("admin");
    expect((await getJson(lecturerApi, "/me")).body.role).toBe("lecturer");
    expect((await getJson(studentApi, "/me")).body.role).toBe("student");

    const lecturerUserId = await appUserIdByEmail(adminApi, lecturerId.email);
    const studentUserId = await appUserIdByEmail(adminApi, studentId.email);

    // S0 — admin creates the runId-scoped module (lecturer owner) + its draft sections.
    const create = await postJson(adminApi, "/admin/modules", {
      title: `4.8d smoke ${runId}`,
      description: `staging smoke ${runId}`,
      ownerId: lecturerUserId,
      timezone: "UTC",
      startsOn: "2026-01-12",
      endsOn: "2026-05-01",
    });
    expect(create.status, "POST /admin/modules").toBe(201);
    const moduleId = create.body.id as string;
    artifact.moduleId = moduleId;

    const sectionsResp = await getJson(adminApi, `/modules/${moduleId}/sections`);
    expect(sectionsResp.status).toBe(200);
    const sections = sectionsResp.body as Array<{ id: string; title: string; type: string }>;
    const lecture = sections.find((s) => s.type === "lecture") ?? sections.find((s) => s.title?.startsWith("Lecture"));
    if (!lecture) throw new Error("no lecture section was generated for the module");
    const sectionId = lecture.id;
    artifact.sectionId = sectionId;

    // NC1 — STUDENT not yet a member → 404 (row P). Capture the body.
    const nc1 = await getJson(studentApi, `/student/sections/${sectionId}/summaries`);
    expect(nc1.status, "NC1 non-member → 404").toBe(404);

    // S1/S2 — admin assigns the lecturer (owner may already be a member) + the student.
    const assignLecturer = await postJson(adminApi, `/admin/modules/${moduleId}/members`, {
      userId: lecturerUserId,
      role: "lecturer",
    });
    expect([201, 409], "assign lecturer").toContain(assignLecturer.status);
    const assignStudent = await postJson(adminApi, `/admin/modules/${moduleId}/members`, {
      userId: studentUserId,
      role: "student",
    });
    expect(assignStudent.status, "assign student").toBe(201);

    // NC2 — STUDENT is now a member, but the section is DRAFT → 404 (row D), BYTE-IDENTICAL to NC1.
    const nc2 = await getJson(studentApi, `/student/sections/${sectionId}/summaries`);
    expect(nc2.status, "NC2 member+draft → 404").toBe(404);
    // THE assertion: the two 404 bodies equal EACH OTHER (existence-leak proof), not a hardcoded string.
    expect(nc2.body, "NC1≡NC2 byte-identical 404").toEqual(nc1.body);
    artifact.nc1_eq_nc2 = JSON.stringify(nc1.body) === JSON.stringify(nc2.body);

    // S3 — lecturer uploads the fixture → hosted pipeline.
    const upload = await lecturerApi.post(`/modules/${moduleId}/sections/${sectionId}/transcript`, {
      multipart: { file: { name: "sentinel-lecture.vtt", mimeType: "text/vtt", buffer: readFileSync(FIXTURE) } },
    });
    expect(upload.status(), "transcript upload").toBe(201);

    let finalStatus: any = null;
    await pollUntil("pipeline → summarized", async () => {
      const s = await getJson(lecturerApi, `/modules/${moduleId}/sections/${sectionId}/transcript-processing-status`);
      if (s.status !== 200) return false;
      finalStatus = s.body;
      const overall = s.body.overallState ?? s.body.overall_state;
      return overall === "summarized" || overall === "failed";
    });
    // §3 post-smoke app-data assertion (real status projection, not RQ internals).
    expect(finalStatus.overallState ?? finalStatus.overall_state, "overallState terminal").toBe("summarized");
    const steps = (finalStatus.steps ?? {}) as Record<string, any>;
    for (const [name, value] of Object.entries(steps)) {
      const state = (value && typeof value === "object" ? value.state : value) ?? "unknown";
      expect(["completed", "not_applicable"], `step ${name} not failed/retryable`).toContain(state);
    }

    // Canary (best-effort, hook-free, non-vacuous when available): the LECTURER can reach the raw
    // transcript and the sentinel is genuinely in it — so its absence from the student surface is a
    // live guarantee. The student-absence assertions below are the rigorous NC4 regardless.
    const lecturerTranscript = await getJson(lecturerApi, `/modules/${moduleId}/sections/${sectionId}/transcript`);
    artifact.canary_lecturer_sees_sentinel = lecturerTranscript.status === 200 && lecturerTranscript.text.includes(SENTINEL);

    // rule-11: capture the real K2Think model IDs from the lecturer summary provenance (both routes).
    const lecturerSummaries = await getJson(lecturerApi, `/modules/${moduleId}/sections/${sectionId}/transcript-summaries`);
    artifact.k2thinkModelIds = extractModelIds(lecturerSummaries.body);

    // S4 — lecturer PUBLISHES.
    expect((await postJson(lecturerApi, `/modules/${moduleId}/sections/${sectionId}/publish`)).status, "publish").toBe(200);

    // NC3 — STUDENT is a member AND the section is published → 200, both summaries.
    const nc3 = await getJson(studentApi, `/student/sections/${sectionId}/summaries`);
    expect(nc3.status, "NC3 member+published → 200").toBe(200);
    expect(nc3.body.summaries.brief.state).toBe("ready");
    expect(nc3.body.summaries.detailed.state).toBe("ready");
    expect(nc3.body.summaries.brief.content).toBeTruthy();
    expect(nc3.body.summaries.detailed.content, "detailed validator section").toContain("Overview");

    // NC4 — raw transcript NEVER visible: THREE independent surfaces (MF1).
    // (2) API — the REAL one: no raw-transcript text in any student response.
    for (const path of [
      `/student/modules/${moduleId}/sections`,
      `/student/sections/${sectionId}`,
      `/student/sections/${sectionId}/summaries`,
    ]) {
      const r = await studentApi.get(path);
      expect(r.status(), `student ${path}`).toBe(200);
      expect(await r.text(), `sentinel absent from ${path}`).not.toContain(SENTINEL);
    }
    // (3) No signed URL — the most dangerous surface: no signed storage URL / raw-file ref in the student
    //     payload, and every transcript text-bearing endpoint rejects the student token (no student route
    //     mints a signed URL).
    expect(nc3.text, "no signed storage URL in student payload").not.toMatch(/token=|X-Amz|[?&]sig=|\.vtt/i);
    for (const path of [
      `/modules/${moduleId}/sections/${sectionId}/transcript`,
      `/modules/${moduleId}/sections/${sectionId}/transcript-summaries`,
      `/modules/${moduleId}/sections/${sectionId}/transcript-active-summary-preview`,
    ]) {
      expect((await studentApi.get(path)).status(), `student blocked from ${path}`).toBe(403);
    }
    // (1) UI — the WEAKEST (DOM-absence ≠ security): no transcript text on the rendered student page.
    const studentContext = await browser.newContext();
    await seedBrowserSession(studentContext, env, studentSession);
    const studentPage = await studentContext.newPage();
    await studentPage.goto(`/student/modules/${moduleId}/sections/${sectionId}`);
    await expect(studentPage.getByTestId("student-section-detail")).toBeVisible({ timeout: 30_000 });
    const pageText = await studentPage.locator("body").innerText();
    expect(pageText).not.toContain(SENTINEL);
    expect(pageText).not.toContain("sentinel-lecture.vtt");
    await expect(studentPage.getByText(/view transcript/i)).toHaveCount(0);
    // §8 hosted half: the staging artifact has no token-override hook.
    expect(await studentPage.evaluate(() => typeof (window as any).__xyzE2E !== "undefined")).toBe(false);
    await studentContext.close();

    // Supporting hosted proofs.
    expect((await getJson(studentApi, "/health")).status, "/health").toBe(200);
    expect((await getJson(studentApi, "/health/ready")).status, "/health/ready (alembic head)").toBe(200);

    // SSE probe (C1): chunks arrive PROGRESSIVELY over D1 (inter-chunk delta preserved), not one flush.
    const sse = await measureSseProbe(browser, env, adminSession);
    expect(sse.chunks, "SSE chunk count").toBeGreaterThanOrEqual(3);
    expect(sse.maxDeltaMs, "SSE inter-chunk spread (not buffered into one flush)").toBeGreaterThan(200);
    artifact.sse = sse;

    // Artifact identity — machine-written by the run that passed (O4); the report ingests it.
    artifact.gitSha = process.env.STAGING_GIT_SHA ?? null;
    artifact.backendImageDigest = process.env.STAGING_BACKEND_IMAGE_DIGEST ?? null;
    artifact.frontendImageDigest = process.env.STAGING_FRONTEND_IMAGE_DIGEST ?? null;
    artifact.alembicHead = process.env.STAGING_ALEMBIC_HEAD ?? null;
    artifact.embeddingModelRevision = process.env.EMBEDDING_MODEL_REVISION ?? null;
    artifact.finishedAt = new Date().toISOString();
    const outPath = resolve("test-results/4.8d-artifact-identity.json");
    mkdirSync(dirname(outPath), { recursive: true });
    writeFileSync(outPath, `${JSON.stringify(artifact, null, 2)}\n`);
  } finally {
    await adminApi.dispose();
    await lecturerApi.dispose();
    await studentApi.dispose();
  }
});
