---
type: findings
stage: "4.3.5"
session: "4.3.5e"
slug: transcript-ui-backfill
status: open
created: 2026-06-08
updated: 2026-06-08 20:47 +0400
---

# Findings - 4.3.5e Transcript UI Backfill

## Linked documents
- Recovery plan: [[specs/recovery/client-edge-recovery-plan]]
- Architecture: [[architecture/frontend]]
- Prior findings: [[findings-4.3.5d]]
- Spec: [[specs/stage-04/4.3.5e-stage4-transcript-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5e-stage4-transcript-ui-plan]]
- Report: [[4.3.5e-part2-prerequisite-terminal-state-repair]]
- Report: [[4.3.5e-part3-transcript-frontend-ui]]
- ADR: [[decisions/adr-024-stage-4-3-post-chunk-terminal-status]]

## Checkpoint 0 surface map
- Upload endpoint: `POST /modules/{module_id}/sections/{section_id}/transcript`.
- Status endpoint: `GET /modules/{module_id}/sections/{section_id}/transcript`.
- Response DTO: `TranscriptMeta` metadata only.
- Worker path: backend enqueues RQ jobs to the `ingestion` queue; worker consumes the same queue.
- Product UI state: transcript feature code exists but is not mounted in the lecturer module detail route.

## Terminal-state behavior
- Controlled live probe uploaded `checkpoint0-probe.vtt` through the backend API on the running stack.
- Parse job completed.
- Chunk job completed.
- Segment rows persisted: `2`.
- Chunk rows persisted: `1`.
- Product-visible transcript status after chunk completion remained `chunking`.
- `chunking` is not terminal for 4.3.5e acceptance.
- Part 2 repair changed successful chunk completion to set `Transcript.status = "completed"`.
- Targeted worker tests passed after the repair: `19 passed`.
- Full backend tests passed after the repair: `151 passed, 78 warnings`.
- Generated API client freshness passed after the repair: `bash scripts/generate-api-client.sh && git diff --exit-code frontend/src/lib/api` exited 0 with no diff.

## Upload contract
- Multipart field: exactly one file field named `file`.
- Accepted extensions: `.vtt`, `.txt`.
- Accepted content: UTF-8; VTT must start with `WEBVTT`; TXT must be non-empty.
- Effective MIME values: `text/vtt`, `text/plain`.
- Max size: `MAX_TRANSCRIPT_UPLOAD_BYTES`, default `10485760`.
- Accepted section types: `lecture`, `lab`.
- Rejected section types: `assignment`, `supplementary` with `422 SECTION_TYPE_UNSUPPORTED`.

## Status read contract
- Endpoint returns `TranscriptMeta` only.
- No raw transcript text, parsed segments, chunks, storage key, checksum, or counts are exposed through the product endpoint.
- Counts are available only through DB/job tables and should be proven in E2E by test-level DB reads unless an approved backend projection is added later.

## One-active behavior
- A second upload to the same section with an active transcript returns `409 TRANSCRIPT_ALREADY_EXISTS`.
- Supersession/replacement is not implemented and remains out of scope before Stage 4.6 unless explicitly approved.

## Student denial behavior
- Student upload to the transcript endpoint returns `403 TRANSCRIPT_FORBIDDEN`.
- Student `/me` remains valid after the 403.
- Student status read also returns `403 TRANSCRIPT_FORBIDDEN`.
- No student-facing raw transcript read path was found.

## Worker-in-E2E behavior
- `docker compose ps` showed the worker service running.
- `docker-compose.yml` runs the worker with `python -m app.workers.worker`.
- `docker-compose.e2e.yml` layers `.env.e2e` onto backend, worker, and frontend.
- Backend and worker both use `INGESTION_QUEUE_NAME = "ingestion"` with `REDIS_URL`.

## Findings

| ID | Finding | Severity | Resolution state | Required decision |
|---|---|---|---|---|
| F-4.3.5e-001 | No current 4.3.5e session spec file was found under `knowledge/specs/stage-04/`, even though Checkpoint 0 referenced it. | blocker | fixed_in_current_block | Fixed by persisted spec `knowledge/specs/stage-04/4.3.5e-stage4-transcript-ui-backfill.md`, plan `knowledge/plans/stage-04/4.3.5e-stage4-transcript-ui-plan.md`, and Part 2 report. |
| F-4.3.5e-002 | Successful parse+chunk leaves `transcripts.status = 'chunking'` after the chunk job completes and chunks persist. `chunking` is not terminal for the browser gate. | hard blocker | fixed_in_current_block | Fixed by `backend/app/domains/transcripts/chunk_service.py`; `tests/test_transcript_worker.py` now proves post-chunk `completed`. |
| F-4.3.5e-003 | Product status endpoint exposes no segment/chunk counts. | medium | accepted_non_blocking_with_rationale | Use test-level DB reads for the Playwright gate; do not add product raw-text/count endpoints in Checkpoint 0. |
| F-4.3.5e-004 | Existing transcript frontend code is unmounted and bypasses the wrapper/upload-helper auth-recovery pattern. | medium | fixed_in_current_block | Fixed in Checkpoint A/B by `api.transcripts.getActive`, `uploadTranscript`, `SectionTranscriptControl`, `TranscriptStatusBadge`, lecture/lab-only mounting in `LecturerModuleDetail.tsx`, and removal of the old unmounted `frontend/src/features/transcripts/*` bypass; frontend type-check/build and guardrail scans passed. |
| F-4.3.5e-005 | E2E has no reusable safe DB read helper/run manifest, and prior Stage 3 runs recorded teardown gaps for product-created rows/storage objects. | medium | deferred_to_named_future_session | Deferred to 4.3.5e Checkpoint D because run manifest and teardown utility are E2E tooling work. |

## Recommendation
Proceed to 4.3.5e Checkpoint A/B only after human approval.

Do not mark Stage 4.1-4.3 FULLY VERIFIED until the Playwright browser gate passes.
