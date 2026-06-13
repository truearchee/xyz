# XYZ LMS — Development Roadmap v3.1

**Approach:** Option C — Walking Skeleton, then widen.
**Supersedes:** Roadmap v2. The Client Edge Recovery Plan remains the archived implementation record for 4.3.5.
**v3.1 change:** design-plan linkage notes added — each stage now carries a **Design input** line. No scope or ordering changes.
**Companion document:** `knowledge/design-plan.md` (Design Plan v1) — the visual reference for this roadmap. How it plugs in is defined in the **Design plan linkage** block after the cross-cutting rules; the per-stage **Design input** lines say exactly which design-plan section feeds each stage's spec.
**Permanent rule:** No backend slice merges without a thin UI slice and a browser-verifiable gate.
**Repo rule (new in v3):** This file lives at `knowledge/roadmap.md`. Its status table is updated **in the same commit** as the work that closes a stage (extension of cross-cutting rule 12). A roadmap living outside the repo drifts — v2 demonstrated this by still reading "4.4 NOT STARTED" after 4.4 shipped at `442f221`.

---

## Governing principle (unchanged)

Do not build horizontally isolated backend layers. Every stage proves a thin vertical path:

```
Browser
→ frontend route / component
→ authenticated API call
→ backend service
→ database / storage / worker
→ observable result back in the browser
```

Backend tests are necessary but not sufficient. A phase gate closes only when the feature is **browser-verifiable**. For infrastructure-heavy work, "UI slice" means a real, browser-observable result (a status, an output, a visibility rule taking effect) — not a museum for vectors.

---

## The UI proof obligation (unchanged)

Every stage carries one line stating the thing a human must be able to *see happen* in a real browser, against the real backend, for the stage to count. A component rendering against a mock does not satisfy it. Only real browser → real backend → real result satisfies it.

---

## Status vocabulary (unchanged)

```
NOT STARTED      — no work begun
BACKEND VERIFIED — backend built + tested. Browser gate NOT passed. This is NOT done.
UI PENDING       — backend verified; browser gate explicitly scheduled
FULLY VERIFIED   — backend AND browser gate both pass (product/infra stages)
DONE             — governance stages where no browser gate applies (Stage 0 only)
```

**BACKEND VERIFIED is not DONE.**

---

## Current reality

```
✅ Stage 0     Knowledge system / ADRs / stack lock      DONE
✅ Stage 1     Repo skeleton / KM1                        FULLY VERIFIED  (gate: 4.3.5a)
✅ Stage 2     Identity + access / P0                     FULLY VERIFIED  (gate: 4.3.5b + 4.3.5c)
✅ Stage 3     Content + visibility / P1                  FULLY VERIFIED  (gate: 4.3.5a + 4.3.5d)
✅ Stage 4.1   Transcript upload                          FULLY VERIFIED  (gate: 4.3.5e)
✅ Stage 4.2   Transcript parsing                         FULLY VERIFIED  (gate: 4.3.5e)
✅ Stage 4.3   Transcript chunk persistence               FULLY VERIFIED  (gate: 4.3.5e)
✅ Stage 4.3.5 Client Edge Recovery                       COMPLETE
✅ Stage 4.4   Embeddings                                 FULLY VERIFIED  (gate: 4.4 embedding browser run)
✅ Stage 4.5   AI infrastructure + summary generation   FULLY VERIFIED  (gate: 4.5d browser gate + full E2E + real-provider smoke)
   Stage 4.5.1 Map-reduce summarization (F-4.5-51)        4.5.1a BACKEND VERIFIED  (engine: partition→map→reduce + §3.3 tiered guard + C3 resume; backend 436/0; deterministic sentinel content-flow proof). 4.5.1b (brief-from-detailed + gating + backfill) + 4.5.1c (real-provider smoke + browser gate + 4.7 RE-GATE + backfill) PENDING. NOTE: 4.7 already shipped on the Option-A truncation path → 4.5.1c MUST backfill existing truncated summaries before Stage 5 reads them.
✅ Stage 4.6   Replacement / retry / supersession         FULLY VERIFIED  (gate: 4.6d replace+retry browser run)
✅ Stage 4.7   Student-facing summaries                   FULLY VERIFIED  (gate: 4.7 student-summaries browser run)
Stage 4.8   First hosted deploy (staging)              BACKEND VERIFIED  (4.8a–d built + locally verified; hosted browser gate deferred — trigger: before Stage 8.3 or demo/real-user exposure)
Stage 4.9   Frontend foundation + platform hygiene     FULLY VERIFIED*  (Tailwind v4 two-layer tokens + shell, 9-component lib, Vitest harness, §8 gates + CI + Husky, bounded restyle, hygiene batch; backend 421 + full active E2E 11/11 green) — *3 developer-owned residuals stated below, not hidden
Stage 5     Shared quiz engine + event spine           NOT STARTED
Stage 5.5   Module schedule & section metadata         NOT STARTED  (new in v3; parallel-OK with 5; blocks 6)
Stage 6     Complete quiz modes                        NOT STARTED
Stage 7     Glossary                                   NOT STARTED
Stage 8     Assistant                                  NOT STARTED
Stage 9     My Progress                                NOT STARTED
Stage 10    Gamification                               NOT STARTED
Stage 11    Proactive analytics                        NOT STARTED
Stage 12    Release hardening                          NOT STARTED
```

**\* Stage 4.9 FULLY VERIFIED — three developer-owned residuals, stated not hidden** (a bare FULLY VERIFIED
hiding pending human/remote steps is not defensible):
1. **Design-match visual sign-off** — evidence captured (16 desktop+mobile screenshots in
   `steps/stage-04/4.9-design-review/`, all 8 surfaces 0px horizontal overflow at 375px); the *visual
   judgement* is the developer's, as 4.6/4.7 were human-stamped.
2. **Keyboard pass** — the manual checklist is authored (`steps/stage-04/4.9-keyboard-checklist.md`, 4.9d);
   the run-through is the developer's. Full automated keyboard + axe = Stage 12 (ADR-048).
3. **Remote-CI enforcement** — local gate proven (Husky pre-commit demonstrably blocks; `ci.yml` shipped);
   marking the checks **required** on `main` via branch protection + the failing-merge demo is **F-4.9-5**
   (owner: developer, trigger: next push). A CI job that runs but isn't required is the "yaml costume" failure mode.
All automated evidence is green: backend `pytest` 421 (0 httpx deprecations under `-W error`); full active
Playwright suite 11/11 (CORS credentials off); §8 gates green; contrast 35/35; mobile sanity 8/8 at 0px.

---

## Completed stages 0 → 4.4 (compressed)

