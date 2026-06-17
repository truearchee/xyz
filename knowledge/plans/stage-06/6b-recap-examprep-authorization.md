---
type: session-plan
stage: "06"
session: "6b"
slug: recap-examprep-authorization
status: executed     # proposed → approved → executed
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6b-recap-examprep-authorization.md
report: knowledge/steps/stage-06/6b-recap-examprep-authorization.md
---

# Session 6b — Implementation Plan — Recap + exam-prep modes + authorization

## Linked documents
- Spec: [[specs/stage-06/6b-recap-examprep-authorization]]
- Plan: [[plans/stage-06/6b-recap-examprep-authorization]]
- Report: [[steps/stage-06/6b-recap-examprep-authorization]]
- Foundation: [[steps/stage-06/6a-pool-foundation]] · Coordination: [[steps/findings-6-shared-infra]]

## Scope confirmation
Delivers recap + exam-prep backend on the 6a engine + AssessmentScope CRUD + the binding authorization,
**no UI / no retake / no mistakes-bank / no post-class retrofit / no new event-feature name**. Migration
0025 only. The `section_week_resolver` date-range read is an additive sibling (never a signature change).

## Approach
Recap and exam-prep are the same shape — a **multi-section QuizDefinition keyed by a canonical `scope_key`,
shared across students, sampled per attempt by the 6a engine**. They differ only in how scope is chosen
(student weeks/date-range vs lecturer AssessmentScope) and the key (sorted eligible section ids vs
assessment_scope_id). A new `scope_service` resolves eligible sections → computes the key → get-or-creates
the shared definition → calls `start_pooled_attempt`. Authorization reuses the shipped lecturer-on-module
predicate and the 404-not-403 student pattern verbatim. The only Stage-5-read change is generalizing
`get_visible_attempt` to also serve multi-section attempts (post_class behavior preserved byte-identical).

## Changes, file by file
- `alembic/versions/0025_assessment_scope_and_multi_section_definition.py` — `assessment_scopes` table;
  `quiz_definitions` ALTER `module_section_id` DROP NOT NULL, ADD `scope_key` (text null) + `assessment_scope_id`
  (FK→assessment_scopes, null) + partial-unique `(module_id, quiz_mode, scope_key) WHERE quiz_mode IN
  ('recap','exam_prep','mistakes_bank')`. Existence-guarded; `down_revision="0024"`.
- `app/platform/db/models/assessment_scope.py` (new) + `quiz_definition.py` (nullable section + scope_key +
  assessment_scope_id, bare-or-FK per house style) + `__init__.py` registration.
- `app/platform/query/section_week_resolver.py` — ADD `resolve_sections_by_date_range(db, *, module_id,
  start_date, end_date)` (additive sibling; same `SectionWeekRow`; `session_date BETWEEN`, active, lecture/lab).
- `app/platform/query/section_eligibility_read.py` (new) — `resolve_eligible_section_ids(db, *, module_id,
  candidate_section_ids, student_id=None)`: keeps lecture/lab with a READY detailed summary (reuse
  `get_section_summary_inputs` + `derive_slot_state`); when `student_id` given, also requires published +
  active student membership; returns `(eligible_ids_sorted, not_ready_ids)` so availability can report what
  is still processing (D3) while excluding ineligible TYPES silently.
- `app/platform/query/quiz_read.py` — generalize `get_visible_attempt`: LEFT JOIN `module_sections` on
  `quiz_definitions.module_section_id`, join `course_modules` on `quiz_definitions.module_id`, and predicate
  `(qd.module_section_id IS NULL) OR (ms.publish_status='published' AND ms.status='active' AND ms.type IN
  lecture/lab)` plus the always-on module-active + active-student-membership. `VisibleAttempt.
  module_section_id` → `UUID | None`; add `section_ids`/scope passthrough as needed for 6c events. post_class
  rows (section set) hit the second branch unchanged.
