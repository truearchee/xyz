# ADR-056 — Assistant modes: `conversation_kind` as the mode discriminator, a strategy coordinator, immutability, and per-mode context snapshot

- **Status:** Accepted (Stage 8.6a, 2026-06-20)
- **Supersedes / relates to:** extends [[adr-048-glossary-definition-cache-collapse]] is unrelated; builds on
  [[adr-049-assistant-conversation-list-data-shape]], [[adr-051-assistant-grounding-architecture]],
  [[adr-054-assistant-conversation-management-contract]].
- **Number note:** Stages 10/11 are authoring ADRs in parallel; 056 claimed at 8.6a commit time. If a
  collision is found at merge, renumber this one (it has no external references yet).

## Context
Stage 8.6 adds three task-specific assistant *modes* (homework help, exam prep, time management). The
assistant already routes every turn through ONE seam — `generate_assistant_answer_async` (8.1/8.2):
claim → resolve+retrieve → ONE gateway call at interactive priority → `decide_grounding` → persist +
generation-time `context_snapshot`. The four existing `conversation_kind` values
(`lecture_default/manual/floating_widget/workspace`) are all the same general-chat behavior.

We needed a way to add per-mode behavior (prompt, context assembly, route) WITHOUT forking that seam,
without new gateway/provider code (rule 6), and without letting a conversation silently change behavior
mid-thread.

## Decision
1. **Mode = `conversation_kind`.** New kinds are added to the existing CHECK constraint (8.6a:
   `homework_help`; 8.6b/8.6c add `exam_prep`/`time_management`). The four legacy kinds keep mapping to the
   existing lecture-grounded behavior.
2. **A strategy coordinator, ONE call, ONE persist.** `generate_assistant_answer_async` dispatches by kind
   to a `_MODE_TURN_BUILDERS` map (default = the extracted-verbatim `_lecture_turn`). Each builder returns a
   `_ModeTurn` — either a `_ShortCircuit` (no gateway call) or a `_GatewayTurn` carrying
   `(prompt_key, output_schema, blob, section_type, grounding inputs, resolution, snapshot_extra)`. The
   coordinator owns the single `gateway.complete(... priority="interactive", feature="assistant")`, the
   shared `decide_grounding`, and the shared `_persist_grounded_answer`. Adding a mode = adding a builder;
   the call/persist path is never touched again.
3. **`conversation_kind` is IMMUTABLE.** It is set once at creation and never read from a request body on
   any update path (rename writes only `title`/`title_source`). A backend test asserts no path mutates it.
   The UI shows the mode as a non-editable LABEL.
4. **Idempotent creation = a natural-key resume-or-create** (not a client key). Homework: partial-unique
   indexes give one active conversation per `(student, module[, section])`; a double-clicked starter resumes
   the existing chat (`IntegrityError` → re-read the winner), mirroring the `lecture_default` pattern.
5. **Per-mode context snapshot** rides the existing per-message `context_snapshot` JSONB (no migration). The
   coordinator merges `snapshot_extra` (`{"mode", "selectedModuleId", "selectedSectionId?", "retrievalScope",
   …}`) so a revisited chat stays understandable and the student-safe answer-basis line is mode-aware.
6. **`feature="assistant"` is kept for all modes** — no `ai_request_logs.feature` CHECK widening. The mode is
   attributable via the distinct `prompt_version` (e.g. `homework_help/v1`) + the snapshot `mode` key, the
   same way summaries split brief vs detailed within shared infra. Saves a migration per sub-stage.

## Consequences
- 8.6b/8.6c add ONLY a strategy builder + a prompt (+ the read models their context needs) — the proven
  8.2 seam, gateway chain, grounding, and persist are reused unchanged. The full 8.2 lecture behavior is
  byte-identical (53 existing assistant tests + the new mode tests both green).
- Module-bound (sectionless) homework conversations required making the conversation list/detail/visibility
  reads section-OR-module aware (a `get_visible_student_module` read + a section-OR-module list query that
  keeps the section-bound path identical) — recorded so 8.6b/8.6c reuse it.
- `conversation_kind` is now overloaded as both "entry point" (the 4 legacy values) and "behavioral mode"
  (the 3 new values); the coordinator's default-to-lecture map keeps that benign.
- Cost-by-mode is a `prompt_version` join, not a `feature` filter — acceptable and documented.
