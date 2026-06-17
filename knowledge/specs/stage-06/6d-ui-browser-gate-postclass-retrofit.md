---
type: session-spec
stage: "06"
session: "6d"
slug: ui-browser-gate-postclass-retrofit
status: approved
created: 2026-06-17
updated: 2026-06-17
owner: developer
plan: knowledge/plans/stage-06/6d-ui-browser-gate-postclass-retrofit.md
---

# Session 6d — UI + browser gate + post-class retrofit

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

## Goal
Close Stage 6 by shipping the quiz-mode UI surfaces, proving the full browser gate against real backend and
DB state, running the real-provider quiz-pool smoke, and either landing the post-class retrofit onto the
pooled model or explicitly deferring it under the spec's revert path.

This document is approved for implementation as of 2026-06-17.

## Developer handoff preserved
- "6c accepted. Both confirmations landed correct, the retake/bank mechanics match spec v2, and
  verification clears the backend gate."
- "Note the bank authorization (own-student-only, per-module, 404/403) is backend-verified here but its
  browser proof is owed at 6d — carry it into the gate, don't consider it discharged."
- "Proceed to 6d — this is where Stage 6 closes, so the bar steps up."
- "All UI surfaces from spec v2's Design input — mode selector (2x2), recap/exam-prep scope selector
  modal, generating waiting state, retake mistake-prefix banner, lecturer AssessmentScope form,
  mistakes-bank entry — composed from the shipped 4.9 components per design-system.md. Read Design Plan
  §2.4 + the v1.1-review additions."
- "The full browser gate as written in spec v2: retake reinforcement + bank persistence; exam-prep scope
  correctness; pool reuse proven in-browser; and the authorization set."
- "Post-class retrofit (D4) — land it here, behind the revert path, re-running the existing post-class
  browser gate to prove the green surface is unbroken."
- "Real-provider smoke (rule 11, model-ID echo assertion) and the full active E2E suite (rule 14) — both
  required to flip the roadmap row."
- "Stage 7 shared-registry reconcile (6a's hard-coded quiz_pool feature name) is still a tracked
  integration item, not a 6d task."

## Current repo observations
- `frontend/src/features/quiz/mcq.tsx` already provides the API-agnostic MCQ card, option button, feedback,
  and result summary from Stage 5d. 6d must reuse these components verbatim and not fork them.
- `frontend/src/features/quiz/PostClassQuizPanel.tsx` already has the backoff polling pattern for
  generating/failed/in-progress/completed post-class attempts. 6d should factor or wrap this behavior for
  pooled modes instead of duplicating it.
- The generated API client already exposes recap availability/start, student exam-prep scope list/start,
  mistakes-bank list/start, and lecturer AssessmentScope CRUD after 6b/6c.
- `knowledge/design-system.md` is referenced by the Stage 6 overview but is not present in the current
  repo search. Per the 2026-06-17 approval, code wins: the shipped 4.9/5d/5.5 source components and
  patterns are the binding design authority for 6d. Do not expand 6d to author the missing document.

## Read first
- [[specs/stage-06/6-complete-quiz-modes]] — Design input, thin UI scope, UI proof obligation, browser gate,
  Done means, and 6d split.
- `.context/plans/stage-6-complete-quiz-modes-implementation-plan.md` — 6d implementation notes and §9
  verification plan.
- `knowledge/design-system.md` if it is restored/found before implementation.
- `frontend/src/features/quiz/mcq.tsx`
- `frontend/src/features/quiz/PostClassQuizPanel.tsx`
- `frontend/src/features/content/student/StudentModuleDetail.tsx`
- `frontend/src/features/content/student/StudentSectionDetail.tsx`
- `frontend/src/features/content/lecturer/LecturerModuleDetail.tsx`
- `frontend/src/lib/api/wrapper.ts`
- `tests/e2e/5d-post-class-quiz.spec.ts`
- `tests/e2e/fixtures/db.mjs`

## Build scope

### Student UI
- **Mode selector:** a 2x2 grid for post-class, recap, exam-prep, and mistakes-bank. Each mode has a clear
  available/unavailable/empty state. Post-class remains anchored on an individual section; recap,
  exam-prep, and mistakes-bank are module-level entries.
- **Scope selector modal:** recap supports weeks or date range within the current module; exam-prep lists
  lecturer-defined `AssessmentScope` rows with availability. The modal shows D3 all-or-wait information
  using ready/processing counts and does not present assignment/supplementary rows as "processing."
- **Generating waiting state:** pooled modes use the 4.5d/5d backoff polling pattern. The state is honest:
  first request can take real seconds; reused-pool quizzes go straight to questions; terminal failure names
  the failed section when available and offers retry/start-over per the existing failure contract. No
  infinite spinner.
