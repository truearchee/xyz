---
type: steps
stage: 12
session: "12e"
slug: real-provider-smoke
status: complete
created: 2026-06-25
updated: 2026-06-25
---

# 12e (B2) — Provider-only real-call confirmation (rule 11)

> **Status: PASS (2026-06-25).** Ran against the **real** `api.k2think.ai` once the owner provided the key in
> `.env`. **No new code** — reused the proven Stage 6 quiz-pool smoke (`backend/scripts/gate3_quiz_pool_smoke.py`).
> **Owner-approved scope amendment (2026-06-25):** B2 is intentionally a **provider-only** rule-11 smoke
> (model echo + clean `GeneratedQuizPool`), not a second DB-backed pre-warm run. The DB-backed
> `prewarm_scope_pools -> ready -> warm start/no cold wait` proof lives in B1 in
> [[steps/stage-12/12e-load-performance-check]].

## Result — PASS (real `api.k2think.ai`, `quiz_pool_generation/v1`, nvidia / reasoning route)
| Field | Value |
|---|---|
| **Model echo (rule 11)** | **`MBZUAI-IFM/K2-Think-v2`** == expected `MBZUAI-IFM/K2-Think-v2` → **OK** |
| Outcome | **PASS** — validated on **attempt 1** (no retries), `GATE3_EXIT=0` |
| Latency | **247.6 s** (under the 330 s reasoning timeout) |
| finish_reason | `stop` (clean; not ramble-trimmed to `length`) |
| HTTP status | `200` |
| Output | parseable `GeneratedQuizPool`, **16 questions**, one-correct-per-question OK |
| Usage | prompt 505 / completion 18360 / total 18865 tokens |

**Model-id resolution note / 12f flag.** The rule-11 expected id is `rendered.model_id` from the
**quiz-pool prompt's own declared model** (`MBZUAI-IFM/K2-Think-v2`), which the real deployment echoed —
match. This is independent of `.env`'s `LLM_DETAILED_MODEL_ID` (set to `MBZUAI-IFM/K2-Think-v0` in this
workspace), which feeds `_pool_model()` / the pool-identity tuple but is **not** what the rule-11 echo asserts
against. Owner disposition: this split is **not a 12e defect**, but it is a **12f config-reconciliation item**
owned by the product owner — align the committed/runtime `.env` model id with the prompt/deployment model in
12f.

> A fresh workspace had no real `LLM_API_KEY` (`.env` ships `LLM_PROVIDER=deterministic`, placeholder — see
> [[running-backend-gates]]); the owner supplied the real key in the gitignored `.env` and B2 was run as below.
> Recorded here so it is tracked and reproducible.

## What B2 confirms
B2 confirms only the **real-provider half** of the pre-warm invariant: the production K2Think transport can
serve the `quiz_pool_generation/v1` prompt, echo the prompt-declared model id, and return a clean parseable
`GeneratedQuizPool` under the bounded retry policy. It deliberately does **not** touch the database, Redis, or
`SectionQuestionPool` rows.

The **DB-backed structural half** is B1 in [[steps/stage-12/12e-load-performance-check]]:
`test_12e_prewarm_warm_pool_serves_without_cold_wait` proves
`prewarm_scope_pools -> ensure_section_pool -> generate_section_pool_async -> ready`, then proves a warm
student start reuses the ready pool with **no new generation enqueued** (no ~264s cold wait). Owner decision:
splitting the proof across B1+B2 is acceptable at single-course MVP scale.

## How to run it (owner shell, real key exported) — reuses the existing Stage 6 smoke
`backend/scripts/gate3_quiz_pool_smoke.py` performs the provider-only half: a real authenticated call through
the production K2Think transport for the `quiz_pool_generation` prompt (the same prompt the pre-warm job
renders), validates the output with the production `GeneratedQuizPool` validator, and asserts the echoed
model id equals the prompt-declared id. It mirrors production's **bounded RQ retry** (`AI_RQ_RETRY_MAX`) so a
slow/rambling-but-valid K2-Think-v2 generation does not false-fail (F-6e).

```bash
# From the repo root, with the real key exported (never commit it). Uses the `backend` compose service
# (image `kyiv-backend`); the bind-mount guarantees current source; --no-deps because the smoke calls the
# provider directly (no DB/Redis needed). Env-var names verified against config.py.
export LLM_API_KEY="…the real IFM/K2Think bearer token…"
docker compose run --rm --no-deps -v "$PWD/backend:/app" \
  -e LLM_PROVIDER=k2think \
  -e LLM_API_KEY="$LLM_API_KEY" \
  -e LLM_PROVIDER_BASE_URL="${LLM_PROVIDER_BASE_URL:-https://api.k2think.ai}" \
  -e LLM_CONTEXT_FALLBACK_ENABLED=false \
  backend python scripts/gate3_quiz_pool_smoke.py
```

> Equivalent canonical form (from the script's own docstring): `docker run --rm … -v "$PWD/backend:/app"
> -w /app kyiv-backend python scripts/gate3_quiz_pool_smoke.py`. If the image is stale, `docker compose
> build backend` first (the bind-mount above already overrides source, so it is optional).

## Pass criteria (rule 11)
- Exit 0 / `PASS`: the route returned a **parseable `GeneratedQuizPool`** and the **echoed model id matches
  the prompt-declared model id** (`quiz_pool_generation/v1` currently declares `MBZUAI-IFM/K2-Think-v2`).
- A `MISMATCH` is a **STOP** (rule 11 caught a deployment/alias problem) — do not stamp 12e.
- Auth/config errors (`401/403/4xx`) are terminal, never retried — rotate/fix the key/model config.
- Expect the reasoning route to be **slow by design** (up to the 330s timeout; F-6e). Queue-wait/latency is
  not a failure; the bounded retry already accounts for K2-Think-v2 non-determinism.

## Why this completes the split B proof
The pre-warm job and this smoke render the **same** `quiz_pool_generation/v1` prompt through the same
provider/validator contract. A green B2 proves the real provider can produce a valid pool payload with the
expected model echo; B1 proves the DB-backed pre-warm job persists that kind of payload as a ready pool and
that a warm student start reuses it. Together they discharge the 12e(B) pass envelope without spending a real
provider call on a duplicate DB-backed run.

## Change history
- 2026-06-25 15:04 +04 — Owner-approved docs amendment after pre-landing review: clarified B2 is
  provider-only rule-11 evidence, not a DB-backed pre-warm run; model-id split tracked for 12f.

## Linked documents
- Report: [[steps/stage-12/12e-load-performance-check]]
- Spec: [[specs/stage-12/12e-load-performance-check]]
- Stage spec: [[specs/stage-12/12-release-hardening]] (§5 12e, rule 11)
- Prior smoke pattern: [[steps/stage-06/6d-real-provider-smoke]]
- F-6e timing invariant: [[roadmap]]
