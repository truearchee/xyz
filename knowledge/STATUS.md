# Status

_Last updated: 2026-06-12 - **Stage 4.7 (student-facing summaries) FULLY VERIFIED — LANDED ON MAIN.** Human-stamped after the P1 assertion-strength audit + Steps 1–3 (4.6d-P1 independence gate, two attributable merges, full re-verification on main). **Verified ON MAIN HEAD `0e0654f`:** backend **389 passed**; full active Playwright suite **11/11** (9 success serial + 2 fault: 4.3.5b/c/e, 4.4, 4.5d-summary-browser + fault ×2, 4.6d ×2 reload-free, 4.7-stage3-content-visibility, 4.7-student-summaries). 4.7a backend boundary: `StudentSummaryAccessPolicy` (§5: row R 403 before lookup; D/P/I byte-identical 404), §6 precedence (corruption≠supersession DISTINCT + logged, two pinned tests), scoped read model (§8.6 MODULE-LEVEL join, >1-active fail-safe, no fetch-then-branch), server-side markdown shaping, Option-B endpoints + coarse list, §8.3 hygiene, `Cache-Control: private, no-store`, migration 0013. 4.7b UI: thin student section page (4 per-slot states + bounded polling + react-markdown raw-HTML-off). **P1 (Stage 3 content-visibility E2E) RESTORED + GREEN (no drift).** Review R1 (sentinel canary strengthened, non-vacuous), R2 (`--workers=1` = CAPACITY: embed RQ-retries 3×[30,120,300]s, non-terminal, GAP ruled out — non-blocking), R3 (row-3 unit test added) all resolved. **4.6d-P1 (F-4.6d-3 fix) also LANDED on main** (independently verified: 3 attributable regression tests + e2e reload-free) via merge `fe9d924`; 4.7 via `0e0654f`. ADR-034..039. Dev `xyz_lms` at 0013. On branch `main`. Next → 4.8 (staging deploy)._

_Prior: 2026-06-11 - **Stage 4.6 FULLY VERIFIED.** The live browser gate ran GREEN — full active Playwright suite 9/9 (4.3.5b/c/e, 4.4, 4.5d-summary-browser, 4.5d-summary-fault ×2, 4.6d replacement-continuity + retry) against a backend image freshly built from branch HEAD (verified by content-hash vs git). The gate surfaced + fixed TWO cross-stage-seam regressions: F-4.6c-1 (startup recovery poisoned the fork-per-job module engine pool → isolated NullPool engine, `tests/test_worker_startup_recovery.py`) and F-4.6b-2 (orphaned activation trigger after the 4.6b DAG decouple → every leaf attempts idempotent activation, 3 ordering regression tests). Backend 353 passed; frontend tsc clean. dev `xyz_lms` migrated 0009→0012. Deferred: F-4.6d-3 (C-lite read-contract violation in the post-retry status path → owner Task 4.6d-P1; production-masked). On branch `stage/4.6-replacement-retry`. Next → 4.7 (student surface) — inherits a resolver proven correct in a real browser._

## Stage 4.6 — Replacement / Retry / Supersession (FULLY VERIFIED)

**4.6d Lecturer UI + active-summary preview endpoint — BUILT (live browser gate pending):**
- **Preview endpoint** `GET .../transcript-active-summary-preview` (lecturer-only, over `ActiveTranscriptSummaryResolver`):
  `activeTranscriptId` + brief/detailed content + `briefEligible`/`detailedEligible` + `hasPendingReplacement`.
  NO student surface (4.7). No checksum/storageKey exposed.
- **Lecturer UI** (4.5d surface): Replace (file input + inline confirm; **double-replacement warning** when a
  pending exists) reusing the upload endpoint (creates pending); Retry (on `failed` && `retryable`, targets
  the active transcript) via the 4.6b retry endpoint; per-step states strip + sanitized reason; **"new version
  processing"** badge from a preview poll that also detects the atomic swap and refreshes to the new active.
