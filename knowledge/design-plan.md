# Design Plan v1 — XYZ LMS

> Companion to `knowledge/roadmap.md`. This is the **visual reference** the roadmap names as its
> second input document. It is **product/brand authority** — the design direction here was
> human-locked in a design-direction session (2026-06-12) and an engineer may not invent or
> override it (roadmap rule; Stage 4.9 prereq 1a).
>
> **Authority hand-off:** from Stage 5 onward, `knowledge/design-system.md` (written from the
> SHIPPED Stage 4.9 code) **replaces Part 1** of this plan as the living visual authority. Part 2
> (screen specs) remains the per-stage seed source. Where shipped code and this plan disagree,
> **code wins** (sacred rule) — fix this plan.
>
> **Scope of the locked values:** Part 1.2 fixes the *palette identity* and anchor values; the full
> mechanical scales (every spacing/radius/elevation step, per-state derived shades, the exact
> type-scale) are **derived in Stage 4.9a** and validated for WCAG AA there (prereq 1b). This plan
> gives the identity + anchors; 4.9a fills in the derivations; `design-system.md` records the final
> shipped numbers.

---

## Part 0 — Identity intent

XYZ is an AI-assisted learning platform. The heavy product surfaces (quiz attempt, glossary,
AI assistant) are coming in Stages 5–8; long-form AI content (summaries, transcripts) and
visible processing status are the recurring experience. The visual identity is therefore:

- **AI-forward but calm** — modern and distinctly "AI product," never loud or gimmicky.
- **Readable first** — long-form content must be effortless to read on a phone or a laptop.
- **Status-honest** — the product does real async work (minutes-long summary/quiz generation);
  the interface shows that work truthfully, including failure, never a frozen spinner or a fake
  success (rule 2).

Locked direction: **Violet / AI-forward palette · Space Grotesk (display) + Inter (body & utility) ·
the processing pipeline as the signature element.**

---

## Part 1 — Visual system

### 1.1 Brand mood
Modern, focused, trustworthy. Violet signals "AI/contemporary" without the corporate-blue default;
geometric display type adds character at headings while a neutral body keeps long content legible;
the one bold moment is reserved for the processing pipeline — the visual that recurs across the
whole product.

### 1.2 Tokens — palette (the locked identity; 4.9a derives full scales + validates AA)

**Two-layer model (structure locked in spec §4.1):** Layer 1 is the raw palette (literal values,
never touched by components); Layer 2 is the semantic roles (the only thing components consume).

**Layer 1 — raw palette (source values):**

```
Brand — Violet
  violet-50  #f5f3ff   violet-100 #ede9fe   violet-200 #ddd6fe   violet-300 #c4b5fd
  violet-400 #a78bfa   violet-500 #8b5cf6   violet-600 #7c3aed   violet-700 #6d28d9
  violet-800 #5b21b6   violet-900 #4c1d95
  ^ primary = violet-600 #7c3aed

Neutral — Zinc
  white #ffffff
  zinc-50 #fafafa   zinc-100 #f4f4f5   zinc-200 #e4e4e7   zinc-300 #d4d4d8
  zinc-400 #a1a1aa   zinc-500 #71717a   zinc-600 #52525b   zinc-700 #3f3f46
  zinc-800 #27272a   zinc-900 #18181b

Status raws (each: solid 600 + light 50 tint + dark 700 text-on-light)
  success  green-600 #16a34a   green-50 #f0fdf4   green-700 #15803d
  warning  amber-600 #d97706   amber-50 #fffbeb   amber-700 #b45309
  danger   rose-600  #e11d48   rose-50  #fff1f2   rose-700  #be123c
  info     indigo-500 #6366f1  indigo-50 #eef2ff  indigo-700 #4338ca
```

**Layer 2 — semantic roles (components consume ONLY these):**

```
--color-surface          → white            base page/card background
--color-surface-muted    → zinc-50          subtle inset / app background
--color-surface-raised   → white            elevated (paired with an elevation shadow)
--color-border           → zinc-200         decorative hairlines / dividers (WCAG 1.4.11-exempt)
--color-border-strong    → zinc-500         functional control boundaries (input/select) — meets 3:1
--color-text             → zinc-900         primary text
--color-text-muted       → zinc-500         secondary/label text
--color-primary          → violet-600       primary actions, active nav, the pipeline
--color-on-primary       → white            text/icon on a primary fill
--color-success          → green-600        --color-on-success → white  (large/bold/UI only)
--color-warning          → amber-600        --color-on-warning → white  (large/bold/UI only)
--color-danger           → rose-600         --color-on-danger  → white
--color-info             → indigo-500       --color-on-info    → white  (large/bold/UI only)
--color-focus-ring       → violet-500       2px ring + 2px offset on every interactive element
```

