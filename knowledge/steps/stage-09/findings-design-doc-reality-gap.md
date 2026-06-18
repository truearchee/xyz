---
type: finding
stage: 09
session: "9"
slug: design-doc-reality-gap
status: accepted
created: 2026-06-18
updated: 2026-06-18
---

# Finding — Design Docs vs. Current Frontend Reality

## Summary
`knowledge/design-system.md` describes a shipped Stage 4.9 monochrome Tailwind system with `frontend/src/app/globals.css`, `frontend/src/components/ui/*`, token checks, and Vitest/a11y tests. This checkout does not contain those files or dependencies.

Verified local reality before Stage 9 implementation:
- No `frontend/src/app/globals.css`.
- No `frontend/src/components/ui/` directory.
- No Tailwind dependency or `check:design-tokens` / `check:inline-styles` scripts in `frontend/package.json`.
- Existing Stage 5-7 UI continues to use local inline `React.CSSProperties`.
- A remote branch `origin/stage/4.9f` contains the claimed UI system, but it has not landed in `origin/main`.

## Decision
Stage 9 implements the My Progress dashboard in the existing inline-style frontend idiom and uses Design Plan §2.7 as layout guidance only. It does not import the 4.9f component system or start the Tailwind repaint.

## Rationale
The sacred rule says code wins when docs and implementation disagree. Importing the 4.9f design system inside Stage 9 would broaden scope, increase merge risk, and create a partial repaint that conflicts with the deferred frontend-foundation work.

## Follow-up
When Stage 4.9/4.9f lands, the Stage 9 dashboard should be included in the shared repaint/design-token sweep.

## Linked documents
- Spec: [[specs/stage-09/9-my-progress-dashboard]]
- Plan: [[plans/stage-09/9-my-progress-dashboard]]
- Design system: [[design-system]]
- Design plan: [[design-plan]]
