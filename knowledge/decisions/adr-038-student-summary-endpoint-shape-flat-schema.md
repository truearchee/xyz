---
type: adr
stage: "4.7"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.7-student-facing-summaries.md
---

# ADR-038 — Student summary endpoint shape + flat schema + reused polling (spec ADR-4.7-5)

> Spec label "ADR-4.7-5". Remapped to repo slot adr-038.

## Linked documents
- Spec: [[specs/stage-04/4.7-student-facing-summaries]]
- Report: [[steps/stage-04/4.7a-student-summary-read-policy]]
- Related: [[adr-034-student-access-availability-table]]

## Context
The list-vs-detail split must avoid per-section fan-out; the security-sensitive content blob wants its own
hardened handler; the generated TS client (rule 3) must stay clean; and "should I poll?" must not become a
server concern.

## Decision (§19 H1–H3 ratified)
- **Option B endpoints:** `GET /student/sections/{id}` (shell + per-slot STATE, no content) and
  `GET /student/sections/{id}/summaries` (per-slot content + state). Plus
  `GET /student/modules/{id}/sections` carrying a COARSE `summaries_state` per section, computed in a
  handful of batched queries (no fan-out). Section-scoped only — no by-summary-id / by-transcript-id route
  (IDOR closure, §8.5).
- **H1:** assignment/supplementary → 200 with both slots `not_applicable`, NOT 404 (404 stays reserved for
  access/existence).
- **H2:** flat `{state, content:nullable}` schema, NOT a discriminated union — OpenAPI `oneOf` produces
  awkward TS client types; flat stays clean (rule 3). `content` is non-null only when `state == ready`.
- **H3:** no server-side polling hints. The client derives "poll iff a rendered slot is `generating`" and
  reuses the 4.5d backoff (no new framework); the response describes STATE, not client mechanics.
- `Cache-Control: private, no-store` on every student response (§8.4) — no stale 200 after unpublish /
  membership removal once a proxy is in front (4.8).

## Consequences
A clean generated client, a single hardened content handler 4.8 reuses, and no cache/IDOR/fan-out
footguns. Verified by `test_student_summaries.py` (schema hygiene + cache-control) and the 4.7 gate.
