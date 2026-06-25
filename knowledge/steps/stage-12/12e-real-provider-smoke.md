---
type: steps
stage: 12
session: "12e"
slug: real-provider-smoke
status: deferred-owner-run
created: 2026-06-25
updated: 2026-06-25
---

# 12e (B2) — D1 pre-warm real-provider confirmation (rule 11)

> **Status: DEFERRED — owner-run.** A fresh workspace has no real `LLM_API_KEY` (`.env` ships
> `LLM_PROVIDER=deterministic`, placeholder key — see [[running-backend-gates]]). The real-provider piece is
> therefore the owner-run half of 12e, exactly like the rule-14 full Playwright gate. **No new code** — it
> reuses the proven Stage 6 quiz-pool smoke. Recorded here so it is tracked and reproducible.

## What B2 confirms
The D1 pre-warm path (`AssessmentScope` create/update → `prewarm_scope_pools` → `ensure_section_pool` →
`generate_section_pool_async`, the `ai`-queue job) makes a section's `section_question_pool` **`ready`**.
Once a scope's pools are `ready`, a student start serves from them with **no ~264s cold generation wait** —
the structural half of that invariant is proven on the deterministic adapter in
[[steps/stage-12/12e-load-performance-check]] (`test_12e_prewarm_warm_pool_serves_without_cold_wait`). B2 is
the **one small real call** that confirms the warming generation actually succeeds against the **real**
configured K2Think provider and **echoes the configured model id** (rule 11).

## How to run it (owner shell, real key exported) — reuses the existing Stage 6 smoke
`backend/scripts/gate3_quiz_pool_smoke.py` already performs exactly this: a real authenticated call through
the production K2Think transport for the `quiz_pool_generation` prompt (the same prompt the pre-warm job
runs), validates the output with the production `GeneratedQuizPool` validator, and asserts the echoed model
id equals the configured id. It mirrors production's **bounded RQ retry** (`AI_RQ_RETRY_MAX`) so a
slow/rambling-but-valid K2-Think-v2 generation does not false-fail (F-6e).

```bash
# From repo root, with the real key exported (never commit it):
docker run --rm \
  -e LLM_PROVIDER=k2think -e LLM_API_KEY="$LLM_API_KEY" \
  -e LLM_PROVIDER_BASE_URL="${LLM_PROVIDER_BASE_URL:-https://api.k2think.ai}" \
  -e LLM_CONTEXT_FALLBACK_ENABLED=false \
  -v "$PWD/backend:/app" -w /app <backend-image> \
  python scripts/gate3_quiz_pool_smoke.py
```

## Pass criteria (rule 11)
- Exit 0 / `PASS`: the route returned a **parseable `GeneratedQuizPool`** and the **echoed model id matches
  the configured identifier** (`LLM_DETAILED_MODEL_ID`, default `MBZUAI-IFM/K2-Think-v2`; pool generation
  uses the nvidia/reasoning route, `_pool_model()`).
- A `MISMATCH` is a **STOP** (rule 11 caught a deployment/alias problem) — do not stamp 12e.
- Auth/config errors (`401/403/4xx`) are terminal, never retried — rotate/fix the key/model config.
- Expect the reasoning route to be **slow by design** (up to the 330s timeout; F-6e). Queue-wait/latency is
  not a failure; the bounded retry already accounts for K2-Think-v2 non-determinism.

## Why this is the warm-pool confirmation
The pre-warm job and this smoke render the **same** `quiz_pool_generation/v1` prompt through the **same**
gateway → provider → validator chain to produce a `ready` pool. A green run proves the real provider warms a
pool with the correct model echo; the deterministic structural test then proves a warm pool serves a student
start with no new generation (no cold wait). Together they discharge the 12e(B) pass envelope.

## Linked documents
- Report: [[steps/stage-12/12e-load-performance-check]]
- Spec: [[specs/stage-12/12e-load-performance-check]]
- Stage spec: [[specs/stage-12/12-release-hardening]] (§5 12e, rule 11)
- Prior smoke pattern: [[steps/stage-06/6d-real-provider-smoke]]
- F-6e timing invariant: [[roadmap]]