v3 compresses completed stages. Their full definitions, gates, and reports live in the per-stage `knowledge/specs|plans|steps` trios and `STATUS.md` — that is the authority for finished work; duplicating it here is how drift happens. Their browser gates remain **live assertions**: under new rule 14 the full active E2E suite re-runs at every stage close.

**Carried debt from completed stages — each item has an owner and a payment date:**

```
Transcript recovery for stuck rows (uploaded/parsing/queued crash states)   → Stage 4.6
Storage orphan cleanup after failed deletes/replacements                    → Stage 4.6 (reconciliation job)
Stage 3 content-visibility E2E spec archived, not in active suite           → restored as Stage 4.7 hard prerequisite
Browser-gate assertions pinned to overall terminal state, not steps          → Stage 4.5 hard prerequisite
Status badge polling model (2.5s / 60s hard timeout)                        → reworked in Stage 4.5d
week_number / session_date / due_at columns exist but never populated;
fixed 4-section template instead of schedule-driven generation              → Stage 5.5
Frontend: zero unit tests, inline styles only                               → Stage 4.9  ✓ PAID (Vitest harness 4.9d; restyle 4.9c; check:inline-styles gate)
httpx ASGI-shortcut deprecation (83 warnings; future upgrade breaks suite)  → Stage 4.9 hygiene batch  ✓ PAID 4.9e (ASGITransport ×3 files; 0 deprecations under -W error)
CORS allow_credentials=True unnecessary with pure Bearer auth               → Stage 4.9 hygiene batch  ✓ PAID 4.9e (dropped; cross-origin E2E green)
No client-regen alias in frontend/package.json (F008)                       → Stage 4.9 hygiene batch  ✓ PAID 4.9e (gen:api + README)
Backend static type checker (mypy/pyright) — frontend tsc shipped 4.9d only → Stage 12 (NOT closed by 4.9)
E2E --workers=1 capacity (4.7-R2: scale embedding_worker / tolerant poll)   → Stage 12 (NOT in the §7 batch)
Hosted Postgres extension bootstrap not automated (F006)                    → Stage 4.8
4.8 hosted gate (pooler pair → NC1≡NC2 → NC4 three-surface → artifact JSON)  → owner: developer; trigger: before Stage 8.3, or before any demo / real-user exposure, whichever comes first
Signed URLs remain valid until TTL after unpublish                          → decision recorded in Stage 12
can_publish derived from role rather than membership                        → reviewed in Stage 12 authz pass
No custom exception handlers (raw default 500 bodies)                       → Stage 12
No roadmap file in repo (F001)                                              → fixed by this document + repo rule above
```

Nothing in the completed work needs reverting. The provenance CHECK constraint, pinned model revision baked into the image, enqueue-after-commit, partial-unique one-active indexes, and the 401/403 boundary are correct and stay.

---

## Cross-cutting rules

Rules 1–5, 7–10, and 13 carry forward from v2 unchanged in substance:

### 1. Every stage has a browser gate
Backend scope, thin UI scope, UI proof obligation, browser gate, exclusions, knowledge updates. No backend-only acceptance.

### 2. Frontend can be thin, never fake
Plain forms and ugly tables are acceptable. Mocked frontend state, fake successes, hardcoded roles, and frontends pretending a backend feature exists are not.

### 3. Generated API client stays authoritative
OpenAPI change → regenerate TypeScript client → commit → consume via generated client or centralized wrapper. The only sanctioned direct-`fetch` exception remains `frontend/src/lib/api/upload.ts`.

### 4. Auth model stays unchanged
Supabase browser login → Bearer token → backend JWT validation → `GET /me` resolves app context (active memberships only). No `/auth/login` without an intentional redesign.

### 5. 401 and 403 are handled differently
401 → clear session, redirect to `/login`. 403 → keep session, render unauthorized state. Never redirect to login on 403.

### 6. AI is infrastructure, not feature code — AMENDED in v3
No direct model calls from feature services, ever:
```
LLMProvider → PromptRegistry → ContextBuilder → RateLimiter → AIRequestLog → OutputValidator
```
v3 additions:
- The provider stack lives in **`platform/llm`** — it is infrastructure consumed by domains. The `backend/app/ai/` placeholder is migrated or deleted in 4.5a.
- The `LLMProvider` interface defines **both `complete()` and `stream()` from day one**. `stream()` may raise NotImplemented until Stage 8.3, but the boundary shape is fixed now so Stage 8 pressure never becomes a reason to bypass the gateway. The deterministic test adapter implements the same interface.
  - **Annotation (4.5a, [[decisions/adr-028-llm-gateway-provider-separation]]):** the public `complete()`/`stream()` contract lives on **`LLMGateway`**, not `LLMProvider`. `LLMProvider` is a thin transport adapter (`send`/`stream_raw`); the gateway owns render/budget/limit/log/validate so a provider can never be invoked outside the chain. Intent preserved and strengthened.
- Every AI-generated artifact carries the **embedding-style provenance set**: `modelId`, `promptVersion`, `backendUsed`, source checksum / input hash, `generatedAt` — enforced by DB constraints where practical — plus an idempotency key per job and a one-active partial-unique index for in-flight jobs of that type. This closes v2 open item #2: the fields are confirmed for all AI tables.
- **AIRequestLog stores metadata and hashes, never raw transcript payloads.** Transcripts contain student speech; duplicating prompts into a log table creates a second PII store. Content hash plus optional truncated debug text only.
- Hard rule preserved: **AIRequestLog table + write path exist BEFORE the first K2Think call.**

### 7. Event spine starts in Stage 5
`StudentActivityEvent` lives in `platform/events`. Source action and event insert commit in the same DB transaction. Idempotency `source_id` points to the action instance. Gamification consumes events; it never owns them.

### 8. platform/query is read models only
Cross-domain reads live in `platform/query`; never business decisions. Domains own their writes and never import each other.

### 9. Testing standard for every browser gate
Real browser, real backend, real DB — no mocks on the critical path. Separate browser contexts for roles. True cross-origin CORS. Session asserted via `getSession()` + `GET /me`. E2E Supabase allowlisted; prefixed `e2e/{runId}/` storage keys; cleanup deletes only that prefix.

### 10. Stop-and-escalate
When plan and reality disagree, stop and write a findings note to `knowledge/steps/findings-{stage}.md`. A workaround that "makes the test pass" usually hides the exact problem the gate was built to find.

### 11. AI testing at the provider boundary — AMENDED in v3
CI/normal Playwright runs may use a deterministic LLMProvider test adapter **at the provider boundary only** — the full code path still runs (AIRequestLog written, provenance stored, output validated). Before any AI stage is FULLY VERIFIED, one dedicated E2E smoke runs against the **real** configured K2Think provider, recorded in `knowledge/steps/{stage}-real-provider-smoke.md`.
v3 additions: the real-provider smoke **asserts the model ID echoed in the response matches the configured identifier** (the IFM reference warns deployment aliases may differ from documented IDs). If the K2 reasoning level (Low/Medium/High) is a real request parameter — confirm at onboarding — it is part of the provider signature and logged per request.

