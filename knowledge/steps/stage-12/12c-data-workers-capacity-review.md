---
type: session-report
stage: 12
session: "12c"
slug: data-workers-capacity-review
status: done
created: 2026-06-24
updated: 2026-06-24
owner: developer
spec: knowledge/specs/stage-12/12c-data-workers-capacity-review.md
---

# Report — Session 12c — Data, Workers & Capacity Review

> Status: **review complete; all checks pass; no code change (review-only).** Verified live in Docker
> (fresh `kyiv-backend` image, clean DB, deterministic provider). Owner gate remaining: full active
> Playwright (rule 14) on the owner `.env.e2e` stack + merge (agent never merges).

## 1. Migration chain — VERIFIED (single head `0059`)
Static: 43 revisions, **single head `0059`** (`0059_student_forecast_advice.py`), no duplicate revision IDs,
one expected merge node `0082 = ("0044","0081")` that `0056→0057→0058→0059` chains after. **Fresh-DB
round-trip GREEN** (`docker compose run --rm backend`, default `xyz_lms`, freshly-created volume):
`alembic heads` → `0059 (head)`; `upgrade head` → `0059`; `downgrade base` → empty; `upgrade head` → `0059`.
No orphaned/duplicate revisions; every migration has a working downgrade. **Actual head recorded: `0059`.**
(Hosted extension bootstrap is the local `docker/postgres/init/001-create-vector.sql` creating `vector` +
`pgcrypto`; migrations 0006/0007 also create `vector`. pgcrypto is init-only — the F006 hosted-bootstrap debt
12f documents.)

