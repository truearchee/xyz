---
type: adr
id: adr-061
stage: "12"
status: accepted
created: 2026-06-23
related-session: "12a"
---

# ADR-061 — Additive error envelope (keep `detail`, add `error`); clean removal deferred

## Status
Accepted (Stage 12a, 2026-06-23). Owner decision D2 = A.

## Context
Stage 12a adds a consistent error envelope and a `request_id` correlation id (carried-debt: "no custom
exception handlers / raw default 500 bodies"). The target shape is
`{"error": {"code", "message", "request_id"}}`, applied uniformly, with `X-Request-ID` on every response.

The codebase already returns raw FastAPI `{"detail": <code-or-message>}` bodies, where `detail` is either a
domain CODE string (`CONTENT_FORBIDDEN`, `SECTION_NOT_FOUND`, …) or — for the assistant — a structured
`{"code": …}` dict. A "clean" cut (replace `detail` with `error`) has a measured blast radius:
- **~48 backend test assertions** read `["detail"]` (several assert the FULL body `== {"detail": …}`);
- **13+ frontend files** read `caught.body.detail` to map error codes to UI copy, **two of which** parse
  `detail` as a 422 validation array;
- the frontend `wrapper.ts` keys 401/403 on `caught.status` (not body), so rule 5 is safe either way.

Doing the clean cut inside an authz-focused hardening sub-session would inject broad frontend-regression
risk and violate "one logical change per commit."

## Decision
**Additive now.** Every error response carries the new `error` object AND preserves the legacy `detail`
field verbatim; every response (success and error) carries the `X-Request-ID` header. `error.code` carries
the existing CODE strings verbatim and lifts the assistant's structured `detail.code`. The catch-all 500
emits the clean `error`-only body (it has no legacy `detail` to preserve) with no stack trace or internal
text.

**Two convergence conditions** so the deferral resolves rather than drifts:
1. **`error` is canonical going forward.** All NEW or CHANGED code (this stage onward) reads `error`, never
   `detail`. No refactor of existing `detail` readers now — that is precisely what is deferred.
2. **The clean removal is tracked, not lost.** It is a named **future frontend-consistency pass** that will:
   drop `detail`, declare an `ErrorEnvelope` OpenAPI component schema, regenerate + commit the TS client
   (rule 3), and migrate the 13+ frontend `body.detail` readers — **with care for the two that parse
   `detail` as a 422 validation array**. Owner = product owner; stage = a post-12 frontend-consistency
   pass (recorded in the carried-debt ledger).

## Consequences
- Near-zero churn in 12a: existing `detail` readers/tests keep working; the only test churn was converting
  full-body `== {"detail": …}` equality asserts (which break on *any* body addition) to `["detail"]`
  subscript form, and normalizing the Stage 4.7 S2 byte-identical-404 comparison to ignore the
  resource-independent `request_id`.
- No OpenAPI contract change (error bodies were already typed `any` in the generated client) → no client
  regen in 12a; verified `app.openapi()` is byte-identical to the committed `backend/openapi.json`.
- The system temporarily carries two error-body fields; the canonical-going-forward rule plus the tracked
  removal keep this from becoming permanent.

## Alternatives considered
- **Clean cut now** (drop `detail`): rejected for 12a — broad FE-touching change in an authz-hardening
  sub-session; deferred per above.
- **Declare the `ErrorEnvelope` schema now** (no body change): rejected for 12a — triggers a large client
  diff (rule 3) for no observable behaviour gain; bundled with the clean cut instead.

## Linked documents
- Spec: [[specs/stage-12/12a-api-boundary-hardening]]
- Plan: [[plans/stage-12/12a-api-boundary-hardening]]
- Report: [[steps/stage-12/12a-api-boundary-hardening]]
- Findings: [[steps/findings-12]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
