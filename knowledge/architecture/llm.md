---
type: architecture
stage: "4.5"
created: 2026-06-10
updated: 2026-06-10
related-session: knowledge/specs/stage-04/4.5a-platform-llm-foundation.md
---

# platform/llm — AI Gateway Architecture

## Linked documents
- Master spec: [[specs/stage-04/4.5-ai-infra-summary-generation]]
- Spec: [[specs/stage-04/4.5a-platform-llm-foundation]]
- Report: [[steps/stage-04/4.5a]]
- Decision: [[decisions/adr-028-llm-gateway-provider-separation]]
- Decision: [[decisions/adr-026-prompt-registry-flat-files]]
- Architecture: [[architecture/worker]] · [[architecture/db-spine]]

## Shape
`backend/app/platform/llm/` is infrastructure consumed by domains (rule 8); a feature job calls
`LLMGateway.complete()` and never touches a provider, limiter, or log directly.

```
domain job handler (summary_service)
  → LLMGateway.complete(prompt_key, output_schema, context_refs, priority, feature)
      registry.render → AIRequestLog.open(running)  ← BEFORE any check (Patch A)
        → ContextBuilder.fit (estimate + route)  → InvalidInput closes invalid_input (no transport)
        → RateLimiter.acquire (TTL lease)        → RateLimited closes rate_limited
        → LLMProvider.send                       → ProviderTransient closes provider_transient
        → OutputValidator.validate               → InvalidOutput closes invalid_output
      → AIRequestLog.close(succeeded, usage) → CompletionResult
```

| module | responsibility |
|---|---|
| `gateway.py` | `LLMGateway` — the only orchestrator; `complete()` (async) + day-one `stream()` (raises until 8.3) |
| `provider.py` | `LLMProvider` Protocol (`send`/`stream_raw`); `K2ThinkProvider` (stub, no call in 4.5a); `DeterministicTestProvider` (+ E2E-only fault injection) |
| `registry.py` | `PromptRegistry` — flat-file load + startup validation + content hashing (adr-026) |
| `limiter.py` | `RedisRateLimiter` — RPM/TPM/concurrency per backend; TTL leases; priority headroom |
| `context.py` | `ContextBuilder` — D2 conservative estimator (`chars/3.5`); route selection + brief→Nvidia fallback |
| `validation.py` | `OutputValidator` — brief length/refusal; detailed required sections; lab→labNotes |
| `logging.py` | `AIRequestLog.open/close` — gateway-attempt semantics, hashes only, independent commit |
| `errors.py` | `InvalidInput`/`RateLimited`/`ProviderTransient`/`InvalidOutput`/`GatewayFailed` |
| `models/` | `PromptKey`, `RenderedPrompt`, `BriefSummary`, `DetailedSummary` |

## Provenance chain
`AIRequestLog` = one row per gateway completion attempt (provider fields nullable; retries open a new
row). On success, `GeneratedLectureSummary` copies `modelId`, `promptVersion`, `promptContentHash`,
`backendUsed`, `reasoningLevel` directly from the log row and stores `aiRequestLogId` (FK NOT NULL),
plus `sourceTranscriptChecksum` + `inputHash`. Failures never produce a summary row.

## Routing (adr-025, fully exercised in 4.5b)
Brief → `K2-V2-Instruct`/Cerebras by default, falling back to `K2-Think-v0`/Nvidia only when the prompt
exceeds the Cerebras window; detailed → `K2-Think-v0`/Nvidia always. Over both windows → `invalid_input`
(D3, no truncation). In 4.5a the route is selected and logged but the transport is the deterministic
provider.

## Boundaries (4.5a)
- No real K2Think HTTP call exists: `K2ThinkProvider.send` raises `NotImplementedError`; `platform/llm`
  imports no HTTP client. The AIRequestLog write path is exercised in CI first (rule 6 hard ordering).
- Prompts live at `backend/prompts/` (build-context constraint; see adr-026). The drift guard runs in
  pytest and as `python -m tests.ci.prompt_drift_guard`.
