---
type: steps
stage: 12
session: "12e"
slug: load-performance-check
status: complete
created: 2026-06-25
updated: 2026-06-25
spec: knowledge/specs/stage-12/12e-load-performance-check.md
plan: knowledge/plans/stage-12/12e-load-performance-check.md
---

# Report — Session 12e — Load & Performance Check

> Written from evidence (`git diff` + captured command output), not memory (AGENTS.md §5). 12e is
> **measure-and-verify**: the only code is a **test-only** pytest harness (`backend/tests/test_12e_load_perf.py`).
> **No product code, no migration (head stays `0059`), no new ADR (`064` stays next-free).** The roadmap
> status line is intentionally **not** flipped — Stage 12 closes at 12f (rule 12).

## Confirm-don't-assume (re-verified live this session)
| Fact | Live value | How |
|---|---|---|
| Alembic head | **`0059 (head)`**, single | `docker compose run --rm backend alembic heads` |
| Queue topology | `ingestion` / `embedding` / `ai`; `AgentRun` on `ingestion` | `workers/queues.py:12-14,190,204` (orientation) |
| Limiter budgets | **20 Cerebras / 10 Nvidia RPM, 100k/105k TPM, conc 10, 20% headroom** | `test_12e_limiter_budgets_match_rule15` asserts the live `limits_for()` values |
| Next-free ADR | **`064`** | `ls knowledge/decisions/` (highest `adr-063`) |
| Migration for 12e | **none** | load-and-measure; no schema change surfaced |

## Step 0 (read-first) — student wait-state: a clear "generating" state already EXISTS
Reported, not built (hardening adds no UI). Evidence:
- In-attempt: `frontend/src/features/quiz/QuizAttemptPanel.tsx:175-189` → `role="status"` **"Generating your
  quiz."** + progress bar; 5-min cap → "Still preparing - refresh to check." Post-class variant
  `PostClassQuizPanel.tsx:253-258`. Polling bounded (1.5s → ×1.5 → 12s, 5-min cap) — no infinite/frozen state.
- Pre-attempt exam-prep CTA (three states): `StudentQuizModesPanel.tsx:435-455` → Ready / "Waiting on N
  sections" (`reasonCode==="processing"`) / "No eligible sections" (Start disabled).
- Contract: `QuizAttemptForStudent.status ∈ {generating,in_progress,completed,failed}`
  (`quiz_attempt.py:38-40`); `ScopeAvailabilityResponse` (`schemas.py:133-140`).
- **Disposition:** present → 12e asserts it holds under contention (test below). No finding raised; nothing
  to fix. (Had load broken it, it would have been a finding for the owner — it did not.)

## (A) Limiter / queueing under an exam-week peak — GREEN (this workspace)
Harness `tests/test_12e_load_perf.py::test_12e_limiter_queues_exam_week_peak`. The deterministic provider is
**explicitly injected** (so the limiter is NOT bypassed — `gateway.py:325-329` only bypasses a *non-injected*
deterministic provider) alongside a **real `RedisRateLimiter`** against the compose `redis`; per-call latency
is injected in the `asyncio.to_thread` send (`gateway.py:203`) to hold limiter leases. Concurrency is the
binding dimension (rpm/tpm set ample) so the queue drains as leases release rather than on the 60s window.

**Measured (N=16 concurrent section-pool generations, background budget=4, 40ms holds):**
- `peak_in_flight = 4` — concurrency **never exceeded the budget** (the limiter invariant held under load).
- `total_backoffs = 35` — queued calls **waited** in the in-call backoff loop and then proceeded (queueing is
  real and observable via `AIRequestLog.rate_limit_backoff_count`).
- `16/16` pools reached `ready`, **`0` failed** — **no error, no deadlock, no lost request; the run drained.**
- Wall-clock ~1.2s for the peak test (backoff tuned fast for test speed; the assertion is graceful drain +
  concurrency cap, not production backoff timing).

⇒ **Pass envelope (A) met:** queues gracefully behind the generating state, caps concurrency at the budget,
and drains with no error/deadlock. *(`reasoning_effort` deliberately NOT re-investigated — closed negative
finding; inline reasoning is load-bearing.)*

