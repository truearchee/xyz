# Findings — Stage 6 additive touches to shared `platform/llm` (coordinate with Stage 7)

> Per the Stage 6 spec's parallel-development rule and roadmap rule 10: Stage 6 does **not** change any
> shared **contract** (the Redis limiter interface, the PromptRegistry interface, the `ai` queue/worker
> shape, the pagination envelope). It makes only **additive** extensions to the shared `platform/llm`
> output-schema dispatch. This note enumerates them so the Stage 6 ↔ Stage 7 merge is a trivial rebase,
> not a semantic conflict. Both stages add their own member to the same enums/unions; neither edits the
> other's branch.

## Additive extensions landed in 6a

| File | Change | Nature |
|---|---|---|
| `app/platform/llm/models/quiz.py` | new `GeneratedQuizPool` Pydantic model + `QUIZ_POOL_SCHEMA_VERSION` | new symbol |
| `app/platform/llm/validation.py` | new `_validate_quiz_pool` / `_validate_quiz_pool_object` branch + `QUIZ_POOL_*` constants; widened `validate()` `output_schema` union hint | new branch; the `PostClassQuiz` exactly-10 path is byte-for-byte untouched |
| `app/platform/llm/gateway.py` | widened `complete()` `output_schema` union hint + `CompletionResult.parsed` union | type hints only — not a registry |
| `app/platform/llm/models/prompt.py` | `GatewayFeature` Literal `+= "quiz_pool"` | enum widening (the 5b precedent that added `post_class_quiz`) |
| `backend/alembic/versions/0023_*` | `ai_request_logs.feature` CHECK widened to include `'quiz_pool'` | enumerated CHECK widening (the 0020 precedent) |
| `app/platform/llm/provider.py` | `DeterministicTestProvider` gains a `quiz_pool_generation` fixture | test-double canned output (the established per-prompt pattern) |
| `backend/prompts/quiz_pool_generation/v1.yaml` + `CHECKSUMS.json` | NEW prompt dir + its drift-guard baseline entry | new prompt only — summary/quiz/glossary prompts untouched |

## Shared event-type / AIRequestLog feature-name REGISTRY (Stage 7 — official pattern, locked 2026-06-17)
Stage 7 introduces a **single shared source-of-truth list** for `student_activity_events.event_type` and
`ai_request_logs.feature` names, with **union-aware CHECK migrations** and a **CI test asserting the
constraint equals the union of all stages' values**. This is now the official pattern for BOTH stages —
spec v2's coordination section forbids forking it.

**Why it matters mechanically:** each migration that touches the feature/event CHECK **rewrites it
wholesale**. A name that is not in the shared list gets **silently dropped** by whoever writes the next
such migration. Stage 7's CI union test is the guard; Stage 6's only job is to ensure its names live in
that one list.

**Stage 6 rules:**
- **Register every event-type / feature name through the shared list.** Do NOT keep a second copy in the
  quiz domain. When Stage 7's shared list lands in the integration branch, **point the references at it**.
- **6a reconcile item (NOT a 6a reopen — a small 6b/6c cleanup):** 6a hard-coded the AIRequestLog feature
  `'quiz_pool'` in two places that will reconcile to the shared list at integration — (a)
  `GatewayFeature` Literal in `app/platform/llm/models/prompt.py`, (b) the `ai_request_logs.feature` CHECK
  in migration `0023`. Both are correct + isolated today; when the shared list exists, repoint them so the
  union migration cannot drop `'quiz_pool'`.
- **Events (6c):** `completed_quiz` / `perfect_quiz_score` are **Stage 5's existing types** — 6c only adds
  METADATA (mode + `source_scope` section ids), NOT new types. 6c must read those names **from the shared
  list**, not a local copy.
- **Sequencing (rule 10):** if 6c needs to register a name **before** the shared list exists in this
  branch, do **not** pre-empt it with a local constant — write a findings note and let the two stages be
  ordered. (6c is expected to add no NEW feature/event name beyond the existing `quiz_pool` + the Stage 5
  event types, so this should not bite; flag if it does.)
- **6b introduces NO new event/feature name.** `assessment_scopes.status` (`active|locked`) is a domain
  enum, not part of the shared registry; pre-warm reuses the existing `quiz_pool` feature.

## Expected Stage 7 (Glossary) `platform/llm` overlap
Glossary's definition generation will add its own `output_schema` member the same way (a new Pydantic
model + a new validator branch + a `GatewayFeature`/feature value + a new prompt dir). The textual
collision points are the two **union hint lines** (`validation.validate` and `gateway.complete`); the
feature/event **names** are reconciled via the shared registry above, not by ad-hoc enum edits. Resolve by
keeping both members.

## Migrations — RESERVATION (updated 2026-06-17 per Stage 7 lock)
**Stage 6 holds Alembic revisions `0023`–`0029`.** 6a landed `0023` (section pools) + `0024` (mistake-record
pool identity); `0025`–`0029` are reserved for 6b–6d (6b's `quiz_definitions` multi-section +
`assessment_scopes` is `0025`). Stage 6 stays **at or below `0029`**; single head `0024` today.

**Stage 7 owns `0030` + `0031`** (incl. its feature/event union migration). The branches diverged (Stage 7
branched earlier), so **expect a small merge migration at integration** to reconcile the two heads — normal
parallel-work housekeeping, recorded on both findings notes.

Proactive check (2026-06-17): the `stage-7` branch is 12 commits ahead of `main` but has **no migration
beyond `0022`** — **no clash today**. If Stage 7 ever claims a revision inside `0025`–`0029`, raise it now,
not at merge.
