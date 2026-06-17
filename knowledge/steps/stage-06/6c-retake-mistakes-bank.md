---
type: session-report
stage: "06"
session: "6c"
slug: retake-mistakes-bank
status: complete
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6c-retake-mistakes-bank.md
plan: knowledge/plans/stage-06/6c-retake-mistakes-bank.md
commit: ""
---

# Session 6c — Report — Retake reinforcement + mistakes-bank

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6c-retake-mistakes-bank]]
- Plan: [[plans/stage-06/6c-retake-mistakes-bank]]
- Report: [[steps/stage-06/6c-retake-mistakes-bank]]
- Foundation: [[steps/stage-06/6a-pool-foundation]], [[steps/stage-06/6b-recap-examprep-authorization]]
- Coordination: [[steps/findings-6-shared-infra]]

## Summary
6c is backend-verified. Retakes for pooled source quizzes now start with the current student's active
mistake-review prefix, then draw the normal fresh pool sample while excluding prefixed pool questions.
Correct prefix answers advance the cumulative source-quiz counter and clear `show_in_retake_prefix` after
two successful retake answers; duplicate submits do not double-count; mistakes-bank practice does not
advance the counter. The mistakes-bank is per module (`course_modules` is the codebase grouping/authz unit),
paginated, own-student-only, and assembled synchronously from the student's existing mistake snapshots with
no pool generation or AI call. Stage 6 remains open until 6d's UI/browser gate + post-class retrofit.

The 6b recap `scope_key` invariant is also pinned in the 6c spec: it is derived from the sorted structurally
and publication-eligible section ids; summary READY stays the D3 all-or-wait availability gate and is not a
component of the key.

## Files changed
(Source: `git diff --stat`, `git diff --name-only`, and untracked-file status.)

**backend:** `app/domains/quiz/assembly_service.py` (prefix snapshot assembly, bank assembly helper),
`service.py` (bank list/start, flip-at-2, no duplicate mistakes for mistake-review practice),
`scope_service.py` (mistakes-bank definition helper), `schemas.py` (bank DTO),
`api/routers/quiz.py` (bank list/start endpoints), `platform/query/quiz_read.py` (current-student bank page).

**backend tests:** `tests/test_quiz_mistakes_bank.py` (new 6c gate).

**frontend generated client:** `frontend/src/lib/api/services/QuizService.ts`, `index.ts`,
`models/MistakeBankItem.ts`, `models/PaginatedResponse_MistakeBankItem_.ts`.

**knowledge:** 6c spec/plan/report; `STATUS.md`; `log.md`; prior-session change-history lines in 5c, 6a,
and 6b reports. Existing dirty 6b checkpoint metadata (`commit: 024ae91`) was preserved.

## Verification
| Command | Result | Notes |
|---|---|---|
| `python -m compileall -q backend/app/domains/quiz backend/app/api/routers/quiz.py backend/app/platform/query/quiz_read.py backend/tests/test_quiz_mistakes_bank.py` | passed | cheap syntax check before rebuild |
| `docker compose build backend` | passed | required because backend source is baked into `kyiv-backend` |
| `docker compose run --rm --no-deps backend pytest -q tests/test_quiz_mistakes_bank.py tests/test_quiz_recap_examprep.py tests/test_quiz_pool.py` | `19 passed in 5.23s` | 6c gate + 6b/6a regressions |
| `docker compose run --rm --no-deps backend pytest -q` | first run: `1 failed, 500 passed, 137 warnings` | exposed the premature prefix-clear bug in the first counter implementation |
| `docker compose build backend` | passed | rebuilt after the counter fix |
| `docker compose run --rm --no-deps backend pytest -q tests/test_quiz_mistakes_bank.py tests/test_quiz_recap_examprep.py tests/test_quiz_pool.py` | `19 passed in 5.05s` | focused rerun after fix |
| `docker compose run --rm --no-deps backend pytest -q` | `501 passed, 137 warnings in 71.88s` | full backend green |
| `ruff check backend/app/api/routers/quiz.py backend/app/domains/quiz/assembly_service.py backend/app/domains/quiz/schemas.py backend/app/domains/quiz/scope_service.py backend/app/domains/quiz/service.py backend/app/platform/query/quiz_read.py backend/tests/test_quiz_mistakes_bank.py` | `All checks passed!` | host Ruff; Ruff is not installed inside the backend image |
| `docker compose run --rm --no-deps backend alembic heads` | `0025 (head)` | no 6c migration; single head remains 0025 |
| `npm ci` in `frontend/` | passed with existing audit warnings | needed because host `node_modules` was absent and `scripts/generate-api-client.sh` uses `npx --no-install` |
| OpenAPI export from rebuilt backend image + `npx --no-install openapi --input ../.context/generated/openapi-6c.json --output src/lib/api --client fetch` | passed | avoided localhost `:8000`; only generated client changed |
| `cd frontend && npx tsc --noEmit` | passed | local type-check against regenerated client |
| `git diff --check` | passed | whitespace check |