- **Browser gate** `tests/e2e/4.6d-replace-retry.spec.ts`: RETRY FLOW (forced step fail → retry → summarized,
  no duplicates; embed failure doesn't block summaries) + REPLACEMENT CONTINUITY (preview stays on the active
  while pending → flips to v2 on swap; old superseded with lineage). Fencing = deterministic pytest
  (`test_stale_worker_aborts_after_reaper_then_retry`).
- **Cross-stage e2e fixes (rule 14):** 4.3.5e duplicate-upload `409`→`201` pending; `db.mjs` `is_active`→`lifecycle_state`
  + `getTranscriptsBySection`.
- **Deviations (approved):** live browser gate deferred to the developer; minimal pending UI (badge only).
- Verified: `pytest` **349 passed** (+4: 3 preview + 1 fencing); `tsc --noEmit` exit 0; client regen
  (`getSectionActiveSummaryPreview` + `ActiveSummaryPreviewRead`); `npx playwright test --list` 9 specs.
  Report: [[steps/stage-04/4.6d-lecturer-ui-browser-gate]].

**4.6c Recovery — BACKEND VERIFIED (browser gate → 4.6d):**
- `app/domains/recovery/`: **stuck-row reaper** + **loss-safe storage reconciliation**, both idempotent,
  singleton-locked (`pg_try_advisory_lock` on a dedicated connection), MaintenanceRun-logged.
- Reaper: never-enqueued parse → re-enqueue; queued-not-live-in-RQ → re-enqueue (subsumes the removed
  `reenqueue_summaries.py`); running-past-step-threshold-not-live → mark `failed`+`crashed` (retryable,
  fenced re-read FOR UPDATE). Liveness = RQ registry (stable job_ids for embed/summary) + per-step age
  (parse/chunk); **no heartbeat columns**. Action-capped. Runs at worker startup (`REAPER_RUN_AT_STARTUP`)
  + admin trigger. Produces the `crashed` category 4.6b defined.
- Reconciliation: `storage.list_objects` (recursive, scoped to `…/transcripts/…`, capped) vs DB keys;
  orphans (older than grace) reported, deleted only in `mode='cleanup'` + `RECONCILIATION_CLEANUP_ENABLED`
  (capped); missing refs reported loudly, never auto-fixed; superseded files referenced (retained).
- `MaintenanceRun` table (migration `0012`); admin-only `POST /admin/maintenance/{reap-stuck-rows,reconcile-storage}`.
- **Deviation:** liveness via RQ-registry + age (no heartbeat, spec-allowed); reaper at startup, reconciliation
  admin-only by default. **Not built:** lecturer UI + preview endpoint + browser gate (4.6d).
- Verified: `pytest` **344 passed** (+15 in `test_recovery.py`); migration `0012` round-trips fresh;
  `tsc --noEmit` exit 0; client regen (AdminService +2 methods + `MaintenanceRunRead`). Report:
  [[steps/stage-04/4.6c-recovery-reaper-reconciliation]].

**4.6b Retry — BACKEND VERIFIED (browser gate → 4.6d):**
- Retry endpoint `POST /modules/{m}/sections/{s}/transcript/{transcriptId}/retry` (lecturer-only, assigned;
  superseded → 409 `TRANSCRIPT_SUPERSEDED`; nothing failed → 409 `NO_RETRYABLE_FAILURE`). Targets the
  active transcript OR a failed pending replacement. `resolve_retry_scope` resumes from the earliest failed
  step over the DAG (parse cascade; else earliest of chunk/embed + independent failed summaries).
- **DAG decouple:** summary jobs fork from **parse** (was embed) — an embed failure no longer blocks
  summaries; a summary retry never touches chunks/embeddings. (Moved `insert_summary_jobs` call site; logic
  unchanged — modifies 4.5a wiring, change-history appended.)
- **Fencing** (`fencing.can_commit_step`): before any destructive write, re-read job + transcript FOR
  UPDATE and abort if superseded or no-longer-running. Wired into parse/chunk/embed (incl. each batch)/
  summary. Parse gained a one-active index; chunk keeps coexistence.