**Wait-state under contention** — `test_12e_contended_attempt_stays_generating_then_resolves` (budget=1,
serialized): a `start_pooled_attempt` returns `status="generating"` (what `QuizAttemptPanel` shows), stays
`generating` while the two section pools queue through the single slot, then `try_assemble_attempt_async`
flips it off `generating` once the pools drain. Ties (A) to the Step-0 wait-state — GREEN.

## (B1) D1 pre-warm invariant — GREEN (this workspace)
`test_12e_prewarm_warm_pool_serves_without_cold_wait` drives the **real** `prewarm_scope_pools(factory,
section_ids=[…])` (the `AssessmentScope` create/update path), then drains the generation job so the pool is
`ready`. Asserts: the warm pool carries the rule-15 route identity `(model, prompt_version) = (_pool_model(),
_pool_prompt_version())`; a student `ensure_section_pool` on the **warm** section returns `ready` with **no
new generation enqueued** (no ~264s cold wait); a **cold** (never-pre-warmed) section's first start is the one
that enqueues the generation job. ⇒ the load-bearing F-6e invariant holds: pre-warm keeps a known exam off the
cold-generation wait.

## (B2) Provider-only real-call confirmation (rule 11) — PASS (2026-06-25, real `api.k2think.ai`)
Owner-approved amendment after pre-landing review: B2 is intentionally a **provider-only** rule-11 smoke,
not a duplicate DB-backed pre-warm run. The DB-backed `prewarm_scope_pools -> ready -> warm start/no cold
wait` proof lives in B1 above; B2 proves the real K2Think provider can serve the same `quiz_pool_generation`
prompt cleanly. Ran once the owner supplied the real key in `.env`, via the proven
`backend/scripts/gate3_quiz_pool_smoke.py` (real K2Think `quiz_pool_generation` call + `GeneratedQuizPool`
validation + prompt-model echo assertion + F-6e-aware bounded retry). **PASS on attempt 1:** echo
**`MBZUAI-IFM/K2-Think-v2` == expected prompt-declared model** (rule 11 OK), **247.6 s** (< 330 s),
`finish_reason=stop`, `200`, 16-question parseable pool. Full evidence + the model-id resolution note in
[[steps/stage-12/12e-real-provider-smoke]]. Together B1+B2 discharge the D1 pre-warm invariant at
single-course MVP scale.

## (C) `/benchmark` Core-Web-Vitals baseline — RECORDED (2026-06-25, owner `.env.e2e` stack, head `0059`)
Captured with the gstack `/benchmark` browse daemon, **authenticated** as the seeded `student_e2e@example.test`
(viewport 1440×900), on the three key student pages. LCP/CLS via a buffered `PerformanceObserver`; INP is not
captured (requires interaction). **Baseline (for future regression comparison only — no perf *fixing* in 12e):**

| Page (authenticated) | TTFB | FCP | **LCP** | **CLS** | DOM complete | Full load | Requests | JS | Transfer |
|---|---|---|---|---|---|---|---|---|---|
| `/student` (home) | 38 ms | 52 ms | **260 ms** | **0** | 214 ms | 214 ms | 14 | 4.9 MB | 4.9 MB |
| `/student/progress` (My Progress) | 30 ms | 40 ms | **284 ms** | **0** | 251 ms | 251 ms | 13 | 6.2 MB | 6.2 MB |
| section (lecture summary + quiz)¹ | 40 ms | 56 ms | **312 ms** | **0.021** | 265 ms | 265 ms | 21 | 6.0 MB | 6.1 MB |

¹ `/student/modules/91a211bf…/sections/fdccc355…` (seeded "Cell Division" lecture — summary + quiz panel).

**Read:** LCP 260–312 ms (all **good**, < 2.5 s), CLS 0–0.021 (all **good**, < 0.1), FCP 40–56 ms (all
**good**, < 1.8 s), full load ≤ 265 ms. **Caveat — DEV build:** the e2e frontend runs `npm run dev`
(`frontend/Dockerfile:10`), so the ~5–6 MB JS is the **unminified dev bundle** (HMR), ~10× a production build.
This is a **dev-build baseline**; the production-candidate build (12f, the /cso item-1 deferral) will be far
smaller — so compare future runs against this baseline **on the same (dev) build type**, and re-baseline once
the production frontend lands.

