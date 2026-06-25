---
type: session-spec
stage: 12
session: "12e"
slug: load-performance-check
status: approved
created: 2026-06-25
updated: 2026-06-25
owner: developer
report: knowledge/steps/stage-12/12e-load-performance-check.md
---

# Session 12e — Load & Performance Check (scale-appropriate)

> Filed from the approved Stage 12 v1.2 spec ([[specs/stage-12/12-release-hardening]] §5 12e) and the
> owner-approved 12e plan (2026-06-25). **Measure-and-verify, not a build.** No feature code, no migration
> (chain stays at single head `0059`), no new ADR unless a real finding demands one (`064` stays next-free).
> The roadmap status line is **not** flipped — Stage 12 closes at 12f (rule 12).

## Framing — two concerns, two methods (so we neither burn real budget nor skip the real check)
- **(A) Limiter / queueing mechanics** → scripted concurrency driver on the **deterministic adapter with
  injected latency** (no real K2Think spend). Rule 11 does not require a real call to test queueing.
- **(B) D1 pre-warm invariant** → mechanics proven on the deterministic adapter (B1) + **one small
  real-provider confirmation** (B2, rule 11) that warm pools serve a student without the ~264s cold wait.

## Step 0 (read-first) — student wait-state: REPORT, do not build
**Result: a clear "generating" wait-state already exists** ⇒ 12e *verifies it holds under load*; it adds no UI.
- In-attempt: `frontend/src/features/quiz/QuizAttemptPanel.tsx:175-189` renders `role="status"`
  "**Generating your quiz.**" + a progress bar; after a 5-min wall-clock cap → "Still preparing - refresh to
  check." Post-class variant `PostClassQuizPanel.tsx:253-258`. Polling bounded (1.5s → ×1.5 → 12s, 5-min cap).
- Pre-attempt exam-prep CTA (three states): `StudentQuizModesPanel.tsx:435-455` → Ready / "Waiting on N
  sections" (`reasonCode==="processing"`) / "No eligible sections" (Start disabled when not available).
- Contract: `QuizAttemptForStudent.status ∈ {generating,in_progress,completed,failed}`
  (`backend/app/platform/db/models/quiz_attempt.py:38-40`); `ScopeAvailabilityResponse`
  (`backend/app/domains/quiz/schemas.py:133-140`).
- **Disposition:** present → assert it holds under contention (A3). If load breaks it, that is recorded as a
  **finding for the owner** (one-line fix vs deferred = owner's call), not fixed here.

## Scope & status
| Item | Method | Where it runs |
|---|---|---|
| **(A)** limiter queues an exam-week peak gracefully (no error/deadlock/lost request) | new test-only pytest harness, deterministic provider **explicitly injected** + **real `RedisRateLimiter`**, injected send-latency, low concurrency budget, ~20–30 concurrent generations | **this workspace** (db+redis up) |
| **(B1)** pre-warm invariant mechanics (warm pool ⇒ prompt serve; cold ⇒ generating) | deterministic-adapter test | **this workspace** |
| **(B2)** one small real-provider pre-warm confirmation (rule 11, model-ID echo) | `LLM_PROVIDER=k2think`, one pool | **owner-run** (no real `LLM_API_KEY` in a fresh workspace) |
| **(C)** `/benchmark` CWV + page-load baseline on key student pages | gstack browse daemon vs the running app | **owner-run if browser login needs real Supabase** (`.env.e2e` absent here) |
| **(D)** rule-14 full active Playwright suite green | runbook (fresh DB, :3001, `--workers=1`) | **owner merge-time gate** (`.env.e2e` owner-provided) |

> **Execution-environment reality (per [[running-backend-gates]]):** backend source is **baked** into the
> image (rebuild before pytest). `.env` = dev defaults (`LLM_PROVIDER=deterministic`, placeholder key) ⇒ the
> real-provider smoke (B2) cannot run here. `.env.e2e` (real Supabase) is **owner-provided and absent** ⇒ the
> full Playwright gate (D) is the owner merge-time gate — exactly how 12a–12d closed.

## Pass envelope (measurable — A)
- **No errors, no deadlock, no lost request** — all N concurrent operations complete; none raise; the run drains.
- **Graceful queueing** — concurrent in-flight work never exceeds the limiter's concurrency bound; excess work
  **waits** in the in-path backoff loop (observable via the per-attempt `retry_events` in the single
  `AIRequestLog` row, `gateway.py:344-353`) then proceeds. **Queue-wait is expected, not a failure.**
- **Wait-state holds** — a `QuizAttempt` started under contention stays `status="generating"` (what the
  poller/UI sees), then flips off `generating` once generation drains. Both edges asserted.
- *(Do **not** re-investigate `reasoning_effort` — closed negative finding; inline reasoning is load-bearing.)*

## Pass envelope (B)
- **B1:** `prewarm_scope_pools` ⇒ each eligible section has a `section_question_pools.status='ready'` row for
  identity `(module_section_id, model, prompt_version)`; a start on the **warm** scope assembles promptly; the
  **cold** path (no/`generating` pool) is the one that pays the wait inside the `ai` job.
- **B2 (owner-run):** one real pre-warm ⇒ pool reaches `ready`; echoed model ID matches the configured
  identifier; a real warm start serves with no ~264s cold wait. Recorded in `12e-real-provider-smoke.md`.

## Done means
- (A) harness green against real Redis with the pass envelope asserted; (B1) green; **(B2) recorded or
  owner-deferred** with exact commands; **(C) baseline captured or owner-deferred**; **(D) owner merge-time
  full suite green**. Backend pytest stays green; **no product code changed** (no client regen, no migration).
- `/review` + `/codex` on the test-only diff; report written from evidence; findings-12 appended; the roadmap
  status line **not** flipped (12f closes the stage). Owner merges (agent never merges).

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Plan: [[plans/stage-12/12e-load-performance-check]]
- Report: [[steps/stage-12/12e-load-performance-check]]
- Real-provider smoke (B2): [[steps/stage-12/12e-real-provider-smoke]]
- Findings: [[steps/findings-12]]
- Runbook: [[steps/e2e-run-procedure]]
- Architecture: [[architecture/llm]] · [[architecture/worker]]
- Load-bearing invariant: roadmap F-6e pre-warm note ([[roadmap]])
