---
type: adr
stage: "4.8"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.8-first-hosted-deploy-staging.md
---

# ADR-043 — Ship an internal SSE probe to validate proxy streaming now (spec Decision C1)

> Spec label "Decision C1". Locked in spec §4 with escape hatch C2; recorded BEFORE code.

## Linked documents
- Spec: [[specs/stage-04/4.8-first-hosted-deploy-staging]]
- Related: [[adr-042-browser-backend-transport-direct]] (the probe runs over the D1 transport), [[adr-040-compute-topology-flyio]] (validates Fly's edge does not buffer event-stream)

## Context
The entire reason Stage 4.8 exists before Stage 12 is the forcing function: **SSE breaks under
buffering proxies, and discovering that in Stage 8.3 (the assistant stream) is expensive.** But the
MVP has **no product SSE endpoint yet** — Stage 8.3 owns that transport. So there is nothing in the
shipped product to stream against during the staging smoke. We must either manufacture a streaming
signal now (C1) or assert the proxy is SSE-safe by reasoning alone (C2).

## Decision
- **C1: ship a tiny, env-gated `/internal/sse-probe`** and validate it from the staging browser over
  the app's real transport (ADR-042 / D1). Constraints (spec §7.C2):
  - registered **only** when `ENABLE_INTERNAL_SSE_PROBE=true` — **absent in the prod/staging build by
    default** (same hygiene class as the E2E hooks; covered by `check-staging-env` and the §8 proof);
  - emits **3–5 chunks max**, closes within **<10 s**;
  - `text/event-stream` only, **no compression** (gzip on event-stream is itself a buffering trap);
  - **admin-authenticated and/or rate-limited**;
  - the staging smoke asserts chunks arrive **progressively, not buffered** into one flush.
- **Escape hatch (C2):** if the chosen proxy is independently proven SSE-safe (e.g. Fly's documented
  non-buffering ingress), the probe may be skipped and the finding resolved
  **accepted-with-rationale** instead — but C1 is the default because cheap empirical proof now beats
  an expensive surprise in 8.3.

## Consequences
- A new `ENABLE_INTERNAL_SSE_PROBE` setting + a guarded route; the route does not exist in a build
  without the flag, so it cannot leak in production.
- The probe is validated in **4.8c** (hygiene + edge) and exercised again in the **4.8d** smoke.
- This is throwaway/diagnostic infrastructure, not the Stage 8.3 SSE design; it asserts transport
  behavior only and is expected to be removed or superseded when 8.3 lands a real stream.
