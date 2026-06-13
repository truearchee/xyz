---
type: session-report
stage: 04
session: "post-4.9-B"
slug: inline-summary-presentation
status: complete
created: 2026-06-13
updated: 2026-06-13
spec: knowledge/specs/stage-04/post-4.9-B-inline-summary-presentation.md
plan: knowledge/plans/stage-04/post-4.9-B-inline-summary-presentation.md
---

# Workstream B — Report — Inline Summary Presentation

## Linked documents
- Spec: [[specs/stage-04/post-4.9-B-inline-summary-presentation]] · Plan: [[plans/stage-04/post-4.9-B-inline-summary-presentation]]
- Scope: [[specs/stage-04/post-4.9-corrective-summary-verification-inline]] · Findings: [[steps/findings-4.9]] (F-C3)

## What shipped (frontend-only; no schema/endpoint/behaviour change to the backend)
- **`SectionSummaries.tsx` (new)** — the brief+detailed panel + `SummarySlot` + bounded polling (1.5s→cap
  15s, 8-min wall-clock, unmount-safe) extracted VERBATIM from the old `StudentSectionDetail`. One intentional
  non-verbatim tweak: slot heading levels h3→h4 / loading h2→h3 to fit the new nesting under the section's
  `<h2>` (correct heading hierarchy). Testids byte-identical (`student-summary-brief`/`-detailed`,
  `data-state`, `-content`).
- **`StudentSectionView.tsx`** — renders `<SectionSummaries sectionId={section.id} />` inside the section
  card, so each lecture is ONE block: header · lecturer notes · files · brief · detailed (both fully
  expanded, per B2 = Option 2).
- **`StudentModuleDetail.tsx`** — dropped the "View summaries →" `Link` + the summary-state badge + the
  now-unused `studentSummaries.listSections` fetch (the inline block's own §4.3 state is the only signal now).
- **section route** `.../sections/[sectionId]/page.tsx` — now `redirect('/student/modules/${moduleId}')`
  (O1). Target derived ONLY from the URL params (no section lookup) → reveals nothing about existence /
  publish / access. `StudentSectionDetail.tsx` deleted (logic lives in `SectionSummaries`; grep confirmed no
  other importer; the API *type* `StudentSectionDetail` is untouched). Build proof: the route collapsed to a
  139 B redirect stub; `/student/modules/[moduleId]` grew to 37.4 kB (the summaries moved here).

## Security boundary preserved (developer hold #1 — confirmed by running, not asserting)
- The page redirect does NOT touch the API. The student summary endpoints remain the boundary: **4.7 G4
  (unpublished → 404), G5 (unenrolled → 404, byte-identical body), G6 (non-student → 403) all still pass**
  against the new route shape, and `4.7-stage3-content-visibility` (published-only list) stays green.
- The module page iterates the **published-only** `content.listSections` — no fetch is issued for draft
  sections, so the consolidation cannot surface an unpublished summary. `SummaryMarkdown` stays raw-HTML-off.
- Redirect derives the target from params only → an unpublished/unassigned section URL redirects to the
  module page (which shows only the student's published sections) — no existence leak.

## E2E re-point — same commit, NOT loosened (developer hold #3)
`git diff tests/` shows re-pointed/flipped assertions, never relaxed:
- **4.7 G1/G2/G7** — identical testids + `data-state`/marker assertions, only SCOPED to each section block
  (`student-section-row-{order}-{id}`) on the module page (the summary testids now appear once per section).
  G3a (no transcript text) runs on the module page; G3b/G3c (API sentinel-absence + 403s) and G4/G5/G6 untouched.
- **4.5d (lecturer gate)** — its student-side check failed because the student (enrolled) now legitimately
  sees the published summary inline. Root-caused (not flake): the 4.5d setup enrolls the student + publishes
  all sections, so per Stage 4.7 the student SHOULD see it. The old `getByText(BRIEF_MARKER) count 0` asserted
  the pre-B separate-page presentation, not a security property. **Flipped to a stronger POSITIVE two-surface
  proof:** the student reads the brief via THEIR OWN inline surface (scoped to the lab block) while the
  LECTURER surface stays unreachable (API 403 + lecturer-only `section-summary-panel-*` absent — both kept).
  Re-ran 4.5d alone → pass.
- **4.8d staging smoke** (testIgnore'd / hosted, developer-owned) — re-pointed its student check to the
  module page (`student-section-list` visible) + kept the no-transcript-text checks. Re-verify on the next
  hosted run; not exercised locally.

## Verification
- All 7 §8 frontend gates green (typecheck / lint [only the pre-existing SessionProvider warn] / test:unit 13
  / test:a11y 11 / check:design-tokens 69 files / check:inline-styles 42 files / build — `SectionSummaries`
  is now scanned, the deleted file dropped from the scan).
- **Full active Playwright suite 11/11** (9 success + invalid_output + invalid_input) on the rebuilt frontend
  image with the consolidation.
- **Mobile sanity 7/7 surfaces 0px at 375px** (the consolidated module page is longer but does not overflow);
  screenshots in `knowledge/steps/stage-04/4.9-design-review/` show the one-block layout (header · notes ·
  files · brief · detailed) on desktop + mobile.

## Findings
- **F-C3 RESOLVED** (separate summary page → inline single block). No new findings. The 4.5d cross-spec
  consequence is documented above (intended behaviour change, authz boundary preserved).
- **F-C4** ("Save notes" no UI confirmation, lecturer) — still parked, out of scope.

## Not in this workstream
- Workstream A (generation) — PARKED, gated on the developer's Task 0 step-3 real-provider run.
