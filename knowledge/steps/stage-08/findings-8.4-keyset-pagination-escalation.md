---
type: finding
stage: 08
session: "8.4a"
created: 2026-06-19
status: resolved
---

# Finding 8.4 — Stage 5 pagination envelope can't express the keyset cursor messages need (rule-10 escalation)

## What the plan/spec assumed vs reality
The 8.4 spec wants the assistant **messages** endpoint to use keyset pagination (`before=<created_at,id>`,
limit) because a chat thread mutates under the reader while polling. It instructed: reuse the Stage 5
envelope SHAPE; **if it is offset-only and can't express a cursor, escalate per rule 10**.

Reality (code wins): `platform/query/pagination.py` defines exactly one envelope —
`PaginatedResponse[T] = { items, pagination: { limit, offset, total } }`, offset-based, and its own
docstring says it is "reused verbatim by glossary, conversations, and events" (Stage 5 lock 9). It
cannot carry a cursor. So this is the anticipated rule-10 escalation, not a silent papering-over.

## Resolution (decided, not deferred)
Add a **sibling** envelope, leave the offset one untouched (see [[decisions/adr-053-keyset-pagination-sibling-envelope]]):
- `KeysetPage[T] = { items, nextCursor, hasMore }` beside `PaginatedResponse` in the same module.
- Conversation **list** keeps offset `PaginatedResponse`; **messages** uses `KeysetPage`.
- Opaque base64 `(created_at|id)` cursor (`domains/assistant/cursor.py`); malformed → 422; the
  `(created_at,id)` tiebreak is load-bearing (8.1 stamps the user + assistant rows of a turn with the
  same `created_at`).

## Why not the alternatives
- **Mutate `PaginatedResponse` to add optional cursor fields** — rejected: it's a shared, "defined-once"
  contract reused by glossary/events; conflating offset + keyset in one type is confusing and risks
  every consumer.
- **Force messages onto offset** — rejected: the spec requires keyset, and offset shifts on append while
  polling (the exact failure mode keyset avoids).

## Status
RESOLVED in 8.4a. Backend tests cover newest-page / before-cursor / equal-timestamp tiebreak / invalid
cursor 422 (`test_assistant_workspace.py`). The Stage 5 offset lock is extended, not violated.
