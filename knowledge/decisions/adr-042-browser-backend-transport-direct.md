---
type: adr
stage: "4.8"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.8-first-hosted-deploy-staging.md
---

# ADR-042 — Browser→backend transport: direct cross-origin (spec Decision D1)

> Spec label "Decision D1". Locked in spec §4; recorded BEFORE code.

## Linked documents
- Spec: [[specs/stage-04/4.8-first-hosted-deploy-staging]]
- Related: [[adr-040-compute-topology-flyio]], [[adr-043-sse-proxy-probe]] (the probe must traverse THIS transport to be meaningful)

## Context
The browser can reach the FastAPI backend two ways in staging: **D1** direct cross-origin
(`browser → FastAPI`) or **D2** a same-origin Next.js proxy/rewrite (`browser → Next → FastAPI`). The
deciding factor is Stage 8.3: SSE. A same-origin Next proxy inserts a **Node buffering hop into the
exact streaming path** 4.8 exists to de-risk — defeating the purpose. The frontend already calls the
backend directly today via `NEXT_PUBLIC_API_BASE_URL` (`frontend/src/lib/api/wrapper.ts:30`), and
uploads POST multipart straight to FastAPI (`frontend/src/lib/api/upload.ts`), so D1 matches the
shipped client.

## Decision
- **D1: the staging browser talks directly to the FastAPI origin**, cross-origin.
- `NEXT_PUBLIC_API_BASE_URL` is baked into the **staging-tagged frontend image** as the staging
  backend `https` URL (build-time inlining; cannot be set at runtime).
- Backend **CORS** (`app/main.py`) adds the staging frontend origin to `CORS_ORIGINS`, keeping
  `OPTIONS` + headers `Authorization`/`Content-Type`/`Idempotency-Key` allowed (already `["*"]` today).
- **Escape hatch (D2):** a same-origin Next proxy is viable ONLY if one accepts the Node hop AND makes
  ADR-043's SSE probe traverse that proxy (otherwise the probe validates the wrong path).

## Consequences
- TLS is mandatory on the backend (mixed-content otherwise).
- CORS preflight for non-simple requests must pass against the real cross-origin setup — a true
  cross-origin test, which is also a rule-9 requirement.
- **`allow_credentials=True` is retained for 4.8** and its removal is **deferred to 4.9** (hygiene
  batch); 4.8 only adds the staging origin to `CORS_ORIGINS`.
- ADR-043's probe is registered on the FastAPI origin and hit directly from the staging browser, so it
  measures the same transport real traffic uses.
