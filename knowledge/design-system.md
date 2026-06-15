# Design System v2 — XYZ LMS

> **⚠ TARGET STATE — not yet shipped.** Stage 4.9 code currently ships the v1 **violet** system. This document
> describes the **monochrome Apple×Linear** target locked in design-plan v2. The repaint session
> ([[specs/stage-04/4.9f-monochrome-restyle]]) makes `frontend/src/app/globals.css` + `frontend/src/components/ui/*`
> match this file; **until that PR lands, code wins (sacred rule)** and the violet values are live truth. When
> 4.9f ships, this banner is removed and the file is reconciled against shipped CSS.
>
> From Stage 5 this is the living authority for tokens/components; design-plan §2.x screen specs are the
> per-stage seed. **Version 2.0.0** · changelog at bottom. Breaking contract change → version bump + ADR;
> additive → changelog only.

## 1. Visual theme & atmosphere
Calm, premium, monochrome — "if Apple built an LMS," with Linear's working-tool discipline on dense surfaces.
Type and whitespace carry the design; colour is almost absent. The accent is graphite/near-black on actions; the
only colour is functional status. Depth is surface-tone + hairline (soft shadow only on overlays), never
gradients. Boldness is spent in one place — the pipeline. Reading surfaces breathe (Apple air); authoring/admin
stay dense (Linear).

## 2. Tokens (two layers — `frontend/src/app/globals.css`)
**Layer 1** (`--palette-*`, private): warm-gray ramp `gray-50…800` + `white`/`black` (ink = `#1d1d1f`, never
pure black for text); functional status raws (green/amber/red: solid-600 + tint-50 + text-700). Plus `--z-*`,
`--motion-*`. **Layer 2** (`@theme`, the only colours components use): default Tailwind colour namespace disabled
→ non-semantic colour produces no CSS (`check:design-tokens` gate).

| Token → utility | Maps to | Notes |
|---|---|---|
| `--color-surface` | white | cards / raised content |
| `--color-surface-muted` | gray-100 | the PAGE background (parchment) — the tone step is the divider |
| `--color-surface-raised` | white | overlay surfaces (modal/popover) — these carry a soft shadow |
| `--color-border` / `-strong` | gray-200 / gray-500 | hairline (1.4.11-exempt) / functional control boundary (≥3:1) |
| `--color-text` / `-muted` / `-subtle` | gray-800 / gray-500 / gray-400 | primary / secondary / hint (subtle = large·UI only) |
| `--color-primary` / `-hover` / `--color-on-primary` | gray-800 / black / white | actions, active nav, pipeline (graphite) |
| `--color-info` | gray-800 | NEUTRAL graphite — never a 4th hue |
| `--color-{success,warning,danger}` (+ `-on-*` → white) | green/amber/red-600 + white | solid fills: large/bold/UI ONLY |
| `--color-{success,warning,danger}-surface` / `-text` | tint-50 / text-700 | tonal pairs — body-safe status (Badge default) |
| `--color-focus-ring` | gray-800 | 2px ring + 2px offset on every interactive element |

Non-colour: type scale (`--text-*` w/ line-heights + tracking), `--radius-sm/md/lg/xl` (8/12/16/20) + pill,
`--shadow-md/lg` (overlays only; soft, diffuse, low-opacity), 4px spacing unit, `.z-*`, reduced-motion guard.

**No brand hue** — every affordance is graphite. **Solid status fills are large/bold/UI-only**; body status text
uses the tonal `-text`-on-`-surface` pair. Contrast validated in 4.9f (`scripts/check-contrast.mjs`; AA: 4.5:1
body, 3:1 large/UI).

