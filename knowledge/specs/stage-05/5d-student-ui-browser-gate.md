---
type: session-spec
stage: "05"
session: "5d"
slug: student-ui-browser-gate
status: done
created: 2026-06-16
updated: 2026-06-17
owner: developer
plan: "knowledge/plans/stage-05/5d-student-ui-browser-gate.md"
report: "knowledge/steps/stage-05/5d-student-ui-browser-gate.md"
---

# Session 5d — Student Quiz UI + Browser Gate + Real-Provider Smoke

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5d-student-ui-browser-gate]]
- Plan: [[plans/stage-05/5d-student-ui-browser-gate]]
- Report: [[steps/stage-05/5d-student-ui-browser-gate]]
- Real-provider smoke: [[steps/stage-05/5d-real-provider-smoke]]
- Prior: [[steps/stage-05/5c-answer-feedback-scoring-retake]]

## Goal
Complete the Stage 5 vertical proof by wiring the student-facing quiz UI to the 5c HTTP surface, proving
the full post-class quiz path in a real browser, and recording the required real-provider smoke for quiz
generation.

## Build
- API-agnostic multiple-choice components reusable by Stage 7 glossary.
- `PostClassQuizPanel` mounted below student summaries on the section detail page.
- Quiz API wrapper methods using the generated OpenAPI client and existing auth recovery.
- Generating state that follows the 4.5d bounded backoff pattern, with no 60-second hard timeout.
- Resume behavior that reads an existing attempt but never auto-creates one on page load.
- Failed state with a sanitized message and Start Over.
- Browser gate spec covering availability, start, generating, answers, mistakes, completion events,
  perfect score, non-student denial, and the S7 unpublish-mid-attempt seam.
- Real-provider smoke script proving the configured model echo and parseable 10-question quiz.

## Do not build
- New quiz backend behavior beyond using the 5c API.
- Stage 6 quiz modes, mistakes-bank practice, recap/exam-prep, or retake reinforcement UX.
- Stage 7 glossary UI.
- Client-side math rendering beyond safely escaped plain text.

## Verification
```bash
docker compose exec -T frontend npx tsc --noEmit
python backend/scripts/gate3_quiz_smoke.py
npx playwright test tests/e2e/5d-post-class-quiz.spec.ts --workers=1
```

The browser gate must run against a real backend, real DB, and real browser context. The real-provider
smoke must assert the echoed model id equals the configured `LLM_DETAILED_MODEL_ID`.

## Done means
- Student can see quiz availability, start an attempt, wait through generating, answer questions, receive
  immediate feedback, complete, and see score in the browser.
- Incorrect answer records a mistake; completion records `completed_quiz`; perfect completion records
  `perfect_quiz_score`.
- Non-student gets 403; unpublished-mid-attempt section returns 404 and emits no events while hidden.
- Gate 1 browser run and Gate 3 real-provider smoke are both green.
- Spec, plan, report, STATUS, log, open-questions, and roadmap are updated.

## Amendments
- 2026-06-16 — F-5d-1 raised `post_class_quiz_generation/v1` `max_tokens` from 8000 to 16000 after the
  initial real-provider smoke returned `finish_reason='length'`. The re-confirm run returned
  `finish_reason='stop'` and remained parseable.
