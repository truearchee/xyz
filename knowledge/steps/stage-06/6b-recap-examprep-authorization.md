---
type: session-report
stage: "06"
session: "6b"
slug: recap-examprep-authorization
status: complete
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6b-recap-examprep-authorization.md
plan: knowledge/plans/stage-06/6b-recap-examprep-authorization.md
commit: ""           # filled after the 6b checkpoint commit
---

# Session 6b — Report — Recap + exam-prep modes + authorization

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6b-recap-examprep-authorization]]
- Plan: [[plans/stage-06/6b-recap-examprep-authorization]]
- Report: [[steps/stage-06/6b-recap-examprep-authorization]]
- Foundation: [[steps/stage-06/6a-pool-foundation]] · Coordination: [[steps/findings-6-shared-infra]]

## Summary
Recap (student weeks/date-range) and exam-prep (lecturer AssessmentScope by covered weeks) now assemble
end-to-end on the 6a pool engine — multi-section QuizDefinitions keyed by a canonical `scope_key`, SHARED
across students, sampled per attempt — behind the spec's binding Authorization & visibility. Migration 0025
makes `quiz_definitions` multi-section and adds `assessment_scopes`. No UI (6d), no retake flip / mistakes-
bank (6c), no post-class retrofit (6d). The OpenAPI client was regenerated (new endpoints) and `tsc` is
green.

## Files changed
(Source: `git diff --stat` + `git status`.)

**backend — new:** `alembic/versions/0025_assessment_scope_and_multi_section_definition.py`;
`app/platform/db/models/assessment_scope.py`; `app/domains/quiz/scope_service.py`;
`app/platform/query/section_eligibility_read.py`; `app/domains/assessments/{__init__,schemas,service}.py`;
`app/api/routers/assessments.py`; `tests/test_quiz_recap_examprep.py`.

**backend — edits:** `quiz_definition.py` (nullable section + scope_key + assessment_scope_id + dedup
index), `models/__init__.py` (register `AssessmentScope`); `platform/query/section_week_resolver.py`
(additive `resolve_sections_by_date_range`), `quiz_read.py` (unified `get_visible_attempt` + `source_scope`
on `VisibleAttempt`); `domains/quiz/service.py` (recap/exam-prep endpoints + scope-aware event metadata +
section/pool-aware `answer()` mistake creation), `schemas.py` (recap/exam-prep DTOs); `api/routers/quiz.py`
(student endpoints), `app/main.py` (register router); `dev_reseed.py` (Alembic pin 0024→0025).

**frontend:** regenerated client — `services/{QuizService,AssessmentsService}.ts`, `index.ts`, + 8 new
model files (no hand-written UI).

**knowledge:** 6b spec/plan/this report; `findings-6-shared-infra.md` (Stage 7 registry + 0023–0029
reservation); STATUS.md / log.md; `5.5d-dev-reseed.md` change history.

## Verification
| Command | Result |
|---|---|
| `alembic upgrade head && downgrade base && upgrade head` + `alembic heads` | clean, single head **0025** |
| `pytest tests/test_quiz_recap_examprep.py` | **7 passed** (the 6b proofs below) |
| `pytest -q` (full backend) | **497 passed** (0 failed; +7 over 6a's 490) |
| `ruff check` (all changed) | clean |
| `scripts/generate-api-client.sh` (via app-dump; port 8000 held by sibling) | regenerated — 8 models + `AssessmentsService` + `QuizService`/`index`, purely additive |
| `tsc --noEmit` (frontend image rebuilt with new client) | exit 0 |

**6b proofs:** (1) AssessmentScope create authz — lecturer-on-module OK; student → 403; lecturer-not-member
→ 403. (2) Pre-warm — one pool per eligible section; an edit re-warms idempotently (no new generation). (3)
Recap start **404-not-403** for an unassigned student. (4) Recap dedup — two students, same span → ONE
shared recap definition (`scope_key` = canonical sorted-eligible-ids hash; `module_section_id` NULL); two
attempts against it. (5) Eligibility — assignment + unpublished-for-student excluded **silently** (not
"processing"). (6) D3 all-or-wait — a still-GENERATING summary → unavailable (`reason='processing'`); start
→ 409. (7) Exam-prep scope correctness — sampled `source_section_id` ⊆ in-scope eligible (the out-of-scope
week-5 section never appears); 5 per section × 2; + unified visibility: the multi-section attempt is visible
to its owner (module-level) and 404s for a non-member.

## Deviations from spec (recorded as Amendments)
- **Pulled forward from 6c (forced by enabling multi-section completion):** scope-aware `complete()` event
  metadata (guard-rail #2 — `moduleSectionIds`/`assessmentScopeId`, never `str(None)`); section- and
  pool-upsert-aware `answer()` mistake creation. Retake flip + mistakes-bank stay 6c.
- **Unified `get_visible_attempt`** (a Stage 5 shared read) generalized for multi-section attempts;
  post_class behavior verified byte-identical (existing quiz suite green).
- These are in the spec's `## Amendments`.

## Modified prior sessions
- Session 5.5d — `dev_reseed.py`: `EXPECTED_ALEMBIC_VERSION` 0024→0025 (Stage 6b added 0025). Logged in the
  5.5d report change history.
- Session 5b — `domains/quiz/service.py` (`answer`/`complete`) + `platform/query/quiz_read.py`
  (`get_visible_attempt`): generalized for multi-section; post_class path unchanged (verified).

## Decisions made
No new ADR. The recap-key-is-the-eligible-set grain (not the week range) and the unified-visibility
OR-predicate are documented in the plan + this report; promote to an ADR only if a future reader needs it.

## Risks introduced
- `get_visible_attempt` is now shared by post_class (S7 gate) and pooled (module-level) attempts via one
  OR-predicate. Guarded by the existing post_class suite (green) + a multi-section visibility test.
- AssessmentScope edit-after-attempts: 6b re-resolves + re-warms but does not mutate an existing definition;
  the lock/record affordance surfaces in 6d (open question carried in the plan).

## Follow-ups
- 6c: retake `retake_correct_count` increment + flip-at-2 (the mistake CREATION is already pool-aware from
  6b); mistakes-bank assembly per module from snapshots + pagination; (events already scope-aware).
- 6d: UI + browser gate + real-provider smoke + post-class retrofit + full active E2E.

## Knowledge updates
- 6b spec/plan/report filed + cross-linked; findings note + STATUS + log updated; 5.5d change history
  appended. No ADR; architecture/ unchanged (no quiz-internal architecture map).

## Close-the-loop checklist
- [x] Spec approved · [x] Plan approved before coding · [x] Stayed in scope (deviations as Amendments)
- [x] Verification run; real output recorded · [x] Report from git diff + output
- [x] spec ↔ plan ↔ report links resolve · [x] STATUS.md overwritten; log.md appended
- [ ] architecture/ — n/a · [ ] ADR — none warranted · [ ] open-questions.md — edit-after-attempts noted in plan

## Change history
- 2026-06-17 — initial completion (backend-verified; client regenerated; tsc green). Commit filled at the
  6b checkpoint.
