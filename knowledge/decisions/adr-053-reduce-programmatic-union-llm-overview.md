---
type: adr
id: adr-053
title: Map-reduce reduce = programmatic union of structured partials + an LLM overview
status: accepted
date: 2026-06-13
stage: "4.5.1c"
supersedes: "the LLM-merge reduce of 4.5.1a (detailed_summary_reduce prompt + tiered guard)"
relates_to: [adr-051-map-reduce-rule15-deviation, adr-052-brief-from-detailed-dag]
---

# ADR-053 — The reduce is a programmatic union, not an LLM merge

## Context
4.5.1a's reduce asked the LLM to MERGE the map partials into one coherent `DetailedSummary` (the
`detailed_summary_reduce` prompt), with a tiered fallback when the serialized partials exceeded an input
budget. The 4.5.1c real-provider smoke showed this does not work on the reasoning model:

- The map partials are RICH and cover the whole lecture (~7 units, ~13KB serialized, ~45 concepts / ~16
  worked examples for a real hour lecture).
- Asked to "merge faithfully, all keys, preserve every portion's content," K2-Think-v2 instead produced a
  ~900-char, intro-focused summary that DROPPED the required `examples` key — identically under prompt v1
  and a hardened v2. Its summarize-and-compress prior overrode the instructions.
- The faithful-merge intent also broke the tiered fallback: a merge that preserves content doesn't shrink,
  so tiering never converged.

The map partials are already STRUCTURED data (lists of keyConcepts / examples / importantDefinitions /
mainExplanations / examRelevantPoints). Asking a model to losslessly carry structured lists through a free-
text generation fights its nature.

## Decision
The reduce is split by what each tool is good at:
- **Programmatic union (deterministic).** `_union_partials` concatenates + dedupes (case-insensitive, first-
  spelling, lecture order, capped) every structured list across the map partials. Coverage is GUARANTEED by
  construction — no LLM compression can drop content the map already extracted. The latter-half content
  (one-sided limits, indeterminate forms, worked examples) survives because it is in the partials.
- **One LLM overview call.** `detailed_summary_overview/v1` (nvidia, JSON mode) takes a small input (the
  per-portion overviews + merged key concepts) and produces ONLY the 2-4 sentence overview — the one part
  that genuinely needs synthesis, and the part the model does reliably. `_assemble` builds the
  `DetailedSummary` from the union + that overview.

The LLM-merge reduce (`detailed_summary_reduce` prompts, the tiered `_reduce`/`_greedy_groups`, and the
`LLM_SUMMARY_REDUCE_INPUT_*_BUDGET` config) is retired; the artifacts stay in history (dormant).

## Consequences
- Full coverage is a structural guarantee, not a prompt hope. Verified on a real hour-length lecture:
  40 keyConcepts / 16 examples / 19 definitions in the regenerated detailed, latter-half limit theory present.
- The detailed's persisted provenance (model/prompt/backend, and the eligibility-gated `prompt_version`)
  comes from the OVERVIEW call (`detailed_summary_overview/v1`, nvidia); the map prompt version is in
  `generationMetadata`. `EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE[detailed]` tracks the overview version.
- No tiering ⇒ no non-convergence and no reduce-input 408 surface; the reduce LLM input is small (overviews
  + concepts), well under the provider ceiling regardless of lecture length.
- Dedup is exact-match (case-insensitive); near-duplicate phrasings across portions may both appear. For a
  comprehensive study summary this is acceptable (over-inclusion beats lossy compression). Cross-portion
  narrative coherence is carried by the overview, not the lists.
- Rule 15 / ADR-051 unchanged (still N map calls + now ONE overview call per detailed, one-time ingestion).
