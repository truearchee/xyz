---
type: adr
stage: "4.9"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.9d-vitest-gates.md
---

# ADR-048 — Component a11y verification: required static smoke now, manual keyboard now, automated axe+keyboard at Stage 12

> Stage 4.9 umbrella §6.4 + §11. Recorded with the 4.9d code.

## Linked documents
- Spec: [[specs/stage-04/4.9d-vitest-gates]] · Umbrella: [[specs/stage-04/4.9-frontend-foundation-platform-hygiene]]
- Keyboard checklist: [[steps/stage-04/4.9-keyboard-checklist]] · Related: [[decisions/adr-046-component-primitive-strategy]]

## Context
The §4.2 component contract is mostly prose without executable a11y checks. But a full automated
keyboard + axe audit is heavy and brittle while the design is young (umbrella §3 excludes it; it is the
Stage 12 job). We need a proportionate baseline now that catches contract regressions, without
prematurely building the Stage 12 audit.

## Decision
- **Required static-a11y RTL smoke NOW (§6.4).** Co-located `*.a11y.test.tsx` per component, run as the
  blocking `test:a11y` gate (vitest + jsdom + RTL, structural assertions via native `expect`): real
  `<button>` + `aria-busy`; Input label association + `aria-describedby`; Badge text label; Modal
  `role=dialog` + labelled + initial focus target; Table semantic + button sort headers; Toast live
  region + error-no-auto-dismiss; Progress failed = explicit text. (11 assertions, all green.)
- **Dynamic keyboard behaviour on a MANUAL checklist NOW.** Focus trap / Esc / focus-return / skip-link /
  tab order / reduced-motion → `4.9-keyboard-checklist.md`, with the implementation basis recorded; the
  human keypress pass is owned by the developer (interactive keyboard can't be driven headlessly, and
  automated keyboard tests are Stage 12).
- **Full AUTOMATED keyboard + axe audit → Stage 12.** Not built in 4.9.

## Reserved test dependencies (hold from the developer — explicit, not silent dead devDeps)
Installed in 4.9b, deliberately NOT wired into the 4.9 harness; **reserved for Stage 12**, NOT dead:
- `vitest-axe` + `axe-core` — the automated **axe** scan (this ADR defers axe to Stage 12).
- `@testing-library/user-event` — dynamic interaction/keyboard simulation (the automated keyboard pass = Stage 12).
- `@testing-library/jest-dom` — available for richer matchers; the 4.9d/§6.4 tests use **native vitest
  `expect`** (zero matcher-augmentation risk under `tsc`), so jest-dom is opt-in, not required.
Stage 12 wires these into the automated keyboard + axe audit. Until then they are documented here so they
do not rot into silent dead deps.

## Consequences
- `test:a11y` is a fast, blocking gate from 4.9d; the manual keyboard checklist is the human complement.
- Stage 12's audit has its tools pre-installed + a documented home; the 4.9 baseline is proportionate.
