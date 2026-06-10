---
type: adr
stage: "4.5"
status: accepted
created: 2026-06-10
updated: 2026-06-10
related-session: knowledge/specs/stage-04/4.5a-platform-llm-foundation.md
---

# ADR-028 - LLMGateway / LLMProvider Separation (rule-6 reconciliation)

> Spec label ADR-018. Renumbered to adr-028 because adr-015..024 already exist (transcript topics).

## Linked documents
- Master spec: [[specs/stage-04/4.5-ai-infra-summary-generation]]
- Spec: [[specs/stage-04/4.5a-platform-llm-foundation]]
- Plan: [[plans/stage-04/4.5a-platform-llm-foundation]]
- Report: [[steps/stage-04/4.5a]]
- Related: [[adr-026-prompt-registry-flat-files]]

## Context
Roadmap rule 6 ("AI is infrastructure, not feature code") names the chain
`LLMProvider → PromptRegistry → ContextBuilder → RateLimiter → AIRequestLog → OutputValidator` and
states that the `LLMProvider` interface defines both `complete()` and `stream()` from day one. Taken
literally, that places orchestration concerns (rendering, budgeting, limiting, logging, validation)
on the provider — which would force every provider (real K2Think and the deterministic test double)
to re-implement the whole chain, and would let a provider be called without the logging/limiting
guarantees the stage exists to enforce.

The stage also imposes a hard ordering: the AIRequestLog table + write path must exist and be
exercised in CI *before* any real K2Think call exists in the codebase.

## Decision
Split the two responsibilities:

- **`LLMGateway`** owns the public contract and all cross-cutting concerns. `complete()` (and the
  day-one `stream()` signature, which raises `NotImplementedError` until Stage 8.3) live here. It
  runs render → open AIRequestLog (status=running) → ContextBuilder.fit → RateLimiter.acquire →
  LLMProvider.send → OutputValidator.validate → close AIRequestLog.
- **`LLMProvider`** is a thin transport adapter only: `send()` and `stream_raw()`. It knows HTTP and
  authentication and nothing else. `K2ThinkProvider` (real, a no-op stub in 4.5a) and
  `DeterministicTestProvider` implement the same Protocol.

`AIRequestLog.open()` is called **before** `ContextBuilder.fit()` so an `invalid_input`
(over-context, detected before transport) is loggable — one row per gateway completion attempt, with
provider fields nullable (Patch A).

## Rationale
- Single place for logging/limiting/validation; a provider physically cannot be invoked outside the
  chain, so Stage 8's streaming pressure cannot become a reason to bypass the gateway.
- Real and deterministic providers are behaviorally identical behind the gateway, so CI exercises the
  full path (render, ContextBuilder, limiter, log, validate) at the provider boundary only (rule 11).
- The intent of rule 6 (everything passes through the chain; stream signature fixed day one) is
  preserved and strengthened; only the *location* of the public contract moves from the provider to
  the gateway.

## Consequences
- Rule 6 is annotated in `knowledge/roadmap.md` in the same commit: the `complete()`/`stream()`
  public contract lives on `LLMGateway`, not `LLMProvider`.
- The 4.5a hard gate holds by construction: `K2ThinkProvider.send` raises `NotImplementedError` and
  no HTTP client is imported in `platform/llm`; the AIRequestLog write path is exercised in CI first.
- Stage 8.3 implements the SSE transport over the existing `stream()`/`stream_raw()` signatures — no
  provider rewrite, no gateway bypass.
