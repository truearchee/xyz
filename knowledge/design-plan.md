# Design Plan v2 — XYZ LMS

> Companion to `knowledge/roadmap.md` — the visual reference it names as its second input document.
> **Product/brand authority:** locked in a design-direction session (2026-06-15); supersedes Design Plan v1
> (violet). An engineer may not invent or override it.
>
> **Supersession:** v1 = Violet / AI-forward. v2 = **monochrome Apple×Linear** (below) — **SHIPPED 2026-06-15**
> by the repaint ([[specs/stage-04/4.9f-monochrome-restyle]]). The frontend now renders this system end-to-end;
> `design-system.md` is reconciled against the shipped CSS (TARGET banner removed — code wins).
>
> **Hand-off:** from Stage 5, `design-system.md` (written from SHIPPED code) is the living authority for
> tokens/components; this plan's Part 2 (screen specs) is the per-stage seed. Stage 5 specs = roadmap +
> design-plan §2.x + design-system.md.

---

## Part 0 — Identity intent
XYZ is an AI-assisted learning platform; the recurring experience is long-form AI content and visible async
processing. Identity:
- **Calm and premium** — "if Apple built an LMS." Type and whitespace carry the design; colour is almost absent.
- **Readable first** — long-form content effortless on phone or laptop (Apple reading cadence, 17px body).
- **Status-honest** — real, minutes-long, sometimes-failing work shown truthfully, never a frozen spinner or fake success.
- **A working tool, not a billboard** — authoring/admin stays dense and efficient (Linear); reading surfaces breathe (Apple).

