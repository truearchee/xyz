---
type: finding
stage: 08
session: "8.4c"
created: 2026-06-19
status: resolved
---

# Finding 8.4 — live local browser gate: 3 issues caught + fixed, 2 local-stack gotchas

The live browser gate ran LOCALLY (the local stack CAN come up — no remote staging needed): backend +
workers on host :8005 (existing image + live bind-mount), the frontend in the node:20 container on
:3005, against the local Supabase (`127.0.0.1:54321`), seeded via `seed.mjs`, with `test2` left
untouched (port remap in `.context/8.4-gate.override.yml`). Final: full active suite **20/20** + the
rule-11 real-provider smoke PASS → Stage 8.4 FULLY VERIFIED.

## Real bugs the gate caught (fixed — these are why the gate exists)
1. **Render/fetch loop in `AssistantWorkspaceConversation`.** The mount `useEffect` had the store
   *value* (`store`) in its dependency array. The provider's `value` re-references on every conversation
   update, and the effect calls `store.loadInitial` (which mutates the store) → the effect re-ran in a
   loop, never letting `detailState` settle (so the access-revoked "no longer available" state never
   stuck) and hammering the backend. **Fix:** depend on the stable `useCallback` actions
   (`loadInitial`/`markDeleted`), not the value object.
2. **Conversation page didn't show the conversation's (renamed) title.** The display title lived only in
   the Workspace list, so a rename had no visible effect on the conversation page. **Fix:** added a
   `assistant-conversation-title` heading (derive-on-read display title) — a real UX gap, not just a test
   prop.
3. **Spec used the wrong nav test id.** `nav-assistant` exists only on the `/student` dashboard; on a
   lecture page the persistent nav home is `shell-nav-assistant` (AppShell). The click on a non-existent
   element hung to the test timeout (Playwright's default action timeout is 0). **Fix:** the spec uses
   `shell-nav-assistant` (which also proves the persistent AppShell nav home).

## Local-stack gotchas (not code bugs — record for future local gate runs)
- **Node 25 host breaks Next SSR.** Running `next dev` on the node-25 host throws
  `localStorage.getItem is not a function` (node 25 ships a partial global `localStorage`: `typeof
  localStorage === 'object'` but `getItem` undefined, so the SSR guard passes then `.getItem` throws).
  **Run the frontend in the node:20 container** (the established gate pattern), never on the host.
- **State pollution across repeated same-run-id runs.** Re-running the quiz gates (5d/6d) multiple times
  against the SAME seeded DB + run id left stale `in_progress` attempts and pre-warmed pools, which made
  the quiz specs fail (e.g. 6d's transient "generating" state is unobservable once a pool is pre-warmed;
  5d resumed a stale attempt). Quiz GEN was never broken (14 attempts completed, stuck ones each had 10
  questions). **On a freshly reset DB the full suite is 20/20.** Lesson: a clean DB per full-suite run
  (drop/recreate `xyz_lms` → migrate → seed) — these gates assume near-clean state. NOT an 8.4 issue
  (8.4 touches zero quiz-generation code).

## Status
RESOLVED. Code fixes (1–3) are present in the working tree; gotchas recorded for the gate runbook.

## Post-review rerun
External review found three additional pre-commit gaps: store-level send idempotency, 0040 downgrade
delete→reopen reconciliation, and the lecture widget context pill. After fixing them, the full active
suite reran on a clean DB (`e2e-stage84-fix-1781883673`) with `.env` + `.env.e2e` exported into
Playwright: **20/20 passed**. The strengthened 8.4 gate now asserts widget context pill, "Where did this
come from?", double-click send, retry-after-accepted-timeout, and two visible surfaces racing the same
draft.

## Second external-review rerun
The second external review found four more pre-commit gaps:

1. Workspace deep-link could enable the composer before the async initial message load settled.
2. Floating widget could bypass the assistant readiness gate.
3. Shared polling/load handling swallowed 404s from deleted or access-revoked conversations.
4. The mobile keyboard-aware/mobile-verified claim was not implemented or proven.

Fixes made: `ConversationView` now receives `loading`/`gone` and disables the composer while loading or
gone; backend `send_message` locks the conversation and rejects a new client key while an assistant turn
is pending; widget start mirrors availability and server open/create enforces readiness; the shared store
transitions 404 load/poll/send/retry failures to gone. For item 4, we chose the documentation path:
keyboard-overlap behavior is explicitly **not verified** in 8.4 and no keyboard-aware claim remains.

Clean-DB full suite rerun: **20/20 passed** with run id `e2e-stage84-review2-env-1781886621`, `.env` +
`.env.e2e` exported, backend/frontend on `:8005`/`:3005`, serial `--workers=1`. The 8.4 specs now cover
deep-link pending disable, widget readiness for processing/unavailable lectures, and deleted/gone state
in a second surface. A parallel attempt was invalid evidence because existing suite-level worker
fault-injection specs mutate global env and the Playwright manifest writer is not parallel-safe.
