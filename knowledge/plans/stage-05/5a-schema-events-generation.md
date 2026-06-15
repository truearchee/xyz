---
type: session-plan
stage: "05"
session: "5a"
slug: schema-events-generation
status: draft-awaiting-approval
created: 2026-06-13
updated: 2026-06-13
spec: knowledge/specs/stage-05/5a-schema-events-generation.md
---

# Session 5a — Implementation Plan — Schema + Event Spine + Quiz Generation

## Linked documents
- Spec: [[specs/stage-05/5a-schema-events-generation]] · Umbrella: [[specs/stage-05/5-shared-quiz-engine-event-spine]]

## Steps (backend-only; each lands with its pytest)
1. **Models** (`platform/db/models/`): `QuizDefinition`, `QuizAttempt`, `StudentAnswer`, `MistakeRecord`
   (min schema), and `platform/events/models.py::StudentActivityEvent` (+ the UNIQUE
   `(user_id, event_type, source_id)`). Question/option ids = uuid7 (OA1: correctness by identity).
2. **Migration 0014** — all five tables + indices (one-active partial-unique on `QuizDefinition` per section;
   the event unique constraint). Assert fresh-DB up/down round-trip (the standing migration test).
3. **Generation primitives**: `prompts/quiz_generation/v1.yaml`; `QuizQuestions` Pydantic `output_schema`;
   `DeterministicTestProvider` `quiz_generation` branch (5×4 canned MCQ, one correct). Unit-test the schema
   validates the canned output via the real `OutputValidator`.
4. **Job + enqueue**: `insert_quiz_job` (idempotent, one-active per section) + wire the enqueue into the
   DETAILED-summary completion path (`_persist_summary_success`, detailed spec only). Test: detailed
   completion enqueues exactly one job; brief does not; re-run is a no-op.
5. **Worker `generate_quiz`**: claim → `gateway.complete` (ONE call) → `_persist_quiz_success`
   (`QuizDefinition` + provenance from `AIRequestLog` + `source_transcript_checksum`) → mark completed;
   failure → `failure_category`, bounded RQ-retry. Test: one `QuizDefinition` with full provenance + exactly
   one gateway call (spy/log-count); failure path marks job, writes no artifact.
6. **`derive_quiz_state`** (pure): unit-test `available` / `available_stale` (checksum mismatch) /
   `generating` / `unavailable` / `not_applicable`.
7. **Gate**: `pytest` green (+N), 0014 round-trip, `tsc` untouched. Report → BACKEND VERIFIED; commit.

## Risks & mitigations
- **R1 one-call discipline** — assert the gateway is invoked exactly once per generation (count `AIRequestLog`
  rows / spy), so no per-question drift creeps in (rule 15).
- **R2 enqueue coupling** — wiring into `_persist_summary_success` must not perturb the summary flow; gate on
  the full backend suite (4.5/4.6/4.7 summary tests stay green) + the one-active idempotency test.
- **R3 deterministic shape drift** — the canned quiz output must satisfy `QuizQuestions` + the
  correctness-by-identity invariant; unit-test the adapter output against the schema (the gate depends on it).
- **R4 migration scope** — one migration creates tables 5b/5c only later write to; verify down-migration drops
  cleanly so a fresh DB isn't half-built.
- **R5 stale logic** — `derive_quiz_state` must reuse the 4.7 read-time checksum compare, not a stored flag
  (umbrella O1); test the mismatch path explicitly.

## Out of scope (5b/5c)
HTTP endpoints + client regen + UI; attempt/scoring/answer/mistake/event WRITES; pagination envelope; retake
behavior; real tool-calling; the browser gate.

## Approval gate
No source edits until the developer approves this spec + plan (and OA1: `content_json` shape / id stability).