- **Retake mistake-prefix banner:** when an attempt has mistake-review prefix questions, show a compact
  banner before the first question explaining that missed questions come first. The banner is driven by
  server state (`mistakeReviewQuestionCount` or equivalent); do not infer from text.
- **Mistakes-bank entry:** student chooses a module, sees the paginated bank/empty state, and can start a
  practice attempt assembled from that module's own mistakes. Empty assigned module is an empty state, not
  an error.

### Lecturer UI
- **AssessmentScope form:** on a lecturer module page, add a creation form for name + covered weeks and a
  paginated list/table of existing scopes with status/covered weeks. Use the generated
  `AssessmentsService` through `wrapper.ts` and preserve 401/403 behavior.
- **Edit semantics:** 6b backend has update support, but 6d UI should not silently expose a mutating edit
  path if the past-attempt lock/recording affordance is unclear. Minimum 6d acceptance is create + list.
  Edit UI requires explicit approval or a tiny amendment if implementation proves the backend/status model
  gives a safe affordance.

### Post-class retrofit
- Move post-class start onto the 6a pooled model so post-class, recap, and exam-prep use the same
  per-section pool + per-attempt sampling path.
- Preserve backward compatibility: existing pre-retrofit attempts and mistakes with
  `source_pool_question_id = NULL` remain readable/scorable and retain Stage 5 mistake identity.
- Keep a clean revert path. If retrofit risk threatens the Stage 6 browser gate or weakens the existing
  post-class browser contract, leave post-class on its current Stage 5 path and record the finding instead
  of forcing the retrofit.

## Do not build
- No Stage 7 shared-registry reconcile unless a 6d code path forces it. The hard-coded `quiz_pool` item
  remains a tracked integration task in [[steps/findings-6-shared-infra]].
- No new quiz algorithms beyond the post-class retrofit, retry/failure UI needed for 6d, and test helpers.
- No new event types or AIRequestLog feature names.
- No global redesign, marketing page, gamification, leaderboard, adaptive engine, lecturer question bank,
  proctoring, or cross-module combined mistakes pile.
- No browser-gate weakening. If timing changes under the retrofit, adjust waits/assertions while preserving
  the observable contract.

## Browser gate
The browser gate is developer-run against rebuilt images and real backend/DB state. It must use separate
browser contexts and DB assertions. The deterministic adapter still writes `AIRequestLog`, so reuse/no-new-
generation assertions are DB-backed in CI.

### Retake reinforcement + bank persistence
1. Student completes an original source quiz with mistakes.
2. Retake starts with the exact missed-question snapshots as the prefix.
3. Student answers one prefixed mistake correctly across two source-quiz retakes.
4. The mistake leaves the retake prefix after the second correct answer.
5. The same mistake remains visible and playable in the module mistakes-bank.
6. At least one mistake originating from a multi-section recap or exam-prep attempt also lands in that
   module's bank, proving cross-mode bank aggregation in-browser.

### Exam-prep + scope correctness
1. Lecturer creates an `AssessmentScope` with covered weeks.
2. Student starts exam-prep from that scope.
3. Every sampled question's `source_section_id` is within the in-scope eligible section set.
4. A deliberately out-of-scope week's question never appears.
5. Completing the attempt inserts `completed_quiz` in the same transaction as score, and
   `perfect_quiz_score` when the deterministic run scores 100%, with mode/scope metadata.

### Pool reuse
1. Student A opens a recap or exam-prep span with an ungenerated section and sees the generating state.
2. Student A completes the quiz.
3. Student B opens the same span and reaches a ready quiz immediately.
4. There is no new `AIRequestLog` row for that section/prompt/model after Student B starts.
5. A retake draws from the existing pool with no new generation row.

### Authorization
1. Unassigned student access to module quiz surfaces returns 404 and does not leak existence.
2. Student never samples questions from unpublished or structurally ineligible sections.
3. Student B cannot see or start from Student A's mistakes.
4. Wrong-role access keeps the session on 403; 401 behavior remains auth recovery.

### Post-class preservation
Re-run `tests/e2e/5d-post-class-quiz.spec.ts` after the retrofit or fallback decision. The existing
post-class green surface must remain green.

### Screenshot evidence
Capture desktop and narrow/mobile screenshots during the browser gate for each new surface: mode selector,
recap scope modal, exam-prep scope modal, generating state, retake-prefix banner, mistakes-bank entry, and
lecturer AssessmentScope form/list. Include paths and a short visual note in the 6d report.