**To reproduce / re-baseline (copy-paste):**

```bash
# 1. Stand up the seeded stack (per the runbook). Ensure no sibling stack holds :3000/:8000/:5432/:6379.
export COMPOSE_PROJECT_NAME=stockholm            # fixtures call bare `docker compose exec`
# F-12C-CORS: a fresh .env ships CORS :3000 only — add :3001 in the gitignored .env or student login 400s:
#   CORS_ORIGINS=http://localhost:3000,http://localhost:3001
docker compose --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build
docker compose exec -T backend alembic upgrade head          # expect 0059 (head)
export E2E_RUN_ID="e2e-$(echo $RANDOM | md5 2>/dev/null | head -c8 || date +%s)"
node tests/e2e/fixtures/seed.mjs                              # seeds the student + module/sections

# 2. Run /benchmark (gstack skill, browse daemon) against the three key student pages on :3001.
#    Log in as the seeded student first, then benchmark each (per-page URLs are seed-id-dependent —
#    navigate from the dashboard):
#      • progress dashboard   → http://localhost:3001/student
#      • lecture/summary page → a published lecture under the seeded module
#      • quiz attempt page    → start a post-class/recap quiz from a completed lecture
```

Paste the CWV (LCP / CLS / INP) + page-load numbers here as the regression baseline. No perf *fixing* in
12e unless a finding demands it — this is a baseline for future comparison only.

## (D) Rule-14 full active Playwright suite — RAN GREEN (2026-06-25, head `0059`)
Ran on the owner `.env.e2e` stack once it was provided. Fresh clean stack (`down -v` → full e2e stack up on
`:8000`/`:3001`, all 8 services healthy → `alembic upgrade head` = `0059` → seed → source `.env.e2e` →
`PLAYWRIGHT_BASE_URL=http://localhost:3001 --workers=1`; run id `e2e-stockholm-12e-1782380955`). **Result:
34 passed / 1 failed on the single pass (7.7m), the 1 failure confirmed a flake → effective 35/35.** The
failure was `10-gamification.spec.ts:237 Scenario A: earn + extend, idempotent` — a **login-redirect flake**
(`signIn` timed out at `/login`, `:205`; scenarios B/C/D passed with the same helper), the documented
"gamification login flake that passes on retry" from the 12a/12b gate. Re-ran in isolation (`--last-failed`):
**passed in 4.9s.** **12e changed no product code** (test-only), so this is **not a 12e regression** and not the
DB-state idempotency issue. *(Setup notes: stopped the sibling `montpellier` stack to free `:8000`/`:3001`
per the runbook; `npm install` + `npx playwright install chromium` were needed in the fresh workspace —
`node_modules` was absent, so `npx` had grabbed a mismatched temp Playwright.)* **Copy-paste (per
[[running-backend-gates]] / [[steps/e2e-run-procedure]]):**

```bash
export COMPOSE_PROJECT_NAME=stockholm
docker compose down -v                                            # genuinely FRESH DB per full-suite run
docker compose --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build
docker compose exec -T backend alembic upgrade head              # expect 0059 (head)
export E2E_RUN_ID="e2e-$(echo $RANDOM | md5 2>/dev/null | head -c8 || date +%s)"
node tests/e2e/fixtures/seed.mjs
set -a; . ./.env.e2e; set +a                                     # source .env.e2e INTO the runner
PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1   # target 35/35 at head 0059
```

## Backend pytest (this workspace)
- `tests/test_12e_load_perf.py` — **4 passed** (baked image): budgets-match-rule15, exam-week-peak,
  contended-wait-state, prewarm-invariant. Runs against compose `db` + `redis`.
- Full backend suite (baked image): **852 passed** (355.63s) — additive test-only change (848 prior + 4).
  Re-confirmed on the final post-review artifact.

## Pre-merge review (`/review` + `/codex`) — both run, both findings fixed
Independent adversarial passes on the test-only diff (rule: every code change gets `/review` + `/codex`):
- **Claude adversarial subagent — ship-as-is.** Verified the limiter proof is sound (deterministic provider
  explicitly injected ⇒ real limiter exercised, not bypassed; sync `send` runs in `asyncio.to_thread` ⇒ real
  thread concurrency; nvidia is the correct monkeypatch dimension), assertions non-vacuous (a 0-pool or
  uncapped-concurrency regression fails), no correctness bug.
