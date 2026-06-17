---
type: session-plan
stage: "06"
session: "6d"
slug: ui-browser-gate-postclass-retrofit
status: approved
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6d-ui-browser-gate-postclass-retrofit.md
---

# Session 6d — Implementation Plan — UI + browser gate + post-class retrofit

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Plan: [[plans/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Report: [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Real-provider smoke: [[steps/stage-06/6d-real-provider-smoke]]
- Foundation: [[steps/stage-06/6a-pool-foundation]], [[steps/stage-06/6b-recap-examprep-authorization]], [[steps/stage-06/6c-retake-mistakes-bank]]
- Capacity ADR: [[decisions/adr-047-section-question-pool-capacity]]
- Stage 7 coordination: [[steps/findings-6-shared-infra]]
- Prior browser gate: [[steps/stage-05/5d-student-ui-browser-gate]]

## Scope confirmation
This plan is approved for implementation as of 2026-06-17.

6d closes Stage 6 by adding the student and lecturer UI surfaces, proving the complete browser gate, running
the quiz-pool real-provider smoke, running the full active E2E suite, and applying the D4 post-class
retrofit only if the existing post-class green contract stays intact. It does not pull forward the Stage 7
shared-registry reconcile.

## Plan-design-review note
`/plan-design-review` was requested for the 6d surfaces. The local skill ran in text-only mode: Conductor
session detected, but no live design/mockup tooling was available (`DESIGN_NOT_AVAILABLE`,
`BROWSE_NOT_AVAILABLE`). This plan therefore records the design review as a repo-grounded surface review,
not a visual mockup review.

Initial design completeness rating for this approved plan: **8/10**. It is implementable and covers all
states called out by the Stage 6 Design input. Per approval, the missing `knowledge/design-system.md` is a
tracked cross-stage residual, not a blocker; the shipped source components are the binding authority.
Lecturer AssessmentScope edit UI remains deferred.

## What already exists
- `mcq.tsx` — API-agnostic question card, answer option, feedback, and result summary. Reuse verbatim.
- `PostClassQuizPanel.tsx` — availability/start/detail polling/answer/complete/result orchestration and
  the 4.5d-style backoff polling pattern.
- Generated `QuizService` endpoints for recap, exam-prep, and mistakes-bank.
- Generated `AssessmentsService` endpoints for lecturer AssessmentScope create/list/get/update.
- `wrapper.ts` with `withAuthRecovery`, `ForbiddenError`, and existing `api.quiz` methods.
- `tests/e2e/5d-post-class-quiz.spec.ts` and `fixtures/db.mjs` with role contexts, API contexts, DB JSON
  helpers, run manifests, summary waiters, and existing post-class gate assertions.

## Not in scope
- No Stage 7 shared-registry reconcile unless a 6d implementation path is blocked by it.
- No new event or AIRequestLog feature names.
- No full visual redesign or new component library.
- No cross-module/all-subject mistakes-bank.
- No weakening of the Stage 5d post-class browser contract.
- No AssessmentScope edit UI. Create + list only is approved for 6d.

## Design review findings folded into the plan
- **Information architecture:** put module-level quiz modes on the student module page; keep post-class on
  section detail. This matches scope grain and avoids asking students to pick a section for recap/exam-prep
  or a module for post-class.
- **State coverage:** every startable mode needs loading, available, unavailable, generating, failed/retry,
  in-progress, completed, and empty states. Mistakes-bank additionally needs empty assigned module.
- **Journey coherence:** a student should move from mode selection to scope modal to the same MCQ attempt
  shell. The only mode-specific visual differences are the scope summary and retake-prefix banner.
- **AI-slop risk:** avoid broad explanatory panels. The UI should show concrete state and actions, not
  marketing copy about quiz features.
- **Design-system alignment:** use existing 8px-radius panels, compact headings, buttons, table/list rows,
  modal shell, badges, progress/status copy, empty states, and toasts if/when found in the 4.9 system.
  `knowledge/design-system.md` is absent; use the shipped Stage 5d/5.5 source conventions as authority and
  record the Stage 4.9/Stage 7 residual.
- **Responsive/accessibility:** the 2x2 mode selector becomes one column on narrow screens; modal content is
  keyboard reachable; buttons have stable sizes; status text uses `role=status`/`role=alert`; question
  answer groups keep the existing accessible MCQ behavior.
- **Approved edit stance:** lecturer AssessmentScope UI is create + paginated list only. If no recovery
  path exists for a mistyped scope, record it as a known MVP limitation rather than adding delete UI.

## Implementation order

### 0. Pre-flight
1. Re-run `find . -iname 'design-system.md' -o -iname '*design*'`.
2. If `knowledge/design-system.md` is absent, record it in the 6d report and shared findings note; proceed
   with the shipped source-component authority.
3. Inspect generated client exports after any backend changes; regenerate only if contracts changed.
4. Rebuild backend/frontend images before browser tests because this compose setup bakes code into images.

### 1. Frontend API wrapper
Add wrapper methods around generated services:
- `api.quiz.getRecapAvailability(moduleId, payload)`
- `api.quiz.startRecap(moduleId, payload)`
- `api.quiz.listExamPrepScopes(moduleId)`
- `api.quiz.startExamPrep(scopeId)`
- `api.quiz.listMistakesBank(moduleId, limit, offset)`
- `api.quiz.startMistakesBank(moduleId)`
- `api.assessments.create/list/get/update` as needed for lecturer pages

Keep all calls inside `withAuthRecovery`.

### 2. Shared quiz attempt shell
Refactor without forking MCQ:
- Extract a reusable attempt controller/panel from `PostClassQuizPanel` or add a sibling
  `QuizAttemptPanel` that accepts mode-specific `start`, `load`, `complete`, and heading/banner props.
- Preserve Stage 5d behavior for post-class while allowing recap/exam-prep/mistakes-bank starts.
- Add retake-prefix banner driven by attempt metadata. Confirm whether the current attempt DTO already
  exposes `mistakeReviewQuestionCount` before adding a new field.
- Add terminal failed/retry display using existing sanitized copy and start-over behavior.

### 3. Student module-level quiz surface
Add a `StudentQuizModesPanel` to `StudentModuleDetail`:
- 2x2 mode selector: post-class summary/deep link, recap, exam-prep, mistakes-bank.
- Recap modal: weeks input and date-range input as mutually exclusive controls; availability check before
  start; show ready/processing counts.
- Exam-prep modal: list lecturer scopes, availability badges, start action only for available scopes.
- Mistakes-bank entry: list first page of mistakes, show empty state, start bank attempt.
- On start, render the shared attempt shell in place or navigate to a stable module quiz surface if the
  existing app routing makes that cleaner. Prefer in-place to keep scope tight.

### 4. Lecturer AssessmentScope surface
Add `AssessmentScopePanel` to `LecturerModuleDetail`:
- Create form with name + covered weeks.
- Paginated list/table of existing scopes, covered weeks, status, updated timestamp.
- Error states preserve 403 session behavior through `ForbiddenError`.
- Do not add edit UI.

### 5. Post-class retrofit
Backend-first, behind a small revertable change:
- Make post-class `start` resolve/get-or-create a single-section `post_class` `QuizDefinition` compatible
  with the 6a pooled assembly path.
- Ensure the pool scope uses the section id and the existing post-class quiz length.
- Preserve existing non-pooled attempts and mistake records (`source_pool_question_id = NULL`) in reads,
  answers, completion, history, and browser gate behavior.
- Keep the old Stage 5 generation code callable until the retrofit browser gate is green, so reverting is a
  small service-level switch rather than a broad rollback.
- If this risks breaking the shipped post-class gate, stop and record a D4 fallback finding.

### 6. Browser gate spec
Add `tests/e2e/6d-quiz-modes-browser-gate.spec.ts`:
- Seed one module with multiple published lecture/lab sections across weeks, completed detailed summaries,
  and at least one out-of-scope/unpublished section with a pool available from lecturer/backend setup.
- Use separate contexts for admin/lecturer/student A/student B/unassigned or create API tokens as needed.
- Assert retake prefix order by DB-backed missed snapshot ids, not brittle text.
- Assert bank persistence by listing/starting bank after prefix flip.
- Assert that a mistake originating from a multi-section recap or exam-prep attempt also appears in the
  same module bank.
- Assert exam-prep source correctness by querying `quiz_questions.source_section_id`.
- Assert reuse by counting `ai_request_logs` rows for `quiz_pool` at section granularity before/after
  Student B start and retake.
- Assert authorization with UI/API combined checks: unassigned 404, no unpublished sampling, student B no
  access to student A mistakes, wrong role 403 session kept.

### 7. Real-provider smoke
Add or adapt a script such as `backend/scripts/gate3_quiz_pool_smoke.py`:
- Invoke the quiz-pool generation path, not the Stage 5 post-class attempt-generation path.
- Assert model echo equals the configured reasoning model id.
- Validate the response through the existing quiz-pool validator.
- Record output in `knowledge/steps/stage-06/6d-real-provider-smoke.md`.

### 8. Verification and closeout
Run in this order:
1. Focused backend tests for retrofit and any DTO additions.
2. Full backend pytest and ruff.
3. Alembic round-trip and single head.
4. API client generation and frontend `tsc`.
5. Existing post-class browser gate.
6. New 6d browser gate.
7. `/qa` browser-flow pass over the implemented surfaces and fixes for any blocking findings.
8. Light `/cso` pass over authorization status codes and cross-student/cross-module data boundaries.
9. Full active E2E suite.
10. Real-provider smoke.
11. Evidence-based report with screenshots, status/log updates, prior-session change-history lines, and
    final commit. Do not flip the roadmap row until evidence is reviewed.

## File plan
- `frontend/src/lib/api/wrapper.ts` — add wrapper methods for 6b/6c and assessments endpoints.
- `frontend/src/features/quiz/PostClassQuizPanel.tsx` — refactor carefully or leave as wrapper over the new
  shared attempt shell.
- `frontend/src/features/quiz/QuizAttemptPanel.tsx` (new, if cleaner) — shared attempt render/poll/answer/
  complete logic.
- `frontend/src/features/quiz/QuizModeSelector.tsx` (new) — compact 2x2 mode selector and scope modal entry.
- `frontend/src/features/quiz/ScopeSelectorModal.tsx` (new) — recap/exam-prep scope picking.
- `frontend/src/features/quiz/MistakesBankPanel.tsx` (new) — bank list/empty/start.
- `frontend/src/features/quiz/AssessmentScopePanel.tsx` (new) — lecturer create/list.
- `frontend/src/features/content/student/StudentModuleDetail.tsx` — mount module-level mode selector.
- `frontend/src/features/content/student/StudentSectionDetail.tsx` — preserve post-class entry, possibly
  through shared shell.
- `frontend/src/features/content/lecturer/LecturerModuleDetail.tsx` — mount AssessmentScope panel.
- `backend/app/domains/quiz/service.py`, `generation_service.py`, `assembly_service.py`, and related tests
  only as needed for post-class retrofit and attempt metadata.
- `tests/e2e/6d-quiz-modes-browser-gate.spec.ts` — new Stage 6 closing browser gate.
- `backend/scripts/gate3_quiz_pool_smoke.py` — real-provider smoke if no existing script fits.
- Knowledge docs listed in the spec.

## Test strategy
- **Unit/backend:** post-class pooled start creates/uses a section pool, preserves old attempt reads, emits
  existing events, and does not mutate pre-retrofit mistake identity. If attempt metadata is added, assert
  DTO values for new/prefix counts.
- **Frontend type:** `npx tsc --noEmit` after generated client and wrapper updates.
- **Browser:** one dedicated 6d gate plus existing 5d gate plus full active suite.
- **Security:** include API-level assertions inside Playwright for 404/403 because UI-only checks can hide
  the actual status code. Verify Student B bank isolation from DB and response payload.
- **Capacity/reuse:** count `AIRequestLog` rows by section/model/prompt/feature before and after second
  student and retake. Do not rely on timing alone.

## Risks and mitigations
- **Missing design-system document:** implementation starts by searching it. If still absent, use only the
  shipped Stage 5d/5.5 component/source conventions and record the Stage 4.9/Stage 7 residual.
- **Post-class retrofit risk:** keep the switch small; run the existing 5d browser gate immediately after
  retrofit. If it fails for structural reasons, revert only the switch and document fallback.
- **Long browser setup:** rebuild images and use serial Playwright (`--workers=1`) as prior gates did.
- **Brittle "fresh combination" assertions:** assert no new generation rows and use seedable sampler/DB
  source ids for combination proof; avoid requiring every question to differ.
- **Auth leakage:** use API status checks for unassigned/cross-student cases, not only absent UI elements.

## Approval checklist
- [x] Lecturer AssessmentScope UI is create + list only; edit UI deferred.
- [x] Shipped 4.9/5d/5.5 source components are the design authority because `knowledge/design-system.md`
      is absent.
- [x] In-place student module quiz surface approved, with discretion for a small dedicated route if cleaner.
- [x] Post-class retrofit fallback approved: leave post-class on the Stage 5 path if retrofit threatens the
      green contract.
