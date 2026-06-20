# Status

_Last updated: 2026-06-20 — **Stage 8.5 (Save-to-Glossary from the Assistant) is FULLY VERIFIED.** Implemented end to end and verified at the backend (625 real-DB pytest), type (tsc), frontend-wiring (vitest component), and live-browser levels. The 8.5 browser gate + the **rule-14 full active Playwright suite ran GREEN (21/21) on a clean DB** locally (non-disruptive alt-port stack :8005/:3005, local Supabase :54321, deterministic LLM adapter); **/cso CLEAN**, **/review** cross-model (one anti-spoofing hardening), **/qa** real-browser save-from-chat drive CLEAN. Not merged — ready for owner review/merge._

## Current branch
- Branch: `stage-8.5-implementation`
- Target branch: `origin/main`
- Migration block used: `0041` inside the assigned `0041-0046` block (single expected head `0041`; chain `… → 0039 → 0040 → 0041`, with `0034-0037` frozen for 8.3). Reconciliation: 8.4 used only `0040`; its docstring "reserved" 0041–0045 but the owner reassigned `0041-0046` to 8.5 — `0041` is the real next head.

## Stage 8.5 delivered (save-to-glossary from the assistant — reuse-and-wire)
- **Definition fork resolved (ADR-055 / rule-10):** Stage 7's definition job injects the highlighted
  `selected_text` into the prompt on a cache miss. Chat saves pass `definition_context=""` → subject-level
  definition identical to the manual-add AI path. Proof: cache key excludes context, input hash includes
  it ⇒ empty-context chat save shares the manual-add cache row + input hash ⇒ no new AI behavior ⇒ **no
  rule-11 smoke**.
- **ONE write path:** the existing `POST /student/glossary/highlight` gains an optional discriminated
  `conversation` source (validator: exactly one of `moduleSectionId` | `conversation`). The glossary
  domain owns the write; assistant state read via the new `platform/query/assistant_save_source_read`
  (rule 8). Anti-spoofing: completed assistant message + owned/bound/published+assigned + selectedText-in-
  message (conservative markdown normalizer); pinned 404 mirrors the assistant; role/status/text are
  distinct 4xx after ownership.
- **Migration 0041:** `source_conversation_id`/`source_message_id` FKs (SET NULL) + widened `source_type`
  CHECK (+`'conversation'`) + partial-unique idempotency index on `(entry, message)`. `dev_reseed` head
  pin 0040→0041.
- **Frontend:** generalized `<SaveToGlossary>` (backward-compatible `source` prop); single mount point in
  the shared `ConversationView`→`AssistantAnswerBody` covering inline panel + workspace + widget; gated on
  a section-bound conversation (D4) and completed assistant replies only; read-only destination (D2);
  duplicate = "already saved" + idempotent source-attach (D3).

## Verification
- Alembic: fresh DB reached `0040 -> 0041`; `alembic heads` → `0041 (head)`; `downgrade 0040 → upgrade
  head` round-trip clean.
- Backend `pytest`: first full run **619 passed + 1 failed** (the dev_reseed version pin) → fixed → **620 passed**; the pre-landing review added 5 tests → **625 passed**; new `test_glossary_conversation_save`
  **16 passed** (all spec negatives + empty-context/cache-collapse proofs); `test_glossary_save` **9
  passed** (summary regression, untouched).
- Client regenerated from the live OpenAPI (only the 4 expected files); frontend `tsc` exit 0; `test:unit`
  **9 passed** incl. 5 new `ConversationView` affordance-gating tests; a11y/vitest green.
- E2E gate `tests/e2e/8.5-assistant-save-to-glossary.spec.ts` authored; `playwright --list` discovers it;
  full suite lists 21 tests / 18 files.
- **Live gates GREEN (ran LOCALLY, clean DB):** 8.5 browser gate `tests/e2e/8.5-assistant-save-to-glossary.spec.ts` passed; **full active Playwright 21/21** (rule 14, serial, run id `e2e-mqlw0xei-9d1e2ebc`, 11.4m). /cso CLEAN; /review (Claude + Codex gpt-5.5) → term-in-message hardening; /qa real-browser drive CLEAN (0 bugs, no console errors). Stack: alt-port :8005/:3005 via `.context/8.5-gate.override.yml`, `kyiv-frontend` node:20 container, local Supabase :54321, deterministic adapter. The gate caught one test-wiring fix (selector scoping, commit `011a635`). → [[steps/stage-08/findings-8.5-gate-handoff]].

## Known-state notes
- `check:design-tokens`/`check:inline-styles` are known-red (396 pre-existing inline-idiom violations =
  Stage 12 backlog); 8.5 added zero new violations.
- Restored the tracked stale `backend/openapi.json` (Stage-7 snapshot) after using it transiently for codegen.

## Stage 8.5 documents
- Spec: [[specs/stage-08/8.5-save-to-glossary]]
- Plan: [[plans/stage-08/8.5-save-to-glossary]]
- Report: [[steps/stage-08/8.5-save-to-glossary]]
- ADR: [[decisions/adr-055-conversation-sourced-glossary-save]]
- Gate handoff: [[steps/stage-08/findings-8.5-gate-handoff]]

## Prior
- 2026-06-19 — Stage 8.4 Assistant Workspace + floating widget FULLY VERIFIED (migration 0040); PR #10.
- 2026-06-19 — Stage 4.9g monochrome redesign merge complete and verified on main.
- 2026-06-18 — Stage 9 My Progress FULLY VERIFIED (0038-0039); Stage 8.2 + 8.1 FULLY VERIFIED.
- 2026-06-18 — Stage 7 core (7a-7c) FULLY VERIFIED; Stage 6 + Stage 5.5 + Stage 5 FULLY VERIFIED.
