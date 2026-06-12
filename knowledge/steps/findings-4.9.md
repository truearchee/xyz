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

**Raised:** 2026-06-12. **Status: RESOLVED — fixed in this block (4.9e §7.4), DEMONSTRATED not asserted.**

**Resolution (2026-06-13, 4.9e):** both prevention halves shipped + proven fail-loud (not just present):
- **Unconditional teardown** — `tests/e2e/run-active-suite.sh` wraps the whole run in `trap cleanup EXIT`,
  so prefix-scoped (`teardown.mjs $E2E_RUN_ID`) cleanup runs on ANY exit — normal, a crashed spec, or
  Ctrl-C. This is the "afterAll/finally semantics" §7.4 requires. Implemented as a trap **not** a Playwright
  `globalTeardown` on purpose: globalTeardown fires per `playwright test` invocation and would wipe the seed
  **between** the 3-part fault orchestration's invocations (success set → invalid_output → invalid_input).
  The trap tears down ONCE at the end. (The globalTeardown I first wrote was deleted; playwright.config reverted.)
- **Pre-run orphan check** — `tests/e2e/fixtures/check-orphans.mjs` counts e2e-owned `course_modules`
  (`title <> 'e2e_module'`, excluding the seed's standing fixture) and **exits 1** if any leaked from a prior
  run, aborting the suite before it starts. **DEMONSTRATED:** clean → "OK" exit 0; inject one orphan module →
  "FAILED" exit 1; delete it → "OK" again (the inject/clear cycle, run in the 4.9e gate). Both heavy gates'
  pre-run checks reported "check-orphans OK", and teardown manifests show full prefix-scoped cleanup.

The §7.4 batch item (the 4th hygiene item, per the umbrella §7.4 amendment) is closed. Original framing kept below.

---

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

---

## F-4.9-3 — `next@15.3.3` + `postcss` npm-audit advisories (surfaced when 4.9a added deps)

**Raised:** 2026-06-12 (4.9a). **Status: ACCEPTED-WITH-RATIONALE for Stage 4.9; the Next upgrade DEFERRED to Stage 12 (release hardening).**

`npm audit` flags two advisories after the 4.9a dep install. Assessed for **severity + reachability**
(the two things that decide whether it jumps the queue):

| Advisory | Severity | Reachable in THIS app? | Verdict |
|---|---|---|---|
| **next** — Image Optimization API cache-key confusion (GHSA-g5qg-72qw-gw5v, CVSS 6.2; npm rolls next up as "critical") | moderate (6.2) | **No** — app uses **no `next/image`**, **no middleware**, **no server actions** (grep-confirmed); the `/_next/image` optimization route is not on any app flow | not high-and-reachable |
| **postcss** — XSS via unescaped `</style>` in CSS stringify (GHSA-qx2v-qp2m-jg93, CVSS 6.1) | moderate (6.1) | **No** — postcss runs **build-time on our own authored `globals.css`**, never on untrusted input | not reachable |

**Pre-existing, not introduced by 4.9:** Stage 4.8 already shipped on `next@15.3.3`; the postcss
advisory is a transitive of Next/Tailwind that 4.9a's explicit `postcss@^8` merely surfaced.

**Resolution (rule 13):**
- **Accepted-with-rationale for Stage 4.9** — neither advisory is high-severity AND reachable; upgrading
  Next mid-foundation risks rippling the App Router / build behavior 4.9 is actively changing.
- **Deferred:** the actual **`next` upgrade → Stage 12 (release hardening)** (its natural home; not forced
  sooner because unreachable here). postcss resolves on the next Next/Tailwind bump. **Re-assess if the
  CVE severity rises or a reachable path (next/image, middleware, image-opt) is added before Stage 12** —
  at which point it jumps to the §7 hygiene batch or sooner.
- Logged here as F-4.9-3 so it cannot evaporate as a loose `npm audit` line.

---

## F-4.9-4 — Unconsumed legacy `features/content/*.tsx` generation (surfaced by the 4.9d gates)

**Raised:** 2026-06-12 (4.9d, by `check:inline-styles`/`check:design-tokens`). **Status: deferred to Stage 12 (delete) — LEFT per §5.**

Standing up the §8 gates (and the 4.9c inline-style grep that found `ModuleDetailView`) surfaced an
entire **unconsumed older generation** of content components living **directly** in `src/features/content/`:
`LecturerNotesEditor`, `PublishToggle`, `SectionAssetList`, `StudentSectionList`, `StudentSectionView`,
`UploadButton` (+ the `features/content/api/*` helpers), all barrel-only exports of `features/content/index.ts`.
**Confirmed dead:** nothing outside `features/content/` imports the barrel or any of these components/JSX,
and the live UI uses the `features/content/{lecturer,student}/*` subdir components (restyled in 4.9c) +
`lib/api/wrapper`. Plus `features/modules/ModuleDetailView.tsx` (same: barrel-only, no consumer).

**Resolution (rule 13): deferred to Stage 12 — LEFT, not restyled (§5 componentize-or-leave).** Restyling
dead code is a YAGNI/§5 violation; deleting code (even dead) is a deliberate developer decision out of
4.9's restyle scope. The gates EXCLUDE these paths (`src/features/content/[^/]+\.tsx` + ModuleDetailView)
with the reason inline. **Stage 12 action: delete the unconsumed `features/content/*.tsx` generation +
`ModuleDetailView`** (or confirm + restyle if a consumer is reintroduced). This is the entire Stage-12
Part-3 dead-code backlog from 4.9. *The gates finding surfaces the recon missed is the argument for
mechanical verification over eyeballing.*

**4.9c scope completion note (not a finding):** the same gate run caught two **live** surfaces the recon
missed — `app/(app)/lecturer/page.tsx` + `app/(app)/student/page.tsx` (tiny `style={{grid}}` wrappers).
These ARE consumed → **restyled in 4.9d** (token classes) and logged in the restyle inventory; the
suite/gates cover them.

---

## F-4.9-5 — Remote CI branch-protection enforcement (owner: developer; trigger: next push)

**Raised:** 2026-06-12 (4.9d). **Status: DEFERRED — accepted-with-owner; trigger: the next push to the remote.**

Prereq 5 requires the §8 gates to be a REAL gate, not folklore. 4.9d delivers + **proves the LOCAL half**
(Husky pre-commit demonstrably blocks a failing commit) and ships `.github/workflows/ci.yml`. The **REMOTE
half** — marking `frontend gates` + `backend pytest` as required status checks on `main` via branch
protection, and demonstrating a failing check blocks a merge — **cannot be done from this environment**:
`gh` is not installed and `gh auth login` is interactive (needs the developer's GitHub identity); the
remote `main` is also 20 commits behind (4.8 + 4.9a-d unpushed). This is a boundary to respect, not engineer
around (the agent must not act as the developer's GitHub identity).

**Resolution (rule 13): deferred, owner = developer, trigger = next push.** Exact commands in
[[steps/stage-04/4.9d-vitest-gates]] ("Branch-protection handoff"): push the branch → one Actions run →
`gh api … /branches/main/protection` marking both checks required → open a PR with a failing check and
confirm GitHub blocks the merge. **Until done, a CI gate that runs but is not required is the "yaml costume"
failure mode — so 4.9's roadmap status states this explicitly** (FULLY VERIFIED with remote-CI enforcement
pending this finding; local enforcement proven). F-4.9-5 flips to resolved when the developer completes the push + protection + failing-merge demo.

---

## F-4.9-6 — Mobile horizontal overflow on restyled authoring surfaces (caught by the 4.9e design-match capture)

**Raised:** 2026-06-13 (4.9e close-out, by the automated mobile-sanity check). **Status: RESOLVED — fixed in this block (CSS only, no behaviour/selector change).**

The 4.9e design-match capture (`tests/e2e/fixtures/capture-screenshots.mjs`) measures
`documentElement.scrollWidth − innerWidth` at 375px per surface. It caught real horizontal overflow on two
**restyled (4.9c) authoring** surfaces: **`/admin` (150px)** and **`/lecturer/modules/{id}` (5px)**. All five
**mobile-first student** surfaces + login + unauthorized were already **0px** — i.e. the design plan's actual
mobile-first requirement was met; the misses were on desktop-first surfaces. *(This is the automated check
earning its keep — the same "mechanical verification over eyeballing" lesson as F-4.9-4.)*

**Root cause (proven by a DOM ancestor-chain trace, not guessed).** Two compounding CSS mechanisms, NOT the
tables (the `min-w-0 overflow-x-auto` table wrappers clip correctly — trace showed `off=309, overflow-x:auto ◀ CLIPS`):
1. **Grid items default to `min-width:auto`** and refuse to shrink below their content's min-content, so a
   wide member table or the auto-fit form grid forced the panel (then the page) past 375px. (`grid gap-6`
   page section measured `client=343` but `scroll=509`, overflow-x visible all the way up — nothing clipped.)
2. **`<select>` intrinsic width = its widest `<option>`** (long emails/titles like
   `lecturer_unassigned_e2e@example.test`); `panelClasses.input` had no width constraint, so the select alone
   was 492px and forced its form column wide.

**Fix (CSS utilities only; every `data-testid`/role/structure preserved byte-for-byte → E2E selectors untouched):**
- `frontend/src/features/admin/shared.ts`: `panelClasses.panel` += `min-w-0 [&>*]:min-w-0`; `stack` +=
  `[&>*]:min-w-0`; `input` (used by selects) += `w-full min-w-0` — so the panel shrinks within the page grid,
  its children shrink (auto-fit form grid then sees a DEFINITE 343px width and collapses to ONE column;
  table wrappers clip; selects truncate). `grid` left at `minmax(220px,1fr)` (a `minmax(min(220px,100%),1fr)`
  attempt was REVERTED — with an indefinite container it resolved to max-content and made `/admin` *worse*,
  402px; recorded so the dead-end isn't re-attempted).
- `frontend/src/features/admin/{users,modules}/*Panel.tsx`: the `overflow-x-auto` table wrappers += `min-w-0`.
- `frontend/src/features/content/lecturer/LecturerModuleDetail.tsx`: `[&>*]:min-w-0` on the three grids +
  `min-w-0`/`break-words` on the header title divs.

**Verification (falsifiable):** the DOM-trace diagnostic (`tests/e2e/fixtures/diagnose-overflow.mjs`) reports
**zero true wideners** on both surfaces; the mobile-sanity capture reports **all 8 surfaces = 0px** at 375px;
the desktop screenshots confirm the **2-column form layout is preserved** (`min-width:0` only *enables*
shrinking). `npm run build` compiles the `[&>*]:min-w-0` arbitrary variants (no purge/validity error); full §8
gate + full active E2E suite green after the change (selectors intact). No behaviour added (umbrella §3).
