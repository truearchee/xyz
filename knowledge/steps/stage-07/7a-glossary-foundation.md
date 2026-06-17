---
title: Stage 7a — Glossary foundation
status: fully-verified as part of Stage 7 core
updated: 2026-06-17
---

# Stage 7a — Glossary foundation (report)

Personal per-student glossary: save terms (highlight-from-summary + manual), async AI definitions in the
student's preferred language through the **existing** AI infrastructure, server-side dedup, definition
cache with cross-student collapse, folders (+ "Unsorted"), archive-style delete, personal-scoping 404,
`glossary_term_saved` events, KaTeX, language preference, RTL. Built in parallel with Stage 6.

## What was built

### Migration (block 0030–0031; this session: 0030)
`backend/alembic/versions/0030_glossary_foundation.py` (down_revision `0022`): tables
`glossary_folders`, `glossary_entries`, `glossary_source_references`, `glossary_definition_cache`;
`app_users.preferred_language` (default `'en'`, CHECK 5 langs, mirrors `timezone`); **union-aware**
widening of `ck_ai_request_logs_feature` (+`glossary_definition`) and
`ck_student_activity_events_event_type` (+ the two glossary events). `ingestion_jobs` untouched.
Existence-guarded; round-trips (base→head→base).

### Models (`backend/app/platform/db/models/`)
`glossary_folder.py`, `glossary_entry.py`, `glossary_source_reference.py`,
`glossary_definition_cache.py` (+ registered in `__init__.py`). Dedup partial-unique
`(student_id, subject_id, normalized_term) WHERE status='active'`; cache unique
`(cache_key, prompt_version)` = the one-active-keyed-on-cache-key guard. Provenance set on entry + cache.

### Domain (`backend/app/domains/glossary/`)
`normalize.py` (NFKC/casefold/collapse, no AI), `cache_keys.py`, `specs.py`, `translation_service.py`
(the `TranslationService` abstraction + `GatewayTranslationService` adapter over the gateway; language
baked into input — B1; language soft-check logs, never rejects — D3), `definition_service.py` (async job:
claim cache row → re-check cache → one gateway call → write-through cache → fan-out to all pending
entries sharing the key; RQ-retry on transient), `save_service.py` (normalize → dedup → create → cache
check → winner-enqueues → `glossary_term_saved` in-txn → commit → enqueue-after-commit), `schemas.py`,
`policy.py`, `service.py`, `jobs.py`. Read model `platform/query/glossary_read.py`. Router
`api/routers/glossary.py` (registered in `main.py`). Queue `enqueue_generate_glossary_definition`
(`workers/queues.py`). Prompt `backend/prompts/glossary_definition/v1.yaml` (+ `CHECKSUMS.json`).

### Definition shape (D3)
Reuses `BriefSummary` (`{"text": ...}`) — one markdown definition (KaTeX-capable), light validation
(non-empty/not-refusal) = the spec's stated check. No `validation.py` change. Structured columns reserved.

### Concurrency / cost
Cache HIT = no model call. Concurrent miss collapses to ONE call (winner inserts the `pending` cache row
via `ON CONFLICT DO NOTHING`; losers attach + wait; the job fans the single definition out to every
pending entry sharing the key). AIRequestLog written with `feature='glossary_definition'`,
`ingestion_job_id=None` (quiz pattern).

