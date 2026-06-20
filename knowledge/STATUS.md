# Status

_Last updated: 2026-06-20 — **Stage 8.6b (Assistant Exam-prep mode) is FULLY VERIFIED**, stacked on 8.6a on `stage-8.6-assistant-modes` and rebased over the Stage 10 mainline state. 8.6b lets a student pick a named AssessmentScope and opens an `exam_prep` conversation that discusses only that scope using covered weeks' permitted summaries, Stage 9 weak topics, and read-only `platform/query` helpers. It points to the Stage 6 quiz with all three precise states live-verified: ready CTA, processing "being prepared", and none "not available yet", but never generates a quiz. Routed V2/Cerebras. Verified: backend mode pytest, prompt drift, frontend `tsc` + vitest **19**, updated 8.6b browser gate **2/2**, full active Playwright **24/24**, and rule-11 exam-prep smoke. Stage 10 Gamification is already merged to `main`; its Alembic head is `0081`, so `dev_reseed` remains pinned to the higher merged head during this branch rebase._

_(8.6a, earlier on this branch: Mode Coordinator + Homework help — FULLY VERIFIED; full active Playwright 22/22 + rule-11 homework smoke.)_

## Current branch
- Branch: `stage-8.6-assistant-modes`
- Target branch: `origin/main`
- Base branch includes Stage 10 Gamification merged to `main` with Alembic head `0081`.
- Stage 8.6 migrations currently applied on this branch: `0042` (homework) and `0043` (exam-prep); later
  stacked commits add `0044` for time management.
- Gate harness (workspace-local, gitignored): `.context/8.6a-gate.override.yml` runs the stack on
  :8005/:3005 with a unique image tag `dallas-stage86-gate` plus a production frontend.

## Stage 10 delivered on main
- Stage 10 Gamification is FULLY VERIFIED and merged to `main`.
- Migration block `0080-0081` is on main; expected merged Alembic head is `0081`.
- The Stage 10 report and log entries remain the source for the full gamification verification record.

## Stage 8.6b delivered (Exam prep)
- **Conversation contract.** `exam_prep` conversations bind to a named AssessmentScope and resume-or-create
  one active chat per student/scope.
- **Grounding contract.** The assistant discusses only the covered scope using permitted summaries, scoped
  retrieval, and Stage 9 weak topics. It does not import quiz-domain code and does not generate quiz content.
- **Quiz pointer.** The frontend points to the Stage 6 exam-prep quiz with ready/processing/not-available
  states sourced from the quiz surface.
- **Routing.** V2/Cerebras route follows the 8.6a smoke lesson.
- **Verification.** Backend mode tests, prompt drift, frontend type/unit tests, updated browser gate **2/2**,
  full active Playwright **24/24**, and rule-11 exam-prep smoke passed in the final 8.6b gate.

## Stage 8.6a delivered (mode foundation + Homework help)
- **Mode = `conversation_kind` + a strategy coordinator (ADR-056).** `generate_assistant_answer_async`
  dispatches by kind via `_MODE_TURN_BUILDERS`; lecture behavior remains the default path, while
  `homework_help` routes to the homework turn builder.
- **Homework (ADR-057).** Routes V2/Cerebras/32k via `homework_help/v1.yaml`, grounds on the bound module or
  narrowed section, and always coaches rather than giving direct answers.
- **Resume-or-create.** Migration 0042 adds one-active homework partial-unique indexes for module and
  optional-section bindings.
- **Frontend.** Workspace homework entry, picker, starters, mode label, context pills, and shared
  `ConversationView` support.

## Known-state notes
- `dev_reseed.EXPECTED_ALEMBIC_VERSION` stays on the higher merged mainline pin `0081` while this branch is
  rebased over Stage 10.
- `check:design-tokens`/`check:inline-styles` remain known-red from the pre-existing Stage 12 backlog.
- `test_quiz_pool::test_pool_one_active_lock_concurrent_first_requests` is a pre-existing flaky full-suite
  backend test that passes in isolation.

## Stage 8.6a documents
- Spec: [[specs/stage-08/8.6a-mode-coordinator-homework]]
- Plan: [[plans/stage-08/8.6a-mode-coordinator-homework]]
- Report: [[steps/stage-08/8.6a-mode-coordinator-homework]]
- ADRs: [[decisions/adr-056-assistant-mode-coordinator]], [[decisions/adr-057-assistant-mode-routing-budget]]
- Gate handoff: [[steps/stage-08/findings-8.6a-gate-handoff]]
- Smoke: [[steps/stage-08/8.6-real-provider-smoke]]

## Stage 8.6b documents
- Spec: [[specs/stage-08/8.6b-exam-prep-mode]]
- Plan: [[plans/stage-08/8.6b-exam-prep-mode]]
- Report: [[steps/stage-08/8.6b-exam-prep-mode]]
- Smoke: [[steps/stage-08/8.6-real-provider-smoke]]

## Stage 10 documents
- Spec: [[specs/stage-10/10-gamification]]
- Plan: [[plans/stage-10/10a-foundation]]
- Report: [[steps/stage-10/10a-foundation]]
- ADRs: [[decisions/adr-056-gamification-course-timezone]], [[decisions/adr-057-gamification-on-read-evaluation]]

## Prior
- 2026-06-21 — Stage 10 Gamification FULLY VERIFIED and merged to main (migration head `0081`).
- 2026-06-20 — Stage 8.5 Save-to-Glossary from the Assistant FULLY VERIFIED (migration 0041); gate 21/21.
- 2026-06-19 — Stage 8.4 Assistant Workspace + floating widget FULLY VERIFIED (migration 0040); PR #10.
- 2026-06-18 — Stage 9 My Progress FULLY VERIFIED (0038-0039); Stage 8.2 + 8.1 FULLY VERIFIED.
- 2026-06-18 — Stage 7 core (7a-7c) FULLY VERIFIED; Stage 6 + Stage 5.5 + Stage 5 FULLY VERIFIED.
