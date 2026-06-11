---
type: findings
stage: "04"
relates_to: ["4.6d-G1", "4.6c"]
status: open
created: 2026-06-11
---

# Stage 4.6 live-gate findings (Task 4.6d-G1)

## F-4.6c-1 — BLOCKER — startup recovery hook breaks ALL worker job processing (asyncpg cross-loop / fork-inherited dirty pool)

**Status:** FIXED (Task 4.6c-F1, 2026-06-11) · **Severity:** blocker (default config) · **Found by:**
4.6d-G1 live gate · **Resolution:** `_startup_recovery_async` now runs on an isolated `NullPool` engine
(injected into the reaper/reconciliation) and disposes it; the module engine is never connected in the
parent. Regression test `tests/test_worker_startup_recovery.py` reproduces the exact `different loop`
error on the unfixed code and passes on the fixed code. Invariant recorded in
[[decisions/adr-032-stuck-row-reaper-singleton]] (+ flagged for 11.1's parent-side scheduler hooks).
Backend `pytest` 350 passed. Gate re-run tracked below.

### Symptom
Every e2e spec that runs a transcript through the workers fails. In the no-fault success batch:
**4.3.5e, 4.4, 4.5d-summary-browser FAILED** at `waitForTranscriptCompleted`/processing waits; only
**4.3.5c** (admin UI, no transcript processing) passed. Worker log:
```
ERROR rq.worker: job ...: exception raised while executing (app.domains.transcripts.jobs.parse_transcript)
  File ".../parse_service.py", line 132, in _claim_parse_job
RuntimeError: Task <...parse_transcript_async()...> got Future <...> attached to a different loop
```

### Root cause
- `app/platform/db/session.py`: `engine = create_async_engine(DATABASE_URL)` is a **module-level
  singleton with the default connection pool** (not NullPool). Unchanged since Session 2.2.
- RQ's default worker **forks a child process per job**; each job runs `asyncio.run(...)`
  (`app/domains/transcripts/jobs.py`). Pre-4.6c the parent never touched the engine, so each forked
  child got a pristine engine + fresh pool — fine.
- **4.6c added** `worker.py::_run_startup_recovery()` → `asyncio.run(run_stuck_row_reaper())` **in the
  parent**, before `worker.work()`. `run_stuck_row_reaper()` (no args) uses the **module engine**;
  `maintenance_advisory_lock(engine)` does `engine.connect()`, populating the module pool with asyncpg
  connections bound to the **startup event loop**. `asyncio.run` then closes that loop, but the pooled
  connections remain (bound to the dead loop, sockets owned by the parent).
- RQ forks job children that **inherit the parent's dirty pool**. The first DB call in a forked job
  (`_claim_parse_job`) reuses an inherited connection bound to the parent's closed loop →
  `got Future attached to a different loop`. Affects parse/chunk/embed/summary equally (all workers run
  `_run_startup_recovery`; the reaper is singleton-locked, but **every** worker still opens the
  advisory-lock connection via `engine.connect()` regardless of `acquired`).

### Why unit tests missed it
The 4.6c reaper tests inject `session_factory` + `engine=db_session.bind` (the test engine) and never
exercise the real worker's *parent runs asyncio.run, then forks a job* path. The integration only
manifests in the live RQ worker process — exactly what this gate exists to catch. **329→349 green unit
tests did not (could not) cover it.**

### Evidence / confirmation
- Default config (`REAPER_RUN_AT_STARTUP=true`): 3/4 processing specs fail; worker log shows the loop error.
- Diagnostic: recreated all 3 workers with `REAPER_RUN_AT_STARTUP=false` (existing flag; throwaway
  override, no tracked-config change) → **4.4-embedding PASSED (16.8s), 0 "different loop" errors.**
  Stack then restored to canonical reaper-on. The flag toggle isolates the cause unambiguously.

### Proposed fix (for the follow-up task — keeps the reaper-at-startup feature)
Ensure the module engine's pool is **not left populated in the parent before `worker.work()` forks**.
Minimal: `await engine.dispose()` at the end of `_startup_recovery_async` (or in `_run_startup_recovery`'s
`finally`). Alternatives: run startup recovery against a throwaway `NullPool` engine instead of the module
engine; or move startup recovery into a subprocess. After the fix, **re-run the full gate** (this task's
Step 3 onward) — the migration/cutover work is already done and need not repeat.

### Not papering over
Leaving `REAPER_RUN_AT_STARTUP=false` would make the gate *appear* green by disabling a 4.6c feature —
rejected. The stack is restored to canonical reaper-on (the real, broken state). The gate is **BLOCKED**
pending the product fix; Stage 4.6 stays **BACKEND VERIFIED + UI BUILT, gate pending**.

## F-4.6b-2 — BLOCKER — a fully-processed pending replacement never activates (4.6a activation trigger ↔ 4.6b DAG decouple)

**Status:** FIXED (Task 4.6b-F2, 2026-06-11) · **Severity:** blocker (replacement continuity — the
priority gate) · **Found by:** 4.6c-F1 gate re-run (after F-4.6c-1 fixed) · **Resolution:** structural —
`activation.attempt_pending_activation` is now called by EVERY pipeline leaf on success (embed via
`embedding_service`, brief/detailed via `summary_service`); whichever finishes last fires the swap, the
readiness gate no-ops the rest. Regression tests in `test_transcript_lifecycle.py`: embed-after-summaries
activates (fails on unfixed code), embed-before-summaries (summary leaf last) activates, two concurrent
leaf attempts → exactly one swap. Backend `pytest` 353 passed. Gate re-run tracked below.

### Symptom
4.6d replacement-continuity gate: the replacement (v2) processes fully — **all 5 jobs completed,
`status='completed'`** — but stays `lifecycle_state='pending'` forever; the atomic swap never fires, so
the preview never flips to v2 and v1 is never `superseded`. The gate times out (240s) waiting for the swap.

### Root cause (confirmed by completion timestamps)
Activation is triggered **only** by `summary_service.py:292` (`_try_activate_after_summary`, after each
summary completes). Its readiness gate (`activation.py:76`) requires `overall_state == "summarized"`,
which requires **embed completed** too. **4.6b decoupled the DAG** (summaries fork from parse, parallel to
embed). Observed order for v2: parse 48.479 → chunk 48.545 → brief 48.734 → detailed 48.956 → **embed
51.622** (embed finished 2.7s AFTER both summaries). So:
1. brief completes → activate → embed not done → NOT_READY.
2. detailed completes → activate → embed still not done → NOT_READY.
3. embed completes LAST → **no activation trigger exists for embed completion** → pending never activates.
Pre-4.6b, summaries ran *after* embed, so embed was always done when summaries completed — the implicit
ordering masked the missing embed-side trigger. The 4.6b decouple removed that ordering.

### Proposed fix (follow-up task)
Trigger activation after **embed** success too, not only after summaries — i.e.
`embedding_service._persist_success` (and the embed worker terminal path) calls the same idempotent
`try_activate_pending_transcript`. Activation is already a no-op until `summarized`, so re-attempting it
after any step that can be "last" is safe. (Alternative — relax the readiness gate to not require embed —
is riskier: it would let the active transcript serve before embeddings exist; keep "fully processed before
swap" and just add the embed trigger.) Add a regression test: a pending whose **embed completes after its
summaries** still activates. Re-run the continuity gate.

### Not a test artifact
The continuity test replaces with the same file (same checksum); readiness is correctly scoped by
`transcript_id` (`summary_eligibility.py:84`), so same-checksum is NOT the cause — the timing/trigger gap is.
The earlier continuity assertions (preview holds on v1, `hasPendingReplacement=true`, eligible) all
**passed**; only the swap is blocked.

## Gate progress recorded (4.6d-G1 + 4.6c-F1)
- Step 1 ✓ branch `stage/4.6-replacement-retry`, 4.6d committed (43dd2cf); main untouched.
- Step 2 ✓ migration pre-flight on a pg_dump copy of dev data: backfill correct (7→active, 0 NULL), all
  three partial-unique indexes built clean, `maintenance_runs` + provenance present. No data finding.
- Step 3 cutover ✓ images rebuilt; `xyz_lms` migrated 0009→0012 (backfill verified on the live DB);
  e2e stack up (hooks + local Supabase); seed OK; **4.3.5b PASSED, 4.3.5c PASSED**.
- Step 3 first attempt BLOCKED by F-4.6c-1 — transcript-processing specs (4.3.5e/4.4/4.5d) all failed.

### 4.6c-F1 re-run (after the F-4.6c-1 fix)
- F-4.6c-1 **FIXED + proven**: rebuilt the worker image reaper-on; startup reaper ran clean
  (`scanned:3 recovered:3`, 0 loop errors); the **no-fault success batch is GREEN — 5/5**
  (4.3.5b, 4.3.5c, **4.3.5e edited 409→201**, 4.4, **4.5d-summary-browser**). That answers rule-14's open
  question: **the 4.5 gate still passes post-4.6b-decouple.** Regression test
  `tests/test_worker_startup_recovery.py` added (fails on unfixed code with the exact different-loop error).
- Category-(a) e2e fix on the branch: the continuity spec's `getByRole('button', {name:'Replace transcript'})`
  was ambiguous (the file-input label substring-matches) → made it `exact: true`.
- **NEW BLOCKER F-4.6b-2** — 4.6d **replacement continuity (the priority assertion) FAILS**: the
  replacement processes fully but never activates (see F-4.6b-2 above). The preview-holds-on-v1 half is
  proven; the atomic-swap half is blocked by the activation-trigger gap. **Gate still BLOCKED** — Stage 4.6
  stays *BACKEND VERIFIED + UI BUILT, gate pending*.
- Retry flow + 4.5d-summary-fault specs: not yet characterized at this point (the priority assertion
  outranks; stopped per the category-(b) rule).

### 4.6b-F2 re-run (after the F-4.6b-2 fix) — FULL ACTIVE SUITE GREEN
- F-4.6b-2 **FIXED + proven**: every leaf attempts idempotent activation; rebuilt the worker image
  (resolved an e2e-vs-base build-cache divergence where `-f docker-compose.e2e.yml --env-file .env.e2e`
  resolved to a stale cached image; plain `docker compose build backend` baked the fix). 3 activation
  regression tests added (embed-after-summaries fails on unfixed code).
- **Replacement continuity GREEN (13.5s)** — the priority assertion: preview holds on v1 while pending →
  flips to v2 on the atomic swap → v1 `superseded` with lineage → exactly one active. The swap fires.
- **Full active Playwright suite GREEN (9/9):** 4.3.5b, 4.3.5c, 4.3.5e (409→201), 4.4, **4.5d-summary-browser
  (4.5 post-decouple)**, 4.5d-summary-fault **invalid_output** + **invalid_input** (ai_worker LLM-fault runs),
  4.6d **replacement continuity**, 4.6d **retry flow** (forced embed failure → retry → summarized, no
  duplicate segments/chunks/summaries; embed failure did not block summaries).
- Category-(a) e2e robustness fixes on the branch: `recreateEmbeddingWorker` blocks on readiness; the
  retry assertion polls the DB for embed completion then reloads (worker-recreation model-boot is minutes
  on a cold image — a harness artifact, not retry latency). Minor latent finding F-4.6d-3 recorded.
- Backend `pytest` **353 passed** (the F-4.6c-1 + 3 F-4.6b-2 regression tests included).
- **Gate is GREEN.** Pending only the human's go: Stage 4.6 → FULLY VERIFIED + branch → main merge.

## F-4.6d-3 — MINOR / latent — status badge stops polling on the transient post-retry "failed" state
**Status:** open (deferred — UI polish; not a correctness defect) · **Severity:** minor, latent ·
**Found by:** 4.6b-F2 retry-flow gate run.
`apply_retry` resets the failed JOB to `queued` but leaves `transcript.status='failed'` until the worker
claims the re-enqueued job (`retry.py:118-122`). The lecturer status badge's `isSettled` returns true on
`overall_state=='failed'`, so a poll that lands in that transient window settles and **stops** — the badge
then misses the eventual `summarized` and shows the stale failure until a reload. **Masked in production**
(a live worker claims in ~100ms, before the badge's 1500ms first poll → it sees `embedding`, keeps polling);
**exposed** here only because the test recreates the embedding_worker and its minutes-long model-snapshot
boot holds the job unclaimed past the badge's settle. The retry itself is correct (DB: `summarized`,
embed `attempts=2`, no duplicate rows). **Proposed fix (follow-up, NOT this task):** reset
`transcript.status` off `failed` in `apply_retry` (e.g. to `queued`) so the projection shows "retrying"
immediately, or keep the badge polling for a grace period after a retry click. The retry-flow gate reloads
after a DB-confirmed embed completion to assert the lecturer-visible `Summaries ready`.

## Cross-stage-seam pattern (Step 4 of Task 4.6b-F2 — record before 4.7 stacks on this)
The Stage 4.6 live gate surfaced **two** category-(b) bugs that per-session verification structurally
**could not** catch, because both lived in the **seam between** verified sessions, not inside any one:
- **F-4.6c-1** — 4.6c's startup hook + the fork-per-job worker model: the module engine pool, fine until
  something connected it pre-fork.
- **F-4.6b-2** — 4.6a's activation trigger + 4.6b's DAG decouple: the after-summary trigger, correct while
  summaries ran after embed, orphaned once they ran in parallel.
Each session was "backend verified" and genuinely correct in isolation; the bugs are in the *integration*.
Both were invisible to unit tests that **inject** dependencies or **mock** ordering — the very seams the
injection hides are where these live. Evidence, not blame: **"backend verified per session" means
"correct in isolation," not "integrates"** — the walking-skeleton live gate (real workers, real fork, real
DAG race, real browser) is carrying that weight and earning its cost. 4.7 should NOT inherit the assumption
that green-per-session ⇒ integrated; budget for a live integration pass when a new stage touches the
worker/DAG/activation seam. Structural fixes (isolated engine; every-leaf trigger) beat instance fixes
(dispose-in-the-right-order; trigger-after-the-one-step-we-saw-last) precisely because the seam shifts.
