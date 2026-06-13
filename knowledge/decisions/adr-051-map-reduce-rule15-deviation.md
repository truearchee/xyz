---
type: adr
id: adr-051
title: Map-reduce detailed summarization — the rule-15 deviation, justified and bounded
status: accepted
date: 2026-06-13
stage: "4.5.1a"
supersedes: none
relates_to: [adr-050-summary-input-truncation, adr-025-routing-split]
---

# ADR-051 — Map-reduce detailed summarization deviates rule 15, justified and bounded

## Context
Rule 15 ("one model call per summary, never per chunk") was the deliberate guard against an
exam-week cost explosion: a per-chunk fan-out multiplied by every student re-reading a lecture would be
ruinous. Stage 4.5 honored it with a single call per summary.

Reality broke the single call (F-4.5-50): K2-Think-v2 over a real ~60-min lecture (~47KB / ~11.6K tokens)
exceeds the provider's server-side request-TIME ceiling → HTTP 408 on BOTH routes. Context-window fitting
does not help (it fits the window; the wall is processing time). Option A (ADR-050) truncated the transcript
to a labeled first-portion budget as an interim — but that means every real lecture summary covers only the
first ~15 minutes. Full coverage requires more than one call.

## Decision
The DETAILED summary is produced by **partition → map → reduce**: the transcript is partitioned into the
FEWEST consecutive units each under a char + token budget, each unit summarized in its own call, and the
partials reduced into one coherent `DetailedSummary` (tiered when the reduce input itself would exceed the
ceiling). This is **N calls per detailed summary** — a deliberate, bounded deviation from rule 15.

The deviation is justified and contained:
- **It is a ONE-TIME ingestion cost, not per-student.** Quizzes (Stage 5), glossary (7), and the assistant
  (8) read the GENERATED summary; they never re-summarize. The exam-week math rule 15 protected is
  unaffected — that path still reads one stored artifact.
- **Minimized.** Partition is COARSE (fewest units under the budget, not per-chunk); map runs at BACKGROUND
  priority on the shared limiter (interactive headroom preserved); the brief is derived from the completed
  detailed in ONE call (4.5.1b), not independently map-reduced.
- **Bounded.** `LLM_SUMMARY_MAX_MAP_UNITS` (default 20) is a hard cost guard — a partition exceeding it fails
  loud rather than firing an absurd fan-out. Budget for a real ~60-min lecture: ~7–9 map calls + a small
  reduce, once, in the background.
- **Rule 15 stays law for per-student paths.** This ADR is the SINGLE recorded exception, scoped to the
  one-time summary ingestion of an over-ceiling transcript.

## Consequences
- `generation_strategy` distinguishes `map_reduce` (full coverage) from `single_call` (legacy/short) and
  `truncated_fallback` (Option A, retained only as a logged emergency path). Only `map_reduce` + `truncated=
  false` is a full-coverage artifact (downstream gating: 4.5.1b §0.1).
- The persisted `prompt_version` is the REDUCE call's (the artifact-producing call); the map version lives in
  `generation_metadata`. Eligibility expects the reduce version (single source of truth in `summary_specs`).
- The RQ detailed-job timeout scales with `MAX_MAP_UNITS` (a sequential N-call job must not keep the
  single-call timeout — the prior SIGKILL class).
- A new 408 surface appears: the REDUCE input. The §3.3 input guard + tiered reduce mitigate it; real-provider
  confirmation of reduce latency/output-tokens is 4.5.1c.
- The brief stays single-call (it is small and writes from the completed detailed in 4.5.1b — no rule-15
  pressure there).
