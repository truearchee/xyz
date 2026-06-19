# Status

_Last updated: 2026-06-19 — **Stage 8.4 PR #10 is rebased onto current `main` after Stage 4.9g and re-verified on a clean DB.** Conflict resolution preserved the Stage 4.9 monochrome/tokenized frontend foundation from `main` and integrated the Stage 8.4 Assistant Workspace + floating-widget changes on top. Stage 8.4 remains pre-merge; PR #10 is ready for owner review, not merged._

## Current branch
- Branch: `stage-8-4-implementation`
- Target branch: `origin/main`
- PR: `#10`
- Migration block used: `0040` inside the assigned `0040-0045` block (single expected head `0040`; chain `0033 → 0038 → 0039 → 0040`, with `0034-0037` frozen for 8.3).
- Rebase note: `origin/main` still ended at Alembic `0039`, so the Stage 8.4 migration did **not** need renumbering.

## Stage 4.9g baseline now on main
- Stage 4.9g merged the Stage 4.9f monochrome frontend design foundation while preserving Stage 5-9 backend/schema behavior.
- Active frontend baseline includes Tailwind v4/PostCSS, `frontend/src/app/globals.css`, `frontend/src/components/ui/**`, design check scripts, and tokenized restyles for preserved Stage 5-9 surfaces.
- Conflict resolution for Stage 8.4 kept this baseline in `StudentPage`, `AppShell`, and `AssistantPanel`; 8.4 assistant links/shared-store behavior were integrated into the tokenized UI.

## Stage 8.4 delivered (Option A — navigation/UX + conversation management, NO new AI surface)
- **Migration 0040**: `deleted_at` (soft-delete), `title_source` (auto|manual), `last_activity_at` (backfilled); one-active partial-unique index rebuilt to `WHERE conversation_kind='lecture_default' AND deleted_at IS NULL` (delete-then-reopen → fresh row). Downgrade reconciles soft-deleted tombstones before restoring the 0039 unique predicate. `dev_reseed` head pin bumped 0039→0040.
- **Invariants A–E** each tested: one-active-per-lecture, store-level send idempotency, current-access-wins (filtered + 404), supersession keeps access, delete-while-pending no-resurrection.
- **Endpoints** (student-only): `GET /student/assistant/conversations` (offset list), keyset `GET …/{id}/messages`, `GET/PATCH/DELETE …/conversations/{id}`. Every one routes through `require_student` (403) + ownership + the Stage 4.7 visibility gate (404, never 403).
- **Keyset pagination** for messages (ADR-053 sibling envelope; rule-10 escalation); **conversation-management contract** (ADR-054). GET-detail endpoint added (spec amendment).
- **Frontend**: single-source-of-truth store (`AssistantStoreProvider`, one poll loop, in-flight send keys), shared `ConversationView`, refactored `AssistantPanel`, Workspace list + conversation (context pill, Open lecture, inline rename, delete-with-exact-copy), lecture picker, floating widget + drawer (focus trap, ESC, lecture context pill, deterministic placement, a11y aria-live), chat starters, nav home.
- **Second external-review repairs**: workspace deep-link composer stays disabled while initial messages load; backend rejects a new send while an assistant turn is pending; widget and server open/create both enforce assistant readiness; shared store treats deleted/access-revoked 404s as gone.
- **Mobile keyboard claim**: keyboard overlap is explicitly **not verified** and not claimed in 8.4; tracked as follow-up.

## Verification
Post-rebase evidence for PR #10:
- Alembic clean DB upgrade reached `0039 -> 0040`; `alembic heads` returned exactly `0040 (head)`. No migration renumber was needed.
- Backend: targeted grounding regression **2 passed** after adapting existing-conversation coverage to the readiness gate; full backend `pytest -q` **604 passed**, 158 warnings.
- Frontend: `bun test tests/frontend/assistant-send-idempotency.test.ts` **4 passed**; `npm run type-check` passed; `npx next build` passed.
- Browser: cold frontend reproduction `tests/e2e/4.3.5b-shell-routing.spec.ts --workers=1` **1 passed** after prewarming role home routes for local Next-dev cold compilation; full active Playwright suite on a clean DB (rule 14) **20 passed** in 5.9m, run id `e2e-stage84-rebase6-1781890833`, serial `--workers=1`.
- Rule-11 real-provider smoke PASS: assistant/v2 model echo `MBZUAI-IFM/K2-Think-v2` matched on study and off-topic cases; `isStudyRelated` true/false correct.

## Stage 8.4 documents
- Spec: [[specs/stage-08/8.4-assistant-workspace-widget]]
- Plan: [[plans/stage-08/8.4-assistant-workspace-widget]]
- Report: [[steps/stage-08/8.4-assistant-workspace-widget]]
- ADRs: [[decisions/adr-053-keyset-pagination-sibling-envelope]], [[decisions/adr-054-assistant-conversation-management-contract]]
- Findings: [[steps/stage-08/findings-8.4-keyset-pagination-escalation]], [[steps/stage-08/findings-8.4-gate-run]]
- Smoke: [[steps/stage-08/8.4-real-provider-smoke]]

## Prior
- 2026-06-19 — Stage 4.9g monochrome redesign merge complete and verified on main.
- 2026-06-18 — Stage 9 My Progress FULLY VERIFIED (migrations 0038-0039).
- 2026-06-18 — Stage 8.2 grounded retrieval FULLY VERIFIED; 8.1 conversation foundation FULLY VERIFIED.
- 2026-06-18 — Stage 7 core (7a-7c) FULLY VERIFIED; Stage 6 + Stage 5.5 + Stage 5 FULLY VERIFIED.
