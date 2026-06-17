---
type: real-provider-smoke
stage: "05"
session: "5d"
slug: real-provider-smoke
status: PASS
created: 2026-06-16
updated: 2026-06-16
---

# Stage 5d — Real-Provider Smoke (Quiz Generation) — rule 11

**Status: PASS — recorded 2026-06-16 (agent-run against the configured provider, synthetic summary only).**

## What it proves
ONE real authenticated call through the production `K2ThinkProvider` on the reasoning route
(`backend=nvidia`) for `post_class_quiz_generation/v1`, validated by the production `OutputValidator`
(`PostClassQuiz`). The **rule-11 assertion is LIVE**: the echoed model id must equal the CONFIGURED
identifier (`LLM_DETAILED_MODEL_ID`), not the slice-documented `K2-Think-v0` — catching a silent alias
mismatch. Script: `backend/scripts/gate3_quiz_smoke.py` (mirrors the 4.5d `gate3_smoke.py`).

## Command
```bash
docker run --rm --network test2_default \
  -e LLM_PROVIDER=k2think -e LLM_API_KEY="$LLM_API_KEY" \
  -e LLM_PROVIDER_BASE_URL=https://api.k2think.ai -e LLM_CONTEXT_FALLBACK_ENABLED=false \
  -v "$PWD/backend":/app -w /app <backend-image> python scripts/gate3_quiz_smoke.py
```

## Evidence (redacted; no key/body/summary text emitted)
```
--- post_class_quiz_generation/v1 (route nvidia / reasoning) ---
  response model echo : MBZUAI-IFM/K2-Think-v2  (expected MBZUAI-IFM/K2-Think-v2)  -> OK   ← rule 11 LIVE
  backend_used        : nvidia
  finish_reason       : 'length'   (consumed the 8000-token budget — see observation)
  elapsed             : 104.1s  (timeout = 600s)
  usage               : prompt=499 completion=8000 total=8499
  status_code         : 200
  parseable           : YES (PostClassQuiz, 10 questions)
  one-correct-per-q   : OK

PASS: quiz route returned the configured model id (rule 11) and a parseable 10-question quiz.
```

## Re-confirm at max_tokens=16000 (F-5d-1 fix) — PASS, `finish_reason='stop'`
After raising `post_class_quiz_generation/v1` `max_tokens` 8000→16000 (F-5d-1), the smoke was re-run:
```
response model echo : MBZUAI-IFM/K2-Think-v2  (expected MBZUAI-IFM/K2-Think-v2)  -> OK   ← rule 11 LIVE
finish_reason       : 'stop'    (COMPLETE — no longer truncated)
usage               : prompt=499 completion=11350 total=11849   (11350 < 16000 budget)
parseable           : YES (PostClassQuiz, 10 questions);  one-correct-per-q: OK;  status 200; 149.0s
PASS
```
The reasoning model now finishes the JSON within budget — the F-5d-1 truncation is empirically resolved.

## Observation (original run at 8000 — now superseded by the 16000 fix)
`finish_reason='length'` — the reasoning model spent the full `max_tokens: 8000` and was truncated. The
output STILL validated (10 questions, exactly one correct each), so the JSON completed within budget on
this synthetic summary. But a denser/longer detailed summary could truncate mid-JSON → `invalid_output`
→ a generation failure that RQ-retries then fails (recoverable, Start Over available). **Watch item:**
if real quizzes show `invalid_output` from truncation under load, raise the quiz prompt's `max_tokens`
(or shrink the summary-text input). Not blocking — the validator + retry + Start Over handle it; this is
the cohort-burst capacity surface the spec already flags for an ADR if it bites.

## Caveats
- Agent-run with the key already present in the environment (the operator should re-run after any key
  rotation per the 4.5d runbook). Synthetic summary only — no student/production data sent to IFM.
- This is the **Gate 3** half of Stage 5d. Gate 1 (the full active Playwright browser gate) also passed;
  see the 5d step report for that evidence.
