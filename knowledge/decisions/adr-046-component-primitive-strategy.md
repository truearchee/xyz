---
type: adr
stage: "4.9"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.9a-tokens-tailwind-shell.md
---

# ADR-046 — Component primitive strategy: React Aria (headless) + lucide-react (icons)

> Stage 4.9 umbrella §4.2 ("primitive strategy — build vs wrap") + §4.4 (dependency policy). Decided in
> 4.9a (deps installed here); CONSUMED in 4.9b when the components are built.

## Linked documents
- Spec: [[specs/stage-04/4.9a-tokens-tailwind-shell]] · Umbrella: [[specs/stage-04/4.9-frontend-foundation-platform-hygiene]]
- Related: [[adr-045-token-architecture-two-layer]] (primitives are styled ONLY through these tokens), [[adr-047-component-api-contract-stability]] (the contracts built on top — authored in 4.9b)

## Context
Modal and Toast are not harmless: focus trapping, portal stacking, `Esc`, focus restoration, polite
live regions, reduced motion. Owning that from scratch is rarely where a product team adds value
(umbrella §4.2). The constraint that keeps a library compatible with our token system (§4.4):
**headless = behavior only, no styles → fine; a STYLED kit (MUI/Chakra/AntD) brings its own styling and
bypasses our tokens → NOT allowed.** Hard requirements: React 19.1.0 compatibility + truly unstyled.

## Decision
- **Headless primitive: `react-aria-components`** (installed 4.9a, `^1.18.0`, resolves clean against
  React 19.1.0 — no peer override / `--force`). Rationale vs the alternatives:
  - **React Aria Components** — unstyled by design (we bring 100% of classes via tokens); best-in-class
    focus management/trap/restore, `Esc`, and a first-class **toast region + announcer** (polite live
    region) which the §4.2 Toast contract needs. Officially React-19 compatible. Its focus utilities
    cover focus-trap, so the planned internal `focusTrap.ts` helper is **not needed**.
  - *Radix UI* — also unstyled & capable, but no first-class toast-with-live-region and historically
    laggier on React majors. Viable fallback if a React Aria API proves heavy.
  - *Headless UI* — smaller primitive set, **no Toast**; insufficient. *Ariakit* — capable but a smaller
    ecosystem / less battle-tested live-region story. Not the safe foundation.
- **Icon source: `lucide-react`** (installed 4.9a, `^1.18.0`). ONE icon source, imported **per icon**
  (`import { Check } from "lucide-react"`) so it stays tree-shakeable — no full-pack barrel import
  (§4.4). MIT, React-19 compatible, consistent stroke style suited to LMS chrome.
- **Styling rule:** every primitive is styled exclusively through the ADR-045 semantic tokens (literal
  class strings, §4.2 purge footgun). No styled component kit enters the tree.

## Consequences
- New runtime deps recorded (§4.4): `react-aria-components` (headless Modal/Toast/Dialog/focus for 4.9b),
  `lucide-react` (single tree-shakeable icon source). Build-output growth reviewed after 4.9b/4.9e.
- 4.9b builds Modal + Toast on React Aria (focus trap / `Esc` / focus-return / live region for free,
  styled through tokens) and refactors the 4.9a error/404/403 surfaces onto the Empty State component.
- If a React Aria primitive cannot be styled cleanly through our tokens or fights React 19 at build,
  that is a **finding** → fall back to Radix for that primitive (recorded as an amendment), never a
  styled kit.
- Pre-existing `next@15.3.3` advisory (CVE) surfaced by `npm audit` is **not** introduced by these deps;
  a Next upgrade is out of 4.9a scope (tracked separately).
