# Design System v1 — XYZ LMS

> **Written from SHIPPED Stage 4.9 code** (`frontend/src/app/globals.css` + `frontend/src/components/ui/*`),
> not from the plan — code wins (sacred rule, umbrella §10). From Stage 5 onward this **replaces Design
> Plan Part 1** as the living visual authority; design-plan Part 2 (screen specs) remains the per-stage
> seed source. Stage 5 specs = roadmap + design-plan §2.x + this file (the two-input rule).
>
> **Version 1.0.0** · changelog at the bottom. A **breaking** contract change (prop/variant rename or
> removal) bumps the version + needs an ADR (ADR-047); an **additive** change appends to the changelog only.

## Tokens (two layers — `frontend/src/app/globals.css`)

**Layer 1 — raw palette** (`:root --palette-*`; private, NEVER referenced by components):
Violet ramp `violet-50…900` (primary = `violet-600 #7c3aed`), Zinc neutrals `white` + `zinc-50…900`,
status raws (green/amber/rose/indigo: solid-600 + tint-50 + text-700). Plus `--z-*` layering + `--motion-*`.

**Layer 2 — semantic roles** (`@theme`; the ONLY colours components use → Tailwind utilities). The default
Tailwind colour namespace is **disabled** (`--color-*: initial`), so a non-semantic colour (`bg-blue-500`)
**produces no CSS** — build-enforced (proven 4.9a + the `check:design-tokens` gate):

| Token → utility | Maps to | Notes |
|---|---|---|
| `--color-surface` / `-muted` / `-raised` | white / zinc-50 / white | page / inset / elevated |
| `--color-border` | zinc-200 | decorative hairlines (1.4.11-exempt) |
| `--color-border-strong` | zinc-500 | **functional control boundaries** (input/select) — 4.83:1, meets 3:1 |
| `--color-text` / `-muted` | zinc-900 / zinc-500 | primary / secondary text |
| `--color-primary` / `-hover` / `--color-on-primary` | violet-600 / violet-700 / white | actions, active nav, the pipeline |
| `--color-{success,warning,danger,info}` (+ `--color-on-*`) | green/amber/rose/indigo-600/500 + white | **solid fills: large/bold/UI text ONLY** (see below) |
| `--color-{success,warning,danger,info}-surface` / `-text` | tint-50 / text-700 | **tonal pairs — the body-text-safe status treatment (Badge default)** |
| `--color-danger-hover` | rose-700 | destructive button hover |
| `--color-overlay` | `rgb(24 24 27 / 0.55)` | modal scrim (composited → dialog reads ≥3:1 over the dimmed page) |
| `--color-focus-ring` | violet-500 | 2px ring + 2px offset on every interactive element |

Non-colour: type scale (`--text-xs…4xl` w/ line-heights), `--radius-sm/md/lg`, `--shadow-sm/md/lg`,
v4 default spacing multiplier, `.z-base/dropdown/assistant/modal/toast` (read `--z-*`), reduced-motion guard.

**⚠ Solid status fills are LARGE/BOLD/UI-ONLY (the AA line — do not put solid-success/warning/info on body text).**
Validated (`scripts/check-contrast.mjs`): white-on-solid is **success 3.30:1, warning 3.19:1, info 4.47:1**
— fine for badge labels / button text (≥3:1 large/UI), **below 4.5:1 for body**. For **body** status text use the
**tonal** pair (`-text` on `-surface`, ≥4.6:1) — which is the Badge default. white-on-danger (4.70:1) +
white-on-primary (5.70:1) clear body too. (Stage 6: solid-warning on 14px body text would silently fail AA — use the tonal pair.)

## Typography (`frontend/src/app/layout.tsx`, `next/font/local`)
Two self-hosted families, **no external request** (committed `.woff2`): **Space Grotesk** (`--font-display`)
for headings/wordmark/pipeline labels; **Inter** (`--font-sans`) for body AND utility/UI. No monospace this
stage (additive later if dense-data views need it).

