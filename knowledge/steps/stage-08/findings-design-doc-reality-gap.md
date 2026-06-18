---
type: finding
stage: 08
session: "8.1"
slug: design-doc-reality-gap
status: open
created: 2026-06-18
updated: 2026-06-18
---

# Finding (Stage 8) — Design/roadmap docs vs. actual code

Recorded per roadmap rule 10 (stop-and-escalate) and the sacred rule (**code wins**). The product
owner has acknowledged this gap and directed Stage 8 to build in the existing inline-style idiom; this
note is the durable record so the docs get reconciled (a separate task, not Stage 8's job).

## The gaps (verified against the `stage-81-83` branch, 2026-06-18)

1. **Monochrome design system is NOT shipped in code.** `design-system.md` v2.0.0 and `design-plan.md`
   v2 describe a monochrome "Apple×Linear" system as **"SHIPPED 2026-06-15"** via session
   `4.9f-monochrome-restyle`, with `frontend/src/components/ui/*`, `globals.css` `@theme` tokens, and
   Tailwind v4. **Reality:** no `frontend/src/components/ui/` (only `auth/`, `shell/`, a `.gitkeep`),
   **no `frontend/src/app/globals.css`**, **Tailwind not installed** (`frontend/package.json` has only
   `next` + `react-markdown`). The existing UI (Stage 5/6 quiz `mcq.tsx`, 4.7 `StudentSectionDetail.tsx`)
   is **inline styles in a blue palette (`#174a63`)**. Stage 4.9 is **NOT STARTED** per the roadmap —
   the roadmap and the code agree; only the design docs disagree. No `4.9*` spec/step files exist.

2. **KaTeX is NOT in the codebase.** Spec decision 6 says answers reuse "markdown + KaTeX (integrated
   since Stage 7)". **Reality:** Stage 7 (Glossary) is NOT STARTED; no `katex`/`rehype-katex`/
   `remark-math` dependency; `SummaryMarkdown.tsx` uses `react-markdown` with raw-HTML off and no math
   plugin. Math currently renders as literal text (same as `mcq.tsx`). Stage 8 reuses `SummaryMarkdown`
   as-is; **KaTeX is correctly Stage 7's job**, not a Stage 8 freelance addition.

3. **Migration numbering drift in the spec.** The spec says migrations are "…0012 today". **Reality:**
   `alembic heads` is **0025** (Stage 6's last). My assigned block is **0032–0037**. (0026–0031 left for
   the parallel Stage 9.)

## Decision / handling
- **D1 (product owner): build Stage 8 UI in the existing inline-style idiom.** The monochrome repaint is
  deferred to Stage 4.9, which will repaint Stages 5–8 together. Do not introduce Tailwind or a component
  library mid-flight (would collide with parallel Stage 9 and create a divergent half-monochrome codebase).
- Use the design-plan §2.6 as a **layout seed only** (surfaces that exist; bubbles by alignment; a
  streaming cursor in 8.3) — realized in the current idiom.
- KaTeX: not added in Stage 8; record here; reuse `SummaryMarkdown`.

## Follow-up (not Stage 8)
- Reconcile `design-system.md` / `design-plan.md` "SHIPPED" banners against reality, OR actually execute
  Stage 4.9 (Tailwind + `components/ui/` + monochrome repaint). Until then the design docs are
  **target/aspirational**, not true-to-code. Tracked in `open-questions.md`.