Locked direction: **Monochrome (white/parchment canvas · near-black ink #1d1d1f · graphite as the only accent)
· one system font (San Francisco / `-apple-system`) · functional status colour ONLY (green/amber/red) ·
elevation by surface-tone step + hairline, soft shadow reserved for overlays · pill-shaped actions · the
processing pipeline as the signature element.**

---

## Part 1 — Visual system

### 1.1 Brand mood
Quiet, focused, premium. No brand hue — the "accent" is graphite/near-black on actions. Colour appears only as
functional status. Sections and cards separate by **surface-tone change** (white ↔ parchment) and hairlines —
the Apple way — not by shadows or borders-everywhere. Boldness is spent in exactly one place: the pipeline.

### 1.2 Palette — locked monochrome identity (4.9f derives full scales + validates AA)
Two-layer model (unchanged): Layer 1 = raw values (never touched by components); Layer 2 = semantic roles (the
only thing components consume). Default Tailwind colour namespace stays disabled → a non-semantic colour
produces no CSS (`check:design-tokens` gate).

**Layer 1 — raw palette:**
```
Neutral — warm gray (near-black ink is #1d1d1f, NOT pure black — keeps the page photographic, per Apple)
  white #ffffff
  gray-50 #fafafa  gray-100 #f5f5f7  gray-200 #e8e8ed  gray-300 #d2d2d7
  gray-400 #a1a1a6 gray-500 #6e6e73  gray-600 #48484a  gray-700 #333336
  gray-800 #1d1d1f black #000000
Status raws (functional only — solid + light tint + dark text-on-tint)
  success green-600 #16a34a  green-50 #f0fdf4  green-700 #15803d
  warning amber-600 #d97706  amber-50 #fffbeb  amber-700 #b45309
  danger  red-600   #dc2626  red-50   #fef2f2  red-700   #b91c1c
```

**Layer 2 — semantic roles (components consume ONLY these):**
```
--color-surface          → white      cards / raised content (sits on the parchment page via tone-step)
--color-surface-muted    → gray-100   the PAGE background (parchment) — the tone step IS the divider
--color-surface-raised   → white      overlay surfaces (modal/popover) — these get a soft shadow
--color-border           → gray-200   hairlines / dividers (decorative, 1.4.11-exempt)
--color-border-strong    → gray-500   functional control boundaries (input/select) — target ≥3:1
--color-text             → gray-800   primary text (#1d1d1f)
--color-text-muted       → gray-500   secondary / label text (target ≥4.5:1 on white)
--color-text-subtle      → gray-400   hints / disabled (large·UI only — NOT body)
--color-primary          → gray-800   primary actions, active nav, the pipeline (graphite fill)
--color-primary-hover    → black      hover/press on primary
--color-on-primary       → white
--color-info             → gray-800   "info" is NEUTRAL graphite — never a 4th hue
--color-focus-ring       → gray-800   2px ring + 2px offset on every interactive element
--color-{success,warning,danger}          → solid (large/bold/UI text only)
--color-{success,warning,danger}-surface  → the -50 tint
--color-{success,warning,danger}-text     → the -700 (body-safe status text; Badge default)
```

**Binding rules:** no brand hue (every affordance graphite); solid status fills are large/UI-only (body status
uses the tonal `-text`-on-`-surface` pair); decorative borders use `--color-border`, functional control
boundaries `--color-border-strong` (or give inputs a faint `--color-surface-muted` fill); an unvalidated pair is
a finding (validate via `scripts/check-contrast.mjs`; AA: 4.5:1 body, 3:1 large/UI). Dark mode deferred; layer
structure stays theming-ready.

### 1.2b Non-colour tokens (anchors; 4.9f finalizes exact steps)
```
Type (px / line-height / tracking)
  display 36 /1.10/-0.02em · h2 28 /1.20/-0.02em · h3 22 /1.30/-0.01em · h4 18 /1.40/-0.01em
  reading 19 /1.65/-0.005em (summaries/long-form) · body 17 /1.50/-0.01em (default, Apple cadence)
  small 14 /1.50 · micro 12 /1.40 · button 14 /1.20 (500) · eyebrow 13 /1.30/+0.04em (500)
Weights   400 regular · 500 medium (UI labels/buttons) · 600 semibold (headings). No 700 except optional largest display.
Spacing   4px base (xxs4 xs8 sm12 md16 lg24 xl32 2xl48 section80)
Radius    sm 8 · md 12 (inputs) · lg 16 (cards) · xl 20 (modals) · pill 9999 (ALL buttons, toggles, status pills)
Elevation surface-tone step + hairline for cards/sections; shadow ONLY on overlays — shadow-md (popover/toast),
          shadow-lg (modal); soft, diffuse, low-opacity. No shadow on resting cards/buttons/text. No gradients.
Motion    fast150 base200 slow300 · cubic-bezier(.4,0,.2,1) · press scale(.96) · reduced-motion guard
```

### 1.3 Typography — one family
System stack, no web-font request: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto,
Helvetica, Arial, sans-serif`. One family for headings/body/UI. Body runs 17px (the Apple "reading, not
scanning" cadence). Negative tracking on display/headings; eyebrow uses +0.04em to mark taxonomy.

### 1.4 The signature element — the processing pipeline (`StepProgress`)
parse→chunk→embed→summarize; reused by Stage 5 quiz progress + Stage 11 risk rows. pending = hollow gray node ·
active = graphite-filled + subtle reduced-motion-safe animation · completed = graphite-filled + check ·
**failed = danger-red node + explicit "Failed" text** (the one place red appears in the track; status by text,
never colour alone). The one place boldness is spent.

### 1.5 Depth & motion character
Separation is **surface-tone + hairline** (the Apple/Linear way): the page is parchment, content cards are white,
and that tone step is the divider; hairline `--color-border` separates rows inside dense tables/lists. **Soft
shadow is reserved for true overlays only** — `shadow-md` for popovers/dropdowns/toasts, `shadow-lg` for modals —
never on resting cards, buttons, or text. No decorative gradients. Transitions smooth (200ms); press = `scale(.96)`;
`prefers-reduced-motion` removes shimmer/transitions.

---

## Part 2 — Screen specs (per-stage seed source)
Screens unchanged from v1 — only the visual language is monochrome now. Density follows the split: **reading
surfaces breathe (Apple air, mobile-first); authoring/admin stays efficient (Linear discipline, desktop-first).**

### 2.0 Login (mobile-first)
Centered white card (overlay → `shadow-lg`) on the parchment page. Wordmark in the system font, semibold, tight
tracking. Email + password Inputs, a single graphite **pill** primary Button. Errors inline on the field (not
colour-only) + a Toast for auth failure. No nav/shell.

### 2.1 Admin (desktop-first, Linear discipline)
Role-aware shell. Users/Modules as semantic Tables (sortable headers = buttons), hairline row separation, compact
controls; create/assign forms in white Cards; destructive actions via the confirm Modal. Empty states via EmptyState.

### 2.2 Lecturer content (desktop-first authoring)
Module detail: section list as Cards; transcript upload + replace controls; **the pipeline signature** for
processing status (4.5d/4.6 surface); brief/detailed summary panels as readable long-form blocks. Retry on a
failed step = Button + Toast.

### 2.3 Student view (mobile-first, Apple air)
Module list → section detail → summary reading. Summaries render as comfortable long-form (generous measure,
19px reading type, clear hierarchy, lots of whitespace). Brief/detailed selection explicit. Students never see
the raw transcript (4.7 invariant) or unpublished content. Processing/unavailable = EmptyState / passive
"processing…", never a fake value.

### 2.4 Post-class / assessment (Stage 5 seed)
Quiz attempt flow **mobile-first**, consumes Button/Card/Badge/Modal/Progress as-built; the Progress "failed"
state and Badge "status-by-label" rule reused verbatim. Full spec lands with the Stage 5 spec.

### 2.5 Glossary (Stage 7 seed)
Folder sidebar + entry table/card toggle; entry detail sheet; save-to-glossary popover from highlighted summary
text; duplicate warning; flashcard session (flip + rating). Learn/Test reuse §2.4 quiz components.

### 2.6 Assistant (Stage 8 seed — the two most complex surfaces)
Two-pane window; message bubbles (user vs assistant by surface + alignment, not hue); streaming cursor;
mode-selector pills; lecture-breakdown workspace; floating widget. Locked before 8.1 begins.

### 2.7 My Progress (Stage 9 seed)
Module card grid; trend/topic-mastery charts (monochrome, single graphite series; status hues only at pass/fail
thresholds); the grade-forecast panel (signature data moment, incl. the unsoftened "impossible" state); goals.

### 2.8 Gamification (Stage 10 seed)
Streak row; badge grid (locked/unlocked/in-progress by state + label, not colour alone); the one budgeted unlock
animation; next-achievement callout. Additive to §2.7.

### 2.9 Analytics (Stage 11 seed)
Roster table with risk-row treatment (left border + tint + text, never colour alone); student detail sheet;
draft-message modal; assessment-analysis charts; workload planner calendar.

---

## Part 3 — Stage 12 consistency sweep (deferred backlog)
Surfaces 4.9 leaves inline-styled are tracked in `knowledge/steps/stage-04/4.9-restyle-inventory.md` and rolled
up here for the Stage 12 consistency sweep + heavy a11y/mobile audit + visual-regression snapshots.

## Part 4 — Accessibility baseline
**WCAG AA.** Graphite focus ring on every interactive element (2px + 2px offset). Contrast validated at token
level in 4.9f. Status by text label. Reduced-motion guard. Modal focus-trap + Esc + focus-return; skip-to-content;
landmarks; form label association; error toasts don't auto-dismiss. Automated keyboard + axe = Stage 12.

## Part 5 — Mobile strategy
MOBILE-FIRST: student learning (2.3), Stage 5 quiz, Stage 7 glossary, Stage 8 assistant. DESKTOP-FIRST: admin
(2.1), lecturer authoring (2.2). Breakpoints: Tailwind defaults (sm640 md768 lg1024 xl1280). 4.9 sanity: 375px,
no horizontal scroll on mobile-first surfaces.

## Part 6 — Decisions log
```
2026-06-12  v1 LOCKED: Violet / AI-forward, Space Grotesk + Inter. (SUPERSEDED.)
2026-06-15  v2 LOCKED (product owner) — supersedes v1:
            - Palette MONOCHROME: white/parchment canvas, near-black ink #1d1d1f, graphite as the only accent.
              No brand hue. Functional status colour only (green/amber/red); "info" is neutral graphite.
              Reference languages: Apple (air, 17px reading cadence) × Linear (working-tool density).
            - Typeface: ONE system family (San Francisco / -apple-system), no web font.
            - Actions: PILL-shaped (Apple's action signal). Inputs/cards/modals stay rounded-rect (12/16/20).
            - Elevation: surface-tone step (parchment page ↔ white cards) + hairline; soft shadow ONLY on
              overlays (modals/popovers/toasts), never on resting cards — per Apple's "one-shadow" philosophy.
            - Signature pipeline + AA target + mobile-first split: carried from v1.
            - SHIPPED by the repaint ([[specs/stage-04/4.9f-monochrome-restyle]], 2026-06-15): frontend is
              monochrome end-to-end; design-system.md reconciled against shipped CSS (TARGET banner removed).
```

---
## Linked documents
- Roadmap: [[roadmap]]
- Design system (supersedes Part 1 from Stage 5): [[design-system]]
- Monochrome restyle spec: [[specs/stage-04/4.9f-monochrome-restyle]]
- Restyle inventory (Part 3 source): [[steps/stage-04/4.9-restyle-inventory]]