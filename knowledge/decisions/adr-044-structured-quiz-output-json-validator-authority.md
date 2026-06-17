---
type: adr
stage: "5"
status: accepted
created: 2026-06-16
updated: 2026-06-16
related-session: knowledge/specs/stage-05/5b-quiz-generation-recovery.md
---

# ADR-044 — Structured quiz output via the JSON path; OutputValidator is the authority

> Stage 5 spec ADR label "(C)". Remapped to repo slot adr-044.

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- Report: [[steps/stage-05/5b-quiz-generation-recovery]]
- Related: [[adr-045-airequestlog-decoupled-gateway-generalized]]

## Context
The Stage 5 spec allowed tool/function-calling per the IFM reference OR the existing structured-JSON
path — "code wins over docs." The codebase's 4.5 provider uses **JSON-mode** (`response_format=
{"type":"json_object"}` when enabled) + tolerant brace-balanced extraction + last-valid-object
selection (for reasoning-lineage models that think inline) + Pydantic validation. There is no
function-calling path.

## Decision
- Quiz generation uses the **existing JSON path** — no function-calling added. `PostClassQuiz`
  (`app/platform/llm/models/quiz.py`) is the Pydantic schema; the deterministic adapter emits a
  schema-conformant fixture; the real K2-Think-v2 call relies on the same tolerant-extract validator.
- **OutputValidator is the AUTHORITY regardless of mechanism.** `_validate_quiz_object` enforces
  STRUCTURE (exactly 10 questions; exactly `optionsPerQuestion` options; exactly one `isCorrect`; no
  empty/duplicate option or question text; explanation present) and SIZE (payload ≤64 KB, questionText
  ≤1000, option ≤500, explanation ≤2000). **Escape-not-reject:** raw `<`/`>` are stored faithfully
  (legitimate math/code) — escaping is the UI's job at render time; the validator NEVER rejects content
  for angle brackets.

## Consequences
No new transport mechanism; the validator is a single, mechanism-independent gate, so a future switch to
function-calling changes only the provider, not the contract. Verified by the validator unit tests
(valid + wrong-count + multiple-correct + angle-bracket preservation) and the end-to-end invalid-output
path (forced-invalid fixture → `invalid_output`).
