---
type: session-plan
stage: "05"
session: "5d"
slug: student-ui-browser-gate
status: executed
created: 2026-06-16
updated: 2026-06-17
spec: knowledge/specs/stage-05/5d-student-ui-browser-gate.md
report: knowledge/steps/stage-05/5d-student-ui-browser-gate.md
---

# Session 5d — Implementation Plan — Student Quiz UI + Browser Gate

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5d-student-ui-browser-gate]]
- Plan: [[plans/stage-05/5d-student-ui-browser-gate]]
- Report: [[steps/stage-05/5d-student-ui-browser-gate]]
- Real-provider smoke: [[steps/stage-05/5d-real-provider-smoke]]
- Prior: [[steps/stage-05/5c-answer-feedback-scoring-retake]]

## Scope confirmation
Build the thin student UI and verification gates for post-class quizzes. Do not change the backend
answer/scoring semantics except through fixes required by gate findings. Do not build Stage 6 or Stage 7.

## Approach
1. Add API-agnostic MCQ components in `frontend/src/features/quiz/mcq.tsx`. They receive props and
   callbacks only; they do not import the generated API client.
2. Add `api.quiz.*` wrapper methods around the generated `QuizService`, preserving existing
   `withAuthRecovery` behavior.
3. Add `PostClassQuizPanel` to orchestrate availability, start, detail polling, answer submission,
   completion, result display, failed state, and Start Over.
4. Mount the panel in `StudentSectionDetail` below the summary content.
5. Add `tests/e2e/5d-post-class-quiz.spec.ts` for the full browser proof, including S7 unpublish while
   an attempt is in progress.
6. Add `backend/scripts/gate3_quiz_smoke.py` for the real-provider smoke and rule-11 model echo check.
7. If the real-provider smoke exposes truncation, adjust prompt budget through the PromptRegistry,
   update checksums, and re-run the smoke.
8. Update `STATUS.md`, `log.md`, `open-questions.md`, roadmap, and the 5d report from real command output.

## Verification plan
- Frontend type-check: `docker compose exec -T frontend npx tsc --noEmit`.
- Backend behavior remains covered by the 5b/5c pytest suites.
- Gate 3: `gate3_quiz_smoke.py` against the configured provider, with model echo and parseability
  recorded in [[steps/stage-05/5d-real-provider-smoke]].
- Gate 1: `npx playwright test tests/e2e/5d-post-class-quiz.spec.ts --workers=1` against the isolated
  `kyiv` stack.

## Risks
- Real-provider structured output can spend too much token budget on reasoning. Mitigation: prompt budget
  is a flat-file registry knob; F-5d-1 raised `max_tokens` to 16000 and re-confirmed `finish_reason='stop'`.
- Local port conflicts with sibling stacks can make the browser gate hit the wrong service. Mitigation:
  use an isolated compose project/ports and record stack details in the report.
- Browser gate relies on serial execution because the active suite has known capacity limits. Run this
  gate with `--workers=1`.

## Closeout
The report must include exact gate output, real-provider smoke evidence, deviations/residuals, modified
prior sessions, and linked spec/plan/report entries.
