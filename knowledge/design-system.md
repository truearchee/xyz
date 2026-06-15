# Design System v2 — XYZ LMS

> **SHIPPED 2026-06-15** — session [[specs/stage-04/4.9f-monochrome-restyle]] repainted the frontend from v1
> violet to this **monochrome Apple×Linear** system. The values below are **reconciled against the shipped
> `frontend/src/app/globals.css` + `frontend/src/components/ui/*`** (sacred rule — code wins). Contrast validated
> 17/17 (`frontend/scripts/check-contrast.mjs`); `check:design-tokens` + `check:inline-styles` green; `vitest`
> a11y/unit green; `next build` compiles the arbitrary variants. From Stage 5 this is the living authority for
> tokens/components; design-plan §2.x screen specs are the per-stage seed. **Version 2.0.0** · changelog at
> bottom. Breaking contract change → version bump + ADR; additive → changelog only.

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
uses the tonal `-text`-on-`-surface` pair. **`info` renders identical to `neutral`** (shipped): the tonal info
pair is the neutral greys (`info-surface`=gray-100, `info-text`=gray-500) and the `info` Badge/Toast tone uses the
hairline `border-border` (not the graphite `--color-info`), so info is never a 4th hue. `--color-text-subtle`
(gray-400) is the disabled/hint role (large·UI only) and is intentionally NOT contrast-gated (WCAG-exempt).
Contrast validated 17/17 (`frontend/scripts/check-contrast.mjs`; AA: 4.5:1 body, 3:1 large/UI; tightest pair
text-muted/parchment 4.66:1; modal scrim composited 4.05:1).

## 3. Typography (`frontend/src/app/globals.css` `@theme` + `frontend/src/app/layout.tsx`)
**One family — system stack**, no web-font request: `--font-sans` = `-apple-system, BlinkMacSystemFont, "SF Pro
Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif` (and `--font-display` is **aliased to the same stack**,
so the existing `font-display` heading usages keep resolving to the one family — zero feature churn). No
`next/font`, no committed `.woff2`. Weights **400 / 500 / 600** applied via utilities (body 400 · labels/buttons
500 `font-medium` · headings/emphasis 600 `font-semibold`); no 700.

**Shipped scale** (the design ladder is realized via Tailwind's numeric `--text-*` tokens — components consume
those, not named tokens — each with `--text-{n}--line-height` + `--text-{n}--letter-spacing`):
```
xs micro 12 /1.4    · sm small 14 /1.5  · base BODY 17 /1.5/-0.01em (Apple cadence) · lg READING 19 /1.5/-0.005em
xl h3 22 /1.3/-0.01em · 2xl h2 28 /1.2/-0.02em · 3xl 32 /1.15/-0.02em · 4xl display 36 /1.1/-0.02em
```
Body is 17px (not 16). **Long-form reading is 19px**: `--text-lg`=19 also serves subheads, and the **19/1.65
long-form line-height** is applied specifically on the student summary surface (`SummaryMarkdown` =
`text-lg leading-[1.65]`) rather than loosening the generic `text-lg` (so headings reusing `text-lg` keep tight
leading). Eyebrows/overlines render as `text-xs uppercase` (`font-medium` on `text-text`-headings, muted on
subtle taxonomy) — not a separate token. Negative tracking on body + headings.

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
- **2.0.0** (2026-06-15, **SHIPPED** — [[specs/stage-04/4.9f-monochrome-restyle]]) — full monochrome redesign
  superseding v1 violet: warm-gray two-layer tokens, graphite accent (no brand hue), functional status colour
  only (`info` neutral), single system-font family (17px body / 19px reading), surface-tone + hairline depth with
  shadow on overlays only (resting-card `shadow-sm` removed), **pill-shaped buttons** + `scale(.96)` press,
  radii 8/12/16/20. Component contracts unchanged. Banner removed + this file reconciled against the shipped
  `globals.css` + `components/ui/*` (code wins). Verified: contrast 17/17, `check:design-tokens` /
  `check:inline-styles` green, tsc clean, vitest 13+11, `next build` ✓; UI E2E (routing/admin/content-visibility)
  + 375px mobile sanity green; visual screenshots recaptured.