## 6c proofs
- **Retake prefix:** a source-quiz retake snapshots active `MistakeRecord` rows first as
  `source_type='mistake_review'`, preserves exact snapshot text/options, sets `source_mistake_record_id`,
  tracks `mistake_review_question_count`, and excludes the prefixed pool question from the fresh sample.
- **Flip-at-2:** correct source-quiz prefix answers advance `retake_correct_count` 0→1→2 and clear
  `show_in_retake_prefix` only at 2. Duplicate answer returns `alreadyAnswered` and does not increment.
- **Bank practice:** correct mistakes-bank practice answers do not advance source-quiz retake progress; bank
  attempts resume while active and do not create duplicate mistake rows for mistake-review questions.
- **Own-student-only + 404 rules:** student A sees/starts only student A's module mistakes; student B sees
  only student B's; unassigned/cross-module student gets 404; lecturer/non-student gets 403 before lookup.
- **Migration range:** no migration was needed; Stage 6 remains at single head 0025, below the 0029 ceiling.

## Deviations from spec
- The planned single-statement flip update was replaced after a failing full-suite run showed it cleared the
  prefix after one correct answer. The final implementation uses `SELECT ... FOR UPDATE` on the mistake row
  inside the existing answer transaction, then mutates the counter/flag in Python. This preserves the
  accepted D2 behavior and the duplicate-submit fence.
- API client generation used a local OpenAPI JSON exported from the rebuilt backend image instead of
  `scripts/generate-api-client.sh`, because the script requires host `node_modules` and `localhost:8000`;
  this workspace only had `db`/`redis` running and sibling stacks can hold the backend port.

## Modified prior sessions
- Session 5c — `backend/app/api/routers/quiz.py`, `backend/app/domains/quiz/service.py`,
  `backend/app/domains/quiz/schemas.py`, `backend/app/platform/query/quiz_read.py`: extended the original
  student quiz HTTP surface with mistakes-bank endpoints, bank DTO/page read, and retake-progress handling.
- Session 6a — `backend/app/domains/quiz/assembly_service.py`: extended pooled assembly with retake-prefix
  snapshots and synchronous no-AI bank assembly.
- Session 6b — `backend/app/domains/quiz/scope_service.py`, `service.py`, `schemas.py`,
  `backend/app/api/routers/quiz.py`, and `backend/app/platform/query/quiz_read.py`: added the
  `mistakes_bank` mode surface on top of the multi-section definition/visibility groundwork and preserved
  the 6b event metadata behavior.

## Decisions made
No new ADR. The bank grouping was confirmed from code as per module (`course_modules`); there is no
course-above-module quiz/authz concept in this codebase.

## Risks introduced
- Mistakes-bank attempts can be as long as the student's module mistake count. That matches the backend
  "bank from snapshots" scope; 6d UI may need pagination/selection UX if large banks are awkward.
- `npm ci` reported existing dependency audit warnings, including the existing Next.js advisory. No
  dependency changes were made in 6c.

## Follow-ups
- 6d: UI for the four modes, browser gate for retake prefix → two correct → leaves prefix but remains in
  bank, real-provider quiz-pool smoke, post-class retrofit (D4), full active E2E suite. Stage 6 closes only
  there.

## Knowledge updates
- 6c spec/plan/report linked and closed.
- `STATUS.md` overwritten; `log.md` appended.
- Prior-session reports 5c, 6a, and 6b have change-history entries for the files extended by 6c.
- No architecture update and no ADR were needed.

## Close-the-loop checklist
- [x] Spec exists and is approved/done
- [x] Plan existed and was approved before coding
- [x] Stayed in scope; deviations recorded above
- [x] Verification commands run; real output recorded
- [x] Report written from git diff + command output, not memory
- [x] spec ↔ plan ↔ report links resolve
- [x] STATUS.md overwritten; log.md appended
- [ ] architecture/ updated IF source paths changed — n/a (no quiz-internal architecture map)
- [ ] ADR added IF durable decision made — n/a
- [ ] open-questions.md updated IF unresolved — n/a

## Change history
- 2026-06-17 — initial completion (backend-verified; client regenerated; tsc green). Commit pending.