- **Per-step delete-and-regenerate:** parse deletes summaries→chunks→segments (FK order); chunk deletes
  chunks; embed rewrites in place; summary success-only — NO duplicate segments/chunks/summaries on retry.
- **Failure taxonomy:** each step sets a sanitized `failure_category`; projection surfaces `failureCategory`
  (one of 9) + `retryable`. Missing raw file → `storage_missing` (`StorageObjectNotFoundError`). Migration `0011`.
- **Deviation:** endpoint is section-scoped-with-transcriptId (not the spec's literal `/transcripts/{id}/retry`);
  `unsupported_file` has no parse producer (upload gates type). **Not built:** reaper/reconciliation/
  MaintenanceRun (4.6c — produces `crashed`), lecturer UI + preview endpoint + browser gate (4.6d).
- Verified: `pytest` **329 passed** (+24 in `test_transcript_retry.py`); migration `0011` round-trips fresh;
  `tsc --noEmit` exit 0; client regen (+`retrySectionTranscriptProcessing`, +`failureCategory`/`retryable`).
  Report: [[steps/stage-04/4.6b-retry-fencing-failure-taxonomy]].

**4.6a Foundation — BACKEND VERIFIED (browser gate → 4.6d):**
- `transcripts.lifecycle_state` (active|pending|superseded) replaces boolean `is_active` (migration `0010`);
  lineage (`replacement_of`/`superseded_by`/`supersession_reason`/`superseded_at`); partial-unique
  one-active AND one-pending per section.
- Replacement no longer 409s: a second upload creates a `pending` row under a `module_sections` `FOR UPDATE`
  lock; a prior pending is discarded (`discarded_pending`). `try_activate_pending_transcript` swaps
  old→superseded / pending→active atomically once `overall_state=='summarized'` + exactly one eligible
  brief + one detailed; triggered post-summary-completion (no-op otherwise).
- `transcripts/domain/summary_eligibility` owns the predicate (identity + checksum; success-only table →
  "generated" = row exists) + write-side readiness; `platform/query/ActiveTranscriptSummaryResolver` wraps
  the SAME predicate read-only (lecturer preview lands 4.6d; student authz 4.7). ADR-029, ADR-030.
- Per-row provenance: `created_by_ingestion_job_id` on segments/chunks/summaries + a SEPARATE
  `embedding_created_by_ingestion_job_id` on chunks.
- Env-gated fault harness `PIPELINE_FAULT_INJECTION_ENABLED` (no-op off, refuses outside non-prod) +
  `seed_failed_ingestion_job`; wired into all five steps; `docker-compose.fault.yml` override.
- **Deviation:** parse/chunk one-active "current job" indexes deferred to 4.6b (would break the tested
  two-chunk-jobs-coexist replacement path). **Not built:** retry/fenced deletes (4.6b), reaper/
  reconciliation/MaintenanceRun (4.6c), lecturer UI + preview endpoint + browser gate (4.6d).
- Verified: `pytest` **305 passed** (+16 in `test_transcript_lifecycle.py` + provenance test); migration
  `0010` round-trips on a fresh DB (up→base→up, `is_active` gone); `tsc --noEmit` exit 0; client regen
  (+`lifecycleState`). Report: [[steps/stage-04/4.6a-lifecycle-supersession-foundation]].

## Stage 4.5 — AI Infrastructure + Summary Generation (✅ FULLY VERIFIED)
Gate 2.A is GREEN: developer restored `knowledge/roadmap.md` v3 (sha256 `a677c580…`, recorded in
[[steps/stage-04/4.5a]]); the master spec was filed with patches A/B and ADR refs remapped
015..018 → adr-025..028.

**4.5a (platform/llm foundation) — COMPLETE, verified in CI:**
- Built `backend/app/platform/llm/` (gateway; transport-only provider protocol + K2Think stub +
  DeterministicTestProvider with E2E-only fault injection; PromptRegistry flat-files + startup
  validation + content hashing; Redis limiter with RPM/TPM/concurrency + TTL leases + headroom;
  ContextBuilder; OutputValidator; gateway-attempt AIRequestLog helpers).
- `AIRequestLog` + `GeneratedLectureSummary` models + migration `0008`; `IngestionJob.failure_category`
  + summary one-active partial-unique index.
- `ai` RQ queue + `ai_worker` container; after-embed enqueue of both summary jobs (queued rows +
  after-commit enqueue; left queued on enqueue failure for the 4.6 sweeper).
- Status projection gained `summary_brief`/`summary_detailed` steps + `summarizing`/`summarized`
  states + per-step failure with category copy. Prompts at `backend/prompts/` + CI drift guard.
- **No real K2Think call exists** (`K2ThinkProvider.send` raises NotImplemented; `backend/app/ai/` removed).
- Verified: `alembic upgrade head` → `0008`; `pytest` → **236 passed** (43 new); drift guard OK;
  limiter TTL-lease reclaim proven; `ai_worker` live-processed brief+detailed jobs; OpenAPI client
  regenerated; `tsc --noEmit` exit 0. Report: [[steps/stage-04/4.5a]].

**4.5b–4.5d — DONE (Stage 4.5 FULLY VERIFIED 2026-06-11):**
- 4.5b — first REAL K2Think call wired (brief); single-model deviation on `K2-Think-v2` (ADR-025);
  full HTTP error classification; in-call rate-limit backoff recorded in-row; migration 0009.
- 4.5c — detailed generation live; routing split exercised (brief=cerebras / detailed=use_nvidia);
  ADR-027. ([[steps/stage-04/4.5b]], [[steps/stage-04/4.5c]])
- 4.5d — lecturer summary UI (brief + detailed by section) + status-badge rework (backoff polling, no
  60s timeout) + authz 404/403 matrix + browser gate. Close-out gates: **Gate 1** full active E2E
  suite green as a set; **Gate 2** forced-fault coverage (invalid_output/invalid_input); **Gate 3**
  real-provider smoke PASS (model-ID echo matched on both routes; brief 11.9s, detailed 39.8s, both
  finish_reason stop). Real-call-only fixes: F-4.5-48 (extractor/truncation), F-4.5-49 (route-aware
  timeout). ([[steps/stage-04/4.5d]], [[steps/stage-04/4.5d-real-provider-smoke]])
- Open (non-blocking, accepted-with-trigger): F-4.5-27, F-4.5-28. Carried to 4.6: F-4.5-47.

## Current focus
Stage 1 is FULLY VERIFIED. Session 1.1b satisfied the browser gate: the root page called `http://localhost:8000/health` directly through the generated client, CORS allowed `http://localhost:3000`, and the browser showed live backend state.

Stage 2  Identity + access / P0   FULLY VERIFIED  (browser gate: 4.3.5c)

Session 4.3.5c completed the Stage 2 product UI backfill. Admin user/module management, lecturer assigned modules, and student assigned modules are wired to real backend data through the generated client wrapper. The approved Option A read-only admin module-membership projection is implemented and documented in ADR-023.

Stage 3  Content + visibility / P1   FULLY VERIFIED  (browser gate: 4.3.5d Checkpoint E + E2-B1)

Stage 4.1  Transcript upload            FULLY VERIFIED  (browser gate: 4.3.5e)
Stage 4.2  Transcript parsing           FULLY VERIFIED  (browser gate: 4.3.5e)
Stage 4.3  Transcript chunk persistence FULLY VERIFIED  (browser gate: 4.3.5e)
Stage 4.4  Embeddings                   FULLY VERIFIED  (browser gate: 4.4)
Stage 4.5  AI infra + summaries          FULLY VERIFIED  (gate: 4.5d browser gate + full E2E + real-provider smoke)
Stage 4.6  Replacement / retry / superse. FULLY VERIFIED — live browser gate GREEN (full active suite 9/9); F-4.6c-1 + F-4.6b-2 fixed; on branch stage/4.6-replacement-retry

Client Edge Recovery Block (4.3.5): COMPLETE
  Stages 1, 2, 3, 4.1, 4.2, 4.3 all FULLY VERIFIED.
  `/tracer` deleted; `NEXT_PUBLIC_TRACER_ENABLED` removed.
  Stage 4.4 embeddings are fully verified.

## Stage 4.1-4.3 browser gate - 4.3.5e
- Lecturer uploads VTT to lecture section; status appears: PROVEN
- Status reaches worker-driven terminal state (`completed`): PROVEN
- Segments and chunks persisted (counts > 0); no raw text exposed: PROVEN
- TXT fallback reaches terminal: PROVEN
- Transcript upload rejected on assignment section: PROVEN
- One-active-transcript behavior (409 rejected): PROVEN
- Existing active transcript loads after page refresh: PROVEN
- Student transcript upload rejected 403, session kept: PROVEN
- No student transcript text surface: PROVEN

## Stage 3 recovery status - 4.3.5d
4.3.5d-B1 fixed the Checkpoint 0 blocker: admin module creation now generates predefined module sections.

Current state:
- Admin module creation now creates four default `module_sections`: `Lecture 1`, `Lecture 2`, `Lab 1`, and `Assignment 1`.
- Generated sections default to draft and remain hidden from students until published.
- Checkpoint A is complete: lecturers can open assigned module detail, see generated sections from the backend, edit lecturer notes, save through the wrapper/generated client, and re-fetch persisted notes.
- Existing E2E fixtures still insert sections directly for old setup paths; the resumed Stage 3 browser gate must prove the product path.
- 4.3.5d-B0 added the approved multipart upload helper required for Checkpoint B.
- `frontend/src/lib/api/upload.ts` supports section upload and asset replace through the existing backend content routes, with Supabase bearer auth and `FormData` field `file`.
- Checkpoint B is complete: lecturers can upload a real PDF to a generated section, see the backend re-fetched asset row and asset `processingStatus`, replace that specific asset, and see backend non-PDF rejection as `role="alert"`.
- Checkpoint C is complete: lecturers can publish and unpublish sections through wrapper/generated client calls, with backend re-fetch after each toggle and separate visible section `publishStatus` and asset `processingStatus`.
- Checkpoint D is complete: students can open assigned module detail, see only published sections returned by the backend student response, see lecturer notes and published assets, and open/download a PDF through the backend signed URL endpoint.
- Checkpoint E passed the original full Stage 3 browser gate: lecturer uploaded/replaced PDF, added notes, published one section, student saw only published content, opened the PDF via signed URL, and authenticated student upload was rejected with 403.
- Supplemental E2 initially blocked: after lecturer unpublish, the authenticated student section-list response excluded `Lecture 1`, but a fresh signed URL request for that unpublished section asset returned `404 SECTION_NOT_FOUND` instead of the required authenticated `403`.
- 4.3.5d-E2-B1 fixed that denial status. E2 rerun passed with post-unpublish student response `[]`, fresh signed URL status `403`, response body `{"detail":"CONTENT_FORBIDDEN"}`, and `/me` still role `student`.
- Stage 3 is FULLY VERIFIED.

Required next:
- Proceed to 4.3.5e - Stage 4.1-4.3 Transcript UI Backfill.

## Stage 2 browser gate - 4.3.5c
- Admin-created lecturer/student accounts through UI: PROVEN
- Admin-created modules with owner lecturers through UI: PROVEN
- Owner auto-membership accounted for with separate owner actors: PROVEN
- Assign lecturer/student to modules through UI: PROVEN
- Real member list drives removal and re-fetch after removal: PROVEN
- Lecturer sees assigned Module A and not unassigned Module B: PROVEN
- Student sees assigned Module A and not unassigned Module B: PROVEN
- Inactive lecturer fresh login is denied app access: PROVEN
- Existing inactive lecturer session reload is denied app access: PROVEN
- Non-admin admin-endpoint call returns 403 while preserving session and avoiding `/login` redirect: PROVEN

## Client edge - 4.3.5b result
- App shell + role routing (GET /me-driven, role-prefix guard): PROVEN
- Token refresh with rotated-token Authorization header: PROVEN
- 401 recovery (signOut + redirect to /login): PROVEN
- Client route guard cross-role (/unauthorized, session kept): PROVEN
- Server-side 403 cross-role defense in depth (session kept): PROVEN
- Logout from AppShell (session cleared + /login): PROVEN
- /tracer deleted after real transcript UI replaced the temporary recovery route: PROVEN

## Done recently
- 2026-06-10: Comprehensive knowledge base review completed; report at `KNOWLEDGE_REVIEW.md`. Every file in `knowledge/` was read. 27 specific anomalies identified across status values, log types, commit fields, stage number formatting, link paths, and stale architecture documentation. No source code changed.
- 2026-06-10: Comprehensive codebase review completed; report at `knowledge/CODEBASE_REVIEW.md`. Verified live against the running Docker stack: backend `193 passed`, frontend `tsc --noEmit` exit 0, migrations at head `0007`, DB has 10 tables with `vector` 0.8.2 + `pgcrypto`, embedded chunks carry 384-dim L2 vectors with full provenance, direct-fetch/LLM/tracer scans clean. Playwright gates were NOT re-run this session (status inherited from prior reports). Key findings: no in-repo roadmap file; no `platform/llm`/`platform/events` (AI/event stages not started); no frontend unit tests. No source code changed.
- Session 4.4: transcript chunk embeddings completed and fully verified. Final H rerun used the rebuilt `.env.e2e` stack with separate ingestion and embedding workers; 4.4 browser gate passed on run `e2e-1781089037-4-4-final`, 4.3.5e projection regression passed on run `e2e-1781089206-4-3-5e-regression`, backend passed `191 passed`, frontend type-check/build passed, direct-fetch/JWT scans were clean, and embedding DB proof showed one embedded chunk with 384-dimensional vector and complete provenance. Stage 4.4 is FULLY VERIFIED.
- Session 4.3.5e Part 5: final Stage 4.1-4.3 transcript browser gate passed on run `e2e-1780991715-rf0lu0d7`. Lecturer uploaded `ensemble-methods.vtt` through lecture UI and `lab-notes.txt` through lab UI; both reached `completed`; DB proof showed 4 ingestion jobs, 7 segments, and 2 chunks; assignment upload returned 422; duplicate upload returned 409; student upload/status returned 403 while `/me` stayed role `student`; teardown removed exact manifest-owned storage/transcript/job/segment/chunk/module artifacts and reran idempotently. Stage 4.1-4.3 are FULLY VERIFIED and Client Edge Recovery Block 4.3.5 is COMPLETE.
- Session 4.3.5d-E2-B1: repaired post-unpublish fresh signed URL denial status. Backend now returns `403 CONTENT_FORBIDDEN` for authenticated assigned student access to an existing unpublished section asset; targeted content test passed (`1 passed`), full backend passed (`151 passed`), E2 rerun passed on module `019ea733-95e9-774f-9b78-26d30e385ece`, frontend type-check/build/scans passed, generated client fresh, and Stage 3 returned to FULLY VERIFIED.
- Session 4.3.5d-E2: supplemental signed URL revocation proof blocked on fresh post-unpublish signed URL denial status. Browser/API proof used module `019ea719-80ba-771c-bea7-716638033078`; after unpublish, student `/modules/<moduleId>/sections` returned `[]`, but `GET /modules/<moduleId>/sections/<lecture1SectionId>/assets/<assetId>/download-url` returned `404 {"detail":"SECTION_NOT_FOUND"}` instead of required `403`. Student `/me` still returned role `student`. Product source unchanged; Stage 3 moved back to UI PENDING.
- Session 4.3.5d Checkpoint E: full Stage 3 browser gate passed on fresh product-path module `019ea6ac-9d6a-75bc-9219-1dfd6e7c87b6`. Lecturer and student used separate browser contexts; lecturer uploaded `stage3-gate-upload.pdf`, replaced it with `stage3-gate-replacement.pdf`, added notes, published `Lecture 1`, and left `Lecture 2` draft. Student server response contained only `Lecture 1`, signed URL returned HTTP 200, authenticated student upload returned 403, and `/me` still returned student. Frontend type-check/build passed; direct fetch/JWT scans were clean; generated client fresh; no backend changes. Stage 3 was marked FULLY VERIFIED at that point, then superseded by the E2 blocker above.
- Session 4.3.5d Checkpoint D: student published-only view and signed URL open completed. Browser smoke passed on fresh product-path module `019ea663-3999-7084-aa2b-a72e7b24c2e0`; the student server response contained only `Lecture 1`, excluded draft `Lecture 2`, rendered lecturer notes and `checkpoint-d-upload.pdf`, and signed URL fetch returned HTTP 200. Frontend type-check/build passed; direct fetch/JWT scans were clean; no backend changes; Stage 3 remains UI PENDING.
- Session 4.3.5d Checkpoint C: publish/unpublish controls and status separation completed. Browser smoke passed on fresh product-path module `019ea648-4a2e-750e-9563-7263fae4a0a4`; the UI showed section Draft plus asset `completed`, published the section to Published while asset status stayed `completed`, then unpublished to Unpublished while asset status stayed `completed`. Frontend type-check/build passed; direct fetch/JWT scans were clean; no backend changes; Stage 3 remains UI PENDING.
- Session 4.3.5d Checkpoint B: lecturer PDF upload and asset-level replace UI completed. Browser smoke passed on fresh product-path module `019ea629-c5ae-70da-915b-c64b19ab7599`; the UI uploaded `checkpoint-b-upload.pdf`, re-fetched an asset row, rendered asset `processingStatus` separately from section Draft status, replaced the asset with `checkpoint-b-replacement.pdf`, and rendered backend non-PDF rejection as `role="alert"`. Frontend type-check/build passed; direct fetch/JWT scans were clean; no backend changes; Stage 3 remains UI PENDING.
- Session 4.3.5d-B0: restored `frontend/src/lib/api/upload.ts` as the controlled multipart helper for section asset upload and asset-level replace. Frontend type-check and Next build passed; direct fetch/JWT scans were clean; generated client freshness passed; no backend or product UI files changed; Stage 3 remains UI PENDING.
- Session 4.3.5d Checkpoint A: lecturer module detail and notes UI completed. `/lecturer/modules/[moduleId]` renders generated backend sections, saves notes through wrapper/generated client, re-fetches after save, has no create/delete/reorder/upload/publish/student UI, frontend type-check and `next build` passed, direct fetch/JWT scans were clean, and no backend files changed.
- Session 4.3.5d-B1: admin module creation now generates four predefined draft sections in the backend product path. Targeted admin/content tests passed; full backend passed with `151 passed`; frontend type-check passed; generated client freshness passed with no diff; no frontend UI work was added; Stage 3 remains UI PENDING.
- Session 4.3.5d Checkpoint 0: blocked before UI implementation. Generated client freshness passed with no diff; admin module creation source and empirical probe showed `module_sections_count=0`; existing E2E fixture directly inserts sections; product source was unchanged; Stage 3 remains UI PENDING.
- Session 4.3.5c: Stage 2 Admin UI backfill completed. Backend projection tests passed (`30 passed`); full backend suite passed (`149 passed`); frontend type-check passed; direct fetch and JWT-role scans had no matches; Playwright `tests/e2e/4.3.5c-stage2-admin.spec.ts` passed `1 passed (9.4s)`; Stage 2 is FULLY VERIFIED.
- Session 4.3.5b: app shell and role routing completed. Rebuilt E2E stack passed; fixture seed produced four Auth users, four app users, one module, two active memberships, and two sections; Playwright `tests/e2e/4.3.5b-shell-routing.spec.ts` passed `1 passed (13.7s)`; frontend type-check passed; static fetch/JWT scans returned no matches; full backend `pytest` passed with `144 passed, 71 warnings` - completed 2026-06-05 15:42.
- Session 4.3.5a: browser tracer proof passed with real Supabase login, real backend, real app DB rows, local private Supabase Storage, and separate lecturer/student browser contexts - committed at `5f92698`.
- Session 1.1b: Stage 1 browser gate satisfied. Docker-backed automated checks passed (`3 passed` config tests, `4 passed` health/CORS tests, full backend `136 passed`, frontend type-check exited 0), browser polling showed `ok -> unreachable -> ok`, and human DevTools Network confirmed direct `http://localhost:8000/health` with `Access-Control-Allow-Origin: http://localhost:3000` - completed 2026-06-03 13:58.

## In progress
- **Stage 4.7 — BUILT + browser gate GREEN, AWAITING HUMAN VERIFICATION.** On branch `stage/4.7-student-summaries`
  (off `fix/4.6d-p1-overallstate-projection` — §6 depends on the F-4.6d-3 projection fix, so 4.7 cannot merge
  until 4.6d-P1 lands on main first). Terminal state: NOT self-certified FULLY VERIFIED — Arthur reviews
  against §15 (audit G8 + security gates G3–G6 for assertion STRENGTH) and makes the stamp.
  See [[steps/stage-04/4.7a-student-summary-read-policy]], [[steps/stage-04/4.7b-student-page-browser-gate]],
  [[steps/stage-04/4.7-stage3-restore]].

## Next up
- **Arthur:** review the 4.7 report trio against §15; if honestly green, set Stage 4.7 FULLY VERIFIED +
  flip the roadmap status table. Then land 4.6d-P1 on main, then merge 4.7.
- **4.8 — first hosted deploy (staging):** the lecturer→student summary path (incl. one real K2Think summary)
  runs against the staging URL. Keep the 4.7 gate runnable against a configurable base URL (§20). Env hygiene:
  fault-injection + E2E hooks absent in hosted builds; `RECONCILE_AT_STARTUP`/`RECONCILIATION_CLEANUP_ENABLED` OFF.
- Dev `xyz_lms` is **migrated to 0013**. 11.1: point a cron at `run_stuck_row_reaper` / `run_storage_reconciliation`.

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- Transcript raw-object writes are live-tested in the 4.3.5e browser gate; future storage changes must preserve exact-key teardown and private-object behavior.
- Existing storage-key generation does not support run-scoped `e2e/{runId}` prefixes; E2E browser upload tests must clean exact returned keys only unless a future test-infrastructure change is approved.
- Replace/upload cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Already-issued signed read URLs remain usable until expiry; unpublish blocks future minting, not issued bearer URLs.
- Raw transcript files are private and not exposed; future summary/transcript surfaces must continue to avoid exposing raw storage keys.
- Chunk text is not exposed through any user-facing DTO yet; future 4.7 surfaces must preserve the no-raw-key and role-aware visibility boundaries.
- Transcript parse recovery is intentionally deferred to Session 4.6c (reaper): enqueue failure can leave `uploaded`, and mid-parse crash can leave `parsing` plus a `running` job. (4.6a built the state model + provenance the reaper keys off; the reaper itself is 4.6c.)
- Transcript chunk recovery is intentionally deferred to Session 4.6c (reaper): parse-to-chunk enqueue failure can leave a queued chunk job, and mid-chunk crash can leave a `running` chunk job.
- **Dev DB drift RESOLVED (4.6 close-out):** migrations `0010`+`0011`+`0012` were applied to dev `xyz_lms` at the live-gate cutover (after a pre-flight on a pg_dump copy: backfill correct, all three partial-unique indexes built clean). Dev `xyz_lms` is now at `0012` with images rebuilt from the 4.6 branch. Hosted/prod still needs the same `0010→0012` apply at its next deploy (pre-flight on a data copy first).
- Superseded pending transcripts leave orphaned storage objects until the 4.6c reconciliation job reclaims them (by design).
