# Status

_Last updated: 2026-06-20 — **Stage 8.6a (Assistant Mode Coordinator + Homework help) is FULLY VERIFIED** on `stage-8.6-assistant-modes`, rebased over the Stage 10 mainline state. The reusable mode foundation + Homework help are implemented end to end over the existing 8.1/8.2 seam with NO new provider/gateway code (rule 6), ONE call/turn @ interactive priority (rule 15), create-then-poll (no SSE). Verified at every level: backend **649 pytest** (625 prior + 24 new mode tests; 53 existing assistant tests green), migration **0042** single-head + fresh-DB round-trip, prompt-drift OK, frontend **tsc** + **vitest 9** green, client regen, 8.6a browser gate, full active Playwright **22/22**, and rule-11 homework smoke PASS on the Cerebras route. Stage 10 Gamification is already merged to `main`; its Alembic head is `0081`, so `dev_reseed` remains pinned to the higher merged head during this branch rebase._

## Current branch
- Branch: `stage-8.6-assistant-modes`
- Target branch: `origin/main`
- Base branch includes Stage 10 Gamification merged to `main` with Alembic head `0081`.
- Stage 8.6a adds migration `0042`; later stacked Stage 8.6 commits add `0043` and `0044`.
- Gate harness (workspace-local, gitignored): `.context/8.6a-gate.override.yml` runs the Dallas stack on
  :8005/:3005 with a unique backend image tag to avoid sibling workspace image contention.

## Stage 10 delivered on main
- Stage 10 Gamification is FULLY VERIFIED and merged to `main`.
- Migration block `0080-0081` is on main; expected merged Alembic head is `0081`.
- The Stage 10 report and log entries remain the source for the full gamification verification record.

## Stage 8.6a delivered (mode foundation + Homework help)
- **Mode = `conversation_kind` + a strategy coordinator (ADR-056).** `generate_assistant_answer_async`
  dispatches by kind via `_MODE_TURN_BUILDERS` (default = `_lecture_turn`, the existing behavior extracted
  VERBATIM; `homework_help` -> `_homework_turn`). A `_ModeTurn` carries the per-mode prep; the single
  `gateway.complete(... priority="interactive", feature="assistant")`, `decide_grounding`, and
  `_persist_grounded_answer` are shared. Kind is immutable; the per-mode snapshot rides the existing
  `context_snapshot`.
- **Homework (ADR-057).** Routes V2/Cerebras/32k via `homework_help/v1.yaml` after the rule-11 smoke showed
  the originally specced Think/Nvidia route was not suitable. Homework grounds on the bound module's permitted
  material via `retrieve_module_chunks` or the section scan when narrowed, and always coaches rather than
  giving direct answers.
- **Resume-or-create.** Migration 0042 adds one-active homework partial-unique indexes for module and
  optional-section bindings.
- **Section-or-module reads.** Conversation list/detail/visibility reads and DTOs are module-aware for
  module-bound homework while preserving the section-bound path.
- **Frontend.** Workspace "Help with homework" entry, `HomeworkPicker`, `HomeworkStarters`, non-editable mode
  label, homework context pills, and shared `ConversationView` support.

## Verification
- Alembic: `alembic upgrade head` -> single head `0042` during the original 8.6a gate; fresh-DB round-trip
  `downgrade 0041 -> upgrade head` clean.
- Backend pytest: **649 passed** after the 8.6a implementation gate.
- New `tests/test_assistant_modes.py`: **24 passed**; existing assistant tests **53 passed**.
- Frontend `tsc` exit 0; vitest **9 passed**.
- Live 8.6a browser gate passed; full active Playwright **22/22** (`e2e-86a-final`, 7.2m).
- Rule-11 homework smoke passed on Cerebras with the configured model echo and coaching guardrail held.

## Known-state notes
- `check:design-tokens`/`check:inline-styles` remain known-red from the pre-existing Stage 12 backlog; 8.6a
  followed the existing inline idiom.
- `test_quiz_pool::test_pool_one_active_lock_concurrent_first_requests` is a pre-existing flaky full-suite
  backend test that passes in isolation.
- `dev_reseed.EXPECTED_ALEMBIC_VERSION` stays on the higher merged mainline pin `0081` while this branch is
  rebased over Stage 10.

## Stage 8.6a documents
- Spec: [[specs/stage-08/8.6a-mode-coordinator-homework]]
- Plan: [[plans/stage-08/8.6a-mode-coordinator-homework]]
- Report: [[steps/stage-08/8.6a-mode-coordinator-homework]]
- ADRs: [[decisions/adr-056-assistant-mode-coordinator]], [[decisions/adr-057-assistant-mode-routing-budget]]
- Gate handoff: [[steps/stage-08/findings-8.6a-gate-handoff]]
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
