---
type: steps
stage: 12
session: "12f"
slug: real-provider-smoke
status: complete
created: 2026-06-25
updated: 2026-06-25
---

# 12f — Real-provider smoke (rule 11)

> **Status: PASS (2026-06-25).** Ran against the real `api.k2think.ai` with the owner-provided key in `.env`.
> Provider-only rule-11 confirmation (model echo + parseable `GeneratedQuizPool`), reusing the proven
> `backend/scripts/gate3_quiz_pool_smoke.py` — no new code. This is **Gate 3** of the 12f owner-run gates;
> Gate 1 (rule-14 full Playwright) and Gate 2 (`/qa` prod-candidate smoke) are recorded in the 12f report.

## Result — PASS (real `api.k2think.ai`, `quiz_pool_generation/v1`, nvidia / reasoning route)
| Field | Value |
|---|---|
| **Model echo (rule 11)** | **`MBZUAI-IFM/K2-Think-v2`** == expected `MBZUAI-IFM/K2-Think-v2` → **OK** |
| Outcome | **PASS** — validated on **attempt 1** (no retries) |
| Backend route | nvidia (reasoning) |
| Latency | **261.7 s** (under the 330 s reasoning timeout) |
| finish_reason | `length` (ramble-trimmed to the token cap — known F-6e behavior; the pool is still parseable + valid) |
| HTTP status | `200` |
| Output | parseable `GeneratedQuizPool`, **16 questions**, one-correct-per-question OK |
| Usage | prompt 505 / completion 20000 / total 20505 tokens |

## How to run it (owner shell, real key in `.env`)
```bash
set -a; . ./.env; set +a
docker compose run --rm --no-deps -v "$PWD/backend:/app" \
  -e LLM_PROVIDER=k2think -e LLM_API_KEY="$LLM_API_KEY" \
  -e LLM_PROVIDER_BASE_URL="${LLM_PROVIDER_BASE_URL:-https://api.k2think.ai}" \
  -e LLM_CONTEXT_FALLBACK_ENABLED=false \
  backend python scripts/gate3_quiz_pool_smoke.py
```

## Pass criteria (rule 11)
- The route returned a **parseable `GeneratedQuizPool`** AND the **echoed model id matches the prompt-declared
  model id** (`quiz_pool_generation/v1` declares `MBZUAI-IFM/K2-Think-v2`). Both hold → PASS.
- A model-id **MISMATCH is a STOP** (rule 11 catching a deployment/alias drift). Not triggered.
- `finish_reason='length'` (vs 12e's `stop`) is acceptable variance — the reasoning model occasionally rambles
  to the token cap; the pool is still parseable with 16 valid questions (documented F-6e behavior). No code change.

## Notes
- Reuses `backend/scripts/gate3_quiz_pool_smoke.py` (no new code); `--no-deps` provider-only run (no DB/stack).
- **D2 (12f):** the committed `.env.example` `LLM_DETAILED_MODEL_ID` is aligned to `MBZUAI-IFM/K2-Think-v2`; the
  rule-11 echo asserts against the prompt-declared id (also `v2`), so the match is consistent end-to-end.

## Linked documents
- 12f spec / plan / report: [[specs/stage-12/12f-deploy-readiness-mvp-smoke]] · [[plans/stage-12/12f-deploy-readiness-mvp-smoke]] · [[steps/stage-12/12f-deploy-readiness-mvp-smoke]]
- 12f findings: [[steps/findings-12]]
- 12e real-provider smoke (prior run, same script): [[steps/stage-12/12e-real-provider-smoke]]
