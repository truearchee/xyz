---
type: adr
stage: "4.5"
status: accepted
created: 2026-06-13
updated: 2026-06-13
related-session: knowledge/steps/stage-04/4.5-real-provider-smoke.md
---

# ADR-050 — Summary input truncation (Option A, labeled-interim) + map-reduce follow-up

## Linked documents
- Smoke / finding: [[steps/stage-04/4.5-real-provider-smoke]] (F-4.5-50) · Provider/model: [[decisions/adr-025-routing-split]]
- Follow-up: open-questions F-4.5-51 (map-reduce, own spec)

## Context (F-4.5-50)
The real K2Think provider works (ADR-025 deviation `K2-Think-v2`, live-verified), but **single-call
summarization 408s on real-sized transcripts**. The Checkpoint A lecture is ~47KB / ~11.6K tokens; on the
full transcript BOTH routes return **HTTP 408** (the provider's server-side request-time ceiling) — Cerebras
(brief) and Nvidia (detailed). K2-Think-v2 is a *reasoning* model (thinks inline before answering); reasoning
over ~11.6K input tokens exceeds the provider's per-request time budget. **Context-window fitting does not
help** — 11.6K tokens *fits* the window; the wall is processing TIME, not window size. The prior real-provider
smoke (d5982b8) only ever exercised a ~150-token fixture, which hid this.

Empirical ceiling (probed against the real provider, detailed/Nvidia route, max_tokens 8000):
- full ~47KB (~11.6K tok) → **408**
- 16KB (~4K tok) → 200, **145s**
- 8KB (~2K tok) → 200, **90s**

## Decision
**Option A — TRUNCATE the input (labeled-interim).** After the existing structural normalization, the
transcript is truncated to **`LLM_SUMMARY_INPUT_CHAR_BUDGET` = 12000 chars (~3K tokens)** before the model
call (at a clean sentence/word boundary, never mid-word). 12000 sits well under the ceiling (~115s detailed,
solid margin) while capturing a meaningful first portion. Verified: both lectures' brief + detailed regenerate
real + grounded, **no 408s** (brief ~26-30s Cerebras, detailed ~70-88s Nvidia, all HTTP 200).
- **Truncation is NEVER silent.** `generated_lecture_summaries.truncated` (+ `source_char_count` /
  `summarized_char_count`, migration 0014) records it; the student read projection surfaces
  `StudentSummarySlot.truncated`; the inline frame shows **"Based on the first portion of the transcript."**
- **promptVersion bumped** brief/detailed `v1 → v2` (the v2 prompts add a "may be a partial transcript"
  instruction; provenance distinguishes pre/post-truncation summaries). Generation stays json + OutputValidator
  (no tool-calling, F-5-1).
- Both summaries still generate **independently** from the (truncated) transcript — the brief-from-detailed
  sequencing idea (a prior Option 2) was NOT adopted; truncation makes both routes complete directly.

## Consequences
- Over-budget transcripts are summarized from their **first portion only** — lossy, but labeled.
- **Stage 5 flag:** the quiz path generates from the **detailed summary**, which for large transcripts is now
  truncation-based → quiz questions would cover only the first portion too. Stage 5 must surface/account for
  the `truncated` flag the same way (visible, not silent).
- The deterministic test adapter (CI/gate default, rule 11) is unaffected: e2e fixtures are < budget
  (`truncated=false`), and the adapter keys on prompt NAME not version, so v2 maps to the same canned output.
- **Full coverage is map-reduce → F-4.5-51** (own spec, out of Stage 4.5 — see open-questions). The empirical
  ceiling above is recorded there as the threshold B must solve.
- The exposed real key must be **rotated** (smoke-doc residual / §7).
