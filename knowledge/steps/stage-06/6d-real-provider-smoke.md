---
type: verification-report
stage: "06"
session: "6d"
slug: real-provider-smoke
status: passed
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6d-ui-browser-gate-postclass-retrofit.md
plan: knowledge/plans/stage-06/6d-ui-browser-gate-postclass-retrofit.md
---

# Session 6d — Real-provider quiz-pool smoke

## Linked documents
- Spec: [[specs/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Plan: [[plans/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Report: [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]]

## Result — PASS (rule 11 satisfied)

One real authenticated call to K2Think on the `nvidia` reasoning route through the production
`quiz_pool_generation/v1` prompt succeeded. Provider auth cleared (HTTP 200), the echoed model id equals
the configured prompt model id, and the response validated with the production `GeneratedQuizPool`
validator. The feature path under test is **`quiz_pool_generation` → `quiz_pool`** (`QUIZ_POOL_PROMPT_KEY`
+ `QUIZ_POOL_FEATURE`), the Stage 6 reusable-pool generation route.

## Script

- `backend/scripts/gate3_quiz_pool_smoke.py`

The script renders `quiz_pool_generation/v1`, sends one real `k2think` request on the `nvidia` reasoning
route, validates the response as `GeneratedQuizPool`, and asserts the provider's echoed model id equals
the configured prompt model id. The API key is read from the environment and is never printed; no
Authorization header, request body, key, or summary text is emitted — only redacted evidence plus
PASS/FAIL.

## Verification (real provider call)

The key was placed in the gitignored `.env` (`LLM_API_KEY`, never committed or echoed). The smoke ran
with `LLM_PROVIDER` overridden to `k2think`; the key flowed in from `env_file: .env`. Because the
`kyiv-backend` image is shared across workspaces and has no source bind-mount, the run mounted this
workspace's `backend/` over `/app` (the pattern documented in the script header) rather than rebuilding
the shared image.

```bash
docker compose run --rm --no-deps \
  -e LLM_PROVIDER=k2think \
  -e LLM_CONTEXT_FALLBACK_ENABLED=false \
  -e LLM_DETAILED_TIMEOUT_SECONDS=540 \
  -v "$PWD/backend:/app" -w /app \
  backend python scripts/gate3_quiz_pool_smoke.py

# Stage 6d Gate 3 — quiz pool real-provider smoke (synthetic summary; secrets REDACTED)
#
# --- quiz_pool_generation/v1 (route nvidia / reasoning) ---
#   response model echo : MBZUAI-IFM/K2-Think-v2  (expected MBZUAI-IFM/K2-Think-v2)  -> OK
#   backend_used        : nvidia
#   finish_reason       : 'stop'  ('length' = truncated; 'stop' = complete)
#   elapsed             : 322.4s  (timeout = 540s)
#   usage               : prompt=505 completion=23437 total=23942
#   status_code         : 200
#   parseable           : YES (GeneratedQuizPool, 24 questions)
#   one-correct-per-q   : OK
#
# PASS: quiz pool route returned the configured model id (rule 11) and a parseable pool.
```

## Evidence checklist (all met)

- Provider auth succeeds — HTTP `200`, no `401/403`.
- Model-ID echo matches the configured identifier — `MBZUAI-IFM/K2-Think-v2` == expected.
- Output validates as `GeneratedQuizPool` — 24 questions, exactly one correct option per question.
- `finish_reason: 'stop'` — complete, not truncated.
- Nonzero provider usage printed (`prompt=505 completion=23437 total=23942`); `status_code=200`.
- Feature path = `quiz_pool_generation` / `quiz_pool` (reusable-pool reasoning route).
- No secret material printed; key read from env, never echoed; `.env` is gitignored and not committed.

## Operational finding — reasoning-route timeout

The real K2-Think-v2 pool generation took **322.4s**; the default `LLM_DETAILED_TIMEOUT_SECONDS=240`
timed out twice before the call was given 540s. The contract under test (auth + model echo + payload
validation) is unaffected, but this is a real production watch-item: a 240s detailed/reasoning timeout is
too tight for the large (`max_tokens: 32000`) quiz-pool generation prompt under live K2Think latency.
Carried forward as a watch-item (raise `LLM_DETAILED_TIMEOUT_SECONDS` for the pool route, or confirm the
limiter/backoff buffer covers it) — not a Stage 6 gate blocker. Earlier auth-wall history (placeholder key
→ redacted 401/403) is superseded by this PASS.
