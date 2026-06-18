---
type: adr
stage: "8"
status: accepted
created: 2026-06-18
updated: 2026-06-18
related-session: knowledge/specs/stage-08/8.2-context-retrieval.md
---

# ADR-051 — Assistant grounding: exact-scan retrieval, backend-derived status, generation-time snapshot

## Linked documents
- Spec: [[specs/stage-08/8.2-context-retrieval]]
- Plan: [[plans/stage-08/8.2-context-retrieval]]
- Report: [[steps/stage-08/8.2-context-retrieval]]

## Context
The assistant must answer grounded in ONE lecture's material, be honest when a question is off-lecture,
and never leak unpublished or raw-transcript content — driven by a `groundingStatus` that is trustworthy
and auditable. The answer text (model prose) is not a trustworthy grounding signal, and a transcript can
be replaced after an answer is given.

## Decision
- **Server-side context resolver.** The lecture is resolved from the conversation's STORED
  `attached_section_id` (never a client id), re-checking access on every turn. A tampered/forged section
  id is structurally impossible.
- **Exact pgvector scan, scoped + same-model.** `platform/query/assistant_retrieval_read.py` runs an
  exact cosine scan (`<=>`, NO ANN index) over the section's active-transcript chunks, joined through the
  SAME published+assigned visibility gate as 4.7, filtered to the configured embedding model/version,
  bound parameters only. Context = NORMALIZED chunks (capped per-chunk + total), never the raw transcript
  file or verbatim segments, never summaries-as-prose.
- **`groundingStatus` is BACKEND-DERIVED, never parsed from prose.** A pure `decide_grounding(section_
  visible, ready, is_study_related, has_relevant_chunk)` evaluates a FIXED precedence:
  `access_denied → context_unavailable → educational_redirect → lecture_grounded → general_not_from_
  lecture`. The redirect is checked BEFORE the chunk match, so an unrelated question can never become
  grounded on an accidental weak match. The only model signal is one required structured flag
  `isStudyRelated`; a missing/malformed flag fails the turn (`invalid_output`, retryable) with
  `grounding_status` left NULL — never a misleading label.
- **One gateway call per answered turn.** The query is embedded LOCALLY; exactly one INTERACTIVE gateway
  call returns the answer + `isStudyRelated`. `context_unavailable` / `access_denied` short-circuit with
  NO gateway call → NO AIRequestLog row (the chosen, tested convention).
- **Generation-time context snapshot.** At completion the worker writes a server-only
  `assistant_messages.context_snapshot` JSONB (module/section ids+titles, active transcript id + source
  checksum, retrieved chunk refs {chunkId, distance, tokenCount}, threshold, embedding model/version,
  retrieval config version, groundingStatus, prompt/model). The student-facing "Where did this come
  from?" basis is composed ONLY from that snapshot (titles + honest static text) — never chunk ids,
  distances, checksums, prompts, or reasoning. A later transcript replacement cannot make a past answer's
  trace lie.

## Consequences
- Grounding is deterministic + auditable; the security tests (prompt-injection ×2, raw-transcript canary,
  malformed-output fail-safe, ownership/tamper) and a focused `/cso` pass all hold.
- 8.3's `message_end` can carry the finalized `groundingStatus` + basis with no rework; a retried turn
  recomputes retrieval/grounding freshly (the old snapshot is overwritten) and never duplicates the user
  message.
- Threshold + config are versioned (`RETRIEVAL_CONFIG_VERSION`) and stamped per answer, so recalibration
  is auditable. No new endpoint / OpenAPI change — `MessageRead` already exposes `groundingStatus` +
  `answerBasis`.

## Alternatives considered
- Parse grounding from the model's prose — rejected (untrustworthy, spoofable, drifts).
- ANN index — rejected for MVP (one lecture is small; exact scan is correct + simpler; spec says no ANN).
- Re-derive the basis from a fresh join at read time — rejected (a transcript replacement would rewrite
  history; the snapshot freezes the truth at generation time).
