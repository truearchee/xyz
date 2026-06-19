---
type: adr
stage: "4.9"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.9a-tokens-tailwind-shell.md
---

# ADR-045 — Two-layer token architecture; default color namespace disabled (build-enforced)

> Stage 4.9 umbrella §4.1 (token contract). Recorded with the 4.9a code.

## Linked documents
- Spec: [[specs/stage-04/4.9a-tokens-tailwind-shell]] · Umbrella: [[specs/stage-04/4.9-frontend-foundation-platform-hygiene]]
- Design plan: [[design-plan]] (Part 1.2 validated palette + AA table)
- Related: [[adr-044-tailwind-v4-app-router-setup]] (the v4 `@theme` mechanism this rides on)

## Context
Stage 5+ builds three stages of reused UI. If components reach for arbitrary colors, a future theme
(or dark mode) becomes a rewrite of every component. The umbrella §4.1 locks a two-layer token model
and asks that "components use only semantic tokens" be **enforced**, not merely documented — the same
philosophy as the backend's CHECK constraints / grep gates.

## Decision
- **Two layers, in CSS (`frontend/src/app/globals.css`):**
  - **Layer 1 — raw palette:** literal values as `:root` `--palette-*` custom properties (violet ramp,
    zinc ramp, status raws, plus `--z-*` layering and `--motion-*`). Components NEVER reference these.
  - **Layer 2 — semantic roles:** `@theme` variables that reference Layer 1 and carry meaning
    (`--color-surface/-muted/-raised`, `--color-border`, `--color-border-strong`, `--color-text/-muted`,
    `--color-primary`/`-hover`/`--color-on-primary`, `--color-{success,warning,danger,info}` + `-on-`
    pairs + tonal `-surface`/`-text`, `--color-focus-ring`). In Tailwind v4 these ARE the utilities.
- **Disable the default color namespace** with `--color-*: initial` inside `@theme`. Only the semantic
  colors above resolve as utilities; `bg-blue-500`/`text-gray-700`/etc. **produce no CSS** — verified in
  4.9a by a controlled build (a probe referencing `bg-blue-500` emitted 0 rules while `bg-primary`
  emitted its rule). "Components use semantic tokens" is now compile-impossible-to-violate.
- **Only the color namespace is reset** — NOT the global `--*: initial`. Spacing/font/radius/shadow
  scales survive. **Spacing keeps Tailwind v4's default multiplier** (so the 4.9c inline-style removal
  maps cleanly: `gap: 8 → gap-2`, `padding: 16 → p-4`, no per-value arithmetic). 4.9c does not relitigate this.
- **Layering is tokenized:** `--z-base < --z-dropdown < --z-assistant < --z-modal < --z-toast` live once
  in `:root`; the `.z-*` utilities read `var(--z-*)` (no magic numbers at the call site) so portal
  stacking is deterministic (toast over modal over the reserved assistant anchor).
- **Tonal vs solid status (from the validated AA table, design-plan 1.2):** solid `--color-{success,
  warning,info}` fills carry only large/bold/UI text (white-on-fill is 3.19–4.47:1); **body** status text
  uses the tonal `-text`-on-`-surface` pair (≥4.6:1) — the Badge default. `--color-border-strong`
  (zinc-500, 4.83:1) exists for functional control boundaries; `--color-border` (zinc-200) is decorative
  (WCAG 1.4.11-exempt).

## Consequences
- A component needing a color the semantic set lacks is a **finding** (add the role), never a reach into
  Layer 1 — the namespace reset makes the wrong path impossible to compile.
- Theming-ready: a future dark theme is a swap of the Layer-2→Layer-1 mapping, not a component rewrite.
  Dark mode stays out of MVP scope (umbrella §3); no second theme is built.
- 4.9d's `check:design-tokens` gate is the complement: it catches raw hex / arbitrary `bg-[#…]` values
  that the namespace reset alone does not stop.
- Token-level WCAG AA was validated against the SHIPPED `globals.css` hexes (4.9a), not just the plan —
  all 15 pairs PASS.
