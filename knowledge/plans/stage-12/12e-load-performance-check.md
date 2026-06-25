---
type: session-plan
stage: 12
session: "12e"
slug: load-performance-check
status: approved
created: 2026-06-25
updated: 2026-06-25
owner: developer
spec: knowledge/specs/stage-12/12e-load-performance-check.md
report: knowledge/steps/stage-12/12e-load-performance-check.md
---

# Plan — Session 12e — Load & Performance Check

> HOW for [[specs/stage-12/12e-load-performance-check]]. Measure-and-verify; **only new code is a test-only
> pytest harness**. Confirm-don't-assume stays live; anything touching prior-stage code or a posture
> trade-off is **flagged for the owner, not decided**. Owner-approved 2026-06-25.

## Confirmed live at kickoff (re-confirmed in this workspace)
`alembic heads` → **`0059 (head)`** (single). Queues `ingestion`/`embedding`/`ai`; `AgentRun` on `ingestion`.
Limiter defaults (`platform/config.py:525-552`): 20 Cerebras / 10 Nvidia RPM, 100k/105k TPM, conc 10, 20%
interactive headroom. Next-free ADR `064`. **No migration** in 12e.

## Environment (per [[running-backend-gates]])
- `.env` = `cp .env.example .env` (+ local-only `CORS_ORIGINS` :3000,:3001 — gitignored, F-12C-CORS is 12f).
- Sibling stack holds `:8000`; run the harness via a one-off container with a **live source bind-mount** so
  iteration needs no rebuild, and **no host port is published**:
  ```
  docker compose up -d db redis
  docker compose run --rm --no-deps -v "$PWD/backend:/app" backend pytest tests/test_12e_load_perf.py -q
  ```
  Final committed artifact: one clean `docker compose build backend` so the test is baked (matches the
  owner's gate image).

## A — limiter concurrency harness  (`backend/tests/test_12e_load_perf.py`, test-only)
- **Driver layer (Q1 = service-level, owner-approved default):** fire **~24** concurrent
  `generate_section_pool_async(pool_id, gateway=…, session_factory=…)`
  (`backend/app/domains/quiz/pool_service.py`) via `asyncio.gather` (pattern: `tests/test_quiz_pool.py:193`).
  Plus a few `start_pooled_attempt(...)` to assert the observable `generating` wait-state edges.
- **Critical seam (A2):** `LLMGateway(provider=DeterministicTestProvider(), limiter=<real RedisRateLimiter>,
  session_factory=…)`. `gateway.py:114` `_provider_was_injected = provider is not None`; `gateway.py:325-329`
  **bypasses the limiter** for a *non-injected* deterministic provider — so the provider MUST be injected for
  the limiter to run. Real-Redis limiter fixture shape from `tests/test_llm_limiter.py:28-47` (unique
  `key_prefix`; `headroom_percent` as needed).
- **Inject latency:** monkeypatch the provider's `send` to `await asyncio.sleep(latency_ms)` then delegate
  (no native knob — `provider.py:319-359`), so leases are held long enough to force queueing. Drive the
  backoff loop fast with the gateway's injectable `sleep=` (so the test isn't wall-clock-bound) while keeping
  a **low concurrency budget** (small `RedisRateLimiter` concurrency, or `effective_limit` via headroom) so
  N ≫ slots.
- **Assert the pass envelope (A3):** all N complete, none raise; in-flight ≤ concurrency bound (instrument the
  latency shim with a live counter); backoff `retry_events` recorded on the `AIRequestLog` row; a contended
  `start_pooled_attempt` stays `generating` then resolves.

## B — pre-warm invariant
- **B1 (this workspace, deterministic):** seed a module/section with a ready detailed summary; call
  `prewarm_scope_pools` (`assessments/service.py:52-72` path) and assert each eligible section gets a
  `section_question_pools.status='ready'` row for `(module_section_id, model, prompt_version)`
  (`db/models/section_question_pool.py:49-57`); assert a warm-scope `start_pooled_attempt` does **not** sit in
  `generating` on a cold pool (warm reuse, no new generation), per `tests/test_quiz_pool.py:208` reuse proof.
- **B2 (owner-approved amendment, 2026-06-25):** with a real key, run a **provider-only** rule-11 smoke for
  `quiz_pool_generation/v1` (real K2Think call, model echo, clean parseable `GeneratedQuizPool`). This does
  **not** repeat the DB-backed `prewarm_scope_pools -> ready -> warm start` proof; that structural proof lives
  in B1 above. Together B1+B2 discharge the pre-warm invariant at MVP scale: B1 proves the DB-backed warm-pool
  mechanics, B2 proves the real provider can generate the pool payload cleanly. Record B2 in
  `knowledge/steps/stage-12/12e-real-provider-smoke.md`. Exact commands documented in the report.

## C — `/benchmark` baseline
Run `/benchmark` on lecture/summary, quiz-attempt, progress dashboard against the seeded running app; paste
the CWV + page-load numbers into the report. If browser login needs real Supabase (`.env.e2e` absent),
defer-with-owner and record the exact `/benchmark` invocation + target pages.

## D — rule-14 full Playwright suite
Owner merge-time gate (runbook): `down -v` → up → `alembic upgrade head` → seed → `set -a; . ./.env.e2e; set
+a` → `PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1`. Target 35/35 at `0059`. The
12e diff is test-only, so the suite should be unaffected.

## Guardrails
- No feature code; no migration (if one ever looks needed → **STOP, ask owner for a block**, never
  self-select); no new ADR unless a finding demands (`064` next-free).
- Prior-stage code is only *read/exercised*, never modified. A real bottleneck ⇒ flagged for the owner as an
  ADR-justified item, not built here.
- `/review` + `/codex` on the test-only diff; commit on branch; **owner merges**.

## Linked documents
- Spec: [[specs/stage-12/12e-load-performance-check]]
- Report: [[steps/stage-12/12e-load-performance-check]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]] · Runbook: [[steps/e2e-run-procedure]]
- Architecture: [[architecture/llm]] · [[architecture/worker]]
