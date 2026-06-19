---
id: adr-055
title: Conversation-sourced glossary save — subject-level definition, server-verified provenance
status: accepted
date: 2026-06-19
stage: "8.5"
supersedes: none
---

# ADR-055 — Conversation-sourced glossary save

## Status
Accepted (Stage 8.5).

## Context
Stage 8.5 brings Stage 7's "highlight → save to glossary" flow into the assistant's chat replies. A
student highlights a term in a **completed assistant reply** and saves it; everything downstream
(duplicate detection, the shared definition cache, the background gateway-routed definition job, the
`glossary_term_saved` event, flashcards / Learn–Test) is reused unchanged. Two questions needed a
durable decision:

1. **The definition-context fork (rule-10 escalation).** Stage 7's definition job is NOT purely
   subject-level: `save_service._resolve_definition` derives `context_text` from the highlighted
   `selected_text`, and `translation_service._build_input_text` appends it to the prompt as
   `"Context from the lecture: {context}"` when non-empty. Naïvely reusing that path for a chat save
   would feed **assistant-generated conversation text into the definition prompt** — which the spec
   forbids ("NO assistant conversation/message text in the prompt") and which would make the same term's
   definition depend on which save hit the shared cache first.
2. **How a glossary entry records a chat origin** without the assistant domain writing glossary tables
   (rule 8) and without extending the definition cache key.

## Decision

**D1 — Chat saves get a subject-level definition; no chat text reaches the prompt.** A
conversation-sourced save passes `definition_context=""` to `save_term`, decoupling the **stored**
provenance snippet from the **prompt** context. The definition is generated from term + subject only —
**identical to the existing manual-add (`source_type='manual'`) AI path**, which already passes no
context. Proof this is "no new AI behavior":
- The definition **cache key** (`cache_keys.definition_cache_key`) is
  `{normalizeVersion, normalizedTerm, subjectId, entryType, language}` — it **excludes** context.
- The **input hash** (`cache_keys.definition_input_hash`) **includes** context.
- ⇒ an empty-context chat save produces the **same cache key and the same input hash** as a manual add
  of the same term/subject/language, so it lands on the **same cache row** and shares the **one** model
  call. No new prompt, no new model/route, no cache-key change ⇒ **no new real-provider smoke (rule 11)**.

The highlighted snippet is still **stored** (server-verified, ≤500 chars) on the source reference for
provenance/display — it is metadata, never prompt input.

**D2 — One write path, discriminated source.** The existing `POST /student/glossary/highlight` endpoint
gains an optional `conversation: {conversationId, messageId}` source alongside the flat
`moduleSectionId` (now optional; a model validator requires **exactly one**). The assistant domain gets
no parallel write endpoint and writes no glossary tables. The glossary domain reads the assistant state
it must verify through a new `platform/query` read model
(`assistant_save_source_read.get_conversation_save_source`), never importing the assistant domain
(rule 8) — the same boundary discipline as `student_summary_read.get_visible_student_section`, which it
reuses for the Stage 4.7 published+assigned gate.

**D3 — Source-reference model gains a `conversation` origin (migration 0041).**
`glossary_source_references` adds nullable FKs `source_conversation_id` → `assistant_conversations` and
`source_message_id` → `assistant_messages` (`ondelete=SET NULL`), widens the `source_type` CHECK to
include `'conversation'`, and adds a **partial-unique index**
`uq_glossary_source_references_conversation_message (glossary_entry_id, source_message_id)
WHERE source_type = 'conversation'` so the duplicate-save "attach this chat as another source" path is
**idempotent** (same entry + same message never attached twice). This follows the existing cross-domain
FK precedent in the same table (`source_quiz_attempt_id` → `quiz_attempts`, added in 7a for 7d).

**D4 — Server-verified, pinned-404 anti-spoofing.** The save is verified, never trusted: the message
must be a **completed assistant** message that belongs to the referenced conversation; the conversation
must be **owned** by the caller, not soft-deleted, and **section-bound**; the bound section must be
**published + assigned** (live re-check); and `selectedText` must occur in the message after a
conservative markdown-strip + whitespace-collapse normalization (`glossary/snippet.py`). Subject/folder
are server-derived from the bound section. The 404 family (ownership / existence / binding / visibility)
mirrors the assistant's pinned 404 exactly; role / status / text-mismatch are distinct 4xx that fire
only after ownership is proven, so they leak nothing. Threat model: not arbitrary terms (manual add
already allows those) but **false source attribution** — claiming the assistant said something it didn't.

## Consequences
- No new prompt, model, route, queue, or cache-key change (rule 6 satisfied by reuse); rule-11 smoke not
  required for 8.5 (recorded; revisit only if D1 is ever reversed).
- A chat save of a brand-new term and a manual add of the same term produce byte-identical definition
  inputs → they correctly collapse onto one cache row.
- The glossary domain now holds DB-level FKs into assistant tables (schema coupling), but the **code**
  boundary is preserved via `platform/query` (precedent: the quiz FK). `SET NULL` preserves provenance
  if a conversation/message is later removed; assistant conversations are soft-deleted, so the FK rarely
  fires and the read model is what enforces "soft-deleted → 404".
- The markdown normalizer is deliberately conservative (inline emphasis/code markers only): an
  over-aggressive strip could mask a spoof, while a missed legitimate highlight only yields a clean 422
  (the student can still add the term manually). A fuller markdown-aware comparison is a future option.

## Alternatives considered
- **Feed the highlighted assistant text as context (exact Stage 7 reuse).** Rejected: violates the
  "no conversation text in the prompt" lock, re-opens rule 11, and makes the shared definition depend on
  save order. (The rule-10 escalation; owner chose D1.)
- **Extend the cache key with a conversation/source dimension.** Rejected: explicitly out of scope
  ("cache key NOT extended"); would fragment the shared cache and multiply model calls.
- **A new assistant-domain "save from chat" endpoint.** Rejected (rule 8): the glossary domain owns the
  write; one write path.

## Linked documents
- Spec: [[specs/stage-08/8.5-save-to-glossary]]
- Plan: [[plans/stage-08/8.5-save-to-glossary]]
- Report: [[steps/stage-08/8.5-save-to-glossary]]
- Roadmap: [[roadmap]]
- Reuses: [[decisions/adr-048-glossary-definition-cache-collapse]], [[decisions/adr-047-glossary-subject-folder-separation]], [[decisions/adr-051-assistant-grounding-architecture]]
