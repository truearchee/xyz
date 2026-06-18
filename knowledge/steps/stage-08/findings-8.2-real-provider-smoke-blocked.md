---
type: finding
stage: 08
session: "8.2"
slug: real-provider-smoke-blocked
status: resolved
created: 2026-06-18
updated: 2026-06-18
---

> **RESOLVED 2026-06-18.** The env owner provided a real K2 key (via env only, never committed). The smoke
> ran GREEN: model echo `MBZUAI-IFM/K2-Think-v2` matched on both turns and the real K2-Think-v2 emitted a
> valid `isStudyRelated` (true for the study question, false for off-topic). Stage 8.2 flipped to FULLY
> VERIFIED. See [[steps/stage-08/8.2-real-provider-smoke]]. The body below records why it was blocked.

# Finding (8.2) — real-provider smoke (rule 11) is BLOCKED on a missing real K2 API key

The Stage 8.2 close requires a real-provider smoke (rule 11: assert the configured model-ID echoes from
the live provider) before flipping FULLY VERIFIED. **It could not be run in this session: there is no real
`LLM_API_KEY` available.**

- The committed `.env` carries the `.env.example` placeholder (`your-llm-api...`).
- The host shell has `LLM_API_KEY` unset; no `.env.local`/secrets file is present.
- The 8.1 smoke (which PASSED, model echo `MBZUAI-IFM/K2-Think-v2`) was run with a real key injected into
  a one-off `k2think` container — the key was never committed, and it is not present in this workspace now.

This is an environment/credential gap, NOT a code failure. Per the acceptance rule I am stopping at the
smoke rather than working around it (the deterministic provider is the boundary double; faking a real
echo would defeat rule 11).

## Ready to run the moment a real key is available
A smoke script is committed and ready: `backend/scripts/gate8_assistant_smoke.py`. It makes real
authenticated `assistant/v2` calls through the production `K2ThinkProvider`, asserts the model-ID echo
(the rule-11 hard gate), and ALSO exercises the one 8.2-specific risk (R-isStudyRelated): whether the real
K2-Think-v2 reliably emits the REQUIRED structured `isStudyRelated` flag (study question → true, off-topic
→ false). Run it (operator shell, real key exported or in `.env`):

```bash
docker compose run --rm -e LLM_PROVIDER=k2think -T backend python scripts/gate8_assistant_smoke.py
```

Expected PASS: `response model echo : MBZUAI-IFM/K2-Think-v2 (expected MBZUAI-IFM/K2-Think-v2) -> OK` and
a parseable `AssistantGroundedAnswer` for both cases. The `isStudyRelated` correctness is a SOFT signal
(the model's judgment is MVP-accepted; the threshold + decision order are the deterministic backbone) —
log the observed values in [[steps/stage-08/8.2-real-provider-smoke]].

## Until then
Stage 8.2 is **built + backend-verified + browser-gated + full-suite-green + /cso-clean**, but NOT FULLY
VERIFIED — the real-provider smoke is the one remaining gate, pending the key. Do not flip the roadmap
Stage 8 line to "8.2 FULLY VERIFIED" until the smoke is GREEN.

## Action for the env owner
Provide a real K2 `LLM_API_KEY` (or run the script above) so the 8.2 smoke can complete. Consider a
documented, gitignored local secrets path so the rule-11 smoke is runnable per-workspace without
re-injecting the key each time.