## 2. Doc correction (owner D2=A — narrow)
Folded the kickoff "single head `0082`" → `0059` in `findings-12.md:19` (kickoff table) + `:73`, and the 12a
spec `:59`. Left append-only `log.md` and prior-stage `STATUS.md`/`roadmap.md:72`/`8.6d` as historical record
(they reference main's rebase-time state or already show `0059`).

## 3. Workers & scheduler — VERIFIED
- **Topology:** three RQ queues `ingestion`/`embedding`/`ai` (`queues.py:12-14`); no `agent` queue; AgentRun
  runs on `ingestion`.
- **Retry policy (rule 15):** `embedding` + `ai` enqueues use `Retry(max=3, [30,120,300])`; `ingestion`
  parse/chunk and AgentRun use **no RQ Retry by design** (deterministic; recovered by the reaper /
  scheduler-tick reconciliation — RQ retries reserved for provider-transient / invalid-output).
- **AgentRun "committed-but-never-enqueued, no retry" gap — CLOSED.** Both call sites (scheduler
  `service.py:56`, manual API `analytics.py:51`) commit the run then call `enqueue_run_agent_if_needed`
  (idempotent, RQ-liveness-checked). A run whose enqueue fails after commit stays `queued`/requeueable and is
  re-enqueued on the next scheduler tick (the `idempotency_key` collapses duplicates).
- **Reaper covers uploaded/parsing/queued:** `_reap_never_enqueued_parse` (transcript `uploaded`/`queued`),
  `_reap_crashed_running` (job `running`/parsing past threshold), `_reap_stuck_queued` (downstream `queued`),
  plus quiz/pool `generating`. Singleton-locked, action-capped, FOR UPDATE fencing, liveness-not-age,
  MaintenanceRun per run; runs best-effort at worker startup (never blocks boot).
- **Terminal failures observable:** scheduler/reaper/reconciliation log `logger.exception` + write a failed
  MaintenanceRun; the reaper finalizes dangling `running` AIRequestLog rows to terminal so the cost dashboard
  never leaks a hung row; RQ moves failed jobs to its FailedJobRegistry.
- **Scheduled jobs fire:** `scheduler_tick` under a PG advisory lock (singleton across N schedulers), daily at
  `SCHEDULER_DAILY_HOUR` (default 06:00 institution-local), poll `SCHEDULER_POLL_SECONDS` (60s).

## 4. Rate limiter — VERIFIED (budgets confirmed from live config)
`config.py` + `.env.example` agree: Cerebras **20 RPM / 100k TPM / 10 concurrency**; Nvidia **10 RPM / 105k
TPM / 10 concurrency**; `LLM_INTERACTIVE_HEADROOM_PERCENT=20`. `effective_limit` gives interactive traffic the
full budget and caps background to 80% of each dimension (`limiter.py:133-137`) — interactive headroom holds.
Atomic Lua acquire (prune→check rpm/tpm/conc→reserve) on the Redis server clock; concurrency is a TTL lease
(a crashed worker's slot is reclaimed). In-call 429 backoff (`BackoffPolicy`), not RQ retry (rule 15).

## 5. Storage reconciliation (4.6) — VERIFIED
`reconciliation.py`: **report-only default** (`mode="report_only"`); cleanup double-gated (`mode=="cleanup"`
AND `RECONCILIATION_CLEANUP_ENABLED`, default False); **prefix-scoped** (`RECONCILIATION_MANAGED_PREFIX`,
default `modules/`); **deletion-capped** (`RECONCILIATION_DELETION_CAP_PER_RUN`, default 50); **superseded
retained** (their `storage_key` stays in `db_keys` → never an orphan); grace window 86400s; missing-refs
(DB ref with no object = potential data loss) reported loudly, **never auto-fixed**, only when the listing is
complete + full scope. MaintenanceRun per run.

## 6. Logging review — PASS (3 criteria)
- **(a) Unhandled-error → ERROR + request_id.** `errors.py:84-94` catch-all logs `logger.exception("Unhandled
  request error", extra={"request_id": ...})` (ERROR + traceback server-side only; the client body carries no
  trace). Off-request paths (scheduler/reaper/reconciliation) use `logger.exception` + a failed MaintenanceRun
  (the job/run id is the off-request correlation id — there is no HTTP `request_id` off the request path).
- **(b) No PII (rule 6).** AIRequestLog stores only hashes (`prompt_content_hash`/`rendered_prompt_hash`/
  `input_content_hash`); `debug_text_truncated` is non-prod-only and never transcript text; `retry_events_json`
  excludes prompt/transcript/headers/keys. Re-confirms the 12b PASS.
- **(c) Durable platform-captured stdout.** Zero FileHandler / sentry / datadog / dictConfig / aggregation
  stack in `backend/app`; only `logging.basicConfig(level=INFO)` (worker + scheduler) → root StreamHandler →
  stdout/stderr; FastAPI relies on uvicorn stdout. MVP-appropriate.

## 7. AIRequestLog cost review — DONE
Authored "tokens by feature by day": `SELECT feature, date_trunc('day', created_at)::date AS day, count(*),
count(*) FILTER (WHERE status='succeeded'), coalesce(sum(total_tokens),0) FROM ai_request_logs GROUP BY
feature, day ORDER BY day DESC, total_tokens DESC` (index `ix_ai_request_logs_feature_created_at`).
**Returns a result** — 0 rows on the current seed-only / no-usage DB (honest: no AI calls logged yet); an
illustrative rolled-back demo confirmed correct per-feature/day aggregation. **Sanity vs IFM budgets:** the
heaviest feature is `summary_detailed` at ~15–16.5k tokens/call (matches rule 15's ~13–18k full-transcript
prompt; ~6 calls/min before the 105k Nvidia TPM binds — TPM binds before RPM, as documented). One call per
summary / per quiz (never per chunk/question). **No feature is unexpectedly expensive.**

## Verification (captured)
- Migration round-trip: GREEN (head `0059`).
- `docker compose run --rm backend pytest -q tests/test_llm_limiter.py tests/test_recovery.py
  tests/test_scheduler.py tests/test_transcript_worker.py tests/test_worker_startup_recovery.py
  tests/test_error_envelope.py` → **79 passed** (22.85s; 3 known httpx-ASGI deprecation warnings — carried
  4.9 debt).
- Cost query: valid (EXPLAIN), runs, sanity-checked.
- **No code changes** (review-only) ⇒ `/codex` N/A.

## Owner gate remaining
- Full active Playwright suite (rule 14) on the owner `.env.e2e` stack; owner reviews + merges.

## Linked documents
- Spec: [[specs/stage-12/12c-data-workers-capacity-review]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]]
- 12d: [[steps/stage-12/12d-privacy-data-retention]]
- Architecture: [[architecture/worker]] · [[architecture/transcript-lifecycle]] · [[architecture/llm]]
