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

## Expected Stage 7 (Glossary) overlap
Glossary's definition generation will add its own `output_schema` member the same way (a new Pydantic
model + a new validator branch + a `GatewayFeature`/feature-CHECK value + a new prompt dir). The only
textual collision points are the two **union hint lines** (`validation.validate` and `gateway.complete`)
and the two **enum lines** (`GatewayFeature`, the `ai_request_logs.feature` CHECK). All four are
add-a-member edits with **no behavioral coupling** — resolve by keeping both members.

## Migrations — RESERVATION (read before adding a Stage 7 migration)
**Stage 6 reserves Alembic revisions `0023`–`0028`.** 6a has landed `0023` (section pools) and `0024`
(mistake-record pool identity); `0025`–`0028` are reserved for 6b–6d (6b's `quiz_definitions` multi-section
+ `assessment_scopes` is `0025`). Stage 6 is at a **single head `0024`**.

**Stage 7 must number its migrations at `0029` or above.** Do NOT take `0023`–`0028`.

Proactive check (2026-06-17, from this branch): the `stage-7` branch is 12 commits ahead of `main` but has
**no migration beyond `0022`** — so there is **no clash today**. The risk is only forward: a Stage 7
migration that naively picks "head + 1" would grab `0023` and collide, producing a second Alembic head at
integration. If Stage 7 has since added a `0023`–`0028` revision, raise it in a findings note now and
renumber to `0029+` before merge — do not discover it at merge.
