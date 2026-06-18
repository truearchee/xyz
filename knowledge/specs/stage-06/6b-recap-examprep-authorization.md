---
type: session-spec
stage: "06"
session: "6b"
slug: recap-examprep-authorization
status: done            # draft → approved → in-progress → done → superseded
created: 2026-06-17
updated: 2026-06-17
owner: developer
plan: knowledge/plans/stage-06/6b-recap-examprep-authorization.md
report: knowledge/steps/stage-06/6b-recap-examprep-authorization.md
---

# Session 6b — Recap + exam-prep modes + authorization

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6b-recap-examprep-authorization]]
- Plan: [[plans/stage-06/6b-recap-examprep-authorization]]
- Report: [[steps/stage-06/6b-recap-examprep-authorization]]
- Foundation: [[steps/stage-06/6a-pool-foundation]], [[decisions/adr-047-section-question-pool-capacity]]

## Goal
Two new multi-section quiz modes work end-to-end on the 6a pool engine — **recap** (student picks a
week/date span within one module) and **exam-prep** (lecturer defines a named `AssessmentScope` by covered
weeks) — assembled by sampling the in-scope **eligible** section pools, **shared** across students by a
canonical scope key, and protected by the spec's Authorization & visibility rules. No UI (6d); no retake /
mistakes-bank (6c); no post-class retrofit (6d).

## Why now
6a proved the engine on synthetic pooled definitions. 6b puts the real product surfaces on it and is where
the **security-sensitive** authorization lives (assigned-only → 404, published-only sampling, lecturer-on-
module scope creation). It must land and be `/review`/`/cso`-clean before any of it reaches a browser (6d).

## Read first
- [[specs/stage-06/6-complete-quiz-modes]] — **Authorization & visibility** (BINDING) + Recap / Exam-prep / scope-eligibility sections
- `backend/app/domains/content/service.py` `authorize_lecturer_section` + `platform/query/content_read.py` `lecturer_has_active_module_membership` (the lecturer-on-module predicate to reuse verbatim)
- `backend/app/platform/query/quiz_read.py` `get_visible_attempt` (the single-section S7 visibility to generalize)
- `backend/app/platform/query/section_week_resolver.py` (`resolve_sections_by_weeks`; no date-range variant exists)
- `backend/app/platform/query/quiz_availability_read.py` + `student_summaries/precedence.py` `derive_slot_state` (detailed-summary readiness)

## Source paths likely touched
- `backend/alembic/versions/0025_*.py` (assessment_scopes + quiz_definitions multi-section)
- `backend/app/platform/db/models/assessment_scope.py` (new); `quiz_definition.py` (nullable section + scope_key + assessment_scope_id); `__init__.py`
- `backend/app/domains/quiz/scope_service.py` (new — recap/exam-prep scope resolution + canonical key + get-or-create shared definition + availability), `pool_service.py` (pre-warm helper)
- `backend/app/domains/assessments/{service,schemas}.py` + `backend/app/api/routers/assessments.py` (new — lecturer AssessmentScope CRUD)
- `backend/app/api/routers/quiz.py` + `app/domains/quiz/service.py` + `schemas.py` (student recap/exam-prep start + availability endpoints)
- `backend/app/platform/query/section_week_resolver.py` (additive date-range sibling read), `quiz_read.py` (unified visibility), a new section-eligibility read in `platform/query`
- `backend/tests/...`

## Build
- **AssessmentScope** entity + lecturer CRUD (create / list (paginated) / edit), gated lecturer-on-that-module.
- **migration 0025:** `assessment_scopes`; `quiz_definitions` DROP NOT NULL `module_section_id`, ADD
  `scope_key` (text, nullable) + `assessment_scope_id` (FK, nullable) + partial-unique
  `(module_id, quiz_mode, scope_key) WHERE quiz_mode IN ('recap','exam_prep','mistakes_bank')`.
- **Recap (student-driven):** pick weeks **or** date range within ONE module → resolve eligible sections
  via the 5.5 query (add an additive date-range sibling) → canonical `scope_key = sha256(sorted in-scope
  eligible section ids)` → get-or-create the SHARED recap QuizDefinition (the 6a `_get_or_create` race
  pattern) → `start_pooled_attempt`.
- **Exam-prep (lecturer-defined, student-consumed):** `scope_key = str(assessment_scope_id)`; one
  QuizDefinition per scope. D1 **pre-warm** on scope create/edit (enqueue `ensure_section_pool` for in-scope
  eligible sections lacking a fresh pool, **background** priority, idempotent skip).
- **Section eligibility read** (`platform/query`): lecture/lab **AND** a READY detailed summary;
  assignment/supplementary excluded **silently** (never surfaced as "processing"); for STUDENTS further
  filter to **published + assigned**; compute the canonical key **after** that filter.
- **Unified attempt visibility** (generalize `get_visible_attempt`): single-section (post_class) keeps the
  S7 published+active+lecture/lab gate; multi-section (pooled, `module_section_id IS NULL`) is
  module-membership only (content is snapshot-frozen + sampling-time filtered). post_class behavior
  byte-identical.