## Real-provider smoke
Run the rule-11 smoke against the quiz-pool generation path on the reasoning route. The smoke must assert:
- the configured model identifier is echoed by the provider response/log;
- the response validates as a quiz-pool payload;
- the prompt/feature path is `quiz_pool_generation` / `quiz_pool`;
- evidence is recorded in `knowledge/steps/stage-06/6d-real-provider-smoke.md`.

## Verification
Expected commands, adjusted only for the local port/compose constraints recorded in `STATUS.md`:

```bash
docker compose build backend frontend
docker compose run --rm --no-deps backend sh -c "alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic heads"
docker compose run --rm --no-deps backend pytest -q
docker compose run --rm --no-deps backend ruff check .
bash scripts/generate-api-client.sh
cd frontend && npx tsc --noEmit

# Browser gates, with E2E_RUN_ID exported and deterministic provider configured.
npx playwright test tests/e2e/5d-post-class-quiz.spec.ts --workers=1
npx playwright test tests/e2e/6d-quiz-modes-browser-gate.spec.ts --workers=1
npx playwright test --workers=1

# Real-provider smoke: exact script may be added in 6d if none exists yet.
python backend/scripts/gate3_quiz_pool_smoke.py
```

## Knowledge updates required
- Create `knowledge/steps/stage-06/6d-ui-browser-gate-postclass-retrofit.md` from `git diff` and real
  command output after implementation.
- Create `knowledge/steps/stage-06/6d-real-provider-smoke.md` from real-provider evidence.
- Update this spec and the plan linked-doc sections to include the report once it exists.
- Update `knowledge/STATUS.md`, append `knowledge/log.md`, and flip the Stage 6 row in
  `knowledge/roadmap.md` only after the full browser gate, real-provider smoke, and full active E2E suite
  pass.
- Append change-history lines to prior reports for prior-session files modified by 6d, especially Stage 5d
  post-class UI/backend files and Stage 6a/6b/6c backend files if touched.

## Done means
All listed UI surfaces exist and are composed from the shipped component system or documented source
equivalent; recap/exam-prep/mistakes-bank/post-class flows work in a real browser; retake prefix flip and
bank persistence are browser-proven; scope correctness, pool reuse, and authorization are DB-backed in the
browser gate; post-class is either retrofitted and green or explicitly deferred under the fallback; real-
provider quiz-pool smoke passes with model-ID echo; full active E2E suite passes; Stage 6 knowledge and
roadmap closeout are committed with the code.

## Amendments
_Add dated entries here if approval changes scope. Do not silently edit the sections above._
- **2026-06-17 — implementation approval and UI scope:** 6d spec/plan approved. Lecturer AssessmentScope UI
  is create + paginated list only; edit UI is deferred because editing covered weeks after attempts exist
  can change effective shared-definition scope with no MVP benefit. Existing backend patch support remains
  API-only; no delete UI/API is added in 6d. If no recovery path for a mistyped scope exists, record it as
  a known MVP limitation in the 6d report.
- **2026-06-17 — source components are the design authority:** `knowledge/design-system.md` is absent in
  the current repo search. Treat the shipped 4.9/5d/5.5 components and patterns as the binding authority,
  reuse `mcq.tsx` and the post-class panel patterns verbatim, and do not author the design-system document
  in 6d. Record the absent document as a tracked Stage 4.9 residual/debt item and note the cross-stage
  Stage 7 styling risk in [[steps/findings-6-shared-infra]].
- **2026-06-17 — student surface and post-class fallback:** In-place student module quiz surface is
  approved, with discretion to use a small dedicated route if implementation shows it is cleaner.
  Post-class retrofit fallback is approved: prove pooled recap/exam-prep/mistakes-bank first, retrofit
  post-class last behind a service-level switch, rerun the 5d gate immediately, and leave post-class on
  the Stage 5 path if the retrofit threatens the green contract.
- **2026-06-17 — gate refinements:** Add browser proof that a mistake originating from a multi-section
  recap or exam-prep attempt lands in the per-module mistakes-bank. Drive the retake-prefix banner from the
  existing `QuizAttempt.mistake_review_question_count` path if the DTO already exposes it; confirm before
  adding any new DTO field. Any migration needed by 6d must stay within the Stage 6 reserved range
  `0026`-`0029`. Capture desktop and narrow/mobile screenshots for all new 6d UI surfaces and include them
  in the report.
- **2026-06-17 — closeout review gate:** Do not flip the Stage 6 roadmap row merely on completion. Bring
  back implementation evidence, `/qa` browser-flow findings, light `/cso` authorization findings, full gate
  output, real-provider smoke, full active E2E result, and screenshots for review before the roadmap flip.
