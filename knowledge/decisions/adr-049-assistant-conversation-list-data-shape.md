---
type: adr
stage: "8"
status: accepted
created: 2026-06-18
updated: 2026-06-18
related-session: knowledge/specs/stage-08/8.1-conversation-foundation.md
---

# ADR-049 — Assistant conversation data shape (8.4-ready) + lecture_default uniqueness

## Linked documents
- Spec: [[specs/stage-08/8.1-conversation-foundation]]
- Report: [[steps/stage-08/8.1-conversation-foundation]]

## Context
The finished assistant (8.4) is a ChatGPT-style window with a conversation-list sidebar; any conversation
may be attached to a lecture. Stage 8.1 builds only the lecture entry point, but the data must be shaped so
8.4 grows on top with no migration. The lecture entry must also be race-safe (two tabs pressing "Start
chat" cannot create duplicates) without blocking multiple conversations per lecture later.

## Decision
- `assistant_conversations` is a **list per student**: `conversation_kind` CHECK
  `('lecture_default','manual','floating_widget','workspace')` (all four enumerated now so 8.4 needs no
  migration) + an **optional** `attached_section_id` (nullable for the future unattached/manual case).
- One `lecture_default` per `(student, section)` is enforced by a **partial-unique index scoped to that
  kind only**: `unique(student_id, attached_section_id) where conversation_kind = 'lecture_default'`.
  `manual`/`floating_widget`/`workspace` carry no such constraint → multiple conversations per lecture
  remain possible in 8.4 with no migration.
- "Start chat" = get-or-create under that index; an IntegrityError on the race re-reads the winner (a DB
  rejection is never surfaced as a user error), mirroring the quiz `_get_or_create_definition` pattern.
- `assistant_messages` carry an explicit lifecycle (`pending → completed | failed`; 8.3 widens to add
  `streaming/partial/cancelled`), the standard AI provenance set + `ai_request_log_id` (rule 6), a
  nullable `grounding_status` (null in 8.1, populated by 8.2), and a `client_idempotency_key` with a
  partial-unique index on `(conversation_id, client_idempotency_key) where role='user'` for double-send
  safety (decision 8). A retry re-activates the failed assistant row and never duplicates the user message.

## Consequences
- 8.4 (sidebar, manual/widget/workspace conversations) is a pure additive build on this schema.
- 8.2 needs no migration (`grounding_status` already present).
- Migration `0032` (block 0032–0037); `down_revision` rebased onto the live head before PR (Stage 9 parallel).