### Language preference
`app_users.preferred_language` surfaced via `GET /me` (`preferredLanguage`) and set via
`PATCH /me/preferences`. Snapshotted onto the entry/cache at save (preference changes don't retro-translate).

### Thin UI (`frontend/`)
`features/glossary/`: `MarkdownView` (react-markdown + remark-math + rehype-katex, RTL-aware),
`SaveToGlossary` (selection → save → saved/duplicate feedback), `ManualEntryModal` (required course
selector + type), `LanguagePreference`, `GlossaryPage` (folder sidebar, table/card toggle, generating
poll, entry detail with `dir="rtl"` for Arabic, archive delete). Routes `/student/glossary`,
`/student/settings`; nav links on the student page; `SaveToGlossary` wired around the summary surface in
`StudentSectionDetail`. Generated API client regenerated; `wrapper.ts` exposes `api.glossary` +
`api.me.updatePreferences`. KaTeX CSS imported in the root layout.

## Verification (evidence)

```
# Full backend suite (Docker, live code mounted, TEST_DATABASE_URL=xyz_lms_test)
docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q
# 492 passed, 138 warnings in 61.28s

# Targeted Stage-7 + touched tests
pytest tests/test_glossary_unit.py tests/test_shared_check_union.py tests/test_glossary_save.py \
       tests/test_me.py tests/test_event_recorder.py -q
# 25 passed

# Migration round-trip (base→head→base→head) — test_db_spine::test_migration_round_trip — passed
# Dev DB (xyz_lms) migrated to head 0030.

# Frontend type-check (host)
cd frontend && npx tsc --noEmit
# exit 0
```

New backend tests: `test_glossary_unit.py` (normalize + key derivation), `test_shared_check_union.py`
(CI union guard), `test_glossary_save.py` (highlight save + event; dedup attaches source / no 2nd entry
/ no 2nd event; cache-hit copies without a job; concurrent-miss collapse fans out; manual-add enrollment
404; cross-student 404), `test_me.py::test_patch_me_preferences_updates_language`.

## Later closure
Stage 7 core (7a–7c) was fully verified later on 2026-06-17: the real-provider glossary smoke passed
with response model echo `MBZUAI-IFM/K2-Think-v2`, the Stage 7 browser gate passed, and the full active
E2E suite passed 14/14. See [[steps/stage-07/7bc-glossary-practice]] and [[findings-stage-07]] F-7-5.
7d quiz-highlight remains as the next unblocked sub-stage.

## Modified prior sessions
- **Stage 4.7** — `frontend/.../content/student/StudentSectionDetail.tsx`: wrapped the summaries block in
  `<SaveToGlossary>` (highlight-to-save mount point). `SummaryMarkdown.tsx` left as-is (new `MarkdownView`
  carries KaTeX; summaries can migrate later).
- **Stage 5.5** — `backend/app/domains/admin/dev_reseed.py`: `EXPECTED_ALEMBIC_VERSION` `0022`→`0030`.
- **Stage 5** — `ai_request_log.py` / `student_activity_event.py` (source-of-truth tuples + widened
  CHECKs), `platform/events/recorder.py` (allowlist now the model tuple + glossary constants),
  `tests/test_event_recorder.py` (assertion → union), `tests/conftest.py` (`TRUNCATE_TABLES` += glossary
  tables).
- **Stage 2.2 / platform** — `auth/context.py` (`preferred_language`, defaulted), `auth/dependencies.py`,
  `db/models/user.py`, `api/routers/me.py` (+ `PATCH /me/preferences`), `tests/test_me.py`.
- **platform/llm** — `models/prompt.py` (`GatewayFeature` +`glossary_definition`), `provider.py`
  (deterministic glossary fixture, test-only).

## Linked documents
- Spec: [[specs/stage-07/7-glossary]]
- Plan: harness plan (Stage 7 master) — see repo `.claude/plans/`
- Findings: [[findings-stage-07]]
- Decisions: [[decisions/adr-047-glossary-subject-folder-separation]], [[decisions/adr-048-glossary-definition-cache-collapse]]

## Change history
- 2026-06-17 — 7a backend implemented + verified (492 backend / 25 targeted / migration round-trip);
  thin UI built + `tsc` green; client regenerated. Live browser gate + real-provider smoke pending.
- 2026-06-17 21:40 — Stage 7 core closure evidence added in the 7b/7c report and findings; 7a is now
  fully verified as part of the 7a–7c browser gate.
