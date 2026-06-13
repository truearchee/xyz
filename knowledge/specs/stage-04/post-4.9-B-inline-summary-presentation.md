---
type: session-spec
stage: 04
session: "post-4.9-B"
slug: inline-summary-presentation
status: complete
created: 2026-06-13
updated: 2026-06-13
owner: developer
scope-spec: knowledge/specs/stage-04/post-4.9-corrective-summary-verification-inline.md
plan: knowledge/plans/stage-04/post-4.9-B-inline-summary-presentation.md
---

# Workstream B — Inline Summary Presentation (Stage 4.7 revision) — SUB-SPEC

> Authorized by [[specs/stage-04/post-4.9-corrective-summary-verification-inline]] §3. Frontend-only;
> independent of Task 0. **B2 product decision = Option 2 (both brief + detailed fully expanded inline, no
> toggle)** — locked by the developer 2026-06-13. **No source edits until this spec + plan are approved.**

## Goal
The student sees everything for a lecture **in one block on one page** — no hop to a separate summaries page.
Each section block, in order: **header · lecturer notes · files · brief summary · detailed study summary**
(both summaries fully expanded). Remove the "View summaries →" link and the separate section page as a
required navigation step.

## Current state (mapped from code)
- **Module page** `(app)/student/modules/[moduleId]/page.tsx` → `StudentModuleDetail` (client): fetches
  `api.modules.get` + `api.content.listSections` (published-only) + `api.studentSummaries.listSections`
  (state flags) + per-section `api.content.getSection` (notes + assets). Renders each section via
  `StudentSectionView` (header + notes + files) + a summary-state badge + the **"View summaries →" link**
  (`StudentModuleDetail.tsx:199`) → the section page.
- **Section page** `.../sections/[sectionId]/page.tsx` → `StudentSectionDetail` (client) = the "separate
  summaries page": header + notes + files + `SummariesPanel` (`StudentSectionDetail.tsx:124-204`) which
  owns `api.studentSummaries.getSummaries` + **bounded polling** (initial 1.5s, ×1.5 backoff, cap 15s,
  8-min wall-clock cap, unmount-safe) + `SummarySlot` (`:206-236`, the §4.3 ready/generating/unavailable
  states, `data-state` exposed for E2E) + `SummaryMarkdown` (raw-HTML-off, safe-link-only).

## Build
1. **Extract** the summary panel into a reusable client component `SectionSummaries` (new file under
   `features/content/student/`) — moving `SummariesPanel` + `SummarySlot` (+ the polling logic, constants,
   wall-clock cap, mounted cleanup) out of `StudentSectionDetail` verbatim (logic unchanged). Props:
   `sectionId` (+ the initial per-slot states it already has). Renders the brief + detailed slots fully
   expanded. `SummaryMarkdown` stays as-is.
2. **Consolidate onto the module page.** `StudentModuleDetail` renders each section as ONE block:
   `StudentSectionView` (header + notes + files, unchanged) immediately followed by `<SectionSummaries
   sectionId={section.id} … />`. Each `SectionSummaries` fetches `getSummaries(sectionId)` lazily on mount
   and runs its own bounded poll (matches today's section-page behaviour; N independent unmount-safe pollers
   for the handful of sections in a module).
3. **Remove** the "View summaries →" link (`StudentModuleDetail.tsx:199`) and the now-redundant
   summary-state badge (the content is now inline; the per-slot state shows in the block itself).
4. **Redirect** the section route `.../sections/[sectionId]/page.tsx` → the module page (`/student/modules/
   [moduleId]`) so existing deep links don't 404 and it is no longer a required step. `StudentSectionDetail`'s
   summary logic now lives in the extracted `SectionSummaries` (no dead code). *(Redirect, not delete, to keep
   bookmarks working — open question O1 if you'd rather hard-delete.)*

## Do not build
- No schema change, no new/changed endpoint (reuse `getSummaries` / `listSections` / `getSection`).
- No new PUBLIC component (build from the 4.9 library: `Card`/`EmptyState` + the existing `SummaryMarkdown`
  + the extracted `SummarySlot`); token-only.
- No lecturer summary editing; no change to the detailed section set; no generation (Workstream A) work.

## Constraints (B3 — do not regress)
- **Security:** unpublished sections + unassigned modules still 404, non-student 403 — all backend-enforced
  (unchanged). The module page already renders **only published** sections (`listSections` is published-only);
  the consolidation MUST NOT fetch summaries for unpublished sections (it won't — it iterates the
  published-only list). Raw transcript never reachable: `SummaryMarkdown` stays raw-HTML-off; no transcript
  link/filename rendered.
- **§4.3 states:** the extracted component reuses the existing generating / unavailable / failed states +
  the passive "still being generated — refresh to check" wall-clock message. No spinner-implying-hang, no
  empty gap.
- **Data:** read-projection reuse only (per-section `getSummaries`); a schema change is out of scope.

## Verification (B4 + gates)
- **4.7 E2E moved IN THE SAME COMMIT, not loosened:** `tests/e2e/4.7-student-summaries.spec.ts` G1/G2/G7
  assertions (brief `data-state=ready` + `BRIEF_MARKER`; detailed ready + `DETAILED_OVERVIEW_MARKER`; brief
  `unavailable`) re-pointed from the section page to the **section block on the module page**. G3 page-content
  security checks (no SENTINEL / SENTINEL_FILE / "view transcript") re-pointed to the module page. G4/G5/G6
  (API 404/404/403) unchanged. `4.7-stage3-content-visibility.spec.ts` (published-only) preserved.
- **Rollback-not-loosen:** if the suite can't be made honestly green, the layout reverts — the test is never
  weakened (4.9c stance).
- Full §8 frontend gate green; full active Playwright suite 11/11; mobile sanity re-confirmed on the student
  surfaces at 375px (the consolidated module page is now longer — verify 0px overflow + the §4.3 states render).

## Findings
- Resolves **F-C3** (separate summary page → inline single block). No new findings expected; a genuinely
  longer module page is the accepted consequence of B2=fully-expanded (the developer's choice).

## Open questions — RESOLVED (developer, 2026-06-13)
- **O1 — section route: REDIRECT** the `.../sections/[sectionId]` route → `/student/modules/[moduleId]`
  (deep-link-safe; no 404 on bookmarks). Confirmed.
- **O2 — poller count: N INDEPENDENT per-section pollers** (verbatim reuse of today's bounded
  backoff/cap/wall-clock per slot). Confirmed. Revisit only if a module ever has many lecture sections.
