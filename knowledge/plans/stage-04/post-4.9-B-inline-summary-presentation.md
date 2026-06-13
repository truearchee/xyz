---
type: session-plan
stage: 04
session: "post-4.9-B"
slug: inline-summary-presentation
status: complete
created: 2026-06-13
updated: 2026-06-13
spec: knowledge/specs/stage-04/post-4.9-B-inline-summary-presentation.md
---

# Workstream B — Implementation Plan — Inline Summary Presentation

## Linked documents
- Sub-spec: [[specs/stage-04/post-4.9-B-inline-summary-presentation]] · Scope: [[specs/stage-04/post-4.9-corrective-summary-verification-inline]]

## Steps (each frontend-only; no schema/endpoint/behaviour change)
1. **Extract `SectionSummaries`** (`features/content/student/SectionSummaries.tsx`, "use client"): move
   `SummariesPanel` + `SummarySlot` + the polling constants/logic/wall-clock-cap/mounted-cleanup out of
   `StudentSectionDetail.tsx` **verbatim** (pure relocation — diff should show move, not rewrite). Props:
   `sectionId`, plus the initial slot states it already receives. Keep `data-testid` values
   (`student-summary-brief`/`-detailed` + `-content` + `data-state`) byte-identical.
2. **Consolidate `StudentModuleDetail.tsx`:** after each section's `StudentSectionView`, render
   `<SectionSummaries sectionId={section.id} … />`. Delete the "View summaries →" `Link` (:194-200) and the
   now-redundant state badge. Keep the published-only section iteration exactly (no new fetch for drafts).
3. **Redirect the section route:** `.../sections/[sectionId]/page.tsx` → `redirect('/student/modules/${moduleId}')`
   (Next `redirect()`); remove `StudentSectionDetail.tsx` (its logic now lives in `SectionSummaries`). Confirm
   no other importer of `StudentSectionDetail` (grep) before removal.
4. **Update the 4.7 E2E (same commit):** re-point G1/G2/G7 + G3 page-content assertions in
   `4.7-student-summaries.spec.ts` to the module page's section block; leave G4/G5/G6 (API) + the stage-3
   visibility spec untouched. Navigate to `/student/modules/${moduleId}` and assert the brief/detailed slots
   within the section block (testids unchanged → mostly a navigation/scope change, not an assertion weakening).
5. **Gate:** §8 frontend gate (typecheck/lint/test:unit/test:a11y/checks/build) + full active Playwright suite
   (rebuild frontend image; `--workers=1`; 3-part) + mobile-sanity re-capture on the student surfaces.

## Risks & mitigations
- **R1 — extraction changes behaviour.** Mitigate: move verbatim, keep testids; the unit/a11y + E2E catch drift.
- **R2 — E2E weakened to pass.** Mitigate: re-point location only; same `data-state`/marker assertions;
  rollback-not-loosen (revert layout, never the test).
- **R3 — N pollers heavy on a many-section module.** Mitigate: bounded backoff + 15s cap + 8-min wall-clock
  per slot; O2 coordinator deferred unless observed heavy.
- **R4 — longer module page mobile overflow.** Mitigate: re-run mobile-sanity (the 8/8 0px check) post-change.
- **R5 — security widening.** Mitigate: iterate the published-only list only; no draft fetch; SummaryMarkdown
  raw-HTML-off unchanged; E2E G3/G4/G5/G6 preserved.

## Out of scope (parked / separate)
- Workstream A (generation) — gated on the developer's Task 0 step-3 real-provider baseline.
- F-C4 ("Save notes" no UI confirmation, lecturer side) — separate small frontend finding.

## Approval gate
No source edits until the developer approves this spec + plan (and O1/O2 defaults, or overrides them).