### 12. Knowledge updates are mandatory in every session — AMENDED in v3
Every session lists exact files to update; knowledge files update in the same commit as code. v3 addition: **this roadmap's status table is part of those mandatory updates** for any stage-closing session.

### 13. Finding resolution
A finding is resolved only as: fixed in the current block / deferred to a named session / accepted with written rationale / rejected with explanation. Unresolved findings block FULLY VERIFIED.

### 14. Full E2E suite at every stage close — NEW in v3
The **entire active Playwright suite** re-runs when a stage closes, not just the new gate. Green inherited from a prior session's report is not green. **An archived spec is a deleted spec** — if an assertion matters (e.g. "students never see unpublished content"), it lives in the active suite or it does not exist.

### 15. AI capacity is budgeted in three dimensions; request count is sacred — NEW in v3
The K2 reference's "token volume is not the constraint" holds for chat-sized requests only. A full-transcript summary carries ~13–18k prompt tokens; at Nvidia's 105k TPM that is an effective ceiling of ~5 such calls/minute — TPM binds before RPM. Therefore:
- All AI calls pass through a **shared Redis limiter, per backend**, budgeting **requests/min** (20 Cerebras / 10 Nvidia), **tokens/min** (100k / 105k — prompt tokens computed before the call; completions capped by an explicit per-prompt `max_tokens` stored in the PromptRegistry), and **concurrency** (10).
- The limiter takes a **priority parameter** from day one so interactive traffic (Stage 8 assistant) keeps reserved headroom over background jobs — even while the MVP uses only the background priority.
- 429 backoff happens **inside the call path under the limiter**. RQ job retries are reserved for provider 5xx and invalid-output failures.
- Feature design minimizes call count: **one call per summary, one call per quiz generation — never per chunk, never per question.**

---

## Design plan linkage — NEW in v3.1

The design plan (`knowledge/design-plan.md`) is the second input document for this roadmap. The model is **two reference documents feeding one spec per stage** — there is never a separate "design step" outside this roadmap.

```
How it works:

1. Stages 4.6 → 4.8: NO design work. UI stays thin (rule 2). The 4.5d–4.7
   surfaces are added to the Stage 4.9 retroactive restyle list.

2. Stage 4.9 is the ONLY standalone design stage. Its input spec is
   Design Plan Part 1 (tokens + component library + signature element),
   Part 4 (accessibility baseline), and Part 5 (mobile strategy).
   Its deliverable includes `knowledge/design-system.md` — written from the
   SHIPPED code (code wins over docs).

3. From Stage 5 onward, every stage spec is written from TWO inputs:
   this roadmap (what to build) + the design-plan section named in that
   stage's "Design input" line (what it looks like). One spec per stage,
   both concerns, locked together BEFORE implementation begins.

4. No second gate for design. The existing browser gate proves the UI
   functions; "matches the locked design spec" is a light check at stage
   close (see the acceptance rule). The heavy consistency sweep is
   batched at Stage 12 (Design Plan Part 3).
```

Each stage below carries a **Design input** line stating exactly which design-plan section feeds its spec.

---

## Stage 4.5 — AI Infrastructure + Summary Generation

**Status:** ✅ FULLY VERIFIED (2026-06-11). 4.5a (platform/llm foundation) → 4.5b (first real K2Think
call, gate 2.B) → 4.5c (detailed summary, routing split live) → 4.5d (lecturer UI + browser gate +
full E2E + real-provider smoke). All three close-out gates green: full active E2E suite
([[steps/stage-04/4.5d]]), forced-fault browser coverage, and the real-provider smoke
([[steps/stage-04/4.5d-real-provider-smoke]] — PASS, model-ID echo matched on both routes, rule 11).
adr-025/026/027/028 recorded. **F-4.5-27 RESOLVED 2026-06-13** — real key obtained; K2-Think-v2 live-verified
end-to-end on both routes (real grounded summaries, validator-conformant); ADR-025 deviation accepted as
production (see [[steps/stage-04/4.5-real-provider-smoke]]); dev `.env`=k2think, E2E/CI forced deterministic
(docker-compose.e2e.yml). Residual: rotate the exposed key. (Was: open, accepted-with-trigger, rule 13.)
(intended models inaccessible — switch-back = config/prompt edit), F-4.5-28 (backendUsed not
response-verifiable). Carry-forward to Stage 4.6: F-4.5-47 (RQ scheduler / per-request fault injection).

**Goal:** build the complete AI provenance and capacity infrastructure *before* the first K2Think call, then generate brief and detailed summaries.

**Hard prerequisites (block the stage from starting):**
```
1. IFM API key live and verified; exact model identifiers confirmed against the
   deployment (aliases may differ from docs); reasoning-level parameter semantics
   confirmed with IFM. Onboarding lead time is real — verify now, not at 4.5d.
2. Existing browser-gate assertions pinned to step-level facts
   (e.g. steps.embed === 'completed'), with a recorded regression run — so 4.5
   ADDS a pipeline step instead of rewriting prior gates. This ends the
   terminal-state churn (chunked → embedded → summarized) permanently.
3. Status projection supports per-step failure: "embeddings succeeded, summary
   failed" must be representable and visible. Stage 4.6 retry keys off this.
```