## Components (`frontend/src/components/ui/` — real contracts as built; frozen post-4.9 per ADR-047)
| Component | Client? | Key props | Variants / states | a11y |
|---|---|---|---|---|
| `Button` | yes | `variant` (primary/secondary/ghost/destructive), `size` (sm/md/lg), `isLoading`, `leftIcon`, …button attrs | hover/active/focus-visible/disabled/loading | real `<button>`; `aria-busy` when loading; focus ring |
| `Input` | yes | `id`, `label`, `as` (input/textarea/select), `type`, `error`, `description`, value/onChange/… | default/focus/error/disabled/read-only | label assoc; error via `aria-describedby`+`role=alert`+icon (not colour-only); `border-strong` boundary |
| `Card` / `InteractiveCard` | no / yes | `className` / `href`\|`onClick` | static / interactive | interactive = real `<a>`/`<button>` with focus |
| `Badge` | no | `tone` (neutral/info/success/warning/danger) | static | status by TEXT label (tonal tokens), never colour alone |
| `Modal` | yes | `isOpen`, `onOpenChange`, `title`, `footer`, `variant` (default/confirm) | open/closing | React Aria: focus trap, Esc, focus-return, `role=dialog`/`alertdialog` + labelled |
| `Table` + `SortableHeader` | no / yes | `caption` / `label`,`direction`,`onSort`; `tableRowEmphasis` | empty/loaded; sortable | semantic `<table>`; sort headers are `<button>`; emphasis = border+tint |
| `ToastProvider` + `useToast` | yes | `show(tone, message)` (info/success/error) | enter / auto-dismiss / manual | polite live region; **errors do NOT auto-dismiss**; keyboard-dismissible; via `#toast-root` |
| `EmptyState` | no | `title`, `description`, `action`, `icon`, `headingLevel` | — | heading + one action |
| `LinearProgress` / `StepProgress` | no | `value`,`label` / `steps:{label,state}`, `orientation` | per-step pending/active/completed/**failed** | **failed = explicit text + danger, never "not completed"** |
| helpers | — | `Spinner`, `Skeleton`, `VisuallyHidden`, `cn` | — | decorative / sr-only |

**One usage example:**
```tsx
import { Button, Card, Badge, useToast } from "@/components/ui"; // (path is relative in-repo)
<Card className="grid gap-2">
  <Badge tone="success">Summaries ready</Badge>
  <Button variant="primary" isLoading={saving} onClick={save}>Save</Button>
</Card>
```

## The signature element — the processing pipeline (`StepProgress`)
A step track (parse→chunk→embed→summarize; reused by Stage 5 quiz progress + Stage 11 risk rows). Per-step
**pending / active (animated, reduced-motion-safe) / completed / FAILED**; the failed node is danger-coloured
**with explicit "Failed" text** (status by text, never colour alone). This is the one place boldness is spent.

## Async / loading / error conventions (§4.3 — Stage 5+ MUST reuse)
- **Pending/processing:** passive "generating…/processing…", NO hard timeout (backoff polling; 4.5d).
- **Loading:** `Skeleton` for content regions; inline `Spinner` (Button `isLoading`) for button actions.
- **Error:** transient/action → `Toast`; field → inline on `Input`; failed region load → `EmptyState` + retry;
  route crash → `error.tsx` (built on `EmptyState`). Errors explain what + how to fix; never a raw stack trace.

## Accessibility baseline
WCAG **AA**. Visible focus ring everywhere (`--color-focus-ring`). Contrast validated at the token level
(`scripts/check-contrast.mjs`) — all semantic pairs pass (solid status = large/UI-only, above). Status by text
label. Reduced-motion guard. Skip-to-content link + landmarks in the shell. Static-a11y smoke (`test:a11y`) +
the manual keyboard checklist; full automated keyboard + axe = Stage 12 (ADR-048).

## Mobile conventions
Breakpoints: Tailwind defaults (sm 640 · md 768 · lg 1024 · xl 1280). Mobile-first: the student learning
surfaces (module list, section detail, summaries) + Stage 5 quiz / Stage 7 glossary / Stage 8 assistant.
Desktop-first: admin + lecturer authoring. 4.9 sanity target: 375px, no horizontal scroll.

## App Router conventions
Interactive leaves are `"use client"` (Button/Input/Modal/Toast/InteractiveCard/SortableHeader); presentational
stay server components (Badge/EmptyState/linear-Progress/static-Card/helpers). **Literal class strings only** in
variant maps (`variants.ts`) — never `` `bg-${v}` `` (purged in `next build`). Tailwind v4 via `@tailwindcss/postcss`.

## Dependencies added this stage (runtime)
`react-aria-components` (headless Modal behaviour, styled through our tokens), `lucide-react` (single
tree-shakeable icon source, per-icon imports), `clsx` + `tailwind-merge` (the `cn` helper). Modal uses React
Aria; **Toast is owned** (RAC Toast was UNSTABLE_; ADR-046 amendment). Dev: tailwindcss v4 + @tailwindcss/postcss,
vitest + @testing-library/react, eslint-config-next, husky. (axe/user-event reserved for Stage 12 — ADR-048.)

## How to add a component
New visuals come from the **semantic tokens** only. If a component needs a colour/role the semantic set lacks,
that is a **finding** (the plan/system is missing a role — add it to globals.css, like `--color-overlay`/
`--color-danger-hover` were), never a raw hex or a reach into `--palette-*`. Mark interactive leaves `"use client"`;
keep variant→class maps literal; add a co-located `*.a11y.test.tsx` smoke. Breaking changes need an ADR (ADR-047).

## Changelog
- **1.0.0** (2026-06-13, Stage 4.9) — initial system from shipped 4.9a–e code: two-layer tokens, 9 public
  components + helpers, the processing-pipeline signature, §4.3 conventions, AA baseline. `--color-overlay`
  deepened to 55% (4.9e contrast re-validation). Solid-status = large/UI-only rule recorded.