**Tonal (badge/tint) roles** — status surfaces that carry text use a light tint + dark text (the
existing app's accessible pattern, e.g. completed = green-50 bg + green-700 text). 4.9a defines
`--color-{state}-surface` (→ the -50) and `--color-{state}-text` (→ the -700) so the Badge/pipeline
never rely on color alone and always clear AA. A component needing a tint role this set lacks is a
**finding** (add the role), never a reach into Layer 1.

**Contrast — VALIDATED (computed 2026-06-12; re-confirmed in 4.9a against shipped CSS).** Every pair
below was computed with the WCAG 2.x relative-luminance formula. AA = 4.5:1 body, 3:1 large/UI/non-text.

```
PAIR (fg on bg)                              RATIO    AA verdict
text (zinc-900) on surface (white)           17.72:1  PASS body
text (zinc-900) on surface-muted (zinc-50)   16.97:1  PASS body
text-muted (zinc-500) on surface (white)      4.83:1  PASS body
text-muted (zinc-500) on surface-muted        4.63:1  PASS body
primary (violet-600) text/link on surface     5.70:1  PASS body
on-primary  white on violet-600               5.70:1  PASS body + large
on-danger   white on rose-600                  4.70:1  PASS body + large
on-info     white on indigo-500                4.47:1  PASS large/UI  (NOT body — large/bold only)
on-success  white on green-600                 3.30:1  PASS large/UI  (NOT body — large/bold only)
on-warning  white on amber-600                 3.19:1  PASS large/UI  (NOT body — large/bold only)
TONAL (badge: dark text on -50 tint)
  green-700 on green-50                         4.79:1  PASS body
  amber-700 on amber-50                         4.84:1  PASS body
  rose-700  on rose-50                          5.72:1  PASS body
  indigo-700 on indigo-50                       7.07:1  PASS body
NON-TEXT (WCAG 1.4.11, ≥3:1)
  focus-ring violet-500 on white                4.23:1  PASS
  border-strong zinc-500 on white               4.83:1  PASS  (functional control boundaries)
  border zinc-200 on white                      1.27:1  exempt (decorative dividers only; NOT a control boundary)
```

**Rules that fall out of the validation (binding on components):**
- **Solid success/warning/info fills carry only large/bold/UI text** (their white-on-fill ratio is
  3.19–4.47:1 — fine for badge labels/button text, below 4.5 for body). For **body** status text use the
  **tonal** pair (dark `-700` on `-50` tint), which is the Badge default anyway (status-by-text-label).
- **Decorative borders** use `--color-border` (zinc-200, exempt). **Functional control boundaries**
  (input/select outlines, when the border is the only affordance) use `--color-border-strong` (zinc-500,
  4.83:1) to meet 1.4.11. zinc-300 (1.48:1) and zinc-400 (2.56:1) do **not** qualify.
- A new pair a component needs that is not validated above is a **finding** (rule 13) — validate before use.

**Dark mode:** OUT of scope for the MVP. The two-layer structure is theming-ready — a future dark
theme is a swap of the Layer-2→Layer-1 mapping, not a component rewrite (spec §4.1).

### 1.2b Tokens — non-color (anchors; 4.9a finalizes the exact steps)

```
Type scale (px / line-height)   xs 12/16 · sm 14/20 · base 16/24 · lg 18/28 · xl 20/28
                                2xl 24/32 · 3xl 30/36 · 4xl 36/40 (display)
Spacing                         4px base unit (1=4 … 2=8, 4=16, 6=24, 8=32 …)
Radius                          sm 6 · md 8 · lg 12 · pill 9999
Elevation (shadow)              sm (hairline lift) · md (cards/raised) · lg (modals/popovers)
Motion                          fast 120ms · base 200ms · slow 320ms
                                ease-standard cubic-bezier(0.2, 0, 0, 1)
                                prefers-reduced-motion: reduce → transitions/animation removed
Layering (z-index)              base < dropdown < modal < toast  (assistant anchor below toast)
```

### 1.3 Typography (self-hosted via next/font; no external font CSS)

```
DISPLAY   Space Grotesk     headings (h1–h3), the product wordmark, pipeline step labels
          weights 500 / 700   — geometric character where text is SEEN
BODY +    Inter             body copy AND utility/UI: labels, table cells, form text,
UTILITY   weights 400/500/600   buttons, badges, IDs, status text — neutral, hyper-legible
                              where text is READ
```

**Two families only — Space Grotesk + Inter (LOCKED).** Inter covers **both** body and utility/UI;
there is **no separate monospace family** this stage. Each family is exposed as a CSS variable in the
root layout (`--font-display` → Space Grotesk, `--font-sans` → Inter) and mapped into the theme type
tokens (spec §4.1 font-loading rule). Body/UI default is Inter; headings opt into Space Grotesk via
the display token. Both are self-hosted via `next/font/google` (zero layout shift, no external CSS).
*If a later stage needs true monospace for dense data (e.g. checksums, model IDs in an AIRequestLog
view), adding a `--font-mono` token + family is an **additive** change (design-system.md changelog),
not a redesign — it is deliberately out of scope here.*

### 1.4 Signature element — the processing pipeline

The **one memorable visual moment**; the single place boldness is spent.

```
WHAT   A step track rendering an async pipeline. Each step = a node + a connector.
       States (the failed state is MANDATORY and visually distinct — never "not completed"):
         pending    muted, hollow node (zinc-300 ring)
         active     violet-600 node with a subtle progress shimmer (reduced-motion → static)
         completed  violet-600 filled node + check; connector behind it filled violet
         failed     danger rose-600 filled node + ✕ + a text label ("failed"); connector
                    up to it stays filled, the failed node is unmistakably red — a failed
                    step is NEVER rendered as merely an incomplete/pending step
       Orientation  horizontal on desktop; vertical stack on mobile (Part 5)
       Status by TEXT label on every node, never color alone (a11y; Part 4).

WHERE  Stage 4.9: lecturer transcript status (parse → chunk → embed → brief → detailed).
       Stage 5:   quiz generation + quiz attempt progress.
       Stage 11:  risk-row pipeline.
       Built ONCE as the Progress/Step component (spec §4.2); reused everywhere.

WHY    The product does real, visible, sometimes-failing async work. The pipeline is the
       recurring truth-telling visual — so it is where the design invests its character.
```

---

## Part 2 — Screen specs (per-stage seed source)

Concise intent per named surface. Stage 4.9 restyles 2.0–2.3 + the 4.5d–4.7 panels within the §5
boundary; later stages seed from the relevant section.

### 2.0 Login (mobile-first)
Centered card (`--color-surface-raised` + elevation-md) on a `--color-surface-muted` page. Product
wordmark in Space Grotesk. Email + password Inputs, a single violet primary Button. Errors inline on
the field (not color-only) + a Toast for auth failure. No nav/shell (unauthenticated route group).

### 2.1 Admin (desktop-first)
Role-aware shell (nav + main). Users and Modules as semantic Tables (sortable headers are buttons);
create/assign forms in Cards using Input/Button; destructive actions via the confirm Modal. Empty
states use the Empty State component. One-off admin detail screens Stage 5+ never touches may be left
for Stage 12 (§5 inventory).

### 2.2 Lecturer content (desktop-first authoring)
Module detail: section list as Cards; transcript upload + replace controls; **the pipeline signature**
for processing status (the 4.5d/4.6 surface); brief/detailed summary panels as readable long-form
"knowledge" blocks. Retry action on a failed pipeline step uses a Button + Toast feedback.

### 2.3 Student view (mobile-first)
Module list → section detail → summary reading. Summaries render as comfortable long-form content
(generous measure, Inter body, clear heading hierarchy in Space Grotesk). Brief/detailed selection is
explicit. Students never see the raw transcript (4.7 invariant) or unpublished content. Processing/
unavailable states use Empty State / the passive "processing…" convention (§4.3), never a fake value.

### 2.4 Post-class / assessment (Stage 5 seed)
Quiz attempt flow is **mobile-first** and consumes Button/Card/Badge/Modal/Progress as-built; the
Progress/Step "failed" state and Badge "status-by-label" rule are reused verbatim. Detailed spec lands
with the Stage 5 spec (roadmap + this section + design-system.md).

---

## Part 3 — Stage 12 consistency sweep (deferred backlog)

The surfaces Stage 4.9 deliberately LEAVES inline-styled (one-off admin/lecturer screens Stage 5+
never reuses) are tracked in `knowledge/steps/stage-04/4.9-restyle-inventory.md` and rolled up here
for the Stage 12 Part-3 consistency sweep + heavy a11y/mobile audit + visual-regression snapshots.
(Populated at 4.9c.)

---

## Part 4 — Accessibility baseline

**Target: WCAG AA.** The baseline 4.9 guarantees (the heavy audit is Stage 12):

```
- Focus-visible ring on every interactive element (--color-focus-ring, 2px + 2px offset),
  never removed without an equivalent indicator.
- Contrast: every semantic text/surface pair ≥ 4.5:1 (body) / 3:1 (large/UI), validated at
  the TOKEN level in 4.9a (not deferred whole to Stage 12).
- Status by TEXT label, never color alone (Badge, the pipeline, risk rows) — the quiz/risk rule.
- Reduced motion: prefers-reduced-motion: reduce removes the pipeline shimmer + transitions.
- Keyboard: Modal focus-trap + Esc + focus-return; skip-to-content link in the shell; sane
  heading order; semantic landmarks (<nav>/<main>). Dynamic keyboard behavior is a manual pass
  (4.9 keyboard checklist); automated keyboard + axe audit is Stage 12.
- Forms: label association (htmlFor/id); errors linked via aria-describedby, not color-only.
- Live regions: Toast is a polite live region; error toasts do not auto-dismiss.
```

---

## Part 5 — Mobile strategy

```
MOBILE-FIRST surfaces (designed for the phone first, enhanced up):
  - Student learning surfaces: module list, section detail, summary reading (2.3)
  - Stage 5  quiz attempt flow
  - Stage 7  glossary
  - Stage 8  assistant workspace / floating widget
  Rationale: students consume learning content primarily on phones.

DESKTOP-FIRST surfaces (authoring/administration; mobile is sane but not optimized):
  - Admin (2.1), Lecturer content authoring (2.2)

Breakpoints (Tailwind defaults): sm 640 · md 768 · lg 1024 · xl 1280.
4.9 mobile-sanity target: 375px width (iPhone-SE class) — no horizontal scroll, no broken
layout on the mobile-first surfaces. Heavy mobile audit is Stage 12.
```

---

## Part 6 — Decisions log

```
2026-06-12  Design direction LOCKED in a facilitated design-direction session (product owner).
            - Palette: VIOLET / AI-forward (primary violet-600 #7c3aed; zinc neutrals;
              green/amber/rose/indigo status). Chosen over Indigo/Teal/Blue for a modern,
              distinctly-AI identity that fits the Stage 8 assistant without being loud.
            - Typeface: SPACE GROTESK (display) + INTER (body AND utility/UI). Two families
              only; NO separate monospace this stage (additive later if dense-data views need it).
              Distinctive geometric headings + neutral, hyper-legible body/UI.
            - Signature element: THE PROCESSING PIPELINE (bold animated step track with a
              striking failed state). Boldness spent on the product's recurring visual; the
              spec already mandates a distinct failed state, and it is reused by Stage 5 quiz
              progress and Stage 11 risk rows.
            - Accessibility target: WCAG AA. Mobile-first: student learning surfaces.
            - Dark mode: deferred (post-MVP); token layer kept theming-ready.
            Unblocks Stage 4.9 prereq 1a (knowledge/design-plan.md did not previously exist).

2026-06-12  Refinements during Phase 0 close (developer-confirmed):
            - Typography simplified to TWO families: Inter now covers body AND utility/UI
              (JetBrains Mono dropped; mono is an additive future token if needed).
            - Per-state semantic scales derived + EVERY text/surface pair computed against
              WCAG AA (Part 1.2 validated table). Outcomes: solid success/warning/info fills
              are large/bold/UI-only (body status text uses the tonal -700-on-50 pair);
              added --color-border-strong (zinc-500, 4.83:1) for functional control
              boundaries (zinc-200 decorative border is 1.4.11-exempt). 4.9a re-confirms
              against shipped CSS.

(Subsequent decisions — full token scales, contrast resolutions, component contracts — are
 recorded in the Stage 4.9 ADRs adr-044…adr-049 and, once shipped, in design-system.md.)
```

---

## Linked documents
- Roadmap: [[roadmap]]
- Stage 4.9 spec: [[specs/stage-04/4.9-frontend-foundation-platform-hygiene]]
- Design system (deliverable, supersedes Part 1 from Stage 5): [[design-system]]
- Restyle inventory (Part 3 source): [[steps/stage-04/4.9-restyle-inventory]]