**Backend scope:** `platform/llm` (LLMProvider with `complete()` + `stream()` signatures; deterministic test adapter); PromptRegistry over a versioned flat-file `/prompts` directory — loaded and validated at startup, exposing name, version, content, `max_tokens`, model, backend, reasoning level (this closes v2 open item #1: **flat files, not a DB table** — git gives review/audit/deploy semantics free; the registry abstraction keeps a DB swap open post-MVP); the rule-15 Redis limiter; `AIRequestLog`; dedicated `ai` RQ queue + worker container (mirroring the embedding-worker isolation pattern); OutputValidator; `GeneratedLectureSummary`; brief + detailed generation as **two separate IngestionJob types** (`generate_brief_summary`, `generate_detailed_summary` — already enumerated in Slice 2); dev re-enqueue script.

**Key design locks (deviations recorded as ADRs):**
```
Routing split (ADR — deviates from Slice 2's Think-for-both):
  brief summary    → K2-V2-Instruct via Cerebras  (plain writing task; 32k context
                     fits a full transcript; separate rate budget)
  detailed summary → K2-Think-v0 via Nvidia        (reasoning task; 128k context)
  The two jobs draw on SEPARATE backend budgets and run concurrently; the brief
  summary lands in the UI while the detailed one is still generating.

Generation shape: ONE call per summary over the FULL normalized transcript text.
  Never map-reduce over chunks — chunks are Stage 8 retrieval infrastructure.
  A 90-minute lecture (~13–18k tokens) fits both models and the 65,536 request cap.

AIRequestLog row: feature, modelId, promptVersion, backendUsed, reasoning level,
  prompt/completion/total tokens (from the response usage field), latency, status
  (succeeded | failed | rate_limited | invalid_output), attempts, idempotency key,
  context refs (transcriptId, sectionId), input content hash, optional truncated
  debug text. Index (feature, created_at) — "tokens by feature by day" must be one
  query; this is the cost dashboard until real observability exists.

Provenance + idempotency mirror the embedding pattern: GeneratedLectureSummary
  carries sourceTranscriptChecksum + input hash + provenance set; the one-active
  partial-unique index pattern (migration 0007) extends to both summary job types.

Failure contract: a terminally failed summary job leaves a clean, retryable
  IngestionJob + AIRequestLog linkage. That record is the contract Stage 4.6's
  lecturer retry consumes. The 4.5 dev re-enqueue script is a development tool,
  not the product retry path.

Prompts carry the semantic filtering: normalization is structural-only by design,
  so the prompt explicitly instructs ignoring greetings, mic checks, admin
  announcements, small talk (Slice 2's list). The detailed-summary OutputValidator
  asserts the required section structure is present (Overview, Key Concepts,
  Important Definitions, Main Explanations, Examples, Exam-Relevant Points, Lab
  notes if applicable) — not merely non-empty text.

Backfill: transcripts completed before 4.5 will lack summaries. Dev path: the
  re-enqueue script. Product path: Stage 4.6 lecturer retry. Decided here so it
  never becomes an improvised migration.
```

**Thin UI scope:** lecturer sees summary generation status; lecturer views brief and detailed summaries. **Status badge rework (4.5d):** backoff polling, no 60-second hard timeout (limiter queueing + long completions + 429 backoff routinely exceed it), passive "generating" state, per-step failure display without stack traces.

**UI proof obligation:** the lecturer triggers the pipeline and *reads a real AI-generated summary* in the browser, produced through the logged AI infrastructure.

**Browser gate:**
```
Lecturer uploads transcript → parsed/chunked/embedded → both summary jobs run
→ AIRequestLog rows created → summaries stored with full provenance
→ lecturer sees brief summary first, detailed summary when ready
→ a forced invalid output is rejected, retried, and logged
```

**Sub-sessions (specs written before implementation):**
```
4.5a  platform/llm foundation: provider, registry, limiter, AIRequestLog,
      ai queue/worker, test adapter, dev re-enqueue script.
      HARD GATE: no K2Think call exists before this session lands.
4.5b  Brief summary generation (V2 / Cerebras) + ADR for the routing split
4.5c  Detailed study summary generation (Think / Nvidia) + section validator
4.5d  Lecturer summary UI, status badge rework, browser gate,
      real-provider smoke (rule 11, with model-ID assertion)
```

**Done means:** AIRequestLog exists before the first call; both summaries generated through the full stack; provenance + token usage stored; deterministic adapter used in CI at the provider boundary only; real-provider smoke recorded; full E2E suite green (rule 14); browser observes the result.

**Exclusions:** no quiz/glossary/assistant generation, no lecturer editing of summaries, no student visibility (4.7), no streaming transport (8.3 — interface only), no map-reduce summarization.

---

## Stage 4.6 — Replacement / Retry / Supersession

**Status:** IN PROGRESS. **4.6a foundation BACKEND VERIFIED** (2026-06-11): lifecycleState migration +
lineage (`is_active` removed), one-active + one-pending indexes, section-locked pending creation +
`tryActivatePendingTranscript` atomic swap, `transcripts/domain/summary_eligibility` + read-only
`ActiveTranscriptSummaryResolver`, per-row provenance stamps, env-gated pipeline fault harness; backend
305 passed, migration 0010 round-trips on a fresh DB, frontend `tsc` clean. See
[[specs/stage-04/4.6a-lifecycle-supersession-foundation]] / [[steps/stage-04/4.6a-lifecycle-supersession-foundation]],
[[decisions/adr-029-transcript-replacement-atomic-swap]], [[decisions/adr-030-summary-eligibility-domain-resolver-split]].
**4.6b retry BACKEND VERIFIED** (2026-06-11): lecturer retry endpoint
(`POST …/transcript/{transcriptId}/retry`) resumes from the earliest failed step over the DAG; summaries
decoupled to fork from parse (embed failure no longer blocks summaries); every destructive write fenced
against superseded/stale attempts; sanitized `failureCategory` + `retryable` on the status projection;
migration 0011 (failure-category enum + parse one-active index). Backend 329 passed, fresh-DB round-trip,
tsc clean. See [[specs/stage-04/4.6b-retry-fencing-failure-taxonomy]] /
[[steps/stage-04/4.6b-retry-fencing-failure-taxonomy]], [[decisions/adr-031-retry-resume-from-failed-step-fenced]].
**4.6c recovery BACKEND VERIFIED** (2026-06-11): stuck-row reaper (step-aware, RQ-registry/age liveness,
fenced `crashed` producer, singleton-locked, startup + admin trigger) + loss-safe storage reconciliation
(report-only default, grace window, prefix-scoped, deletion-capped, superseded retained, missing reported
never auto-fixed) + `MaintenanceRun` table (migration 0012) + admin maintenance endpoints. Backend 344
passed, fresh-DB round-trip, tsc clean. See [[specs/stage-04/4.6c-recovery-reaper-reconciliation]] /
[[steps/stage-04/4.6c-recovery-reaper-reconciliation]], [[decisions/adr-032-stuck-row-reaper-singleton]],
[[decisions/adr-033-storage-reconciliation-loss-safe]].
**4.6d lecturer UI + preview endpoint BUILT** (2026-06-11): active-summary preview endpoint (lecturer-only,
over the resolver, `hasPendingReplacement`, NO student surface) + lecturer Replace (inline confirm +
double-replacement warning) / Retry / per-step states / sanitized reason / "new version processing" badge on
the 4.5d surface; browser-gate spec (`4.6d-replace-retry.spec.ts`: retry flow + replacement continuity) +
the deterministic fencing pytest; fixed the cross-stage e2e breaks (4.3.5e 409→pending, db.mjs
lifecycle_state). Verified: backend 349 passed, frontend tsc clean, client regen, 9 e2e specs compile.
See [[specs/stage-04/4.6d-lecturer-ui-browser-gate]] / [[steps/stage-04/4.6d-lecturer-ui-browser-gate]].
Remaining for Stage 4.6: the **live browser gate** (developer-run — rebuild images, apply 0010→0012,
restart, `npx playwright`) + full active suite green → marks Stage 4.6 FULLY VERIFIED.

**Goal:** make transcript replacement and failed-processing recovery safe and observable.

**Design input:** none — build thin (rule 2). The retry/replace surfaces and per-step states join the Stage 4.9 retroactive restyle list; their *behavior* spec is this roadmap, not the design plan.

**Backend scope:** replace active transcript (old superseded, new active); **retry covers all five job types** — parse / chunk / embed / generate_brief_summary / generate_detailed_summary; retry idempotency; stale-summary detection via `sourceTranscriptChecksum` mismatch; replacement triggers full regeneration; no mixed old/new student state; failure-reason persistence; recovery for the deferred stuck-row states (uploaded / parsing / queued after crash or enqueue failure); **storage reconciliation job** — periodic diff of object-store keys against DB keys, reporting and cleaning orphans (replacement multiplies the orphaning opportunities; this debt gets an owner here).

**Thin UI scope:** lecturer replace-transcript button; retry-failed-processing button; old/new active status; per-step failed/retrying/completed states.

**UI proof obligation:** the lecturer forces a failure, clicks retry in the browser, watches it reach completed; then replaces a transcript and sees only the new one active with regenerated summaries.

**Browser gate:**
```
Upload → step forced to fail → lecturer clicks retry → reaches completed
Replace transcript → old superseded → new active → summaries regenerate
→ student-visible state never mixes old and new
```

**Testability rule (carried):** failure steps use deterministic E2E-only fault injection or seeded failed-job records — never random failure or manual DB edits. Fault injection must be impossible outside E2E/test environments.

**Done means:** replacement and retry safe; no duplicate segments/chunks/summaries from retry; reconciliation job runs and reports; browser verifies both flows; full suite green.

**Exclusions:** no transcript editing, no speaker correction, no Zoom import, no summary approval workflow.

---

## Stage 4.7 — Student-Facing Summaries

**Status:** NOT STARTED.

**Hard prerequisite:** the Stage 3 content-visibility E2E spec is **restored to the active suite** (it currently lives in archive). "Students never see unpublished content" is the most security-sensitive student-facing rule and must have a live automated browser regression before student surfaces are extended.

**Design input:** read Design Plan **§2.3 (Student Section View)** for screen *structure and content* — block order (Summary / Study Notes / Materials / Lecturer Note), labels, processing and unavailable states. Implement thin (pre-4.9, inline styles acceptable); the visual treatment lands in the 4.9 restyle. Structure from the design plan now means zero markup rework later.

**Backend scope:** student-facing summary read projection; published-section and assigned-module enforcement; processing/unavailable fallback states; no raw transcript exposure.

**Thin UI scope:** student lecture/lab page; brief + detailed summary display; processing state; unavailable state.

**UI proof obligation:** a student opens a published lecture and *reads both summaries* — and cannot see the raw transcript or any unpublished section.

**Browser gate:**
```
Student opens published lecture/lab → sees brief + detailed summary
→ does NOT see raw transcript → unpublished section hidden
→ unassigned student cannot access summary (404, not 403)
```

**Done means:** summaries visible only when allowed; fallbacks clean; restored Stage 3 spec passing in the active suite; full suite green.

**Exclusions:** no quiz generation, no glossary, no student AI chat, no transcript viewer.

---

## Stage 4.8 — First Hosted Deploy (Staging) — NEW in v3

**Status:** NOT STARTED.

**Why here:** after 4.7 the pipeline exercises every infrastructure component end-to-end (DB, storage, three worker types, AI provider, migrations) — the natural first hosted smoke. Stage 12 as the first deployment rehearsal is a classic trap, and there is one specific technical forcing function: **SSE breaks under buffering proxies, and discovering that during Stage 8.3 is expensive.** Platform constraints get discovered here, cheaply.

**Design input:** none — pure infrastructure, no new UI.

**Backend / infra scope:** hosted environment for Postgres (managed, with `vector` + `pgcrypto` bootstrap — closes F006), Redis, backend, all three workers, frontend; **explicit release-phase migration step** (migrations do not auto-run on boot — deliberate locally, fatal if forgotten hosted); secrets handling; repeatable deploy script; hosted CORS origins; **environment hygiene** — `NEXT_PUBLIC_E2E_TEST_HOOKS` and all fault-injection flags absent/disabled in hosted builds (same principle as the Stage 4.6 fault-injection rule, applied to the token-override hook).

**Thin UI scope:** none new — the existing product, served from a hosted URL.

**UI proof obligation:** the full lecturer→student summary path runs in a real browser **against the staging URL**, including one real K2Think-generated summary.

**Browser gate:**
```
Against staging: admin creates module → lecturer uploads transcript
→ pipeline completes on hosted workers → student reads both summaries
→ health endpoints green → migration step ran as a release phase
```

**Done means:** repeatable deploy documented; extension bootstrap automated; E2E hooks verifiably absent; smoke recorded in knowledge.

**Exclusions:** production hardening, autoscaling, CDN, custom domains, observability stack, CI/CD beyond the deploy script (all Stage 12 territory).

---

## Stage 4.9 — Frontend Foundation + Platform Hygiene — NEW in v3

**Status:** NOT STARTED.

**Why here:** Stages 5–8 are the heavy student-facing UI (quiz attempt flow, glossary, assistant workspace). Building three stages of UI in inline styles with zero unit tests means repainting and retro-testing all of it at Stage 12. The thin 4.5d/4.7 panels were cheap to build either way; the quiz UI is not.

**Design input — THE design stage. This is where the design plan becomes code:**
```
Input spec:        Design Plan Part 1 (1.2 tokens, 1.3 component library,
                   1.4 signature element) + Part 4 (accessibility baseline)
                   + Part 5 (mobile strategy) + Part 6 (decisions log)
Build:             tokens in Tailwind config; core components (Button, Input,
                   Card, Badge, Modal, Table, Toast, Empty State, Progress/
                   Step indicators) as code
Retroactive restyle: Design Plan §2.0 (login), §2.1 (admin), §2.2 (lecturer
                   content), §2.3 (student view) — PLUS the 4.5d–4.7 surfaces
                   (summary panels, status badge, retry/replace controls)
Deliverable:       knowledge/design-system.md, written from the SHIPPED
                   components (code wins over docs). From Stage 5 on, this
                   file replaces Design Plan Part 1 as the living authority;
                   Part 2 screen specs remain the per-stage seed source.
```

**Scope:**
```
Styling system: adopt Tailwind. App shell + shared components restyled; full
  retroactive repaint NOT required; all Stage 5+ UI must use it.
Unit test harness: Vitest. First real tests target the highest-value logic:
  wrapper.ts auth recovery (401/403 mapping), status badge step mapping,
  SessionProvider state transitions.
Hygiene batch (one tidy-up commit):
  - pin httpx deliberately or migrate tests to ASGITransport (the 83 deprecation
    warnings mean a future upgrade breaks the suite)
  - drop CORS allow_credentials=True or keep it with a written justification
    (pure Bearer auth does not need it)
  - add a client-regen alias to frontend/package.json (F008)
```

**UI proof obligation / browser gate:** per rule 14 — the **full existing E2E suite green after the restyle**, type-check green, unit tests running in CI. The gate proves the restyle broke nothing.

**Exclusions:** visual redesign, design polish, component-library buildout beyond immediate needs.

---

## Stage 5 — Shared Quiz Engine + Event Spine

**Status:** NOT STARTED.

**Goal:** shared MCQ engine + the platform activity event spine.

**Design input:** Design Plan **§2.4, post-class portions** — quiz entry card (incl. the unavailable state), attempt view, question card with all answer-option states (selected / correct / incorrect / correct-not-chosen), feedback state, score screen, mistakes-bank notice. The two-input spec rule starts here: the 5.x specs are written from this roadmap + §2.4 together, locked before implementation.

**Backend scope (v2 carried):** `QuizDefinition`, `QuizAttempt`, `QuizQuestion`, `AnswerOption`, `StudentAnswer`; `MistakeRecord` minimum schema (`retake_correct_count`, `show_in_retake_prefix`, `source_quiz_definition_id`, `source_question_snapshot`); post-class quiz availability after detailed summary; attempt created on start; AI question generation through the 4.5 infrastructure; validation; shuffling (correctness on option identity, never display letter); immediate submission; mistake creation; `StudentActivityEvent` in `platform/events` with atomic insert and idempotency keys.

**v3 additions:**
```
Generation shape: ONE AI call per quiz generation — never per question (rule 15).
Structured output via FUNCTION/TOOL CALLING (the API supports it): schema
  enforcement at the provider beats regex-parsing free text before the
  OutputValidator even runs.
Pagination envelope: the first large lists land here (attempts, mistake bank).
  Define the standard envelope now; every later list (glossary, conversations,
  events) reuses it. Retrofitting pagination at Stage 7 is the wrong time.
Schema future-proofing: questions belong to attempts (locked, correct), but the
  schema must NOT preclude a Stage 6 question POOL per QuizDefinition (generate
  into a pool, sample fresh combinations per attempt). Flag in the spec; the
  decision itself is Stage 6's.
```

**Thin UI scope:** student sees post-class quiz available; starts; answers; immediate feedback; completes; sees score. Built on the 4.9 styling system.

**UI proof obligation:** a student answers a question and sees correct/incorrect feedback *immediately* in the browser — and a wrong answer visibly becomes a recorded mistake.

**Browser gate:**
```
Student opens lecture/lab with completed summary → post-class quiz available
→ starts attempt → generated questions appear → answers → immediate feedback
→ wrong answer creates mistake → completed_quiz event inserted
  (same transaction as the score)
```

**Exclusions:** recap/exam-prep/mistakes-bank modes; retake-reinforcement UX; leaderboards; graded exams.

---

## Stage 5.5 — Module Schedule & Section Metadata — NEW in v3

**Status:** NOT STARTED. **May run in parallel with Stage 5** (admin domain, not quiz domain). **Hard prerequisite for Stage 6**; also feeds Stage 8.6 (time management) and Stage 11 (calendar seeding).

**Why:** `week_number`, `session_date`, `due_at` exist in the schema but are never populated — module creation emits a fixed 4-section template, not the schedule-driven structure Slice 1 specifies. Recap quizzes (date range), exam-prep quizzes (covered weeks), assistant time-management, and the agent's calendar all resolve scope through exactly these fields. Without this session, Stage 6 stops at a findings note in its first week.

**Design input:** Design Plan **Part 3** note for this stage — simple admin form, **no new components**; compose existing Input / Modal / Table primitives from the 4.9 system. If a screen needs a component the system doesn't have, that's a finding, not an improvisation.

**Backend scope:** module creation accepts schedule parameters (course dates, lecture days, lab days) driving section generation; admin can set/edit `week_number` / `session_date` / `due_at` per section; **backfill path for existing modules** (29 in dev); week→sections resolution query in `platform/query`.

**Thin UI scope:** admin schedule fields on module creation; per-section metadata editing in the admin UI.

**UI proof obligation:** an admin sets schedule values in the browser and a week-scoped query visibly resolves the correct sections.

**Browser gate:**
```
Admin creates module with schedule → sections carry week/date metadata
→ admin edits a section's week → coveredWeeks=[7,8] resolves exactly the
  right sections → lecturer/student views unchanged
```

**Exclusions:** lecturer section creation/delete/reorder (still excluded per Slice 1), timetable UI, calendar features (Stage 11).

---

## Stage 6 — Complete Quiz Modes

**Status:** NOT STARTED. **Hard prerequisite: Stage 5.5.**

**Design input:** Design Plan **§2.4, remaining portions** — quiz mode selector (2×2 card grid), recap/exam-prep scope selector modal, retake mistake-prefix banner — **plus** the lecturer-side `AssessmentScope` creation form and the on-demand "generating your quiz" waiting state (both flagged in the design-plan v1.1 review; spec them honestly against the capacity ADR below — minutes-long waits get a real state, not an infinite spinner).

**Backend scope (v2 carried):** `recap_period`, `exam_prep`, `mistakes_bank`; assessment scope by covered weeks (`AssessmentScope`); mistake-review prefix; retake reinforcement (`retakeCorrectCount`; prefix flag flips false after 2 correct retake answers; mistake stays in the bank).

**v3 addition — capacity decision (ADR required):**
```
The exam-week math: 30 students each starting a 6-section recap
= 180 Nvidia calls ≈ 18 minutes of queue at 10 RPM.
Resolve via question pool + per-attempt sampling (generate per section into a
pool; sample fresh combinations per attempt — preserves "retakes get new
questions" while cutting calls by an order of magnitude), OR explicitly accept
queue-wait UX with a visible generating state. Decide here; Stage 5's schema
was kept compatible with either answer.
```

**UI proof obligation:** a student retakes a quiz, sees missed questions first, answers one correctly twice across retakes, sees it drop from the prefix — while still finding it in the mistakes-bank quiz.

**Browser gate:**
```
Original quiz with mistakes → retake starts with mistake-review prefix
→ 2 correct retake answers → mistake leaves prefix → remains in bank
Lecturer defines covered weeks → exam-prep quiz draws from scoped summaries
```

**Exclusions:** formal grading, lecturer question bank, proctoring, adaptive engine, generation from raw transcript.

---

## Stage 7 — Interactive Glossary & Practice

**Status:** NOT STARTED.

**Scope as v2 / Slice 6:** folders, entries, source references, definition cache (key: normalizedTerm + subjectId + entryType, invalidated on promptVersion change — which aligns exactly with the flat-file PromptRegistry), review state, flashcards with hardcoded intervals, Learn/Test MCQ reusing Stage 5 mechanics, server-side duplicate detection, `TranslationService` abstraction + K2Think adapter, glossary activity events, `<SaveToGlossary>` shared component, KaTeX integrated early.

**Design input:** Design Plan **§2.5** — glossary layout (folder sidebar, table/card toggle), entry detail sheet with tabs, save-to-glossary popover, duplicate warning, flashcard session with flip + rating row, Learn/Test reusing §2.4 quiz components — plus the translation action/display and manual-entry modal (v1.1 review additions).

**v3 notes:** definition generation uses **K2-V2-Instruct via Cerebras** (per slice) through the shared limiter and `ai` queue — no new infrastructure; cache-hit = no model call is the primary cost control; 500-char context cap enforced server-side; entry lists use the Stage 5 pagination envelope.

**UI proof obligation:** a student highlights text in a real summary, saves it, watches the AI definition fill in asynchronously, then practises that term — all in the browser.

**Browser gate:** as v2 (save → duplicate check → entry appears → definition job → status updates → flashcards → Learn/Test → activity event).

**Exclusions:** as v2 (no shared glossary, no transcript sources, no OCR, no advanced SRS, no AI auto-saving).

---

## Stage 8 — Personal AI Assistant

**Status:** NOT STARTED.

**Backend scope (v2 carried):** conversations, folders, messages, context snapshots, tool actions; server-side context resolver; retrieval service; SSE streaming (the sanctioned FastAPI direct-path exception); mode coordinator; history; save-to-glossary action.

**Design input:** Design Plan **§2.6** — main window (two-pane), message bubbles, streaming cursor, mode selector pills, lecture-breakdown workspace, floating widget. These are the **two most complex UI surfaces in the product** (Part 3 note) — the §2.6 design spec, completed with the three missing mode workspaces (exam review / homework help / time management) and their picker flows from the v1.1 review, must be locked **before 8.1 begins**, not per sub-session.

**v3 additions:**
```
8.3 implements the SSE TRANSPORT over the provider stream() that has existed
  since 4.5a — no provider rewrite, no gateway bypass. Validate SSE against the
  STAGING proxy (4.8) early in 8.3; buffering proxies are where SSE dies.
Assistant calls use the INTERACTIVE priority in the shared limiter — the
  headroom reserved since 4.5a is consumed here for the first time.
ContextBuilder enforces per-mode token budgets: 32k (V2 / general chat) vs
  128k (Think / reasoning modes) per the routing table.
Retrieval: exact pgvector scan under module/transcript filters — candidate
  sets are small at MVP scale. NO ANN index (IVFFlat/HNSW) until real query
  patterns justify one; adding it later is an ADR.
```

**Sub-sessions (as v2):** 8.1 conversation/history foundation → 8.2 context resolver + retrieval → 8.3 SSE streaming → 8.4 lecture breakdown + floating widget → 8.5 save-to-glossary → 8.6 homework/exam/time-management modes (8.6 consumes Stage 5.5 schedule data). Each gets its own spec and browser gate before the next begins.

**UI proof obligation:** a student on a lecture page asks a question and sees the answer *stream in token by token* — grounded in that lecture's context, with no access to unpublished material.

**Exclusions:** as v2 (no unrestricted chatbot, no autonomous slide switching, no auto-solving, no lecturer chat monitoring, no voice/video).

---

## Stage 9 — My Progress Dashboard

**Status:** NOT STARTED.

**v3 addition — ADR checkpoint at stage entry:** before Stages 9–11 add their table wave (~15 tables), record an ADR on the **institution/organization model**. "Single-tenant for MVP" is an acceptable answer — but it must be a recorded decision, not an accident, because retrofitting tenancy across that many tables later is a rewrite.

**Scope as v2 / Slice 7:** progress and topic-mastery snapshots, `CourseGradeScheme` (boundaries in DB, never hardcoded; F/U/WF as distinct fail types), `GradeComponent` (weights sum to 100%), grade records, **deterministic forecast engine** (`requiredRemainingAverage = (target − current) / remainingWeight`), goals, anonymized class-average benchmarking, seeded data on production-like schemas, placeholder gamification section.

**Design input:** Design Plan **§2.7** — module card grid, trend/topic-mastery charts, the grade-forecast panel (the signature data moment; all four status treatments incl. the unsoftened "impossible" state), goal setting.

**UI proof obligation:** a student picks a target grade and sees a deterministic forecast — including a clearly shown "impossible" result when the math says so.

**Exclusions:** as v2 (no live LMS integration, no rankings, no named comparisons, no mental-health diagnosis).

---

## Stage 10 — Gamification

**Status:** NOT STARTED. Unchanged from v2.

**Design input:** Design Plan **§2.8** — streak row, badge grid (locked/unlocked/in-progress states), the badge-unlock animation (the one budgeted spring/glow moment in the product — nowhere else), next-achievement callout. Additive to the §2.7 page; small.

Streaks (timezone-aware, scheduled-day-based attendance), badges, progress — all consumed from `StudentActivityEvent`, reproducible from events, never awarded by the frontend. Gate: a completed quiz visibly updates streak and badge progress in My Progress via the event path.

---

## Stage 11 — Proactive AI Agent & Analytics

**Status:** NOT STARTED.

**v3 addition:** the backend scope explicitly includes a **scheduler component** (rq-scheduler or a cron container). RQ alone cannot express "daily 6:00 AM recalculation" or "48-hour pre-deadline check" — every 11.x spec that assumes scheduled triggers depends on this existing, so it lands in 11.1.

**Design input:** Design Plan **§2.9** — roster table with risk-row treatments (left border + tint, never color alone), student detail sheet, draft-message modal (lecturer sends manually), assessment analysis charts, workload planner calendar — plus the plan-rejection nudge banner (v1.1 review addition). Sub-session mapping: roster/detail design before 11.1–11.2; analysis before 11.3; planner before 11.4.

**Scope as v2 / Slice 5:** `AgentRun`, performance/risk snapshots, recommendations, assessment analysis + question insights, internal calendar, availability settings, workload plans/items; deterministic risk classification (every label traceable to `riskReasons` + `supportingMetrics`); 6-phase planning algorithm; `.ics` export; **AI explains deterministic output — it never calculates risk or grades**; no auto-sent messages; estimates stored on records, not hardcoded.

**Sub-sessions (as v2):** 11.1 roster + risk (+ scheduler) → 11.2 student detail + recommendation draft → 11.3 assessment analysis → 11.4 workload planner → 11.5 .ics export → 11.6 grade-forecast advice. Deterministic rules land before AI explanation layers.

**Exclusions:** as v2 (no live LMS metrics, no Google OAuth, no autonomous messages, no black-box scoring, no auto-rescheduling).

---

## Stage 12 — Release Hardening

**Status:** NOT STARTED.

**Backend scope (v2 carried + v3 additions):** security pass; authorization review (**including the `can_publish` role-vs-membership derivation**); migration review; worker retry/failure review; rate-limit review; load checks; logging/observability; deployment rehearsal — now a **staging→production promotion** rather than a first deploy, because 4.8 exists.

**Design input:** Design Plan **Part 3 (design review pass)** + **Part 4 (accessibility audit)** — full-product consistency sweep, spacing/typography audit, empty/error states verified on every screen, keyboard/contrast/reduced-motion checks (WCAG AA), mobile verification of the key surfaces. This is the *only* place the heavy design audit lives — per-stage closes do the light check, Stage 12 does the sweep.
v3 additions:
```
Global exception handlers / consistent error envelope (no raw default 500 bodies)
Signed-URL revocation decision: implement revocation, or accept the TTL window
  with written rationale (finding-resolution vocabulary applies)
Verify the 4.6 storage reconciliation job in the rehearsal
Verify E2E hooks and fault injection are absent from the production build
AIRequestLog cost review: tokens by feature by day, against IFM budgets
```

**Browser gate (end-to-end smoke):** the full MVP path — admin → lecturer content + transcript → pipeline → summaries → student studies → quiz → mistake → glossary → assistant → progress → gamification → analytics — runs in a real browser against the production-candidate environment without manual intervention. Stages 9 and 11 verify against their designed seeded flows (live LMS integration remains explicitly out of scope).

---

## Post-MVP watchlist (triggers, not tasks)

```
Embeddings → separate table keyed (chunk, model, revision, version)
                                      when a second embedding model arrives
Second StorageProvider (R2/S3)        when hosting economics demand it
Signed-URL revocation                 if the Stage 12 TTL acceptance is revisited
Transcript retention/deletion policy  BEFORE any real-student deployment —
                                      recordings of identifiable people stored
                                      indefinitely is a policy decision, not a default
DeepL translation adapter             post-MVP per Slice 6 (adapter swap only)
Zoom import                           as a source adapter into the SAME pipeline
Multi-institution model               per the Stage 9 ADR
OpenAI embeddings option              if retrieval quality demands (Slice 5 note)
```

---

## Updated stage ordering

```
✅ 0 → ✅ 1 → ✅ 2 → ✅ 3 → ✅ 4.1 → ✅ 4.2 → ✅ 4.3 → ✅ 4.3.5 → ✅ 4.4 → ✅ 4.5
✅ 4.5  AI infrastructure + summaries     (4.5a → 4.5b → 4.5c → 4.5d)  FULLY VERIFIED
4.6  Replacement / retry / supersession / reconciliation        ← next
4.7  Student-facing summaries             (prereq: Stage 3 spec restored)
4.8  First hosted deploy (staging)
4.9  Frontend foundation + hygiene
5    Quiz engine + event spine
5.5  Module schedule & section metadata   (parallel-OK with 5; blocks 6)
6    Complete quiz modes                  (prereq: 5.5; capacity ADR)
7    Glossary
8    Assistant                            (8.1 → 8.6)
9    My Progress                          (entry ADR: org model)
10   Gamification
11   Proactive analytics                  (11.1 → 11.6; scheduler in 11.1)
12   Release hardening
```

---

## What changed from v2

**Added:** Stage 4.8 staging deploy (first hosted smoke before SSE work, not at Stage 12); Stage 4.9 frontend foundation + hygiene batch; Stage 5.5 schedule metadata (unblocks Stages 6, 8.6, 11); rule 14 (full active E2E suite at every stage close; archived specs are dead specs); rule 15 (three-dimension AI capacity budget with priority headroom; request-count frugality); Stage 4.5 fully redesigned with hard prerequisites (IFM key verification, step-level gate pinning, per-step failure projection) and locked design decisions (platform/llm location, complete+stream interface, flat-file PromptRegistry, Redis limiter, metadata-only AIRequestLog, routing split brief→V2/Cerebras + detailed→Think/Nvidia, single-call summaries, in-call 429 handling, dedicated ai queue/worker, backfill answer); Stage 5 function-calling and pagination-envelope requirements with pool-compatible schema; Stage 6 capacity ADR; Stage 8 staging-SSE validation, exact-scan retrieval, context budgets; Stage 9 org-model ADR checkpoint; Stage 11 scheduler component; Stage 12 error envelope, can_publish review, signed-URL decision, cost review; post-MVP watchlist; carried-debt ledger with owners; repo rule placing this file in knowledge/ with mandatory status updates.

**Changed:** completed stages 0–4.4 compressed to a debt ledger plus pointers — specs/STATUS.md remain the authority for finished work; the roadmap's job is forward guidance; v2's two open items closed (prompts = flat files via registry; AI provenance fields confirmed and generalized into amended rule 6).

**Preserved:** the governing principle, UI proof obligations, status vocabulary, all v2 cross-cutting rules in substance, risk-based ordering 4.5→4.6→4.7 (tested the alternative: 4.6's retry scope includes summary jobs and can't precede them; 4.7 before 4.6 exposes students to mixed states during replacement), AIRequestLog-before-first-call, event spine design, the permanent acceptance rule.

---

## Permanent acceptance rule (unchanged, one addition)

A stage is done only when *all* hold:

```
Backend tests pass
Frontend type-check passes
OpenAPI client is fresh (regenerated + committed if the contract changed)
A thin (real, not fake) UI slice exists
The UI proof obligation is demonstrable in a real browser
The Playwright/browser gate passes
The FULL active E2E suite passes (rule 14)            ← new in v3
UI matches the stage's locked Design input (light check; Stage 5 onward)  ← new in v3.1
Knowledge files updated in the same commit (incl. this roadmap's status table)
No out-of-scope backend work slipped in
```

A backend feature without a passing browser gate is not done. It is waiting to surprise you later — usually at the least convenient possible moment.

---

**Next action:** run the Stage 4.6 live browser gate (rebuild images, apply 0010→0012, restart, `npx playwright`) + full active suite → mark 4.6 FULLY VERIFIED, then proceed to **Stage 4.7** (first restoring the Stage 3 content-visibility spec to the active suite). Commit this file as `knowledge/roadmap.md` and the design plan as `knowledge/design-plan.md`.
