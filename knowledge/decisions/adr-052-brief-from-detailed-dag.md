---
type: adr
id: adr-052
title: Brief-from-detailed — the summary DAG inverts; brief forks from the detailed, not the transcript
status: accepted
date: 2026-06-13
stage: "4.5.1b"
supersedes: none
relates_to: [adr-051-map-reduce-rule15-deviation, adr-050-summary-input-truncation, adr-046-a]
---

# ADR-052 — Brief-from-detailed DAG

## Context
After 4.5.1a, the DETAILED summary is full-coverage (map-reduce over the whole transcript). The BRIEF,
however, was still generated from the (Option-A truncated) transcript — so on a real lecture the brief
covered only the first portion while the detailed covered everything. Two summaries of the same lecture
with different coverage is the silent-inconsistency class this sub-stage exists to kill.

## Decision
The summary DAG inverts. The brief is DERIVED FROM THE COMPLETED DETAILED summary in one small call on the
BRIEF route (a compression/writing task over the detailed's structured content), NOT re-summarized from
the transcript:

- **DAG:** embed → detailed (map-reduce) → **brief forks from the completed detailed** → activation.
  ``insert_summary_jobs`` creates both job rows at embed-time but enqueues only the detailed; the detailed
  handler enqueues the brief on success. The brief claim reads the latest completed detailed (via
  ``get_latest_transcript_summaries``); if none exists yet it DEFERS (leaves the job queued, no attempt
  consumed) — the fork is the trigger. Lost brief-first ordering is accepted.
- **Provenance:** the brief persists ``generation_strategy='derived_from_detailed'`` (a distinct value,
  migration 0016) with ``generationMetadata.sourceDetailedSummaryId``; its ``input_hash`` is derived from
  the source detailed row, so a REGENERATED detailed yields a distinct brief. The brief inherits the
  source detailed's ``truncated`` flag (a brief from a truncated_fallback detailed is itself truncated).
- **Eligibility:** the brief persists the ``brief_from_detailed/v1`` prompt version; activation eligibility
  accepts a SET of current versions per type (``EXPECTED_PROMPT_VERSION_BY_SUMMARY_TYPE`` → tuple), so both
  the derived brief and the fallback brief are recognized as current while ``prompt_version`` stays the
  true producing prompt's version (no contract-version stamping).
- **OB1 fallback (``ENABLE_DETAILED_SUMMARY=false``):** the brief FALLS BACK to the transcript-based
  single-call (Option-A truncated) path — but with the FULL §0.1 treatment: ``truncated=true``,
  ``generation_strategy='single_call'``, it does NOT satisfy ``is_full_coverage_detailed`` (which keys off
  the DETAILED anyway), and it carries the "based on the first portion" UI label. The detailed-off mode is
  a DEGRADED, honestly-degraded escape hatch — never a back door that puts truncated content into a state
  Stage 5 reads as full-coverage.

### On ``ENABLE_DETAILED_SUMMARY``
It is a cost-control escape hatch, NOT the default — default is ``true`` (4.5c). Flipping it ``false`` in
production is a NAMED product consequence: those lectures' summaries become truncated, labeled, and
**non-quiz-eligible** (no quiz/glossary/assistant generation for them). It is not a silent code path; it is
a documented degraded mode. (Today it is believed to be a 4.5b cost-control leftover with no active prod
user; if that changes, the consequence above is the contract.)

## Consequences
- Quiz/glossary/assistant gating (§0.1) reads ``is_full_coverage_detailed`` on the DETAILED summary, never
  the brief. The brief's ``derived_from_detailed`` label is informational provenance; the brief carries no
  quiz authority.
- A brief retry reads the EXISTING completed detailed (the brief is a pure function of it) — never
  re-summarizes the transcript, so a retry can't produce a different-coverage brief than the one it
  replaces. The brief-claim's §6.1 fence checks the source detailed still matches the ACTIVE transcript
  checksum, so a brief firing after a replacement reads the NEW detailed or defers — never staples a stale
  detailed's brief onto a replaced transcript.
- A stuck-detailed reaper re-fork re-triggers the brief on detailed completion (the dependency holds
  through retry).
- Activation now fires from the brief leaf (the last to complete under the new ordering); the 4.6
  every-leaf-activates mechanism (F-4.6b-2) already supports this.