- **Availability (D3 all-or-wait):** a span is available only when EVERY in-scope eligible section is ready;
  otherwise unavailable with a note of what is still processing (ineligible types never block).

## Do not build
- No mode-selector / scope-modal / lecturer form / any **UI** (6d).
- No **retake reinforcement, mistakes-bank, or event-metadata** changes (6c). (The 0025 index covers
  `mistakes_bank` for 6c, but 6b creates no mistakes_bank definitions.)
- No **post-class retrofit** (6d). post_class stays on its Stage 5 path.
- No new **event-type / AIRequestLog feature name** — pre-warm reuses the existing `quiz_pool` feature; do
  not add to or fork the shared registry (Stage 7 coordination, [[steps/findings-6-shared-infra]]).
- No change to shared contracts (limiter / registry / `ai` queue / pagination interfaces). The
  `section_week_resolver` date-range read is an **additive sibling**, never a signature change.
- No migrations outside **0023–0029**.

## Data model changes
New `assessment_scopes` (id, module_id FK, name, covered_weeks JSONB int[], created_by_user_id FK,
status CHECK active|locked, timestamps). `quiz_definitions`: DROP NOT NULL `module_section_id`, +`scope_key`,
+`assessment_scope_id` FK, + the partial-unique index. Migration **0025**, additive, round-trips on a fresh
DB; single head 0025.

## API changes
- Lecturer: `POST/GET /modules/{moduleId}/assessment-scopes`, `GET/PATCH /assessment-scopes/{scopeId}`
  (lecturer-on-module; list paginated via `PaginatedResponse[T]`).
- Student: recap availability + start (weeks/date-range) and exam-prep availability + start (by scope) under
  the `/student/...` surface; `Cache-Control: private, no-store`. Answer/complete/detail reuse the existing
  quiz endpoints (now visibility-unified). Regenerate the OpenAPI client.

## Authz rules (BINDING — spec v2 §Authorization & visibility)
- Student → quizzes only for **assigned** modules (active membership). Unassigned → **404, not 403** (do not
  reveal existence). The student role gate (403) fires **before** any lookup.
- Student scope resolution filters to **published + assigned + eligible** sections only — a student can
  never be sampled an unpublished/ineligible section's questions even if a pool exists from lecturer use.
- `AssessmentScope` create/edit = **lecturer-on-that-module only**; a student calling it → **403** (session
  kept, rule 5). Reuse `lecturer_has_active_module_membership` verbatim.
- 401 vs 403 per rule 5 throughout.

## Verification
- `pytest` — new 6b tests: lecturer-on-module create/edit (403 paths), student 404-not-403 for unassigned,
  recap canonical-key dedup (same span → ONE shared definition; concurrent first-create races to one),
  eligibility (assignment/supplementary excluded silently; unpublished excluded for students), D3 all-or-wait
  availability, exam-prep pre-warm (idempotent skip), unified visibility (post_class unchanged; multi-section
  module-level), exam-prep scope correctness (sampled questions only from in-scope eligible sections).
- `ruff check` clean; `alembic upgrade head && downgrade base && upgrade head` round-trips; `alembic heads`
  single head **0025**; **full backend suite green** (rule 14, incl. the unchanged post_class quiz tests);
  `bash scripts/generate-api-client.sh` + `tsc --noEmit` (contract changed → regen + commit).

## Knowledge updates required
- `knowledge/steps/stage-06/6b-recap-examprep-authorization.md` (report)
- ADR only if a durable decision emerges (e.g. the unified-visibility generalization) — else none
- STATUS.md / log.md

## Done means
Recap + exam-prep assemble end-to-end on the pool engine, shared by canonical key; authorization holds
(404 unassigned, published-only sampling, lecturer-on-module scope creation, exam-prep scope correctness);
D1 pre-warm + D3 all-or-wait implemented; migration 0025 round-trips single head; full backend suite green;
client regenerated. No UI, no 6c/6d scope.

## Amendments
- **2026-06-17 — pulled forward from 6c (forced by enabling multi-section attempts):** 6b's recap/exam-prep
  start makes a multi-section attempt reachable by the EXISTING `answer`/`complete` endpoints, so two pieces
  that the plan nominally placed in 6c had to land here for correctness (not feature scope):
  1. **Event metadata scope-awareness** (guard-rail #2): `complete()` now emits `moduleSectionId` for
     single-section and `moduleSectionIds` (+`assessmentScopeId`) for multi-section, from `source_scope` —
     never `str(None)`. Event TYPE names are still Stage 5's `completed_quiz`/`perfect_quiz_score`
     constants (read from `platform.events`, not a local copy — shared-registry rule).
  2. **`answer()` mistake creation** made section-aware (uses the question's `source_section_id`, since the
     attempt's definition section is NULL) and pool-upsert-aware (uses the 6a `upsert_pool_mistake` when the
     question carries `source_pool_question_id`). The retake `retake_correct_count` increment + prefix flip
     remain 6c.
- **2026-06-17 — unified visibility:** `get_visible_attempt` (a Stage 5 shared read) was generalized to
  serve multi-section attempts (LEFT JOIN section; module via `QuizDefinition.module_id`; OR-predicate keeps
  the post_class S7 gate). post_class behavior verified byte-identical (existing suite green).
