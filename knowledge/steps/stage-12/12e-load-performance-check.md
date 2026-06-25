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

## (B2) Real-provider confirmation (rule 11) — DEFERRED, owner-run
No real `LLM_API_KEY` in a fresh workspace (`.env` = deterministic). Reuses the existing, proven
`backend/scripts/gate3_quiz_pool_smoke.py` (real K2Think `quiz_pool_generation` call + `GeneratedQuizPool`
validation + model-ID-echo assertion + F-6e-aware bounded retry). Exact command + pass criteria in
[[steps/stage-12/12e-real-provider-smoke.md]]. This is the same owner-run split every prior AI stage used.

## (C) `/benchmark` Core-Web-Vitals baseline — DEFERRED, owner-run
The key student pages (lecture/summary, quiz attempt, progress dashboard) are **authenticated**; browser
login needs real Supabase creds (`.env.e2e`, owner-provided, **absent** in a fresh workspace) and the seeded
fixtures, plus the frontend on `:3001` (the committed compose maps `3001:3000`; `:8000`/`:3001` also collide
with sibling stacks here). It is therefore the same owner-run class as the rule-14 gate. **Owner runbook:**
bring up the seeded production-candidate stack per [[steps/e2e-run-procedure]], log in as a seeded student,
then run `/benchmark` against `/student` (dashboard/progress), a published lecture/summary page, and a quiz
attempt page; paste the CWV (LCP/CLS/INP) + page-load numbers here as the regression baseline.

## (D) Rule-14 full active Playwright suite — owner merge-time gate
`.env.e2e` is owner-provided and absent here, so the definitive single-pass full suite is the **owner
merge-time gate** (per [[running-backend-gates]] / [[steps/e2e-run-procedure]]: fresh DB `down -v` → up →
`alembic upgrade head` → seed → `set -a; . ./.env.e2e; set +a` → `PLAYWRIGHT_BASE_URL=http://localhost:3001
npx playwright test --workers=1`; target **35/35** at head `0059`). **12e changes are test-only** (no product
code, no client/contract change), so the suite is unaffected by construction.

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

## 12e-deferred-with-owner (rule 13)
- **B2** real-provider pre-warm smoke — owner-run with a real key ([[steps/stage-12/12e-real-provider-smoke]]).
- **C** `/benchmark` baseline — owner-run on the seeded stack (runbook above).
- **D** rule-14 full Playwright — owner merge-time gate.

## Modified prior sessions
None — purely additive (one new test file + the 12e knowledge trio + a findings-12 append).

## Linked documents
- Spec: [[specs/stage-12/12e-load-performance-check]]
- Plan: [[plans/stage-12/12e-load-performance-check]]
- Real-provider smoke (B2): [[steps/stage-12/12e-real-provider-smoke]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]] · Runbook: [[steps/e2e-run-procedure]]
- Architecture: [[architecture/llm]] · [[architecture/worker]]
