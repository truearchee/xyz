---
type: adr
id: adr-054
stage: 08
status: accepted
created: 2026-06-19
related-session: "8.4"
---

# ADR-054 — Assistant conversation-management contract (soft-delete, one-active, access-wins, no-resurrection)

## Context
Stage 8.4 makes assistant conversations navigable and manageable (a Workspace + a floating widget). That
turns a handful of correctness questions into invariants a navigation feature quietly breaks: how delete
interacts with the one-active-per-lecture rule, what happens when access is revoked after a conversation
exists, and what a worker does if it finishes after a delete. 8.1 already enforced one active
`lecture_default` per (student, section) via a partial-unique index, and 8.2 routed grounding through the
Stage 4.7 published-section/assigned-module visibility gate with a pinned 404 (don't reveal existence).

## Decision
1. **Soft-delete only** (`deleted_at`), no hard delete. Soft-deleted conversations retain their messages
   and `context_snapshot` rows — fine for staging; feeds the post-MVP watchlist item *"transcript
   retention/deletion policy BEFORE any real-student deployment."* Delete confirm copy must never promise
   permanent deletion.
2. **One ACTIVE per (student, section)**: the partial-unique index is rebuilt (migration 0040) to
   `WHERE conversation_kind='lecture_default' AND deleted_at IS NULL`. A soft-delete frees the slot, so
   reopening the lecture creates a FRESH row (not a resurrection). `_existing_lecture_default` excludes
   tombstones.
3. **Current-access-wins (404, never 403)**: the conversation list is filtered by the SAME 4.7 predicate
   as a direct open (`get_visible_student_conversation_list` reuses `get_visible_student_section`'s
   join), so "filtered from list" and "direct open 404" can't diverge — invariant C is structural.
   `_resolve_owned_conversation` returns a pinned 404 for not-owned / soft-deleted / access-revoked on
   open / messages / rename / delete / get-detail.
4. **No resurrection (delete-while-pending)**: `last_activity_at` orders the list and is bumped on
   user-message creation and **successful** assistant completion only. The worker's bump
   (`_bump_conversation_activity`) takes a row lock and returns early if `deleted_at IS NOT NULL`, so a
   worker that completes after a delete updates only its message (never shown — the conversation 404s)
   and never re-surfaces the tombstone.
5. **Titles are never AI-generated** (rule 15): display title is derive-on-read — the manual title when
   `title_source='manual'`, else the lecture/lab title (no backfill for old null-title 8.1 rows). A
   manual rename flips `title_source` and is never overwritten by the derived title.
6. **Send idempotency** is the 8.1 `client_idempotency_key` partial-unique index, unchanged.

## Consequences
- Invariants A–E each carry a backend test (`test_assistant_workspace.py`) + are exercised by the e2e
  gate. The access paths are `/cso`-clean (0 findings).
- Soft-deleted retention is deliberate debt, owned by the post-MVP retention-policy watchlist item.
- Option A uses only the `lecture_default` kind; the `manual/floating_widget/workspace` kinds enumerated
  in ADR-049 remain unused (no migration needed if a later stage uses them).
