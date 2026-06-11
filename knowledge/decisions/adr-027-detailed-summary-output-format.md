---
type: adr
stage: "4.5"
status: accepted
created: 2026-06-11
updated: 2026-06-11
related-session: knowledge/specs/stage-04/4.5c-detailed-summary-generation.md
---

# ADR-027 - Detailed-Summary Output Format (structured JSON, not markdown)

## Linked documents
- Master spec: [[specs/stage-04/4.5-ai-infra-summary-generation]]
- Spec: [[specs/stage-04/4.5c-detailed-summary-generation]]
- Report: [[steps/stage-04/4.5c]]
- Related: [[adr-025-routing-split]] · [[adr-028-llm-gateway-provider-separation]]

## Context
The detailed study summary (Slice 2) is a multi-section artifact: overview, key concepts, important
definitions, main explanations, examples, exam-relevant points, and (for lab sessions) lab notes. It
must be **machine-validated** (every required section present and non-empty before it reaches a
student) and **cleanly rendered** (no provider chatter, no model reasoning). Two output shapes were
available: free-form markdown with section headers, or a structured JSON object keyed by section.

Markdown-header parsing is fragile: a missing/renamed/re-ordered header, a stray "## " inside prose,
or a reasoning preamble all break extraction, and "is this section non-empty?" becomes a heuristic.

## Decision
The detailed summary is a **structured JSON object** whose shape **is** a Pydantic model
(`DetailedSummary`), mirroring the brief contract (ADR-…, §7):

```python
class DetailedSummary(CamelModel):
    overview: str
    key_concepts: list[str]
    important_definitions: list[Definition]   # {term, definition}
    main_explanations: list[str]
    examples: list[str]
    exam_relevant_points: list[str]
    lab_notes: list[str] | None = None        # required & non-empty IFF section type == 'lab'
```

Validation = **tolerant extract → strict shape** (the 4.5b pattern, now applied to detailed):
- locate the JSON object even if wrapped in ```json fences or preceded by reasoning preamble (a
  reasoning-lineage model may prefix despite instructions — and 4.5c runs detailed on the
  reasoning-lineage `K2-Think-v2`);
- parse to `DetailedSummary`; **strict**: every required section present and non-empty;
- `labNotes` required & non-empty **iff** the source module section type is `lab`; absent/empty
  otherwise (the section-type signal already exists on the data model — no new field);
- store **only** the parsed structured object in `contentJson`; any required section missing/empty →
  `invalid_output` → bounded retry.

The model's camelCase aliases (`keyConcepts`, …) are the persisted `contentJson` shape, so the API/UI
consume a stable, typed structure.

## Rationale
- **Reliable validation:** "section present and non-empty" is a field check on a parsed model, not a
  markdown-header heuristic.
- **Clean rendering:** the UI binds to typed fields; provider preamble/reasoning is stripped by the
  tolerant extractor and never stored.
- **Symmetry:** brief and detailed share one extract→validate→store-only pattern; one mental model,
  one set of failure codes.

## Consequences
- `DetailedSummary` + `DetailedSummaryValidator` live in `platform/llm`; `contentJson` is `model_dump
  (by_alias=True)` so the stored shape matches the spec's camelCase `contentJson`.
- Quiz generation (Stage 5) consumes a typed structure, not parsed prose.
- A future schema change is a `DetailedSummary` version bump + a `detailed_summary/v*` prompt bump,
  caught by the prompt drift guard — not an invisible parser drift.
