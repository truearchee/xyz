---
type: adr
id: adr-053
stage: 08
status: accepted
created: 2026-06-19
related-session: "8.4"
---

# ADR-053 — Keyset pagination as a sibling envelope (not a mutation of the offset envelope)

## Context
Stage 5 lock 9 defined a single pagination envelope — `PaginatedResponse[T] = { items, pagination:
{limit, offset, total} }` (offset-based) — "reused verbatim by glossary, conversations, and events"
(`platform/query/pagination.py`). Stage 8.4's assistant **message history** needs keyset/cursor
pagination instead: a chat thread mutates under the reader (new turns append while the student scrolls
older pages and the UI polls), so an offset window shifts on every insert, and a deep `OFFSET` grows
linearly. The 8.4 spec explicitly requires `before=<created_at,id>` keyset for messages and says: reuse
the Stage 5 envelope SHAPE; **if it is offset-only and can't express a cursor, escalate per rule 10**.
It is offset-only. (Findings note: [[steps/stage-08/findings-8.4-keyset-pagination-escalation]].)

## Decision
Add a **sibling** envelope rather than mutate the shared offset one:
- `KeysetPage[T] = { items, nextCursor, hasMore }` defined ALONGSIDE `PaginatedResponse` in
  `platform/query/pagination.py`. `PaginatedResponse` is left **unchanged**.
- The conversation **list** keeps the offset `PaginatedResponse` (small, bounded — offset is fine). Only
  the **messages** endpoint switches to `KeysetPage`. Both expose `items`, so the shared chat hook reads
  `list.items` regardless; only "load older" reads `nextCursor`/`hasMore`.
- Cursor: opaque URL-safe base64 of `f"{created_at.isoformat()}|{message_id}"`
  (`domains/assistant/cursor.py`); decode validates → **422** on malformed (never a silent fallback).
  No HMAC — the cursor only paginates a conversation the caller has ALREADY passed the ownership +
  visibility gate on, so a forged cursor can at worst page the same owned conversation oddly.
- The composite `(created_at, id)` keyset is **load-bearing**: Stage 8.1 stamps a turn's user + assistant
  rows with the SAME `created_at`, so the `id` tiebreak (backed by `ix_assistant_messages_conversation_created`
  + the PK) is required for a stable order.

## Consequences
- There are now **two** platform pagination contracts. Offset stays the DEFAULT for ordinary lists;
  reach for `KeysetPage` only for deep, high-churn, poll-while-appending feeds (today: assistant
  messages). A future endpoint chooses between them deliberately.
- The messages endpoint response shape changed (offset → keyset) — the generated client was regenerated
  in the same session; the inline panel / shared hook were unaffected (both envelopes carry `items`).
- The Stage 5 "defined once" lock is **extended, not violated**: the offset envelope is untouched and
  remains the single offset contract.
