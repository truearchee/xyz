---
type: architecture
stage: 02
created: 2026-05-29
updated: 2026-06-18
related-session: knowledge/specs/stage-02/2.1-db-spine.md
---

# DB Spine Architecture

## Linked documents
- Spec: [[specs/stage-02/2.1-db-spine]]
- Plan: [[plans/stage-02/2.1-db-spine]]
- Report: [[steps/stage-02/2.1-db-spine]]
- Spec: [[specs/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Spec: [[specs/stage-03/3.2-publish-and-notes]]
- Report: [[steps/stage-03/3.2-publish-and-notes]]
- Spec: [[specs/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair]]
- Plan: [[plans/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair]]
- Report: [[archive/stage-04/4.3.5d/4.3.5d-B1-section-generation-repair]]
- Spec: [[specs/stage-05/5.5-module-schedule-section-metadata]]
- Report: [[steps/stage-05/5.5a-schedule-generation]]
- Report: [[steps/stage-05/5.5b-metadata-edit-and-week-resolver]]
- Report: [[steps/stage-05/5.5c-lab-attachments]]
- Report: [[steps/stage-05/5.5d-dev-reseed]]
- Report: [[steps/stage-05/5.5e-ui-browser-gate]]
- Decision: [[decisions/adr-040-schedule-driven-section-generation]]
- Decision: [[decisions/adr-041-section-metadata-and-week-resolver]]
- Decision: [[decisions/adr-042-lab-attachments]]
- Decision: [[decisions/adr-043-dev-reseed]]
- Spec: [[specs/stage-09/9-my-progress-dashboard]]
- Report: [[steps/stage-09/9-my-progress-dashboard]]
- Decision: [[decisions/adr-052-single-tenant-mvp]]
- Spec: [[specs/stage-04/4.1-transcript-upload]]
- Plan: [[plans/stage-04/4.1-transcript-upload]]
- Report: [[steps/stage-04/4.1-transcript-upload]]
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Spec: [[specs/stage-04/4.3-transcript-chunking]]
- Plan: [[plans/stage-04/4.3-transcript-chunking]]
- Report: [[steps/stage-04/4.3-transcript-chunking]]
- Architecture: [[architecture/storage]]
- Architecture: [[architecture/worker]]
- Decision: [[decisions/adr-015-transcript-upload-boundary-active-invariant]]
- Decision: [[decisions/adr-016-transcript-file-validation-storage-metadata]]
- Decision: [[decisions/adr-017-ingestion-job-worker-spine]]
- Decision: [[decisions/adr-018-transcript-segment-timestamps]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]
- Decision: [[decisions/adr-020-transcript-chunk-normalization-versioning]]
- Decision: [[decisions/adr-021-transcript-chunk-transactional-handoff]]

## Current structure
The backend now has a SQLAlchemy declarative model package under `backend/app/platform/db/models/`. Alembic imports `app.platform.db.models` to register all model metadata before migrations run.

## Tables
- `app_users` anchors local application users and maps them to Supabase Auth through `auth_provider_id`.
- `course_modules` stores course offering containers owned by app users. Stage 5.5a reuses
  `starts_on`/`ends_on` for course dates and adds nullable schedule provenance:
  `week_start_day`, `session_pattern`, and `quiz_day`.
- `course_memberships` connects users to modules and preserves archived enrollment history.
- `module_sections` stores ordered module content instances and keeps scheduling fields separate.
- `section_assets` stores private storage keys and file metadata for uploaded section materials.
  Session 3.1 migrated the Stage 2 placeholder from `file_url` to `storage_key`, added
  `checksum_sha256`, and records `uploaded_by_user_id` for the current stored object. Stage 5.5c adds
  `asset_kind` (`processable` or `attachment`) so PDFs stay processable-but-inert and lab attachments
  are structurally excluded from transcript/AI processing.
- `transcripts` stores raw transcript upload metadata for lecture/lab sections. Session 4.1 adds the table with full lifecycle status values but only writes `status='uploaded'` and `source_type='manual_upload'`.
- `transcript_segments` stores immutable parsed VTT/TXT output for transcripts. VTT segments use integer millisecond timestamps; TXT fallback segments have null timestamps.
- `transcript_chunks` stores normalized, ordered chunk text derived from immutable segments. Chunks carry segment ids, sequence bounds, millisecond time bounds or null TXT bounds, version strings, token counts, nullable `vector(384)` embedding placeholders, and `updated_at` for future embedding writes.
- `ingestion_jobs` tracks idempotent background ingestion work. Session 4.3 wires `job_type='chunk'` after parse and adds `result_metadata jsonb` for structured worker output counts. Session 4.5a uses the pre-seeded `job_type` values `generate_brief_summary` / `generate_detailed_summary` and adds a nullable `failure_category` column (`provider_transient | rate_limited | invalid_output | invalid_input | failed`).
- `ai_request_logs` (Session 4.5a) records one row per `LLMGateway` completion attempt (gateway-attempt log, not provider-call log). Holds prompt identity + hashes + token estimate/usage + status; provider transport fields are nullable because an attempt may terminate before transport (e.g. `invalid_input`). Stores hashes only — never raw transcript or prompt text.
- `generated_lecture_summaries` (Session 4.5a) holds **success artifacts only** — a brief or detailed-study summary as `content_json jsonb` plus the full provenance set and an `ai_request_log_id` FK (NOT NULL). There is no `status` column; failures live in `ingestion_jobs` + `ai_request_logs`.
- `course_grade_schemes`, `grade_boundaries`, `grade_components`, `student_grade_records`, and
  `student_target_grade_goals` (Stage 9) store module grade schemes, letter thresholds, weighted
  components, per-student component scores, and the one active target-grade goal. Weights are decimal
  fractions that sum to `1.0000`; scores are `0-100`; forecast rows are not persisted.
- `student_progress_snapshots` and `student_topic_mastery_snapshots` (Stage 9) store week-scoped
  standing snapshots and lecture/lab section-scoped mastery read models for the progress dashboard.
  These are seeded/read-model tables, not event-source tables.

## Section asset schema notes
- `section_assets.storage_key` is a private object-storage path and is unique.
- `section_assets.module_section_id` is indexed for section asset listing, but it is not unique; a section may have multiple material assets.
- `section_assets.uploaded_by_user_id` points at `app_users(id)` and is updated on replace.
- `section_assets.asset_kind` defaults to `processable`; migration `0021` backfills existing rows to
  `processable` and constrains values to `processable | attachment`.
- `section_assets.processing_status` is technical file state and remains separate from `module_sections.publish_status`, which controls student visibility in later Stage 3 work.
- Section asset list responses are read through `platform/query/content_read.py` projection rows; write behavior remains in the content domain service.

## Section publish and notes behavior
- `module_sections.publish_status` is a service-managed visibility state with values `draft`, `published`, and `unpublished`; `draft` is initial-only.
- `module_sections.lecturer_notes` stores shared plain-text lecturer notes for the section and uses `NULL` as the canonical empty value.
- Session 3.2 implements behavior only; no schema change or `published_at` field was added.

## Module section generation
- Session 4.3.5d-B1 originally added a temporary four-section template. Stage 5.5a replaces that
  product path: `POST /admin/modules` now requires a schedule and creates the `course_modules` row,
  owner membership, and schedule-generated lecture/lab `module_sections` in the same transaction.
- The fixed `Lecture 1`, `Lecture 2`, `Lab 1`, `Assignment 1` template is gone from the product path.
  Assignments remain valid legacy enum values (D12) but are not generated by Stage 5.5.
- Generated sections set `publish_status='draft'`, `status='active'`, `lecturer_notes=NULL`,
  `session_date`, and `week_number`. The generator is pure; the admin domain owns writes.
- Stage 5.5b makes per-section `week_number`, `session_date`, and lab-only `due_at` editable through
  the content boundary and adds `platform/query/section_week_resolver.py`, a read-only stored-week
  resolver for Stage 6 scope lookup. The resolver returns lecture/lab section metadata only and does
  not apply student-facing publish/summary filters.
- Stage 5.5d adds dev-only reseed tooling. It snapshots existing dev modules, deletes dependent rows,
  recreates modules with the Stage 5.5 reference schedule, and seeds one published lab fixture. This is
  replacement of throwaway dev data, not an in-place schema migration or production data path.
- Stage 5.5e adds browser-facing admin and lecturer by-week read routes over the same stored-week
  resolver. These routes do not add structure-mutation capability; section add/delete/reorder remains
  absent from the API/UI. Student-facing section DTOs now include lab `due_at` and material
  `asset_kind` so the frontend can display deadlines and choose the correct download path.

## Transcript schema notes
- `transcripts.module_section_id` points at `module_sections(id)` and has a partial unique index, `uq_active_transcript_per_section`, for `is_active = true`.
- `transcripts.storage_key` is a private object-storage path and is unique.
- `transcripts.uploaded_by_user_id` is nullable and points at `app_users(id)`, matching the P6-confirmed target of `section_assets.uploaded_by_user_id`.
- `transcripts.status` and `transcripts.source_type` use `text + CHECK`, matching the existing status column convention.
- `transcripts.checksum` stores lowercase SHA-256 over raw uploaded bytes; it is not exposed in public `TranscriptMeta`.
- `ix_transcripts_status_created_at` supports future recovery sweeps over low-cardinality transcript states.
- `transcript_segments.sequence_number` is assigned after empty parse output is filtered and is unique per transcript. The database enforces nonblank text, paired timestamp nullability, non-negative starts, and `end_ms > start_ms`.
- `ingestion_jobs.idempotency_key` is unique. Parse uses `parse:{transcript_id}:{checksum}`; `processor_version` is stored as metadata and is not part of the key.
- `transcript_chunks.chunk_index` is unique per transcript. The unique btree on `(transcript_id, chunk_index)` is the transcript lookup path; no separate `transcript_id` index is present.
- `transcript_chunks.embedding` is nullable until Session 4.4. `embedding_generated_at` records embedding time, while `updated_at` records the row's latest mutation.
- `transcripts.status='completed'` means the Stage 4.1-4.3 transcript pipeline has completed upload, parse, and chunk persistence. Successful chunk jobs set the transcript to `completed` while also completing the `chunk` row in `ingestion_jobs`; there is intentionally no `chunked` transcript status. Stage 4.5 does not change `transcripts.status`; summary progress is a read-model concept on the status projection (`summary_brief`/`summary_detailed` steps; `summarizing`/`summarized` overall states).

## AI request log + summary schema notes (Session 4.5a)
- `ai_request_logs.ingestion_job_id` points at `ingestion_jobs(id)` (CASCADE) and is **NOT NULL** in 4.5a (every gateway call is a summary job); a future Stage 8 assistant call will relax it via migration. `attempt_number` indexes the gateway-call attempt; retries open a new row rather than mutating one.
- `ai_request_logs` provider fields (`backend_used`, `prompt/completion/total_tokens`, `provider_request_id`, `latency_ms`, `request_completed_at`) are nullable. `feature`, `backend_used`, and `status` use `text + CHECK`. `index (feature, created_at)` makes "tokens by feature by day" one query. `debug_text_truncated` is non-prod only and never carries transcript/prompt text.
- `generated_lecture_summaries` has a six-column unique constraint `(transcript_id, summary_type, source_transcript_checksum, prompt_version, prompt_content_hash, input_hash)` so a new prompt version produces a distinct row instead of overwriting history. `summary_type` and `backend_used` use `text + CHECK`; `ai_request_log_id` references `ai_request_logs(id)` (no cascade, to preserve provenance).
- `ingestion_jobs` gains a second one-active partial-unique index, `ingestion_jobs_one_active_summary_per_transcript`, on `(transcript_id, job_type)` where `job_type IN ('generate_brief_summary','generate_detailed_summary') AND status IN ('queued','running')` — the same pattern as the embed one-active index (migration 0007), now keyed per summary job type so a brief and a detailed job can both be active.
- Summary job idempotency key = `{transcript_id}:{job_type}:{checksum}` (matching the parse/chunk/embed convention). Migration `0008` creates `ai_request_logs` and `generated_lecture_summaries`, adds `ingestion_jobs.failure_category`, and adds the summary one-active index.

## Progress schema notes (Stage 9)
- Stage 9 migrations use `0038` and `0039` in the assigned `0038-0043` block. No `0040` table was
  needed because benchmark suppression config lives on `course_grade_schemes`.
- ADR-052 records the single-tenant MVP decision; Stage 9 tables intentionally carry no
  `organization_id`.
- `student_target_grade_goals` enforces a partial unique index for one active target-grade row per
  `(student_id, module_id)`. Updating a target changes that row and recomputes the forecast at read time.
- The benchmark surface reads aggregate quiz average and cohort size only from completed
  `quiz_attempts`; individual rows and per-student standings are not exposed by DTOs.

## ID strategy
All primary keys are PostgreSQL `UUID` columns with no database-side default. Application models generate UUIDv7 values through `uuid6.uuid7`, keeping IDs time-ordered while avoiding `gen_random_uuid()` defaults.

## Local database extensions
Local Docker Postgres initializes both `vector` and `pgcrypto` from `docker/postgres/init/001-create-vector.sql`. Migration `0006` also runs `CREATE EXTENSION IF NOT EXISTS vector` before creating `transcript_chunks.embedding`. Hosted Postgres still needs required extensions available to the migration role before first deployment.

## Intentional gaps
Role semantics that require cross-row checks remain service-layer responsibilities for later sessions: lecturer-only module ownership and no-admin memberships are not enforced by database constraints in the MVP schema.