- **Codex (gpt, high reasoning) — 2 findings, both FIXED (test-only):**
  1. `redis_client` **skipped** when Redis was down → a 12e acceptance proof could go green **without running
     the limiter check**. Fixed: the fixture now **fails loudly** (Redis is required for the proof) — matches
     the plan's Q3 posture. 2. `latency_s=0.04` was timing-sensitive. Fixed: lease hold raised to a
     `_LEASE_HOLD_S=0.15` constant so the hold dominates scheduler/DB-claim jitter (peak reliably saturates,
     queued calls reliably back off). Also dropped one tautological assertion the subagent flagged.
  Re-verified **4/4 green** (baked) after the fixes.

## Deviations / decisions (rule 10/13)
- **B2 split proof accepted by owner (2026-06-25):** B2 remains a provider-only real-call smoke (rule-11
  model echo + clean `GeneratedQuizPool`), while B1 is the DB-backed pre-warm -> ready -> warm-start proof.
  No new test run required.
- **12f config-reconciliation item:** B2 echoed the prompt-declared model `MBZUAI-IFM/K2-Think-v2`, while this
  workspace's `.env` `LLM_DETAILED_MODEL_ID=MBZUAI-IFM/K2-Think-v0` feeds `_pool_model()` / pool identity.
  Owner disposition: not a 12e defect; product owner aligns `.env`/prompt/deployment model ids in 12f.
- **(A) driver layer = service-level** `generate_section_pool_async` (owner-approved Q1 default) — the
  function a real recap/exam-prep start hits; exercises gateway → real limiter → backoff end-to-end.
- **Binding dimension = concurrency** (rpm/tpm set ample) so the queue drains in ~1s as leases release. The
  rpm/tpm dimensions are **window-based** (free only as the 60s window slides) and a sustained saturation
  beyond `LLM_RATE_LIMIT_MAX_ELAPSED_MS` (default 30s) terminates as `rate_limited` → pool `failed` (student
  sees the bounded failure + retry affordance, not an infinite spinner). Noted as observed behavior; **not a
  defect** and **not load-tested at 60s** by choice (no value, large time cost).
- **Limiter-bypass-for-non-injected-deterministic** (`gateway.py:325-329`, observation Q4): normal
  deterministic CI/E2E runs do **not** exercise the Redis limiter; only an explicitly-injected-provider
  harness (this one) does. **Not a defect** (keeps CI off Redis). Left as a recorded testing-boundary note;
  **no ADR** (owner declined to formalize unless desired — `064` stays next-free).
- **No new bottleneck found** ⇒ no ADR-justified addition (scale discipline). No prior-stage code modified.

## Owner-gate items — ALL RUN (2026-06-25)
- **B2** provider-only real-call smoke — **PASS** (real `api.k2think.ai`; prompt-model echo
  `K2-Think-v2` OK, 247.6s; DB-backed pre-warm proof lives in B1;
  [[steps/stage-12/12e-real-provider-smoke]]).
- **C** `/benchmark` baseline — **DONE** (recorded above; owner `.env.e2e` stack).
- **D** rule-14 full Playwright — **DONE** (35/35 effective; 1 confirmed login flake).

All 12e gates are now green: (A) limiter queueing, (B1) pre-warm invariant, (B2) real-provider PASS, (C)
benchmark baseline, (D) full Playwright 35/35. Only the owner PR/merge remains (agent does not commit/push).

## Modified prior sessions
None — purely additive (one new test file + the 12e knowledge trio + a findings-12 append).

## Change history
- 2026-06-25 15:04 +04 — Owner-approved docs amendment after pre-landing review: B2 is recorded as a
  provider-only rule-11 smoke, with B1 carrying the DB-backed pre-warm proof; model-id split tracked for 12f.

## Linked documents
- Spec: [[specs/stage-12/12e-load-performance-check]]
- Plan: [[plans/stage-12/12e-load-performance-check]]
- Real-provider smoke (B2): [[steps/stage-12/12e-real-provider-smoke]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]] · Runbook: [[steps/e2e-run-procedure]]
- Architecture: [[architecture/llm]] · [[architecture/worker]]
