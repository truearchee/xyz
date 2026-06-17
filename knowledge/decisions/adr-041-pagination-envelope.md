---
type: adr
stage: "5"
status: accepted
created: 2026-06-16
updated: 2026-06-16
related-session: knowledge/specs/stage-05/5a-quiz-foundation.md
---

# ADR-041 — Offset-based PaginatedResponse envelope as the platform standard

> Stage 5 spec ADR label "(D)". Remapped to repo slot adr-041.

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5a-quiz-foundation]]
- Report: [[steps/stage-05/5a-quiz-foundation]]
- Related: [[adr-040-activity-event-spine]]

## Context
Stage 5 lands the first large lists (attempts, mistake bank). Later stages add more (glossary,
conversations, events). Retrofitting pagination at Stage 7 is the wrong time; the envelope must be
defined once, now, and reused verbatim. Before this, list endpoints returned bare `list[T]` with no
pagination metadata.

## Decision
`app/platform/query/pagination.py` defines:

```
PaginatedResponse[T] = { items: T[], pagination: { limit, offset, total } }   (offset-based)
```

A Pydantic v2 generic with camelCase aliasing (consistent with the generated TS client). Every later
paginated list reuses it verbatim.

## Consequences
One envelope shape across the API; no per-endpoint reinvention; the TS client stays uniform. Defined in
5a so 5b/5c just import it.

## Amendment (2026-06-16, #5c)
The original plan named the Stage-5 "list my attempts for this section" as the envelope's first real
consumer. On building 5c this was reconsidered: the Stage-5 UI renders a SINGLE aggregate line (best
score · attempt count), so the attempts surface is an **aggregate query** (`COUNT(*)` + `MAX(score)`),
not a paginated list — wrapping one summary line in a paginated endpoint is pagination theatre. There is
no other genuine list in Stage 5 (answers are per-question; questions embed in the attempt DTO; mistakes
are not read until Stage 6). So the envelope is **defined + unit-tested in 5a** and **proven by its first
genuine list consumer in Stage 6 (mistakes-bank) / Stage 7 (glossary entry lists)** — not in Stage 5.
The spec's "Done means: envelope proven by one real consumer" is read as "defined + reused-ready," with
the real-consumer proof deferred to that first genuine list. No code change to the envelope itself.
Session 5e amended the Stage 5 spec so the done checklist matches this accepted scope decision.
