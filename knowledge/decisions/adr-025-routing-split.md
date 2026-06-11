---
type: adr
stage: "4.5"
status: accepted
created: 2026-06-11
updated: 2026-06-11
related-session: knowledge/specs/stage-04/4.5b-brief-summary-real-provider.md
---

# ADR-025 - Routing Split (brief=Cerebras / detailed=Nvidia) and the single-model 4.5b deviation

> Spec label "adr-025-routing-split". Slot 025 was reserved by the 4.5 spec for the routing decision;
> it sits among the transcript ADRs (015–024) by number only.

## Linked documents
- Master spec: [[specs/stage-04/4.5-ai-infra-summary-generation]]
- Spec: [[specs/stage-04/4.5b-brief-summary-real-provider]]
- Report: [[steps/stage-04/4.5b-real-provider-smoke]]
- Related: [[adr-028-llm-gateway-provider-separation]], [[adr-026-prompt-registry-flat-files]]

## Context
The 4.5 design routes the two summaries to two backends for cost/latency separation:

- **brief** → `K2-V2-Instruct` on the **cerebras** route (fast, cheap, short paragraph).
- **detailed** → `K2-Think-v0` on the **nvidia** route (larger, reasoning-capable, structured study notes).

The gateway already encodes this: the prompt YAML carries `model` + `backend`; `ContextBuilder` may
fall back brief Cerebras→Nvidia on over-context; the limiter budgets per backend.

At 4.5b implementation time **neither intended model is accessible**. Only `MBZUAI-IFM/K2-Think-v2`
is verified end-to-end (curl: model id echoed, token usage returned, `reasoning_content` present but
null). This is rule 11 in the flesh — the live deployment exposes a model id different from the
documented one. Model ids are **config** (the prompt YAML `model:` field), so this is a config/spec
deviation, not a rewrite.

Two further honesty gaps surfaced:
- The provider does **not** echo which serving backend (cerebras/nvidia) handled the request. We
  control the *requested* route; we cannot prove the *serving* backend.
- The two routes are not proven to share a context window. We only know both *accepted* a request and
  echoed the same model.

## Decision
1. **Keep the routing split as the target architecture.** The mechanism stays in code.
2. **4.5b deviation — single model for the first real call.** The brief path runs on the one verified
   model. `prompts/brief_summary/v1.yaml` `model:` and `LLM_BRIEF_MODEL_ID` are both set to
   `MBZUAI-IFM/K2-Think-v2` so the model SENT, the routed-fit model, and the logged provenance all
   name one model. `backend` stays `cerebras` = the **requested** route.
3. **Provenance honesty in the schema.** `AIRequestLog.backend_used` is the requested route;
   `AIRequestLog.backend_route_source` records *how we know it* — always `requested` in 4.5b, and it
   flips to `provider_echoed` (no contract change) if the provider ever echoes the served route.
4. **Context-window fallback disabled under the deviation.** `LLM_CONTEXT_FALLBACK_ENABLED=false`
   (real-provider env): an over-limit prompt becomes `invalid_input` rather than rerouting onto an
   unverified window. The fallback mechanism stays in `ContextBuilder`, dormant.
5. **Detailed generation gated off** (`ENABLE_DETAILED_SUMMARY=false`): the inaccessible `K2-Think-v0`
   is never called; no detailed job/log row is created (lands in 4.5c).

## Switch-back trigger
When **both** intended models (`K2-V2-Instruct`, `K2-Think-v0`) become accessible:
- Bump the prompt versions and set `model:` back (brief→`K2-V2-Instruct`, detailed→`K2-Think-v0`);
  reset `LLM_BRIEF_MODEL_ID` / `LLM_DETAILED_MODEL_ID`.
- Re-enable `LLM_CONTEXT_FALLBACK_ENABLED` once route-specific context limits are confirmed.
- Run the deferred dual-model gate-2.B verification (F-4.5-27).
- **No Python change** — this is config + prompt-version bumps by design.

## Deviation log (dated)
```
2026-06-11 (4.5b): brief runs on K2-Think-v2 via the DEFAULT (Cerebras) route. Detailed gated off.
2026-06-11 (4.5c): detailed ALSO runs on K2-Think-v2, via the Nvidia route (metadata.use_nvidia) —
  Option A (nominal route separation; F-4.5-38). The routing split is exercised end-to-end for the
  first time: brief→default/cerebras budget, detailed→use_nvidia/nvidia budget, concurrent, separate
  rule-15 budgets. Same single model serves both; serving backend unverified (backend_route_source=
  'requested'). Detailed is a reasoning task, so the reasoning-lineage K2-Think-v2 is a good fit
  here. Switch-back trigger unchanged: Think-v0 access → detailed_summary model edit only (route
  already use_nvidia).
```

## Consequences
- The first real K2Think call is honest: one verified model, request-asserted backend, no faked
  reasoning level (`reasoning_content` is null → `reasoning_level` logged null, never fabricated).
- Per-backend budget bookkeeping rests on "requested route → that backend's budget" — an assumption,
  acceptable at single-model, single-lecturer, brief-only scale, recorded as F-4.5-28 (watchlist:
  flip `backend_route_source` if the provider ever echoes the route).
- 4.5c forward decision (carry-forward): if access is still pending, both summaries would run on
  `K2-Think-v2` and the routing split collapses to one budget — decide in 4.5c whether to keep nominal
  route separation for bookkeeping or accept single-budget contention.
