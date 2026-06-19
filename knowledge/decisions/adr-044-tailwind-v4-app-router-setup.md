---
type: adr
stage: "4.9"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.9a-tokens-tailwind-shell.md
---

# ADR-044 — Tailwind v4 + App Router setup (PostCSS plugin; next/font LOCAL; source detection)

> Stage 4.9 umbrella §4.1 + §11 (ADR decides REPO FIT, not aesthetics). Recorded with the 4.9a code,
> AFTER verifying the build + the dev-image font compile (no stale font line).

## Linked documents
- Spec: [[specs/stage-04/4.9a-tokens-tailwind-shell]] · Umbrella: [[specs/stage-04/4.9-frontend-foundation-platform-hygiene]]
- Design plan: [[design-plan]] (Part 1.3 typography) · Related: [[adr-045-token-architecture-two-layer]], [[adr-046-component-primitive-strategy]]

## Context
4.9 adopts a styling system on an inline-styled Next 15.3.3 / React 19.1.0 App Router frontend. The
ADR must decide **repo fit**: v4 cleanly or fall back to v3 (a finding, not a forced fight). Two repo
constraints dominate: (1) `next.config.ts` already carries a **webpack** hook — the Stage 4.8c e2e-hook
NormalModuleReplacementPlugin — which is on the critical path of every browser gate and must not be
perturbed; (2) the e2e/CI images must not depend on build-time network egress (4.8 offline-image
hygiene), and the design plan requires self-hosted fonts with **no external request**.

## Decision
- **Tailwind v4, adopted cleanly (REPO FIT confirmed).** `next build` compiled in 4.0s, types valid,
  all 9 routes built; no v3 fallback needed. v4's CSS-first `@theme` makes "CSS variable == Tailwind
  token" one object and lets us reset *only* the color namespace (ADR-045) — the deciding advantage.
- **`@tailwindcss/postcss`, NOT the Next/Turbopack plugin.** `postcss.config.mjs` drives v4 identically
  across `next dev` (local + e2e image), `next build`, and standalone output, and leaves the webpack
  e2e-hook stub untouched. No `tailwind.config.js` (v4 config lives in `globals.css`).
- **Source detection:** `@source "../components"; @source "../features"; @source "../app";` in
  `globals.css` — explicit coverage so the literal-class scanner never misses a dir (prod-purge footgun).
  Verified: the `build` gate emits semantic utilities and **drops disabled-namespace classes** (a probe
  referencing `bg-blue-500` produced 0 CSS).
- **Fonts → `next/font/local` (LOCAL), NOT `next/font/google` — verified, then recorded.** Space Grotesk
  (display) + Inter (body/UI) ship as committed variable `.woff2` under `frontend/src/fonts/`
  (`inter-latin-wght-normal.woff2`, `space-grotesk-latin-wght-normal.woff2`), exposed as
  `--font-sans-src`/`--font-display-src` and mapped into the `@theme` type tokens. **Why local over
  google:** `next/font/google` self-hosts to the browser, but its first-compile fetch (in `next dev`,
  inside the image) is a build-time egress dependency — a latent failure that would surface in CI at the
  worst time, and it contradicts the "no external request" intent + 4.8's offline-image rule. **Confirmed
  end-to-end:** the host `next build` AND the rebuilt e2e **dev image** (`next dev`) both load the fonts
  from disk with no network, and the 4.3.5b/4.3.5c browser smoke rendered the shell green. No monospace
  family this stage (design-plan 1.3; additive later if needed).
- **Client/server boundary:** interactive leaves are `"use client"` (AppShell already is; error.tsx is);
  presentational surfaces (not-found, 403) stay server components. The boundary is pushed to the leaf so
  page-level Server Components stay server-rendered (the full component split is 4.9b).
- **Spacing:** keep v4's default spacing multiplier (rationale + cross-ref in ADR-045).

## Consequences
- One CSS pipeline (PostCSS) across dev/build/e2e/standalone; the webpack e2e stub is untouched (browser
  gates unaffected — proven by the green 4.3.5b/4.3.5c smoke on the rebuilt image).
- Fonts are fully offline and reproducible: no build/runtime fetch, committed bytes, deterministic in CI.
- Deps added (4.9a): `tailwindcss@^4`, `@tailwindcss/postcss@^4`, `postcss@^8` (dev). The
  already-committed `frontend/package-lock.json` was updated (NOT generated — it pre-existed; the
  plan-risk R7 was corrected by verification).
- The baked frontend image must be rebuilt when the CSS pipeline/deps change (done before the 4.9a smoke;
  carried as a standing note for 4.9c's E2E re-run).
