# Findings — Stage 4.9

Rule 13 vocabulary: **fixed in this block / deferred to a named session / accepted with written
rationale / rejected as invalid.** Unresolved findings block FULLY VERIFIED (rule 13).

---

## F-4.9-1 — Baseline (prereq 4): full active suite not green locally due to accumulated e2e data

**Raised:** 2026-06-12 (Phase 0, before 4.9a). **Status: RESOLVED — fixed in this block.**

**Resolution (2026-06-12):** developer chose "purge orphaned e2e modules." The 58 e2e-owned
`course_modules` were deleted in a scoped, ordered transaction (transcripts → section_assets →
module_sections → course_memberships → course_modules; deeper rows cascaded), keeping the 2 non-e2e
dev modules. The documented 3-part orchestration is then **11/11 green** at `6dd12db` — recorded in
[[steps/stage-04/4.9-baseline]]. Not a code regression (create returned 201). See the baseline report
for the reproducible run protocol.

**Symptom.** Running the full active Playwright suite at unmodified main `6dd12db`:
- `4.3.5c-stage2-admin` (in the 9-spec success set) **fails deterministically** (also in isolation):
  `expect(getByTestId('admin-module-row-module-a-<runid>')).toBeVisible()` times out — the row never
  renders.
- The 2 fault specs (`4.5d-summary-fault` ×2) fail under a **single** `npx playwright test` invocation.

**Root cause — NOT a code regression (create succeeds).** Backend logs during the failure show:
```
POST /admin/modules               → 201 Created      (module create SUCCEEDS)
GET  /admin/modules?limit=50      → 200 OK           (admin list is capped at 50)
```
The local DB has **60 `course_modules`** accumulated over 3 days (`oldest 2026-06-03`), of which
**58 are owned by e2e-domain users** (`@xyz-lms-e2e.dev` / `@example.test`) — orphaned artifacts from
prior e2e runs that did not run `teardown.mjs` (e.g. "Checkpoint A/B/C/D Smoke", "e2e_module"). The
newly-created module sorts outside the first 50 returned by `?limit=50`, so its row is never in the
DOM → `toBeVisible` times out. The conditional `role="alert"` seen in the snapshot is incidental.

The 2 fault specs are **by design** not runnable in one invocation: each needs the `ai_worker`
restarted with a matching `LLM_FAULT_INJECTION` value (the documented orchestration, confirmed in the
4.8a report): success set via `--workers=1 --grep-invert "fault gate"` (9) **+** invalid_output (1)
**+** invalid_input (1) = 11/11.

**Evidence this is environmental, not main/4.9 regression:** STATUS + the 4.8a report record the
success set as 9/9 at this exact commit; the create POST returns 201; the only differences are (a) 60
accumulated modules vs the admin `limit=50`, and (b) my single-invocation vs the documented 3-part run.

**Resolution (proposed): fixed in this block (Phase 0)** — purge the 58 orphaned e2e modules (those
whose owner email is `@xyz-lms-e2e.dev` / `@example.test`, with cascade), leaving the ~2 non-e2e dev
modules, then record the baseline via the documented 3-part orchestration. **Pending the developer's
go-ahead** (it is their local DB; bulk delete is hard to reverse). Alternatives offered: full local DB
reset, or accept-with-rationale (record 8/9 + the fault orchestration, noting the `limit=50` artifact).

**Same root cause as [[steps/findings-4.8]] F-4.8d-1** ("4.3.5c deterministically flakes on accumulated
DB state (admin-list pagination)"), which 4.8 DEFERRED as "a candidate for the 4.9 hygiene batch." This
data purge resolves the immediate **baseline** blocker; the **root-cause** decision (test isolation
discipline vs an admin-list pagination envelope) is still open and should be closed during the 4.9
build — see F-4.9-2.

---

## F-4.9-2 — E2E data-hygiene PREVENTION (carried from F-4.8d-1; added to spec §7 as the 4th hygiene item)

**Raised:** 2026-06-12. **Status: OPEN — resolve in 4.9d/4.9e (developer-locked framing: prevention, not cleanup).**

F-4.8d-1 deferred the root cause to "the 4.9 hygiene batch," but spec §7 originally listed only
httpx / CORS / client-regen. Per developer decision this is now **spec §7.4** (amendment-added). Framed
as **prevention** so the orphan accumulation that broke the baseline cannot recur — NOT a one-off cleanup:

1. **Unconditional teardown.** `afterAll`/`finally` semantics so a mid-suite crash still triggers
   **prefix-scoped** (runId / `@…e2e.dev` / `@example.test`) cleanup — the suite never leaks e2e rows
   even when a spec throws.
2. **Pre-run orphan check.** A script that counts `@xyz-lms-e2e.dev` / `@example.test`-owned rows
   **older than the current run** and **fails loud** (or auto-purges) on non-zero — so accumulation is
   caught at the start of a run, not discovered as a flake mid-suite.

**Explicitly distinct from the `GET /admin/modules?limit=50` endpoint.** This is **test-harness hygiene
only**. The admin-list **pagination UI** is a §5 one-off (a screen Stage 5+ never reuses) → **Stage 12**
consistency sweep. **4.9 ships no pagination** and no endpoint/schema change (spec §3 honored).

**Resolution target:** 4.9d (author the unconditional teardown + the pre-run orphan-check script, wired
into the verification surface §8) / 4.9e (confirm at close). Final disposition recorded here then.