## 3. Typography (`frontend/src/app/layout.tsx`)
**One family — system stack**, no web-font request: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
Roboto, Helvetica, Arial, sans-serif`. Headings, body, UI all use it. Weights **400 / 500 / 600** (no 700 except
optional largest display). Scale (px / line-height / tracking):
```
display 36/1.10/-0.02em(600) · h2 28/1.20/-0.02em(600) · h3 22/1.30/-0.01em(600) · h4 18/1.40/-0.01em(600)
reading 19/1.65/-0.005em(400, long-form/summaries) · body 17/1.50/-0.01em(400, default — Apple cadence)
small 14/1.50(400) · micro 12/1.40(400) · button 14/1.20(500) · eyebrow 13/1.30/+0.04em(500)
```
Negative tracking on display/headings; +0.04em on eyebrow (taxonomy). Body is 17px, not 16px — the Apple
reading move. Long-form summaries use 19/1.65.

## 4. Components (`frontend/src/components/ui/` — contracts unchanged; only styling is remapped in 4.9f)
Component **API does not change** in the repaint — token values + button shape do.

| Component | Client? | Key props | Variants / states | a11y |
|---|---|---|---|---|
| `Button` | yes | `variant` (primary/secondary/ghost/destructive), `size` (sm/md/lg), `isLoading`, `leftIcon` | **pill-shaped**; hover/active(`scale .96`)/focus-visible/disabled/loading | real `<button>`; `aria-busy` loading; graphite focus ring |
| `Input` | yes | `id`, `label`, `as` (input/textarea/select), `type`, `error`, `description` | rounded-rect (md); default/focus/error/disabled/read-only | label assoc; error via `aria-describedby`+`role=alert`+icon (not colour-only); `border-strong` boundary |
| `Card` / `InteractiveCard` | no / yes | `className` / `href`\|`onClick` | white on parchment (tone-step, NO resting shadow); interactive lifts subtly | interactive = real `<a>`/`<button>` w/ focus |
| `Badge` | no | `tone` (neutral/success/warning/danger) | pill, static | status by TEXT label (tonal tokens), never colour alone; `info`→neutral |
| `Modal` | yes | `isOpen`, `onOpenChange`, `title`, `footer`, `variant` | open/closing | React Aria: focus trap, Esc, focus-return, `role=dialog`/`alertdialog`; **shadow-lg** |
| `Table` + `SortableHeader` | no / yes | `caption` / `label`,`direction`,`onSort`; `tableRowEmphasis` | empty/loaded; sortable | semantic `<table>`; hairline rows; sort headers `<button>` |
| `ToastProvider` + `useToast` | yes | `show(tone, message)` | enter / auto-dismiss / manual; **shadow-md** | polite live region; **errors do NOT auto-dismiss** |
| `EmptyState` | no | `title`, `description`, `action`, `icon`, `headingLevel` | — | heading + one action |
| `LinearProgress` / `StepProgress` | no | `value`,`label` / `steps:{label,state}`, `orientation` | pending/active/completed/**failed** | **failed = explicit text + danger, never "not completed"** |
| helpers | — | `Spinner`, `Skeleton`, `VisuallyHidden`, `cn` | — | decorative / sr-only |

## 5. The signature element — the processing pipeline (`StepProgress`)
parse→chunk→embed→summarize; reused by Stage 5 quiz + Stage 11 risk rows. pending = hollow gray · active =
graphite-filled + subtle reduced-motion-safe animation · completed = graphite-filled + check · **FAILED =
danger-red node + explicit "Failed" text** (the one place red appears). The one place boldness is spent.

## 6. Layout, depth & motion
- **Spacing:** 4px base; card interior `lg` (24px); section rhythm `section` (80px).
- **Depth:** surface-tone step (parchment page ↔ white cards) + hairline `--color-border` for dense rows/dividers.
  **Soft shadow ONLY on overlays** — `shadow-md` popovers/dropdowns/toasts, `shadow-lg` modals. No shadow on
  resting cards/buttons/text. **No gradients.** (Backdrop-blur on sticky bars is an allowed Apple nicety, post-MVP.)
- **Radius:** sm 8 (chips) · md 12 (inputs) · lg 16 (cards) · xl 20 (modals) · **pill (all buttons, toggles,
  status pills)**. Icon-only buttons are circular.
- **Motion:** fast150 / base200 / slow300 ms, `cubic-bezier(.4,0,.2,1)`; press `scale(.96)`; `prefers-reduced-motion`
  removes shimmer + transitions.

## 7. Async / loading / error conventions (Stage 5+ MUST reuse)
Pending/processing → passive "generating…/processing…", NO hard timeout (backoff polling; 4.5d). Loading →
`Skeleton` for regions, inline `Spinner` (Button `isLoading`) for actions. Error → transient/action `Toast`;
field inline on `Input`; failed region `EmptyState` + retry; route crash `error.tsx`. Errors explain what + how
to fix; never a raw stack trace.

## 8. Do's & don'ts (from Apple/Linear, adapted to monochrome)
**Do** — graphite for every affordance and nothing else; pill-shape every button; negative tracking on display;
run body at 17px and reading surfaces at 19px; separate cards by the parchment→white tone step + hairline;
reserve shadow for overlays and the only red for the pipeline's failed state + danger actions; `scale(.96)`
press; status by text label always. **Don't** — introduce a brand hue or 2nd accent; put a shadow on a resting
card/button; use solid status fills on body text (use the tonal pair); add gradients; use `#000000` for text
(use `#1d1d1f`); rely on colour alone for any state; weight body at 500 (body 400, labels/buttons 500, headings 600).

## 9. Accessibility · mobile · App Router
WCAG **AA**. Graphite focus ring everywhere; contrast validated at token level (4.9f). Status by text label.
Reduced-motion guard. Skip-to-content + landmarks. Mobile-first: student learning + Stage 5 quiz / 7 glossary /
8 assistant; desktop-first: admin + lecturer authoring; 375px sanity, no horizontal scroll. Interactive leaves
`"use client"`; presentational = server components; literal class strings only in variant maps (never
`` `bg-${v}` ``); Tailwind v4 via `@tailwindcss/postcss`.

## 10. How to add a component
New visuals come from **semantic tokens** only. A missing colour/role is a **finding** (add it to globals.css),
never a raw hex or a reach into `--palette-*`. Mark interactive leaves `"use client"`; keep variant→class maps
literal; add a co-located `*.a11y.test.tsx` smoke. Breaking changes need an ADR.

## Changelog
- **2.0.0** (2026-06-15, TARGET) — full monochrome redesign superseding v1 violet: warm-gray two-layer tokens,
  graphite accent (no brand hue), functional status colour only, single system-font family (17px body),
  surface-tone + hairline depth with shadow on overlays only, **pill-shaped buttons**, medium card radii.
  Component contracts unchanged. Ships when [[specs/stage-04/4.9f-monochrome-restyle]] lands; banner removed +
  reconciled against shipped CSS then.