- `app/domains/quiz/scope_service.py` (new) — `resolve_recap_scope(...)`, `resolve_exam_prep_scope(...)`:
  resolve candidate sections (weeks/date-range/scope weeks) → `resolve_eligible_section_ids` (student-filtered
  for the student start path) → D3 all-or-wait check → `scope_key` → `get_or_create_pooled_definition(module_id,
  quiz_mode, scope_key, assessment_scope_id, source_scope={sectionIds:[...]})` (the 6a `begin_nested`+
  IntegrityError re-read race pattern) → return the definition. A `recap_availability` / `exam_prep_availability`
  read for the (D3) availability endpoints.
- `app/domains/quiz/pool_service.py` — `prewarm_section_pools(factory, *, section_ids)` (ensure each lacking
  a fresh pool, background priority, idempotent skip) for D1.
- `app/domains/assessments/{service,schemas}.py` + `app/api/routers/assessments.py` (new) — AssessmentScope
  create/list(paginated)/get/edit; role gate (403) → `lecturer_has_active_module_membership` (403) → pinned
  404; edit re-resolves sections and (if pre-warm on) pre-warms newly-added eligible sections; lock-or-record
  if attempts already exist (flag if the design system lacks the affordance — backend records, UI is 6d).
- `app/api/routers/quiz.py` + `app/domains/quiz/service.py` + `schemas.py` — student recap/exam-prep
  availability + start endpoints (student gate 403 before lookup; 404 for unassigned module/scope; on
  available → `scope_service` → `start_pooled_attempt` → return the existing `QuizAttemptForStudent`). Register
  the assessments router in `main.py`. Regenerate the client.

## Order of operations
1. Migration 0025 + models + registration; round-trip + single-head check.
2. `resolve_sections_by_date_range` + `section_eligibility_read` + unit tests.
3. Generalize `get_visible_attempt`; **re-run the existing quiz endpoint/S7 tests first** (post_class must
   stay byte-identical) before adding multi-section coverage.
4. `scope_service` (canonical key + get-or-create race + availability) + `prewarm`.
5. AssessmentScope domain + router (authz tests: lecturer-on-module 403 paths, student 403).
6. Student recap/exam-prep endpoints (404-not-403 + scope-correctness tests).
7. Full backend suite + ruff + migration round-trip + client regen + tsc.

## Test strategy
Authz: parametrize the lecturer-on-module 403 (wrong role, role but not member, inactive membership) and
the student 404 (unassigned module/scope). Dedup: two students, same recap span → ONE definition + shared
pools; concurrent first-create → one row (gather). Eligibility: a scope spanning lecture+lab+assignment+
unpublished → only published-ready lecture/lab sampled; assignment excluded silently (not "processing").
D3: a span with one not-ready eligible lecture → unavailable + names the processing section. Pre-warm:
create scope → `ensure_section_pool` enqueued once per eligible section, skipped for already-fresh. Scope
correctness: assemble an exam-prep attempt → every sampled `source_section_id` ∈ the in-scope eligible set.
Unified visibility: the existing post_class S7 unpublish-mid-attempt test still passes; a multi-section
attempt is visible at module level and 404s for a non-member.

## Risks & mitigations
- Generalizing `get_visible_attempt` touches a Stage 5 shared read → the OR-predicate keeps post_class
  (section set) byte-identical; gate on the existing suite BEFORE extending (step 3).
- Recap `scope_key` is computed from the CURRENT eligible set, so the same week-range can map to different
  keys if eligibility changed between two students — that is two genuinely different scopes, not a dedup
  bug (documented; do not "fix" to a week-range key — it would reintroduce stale-section leakage).
- Date-range resolver is the one `platform/query` touch shared with 5.5 — additive sibling only; flag if a
  signature change ever seems needed.

## Open questions
- AssessmentScope edit after attempts exist: default to **recording** the change + (optionally) locking the
  scope rather than silently altering past draws. Confirm the lock semantics in 6d UI; backend records now.
