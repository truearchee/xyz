---
type: session-spec
stage: 12
session: "12a"
slug: api-boundary-hardening
status: approved
created: 2026-06-23
updated: 2026-06-23
owner: developer
plan: knowledge/plans/stage-12/12a-api-boundary-hardening.md
report: knowledge/steps/stage-12/12a-api-boundary-hardening.md
---

# Session 12a — API Boundary Hardening (authorization + error envelope)

> Filed from the approved Stage 12 v1.2 spec ([[specs/stage-12/12-release-hardening]] §5 12a), narrowed to
> sub-session 12a. The only Stage 12 sub-session that changes the core request/response contract; it goes
> first because everything downstream (the 12f smoke especially) depends on it being stable. Run with
> `/careful`. Kickoff findings that reshape this scope: [[steps/findings-12]].

## Why
Two carried-debt items (roadmap.md:98–99): `can_publish` derived from role rather than membership, and no
custom exception handlers (raw default 500 bodies). Stage 12a closes both at the API boundary, plus adds a
lightweight `request_id` correlation id so 12c logging can tie a user-visible error to a log line.

## What (scope)
1. **`can_publish` → membership-derived (display alignment).** The `ModuleAccessContext.can_publish` flag
   exposed in `ModuleDetail` becomes derived from the caller's **active `lecturer` `CourseMembership`** in
   that module, not the global role. Field type unchanged (`bool`) → no OpenAPI shape change.
2. **Enforcement audit + negative-test matrix.** The publish/modify security boundary is **already**
   membership-gated at the service layer (finding F1) — 12a *verifies* this and locks it with negative
   tests on every content mutation surface, rather than adding new gates.
3. **Global exception handlers + consistent error envelope.** No raw default 500 bodies; no stack traces or
   internal detail in any error response. One uniform shape `{ "error": { "code", "message", "request_id" } }`,
   applied **additively** alongside the existing `detail` (decision D2=A — see plan §D and ADR-061).
4. **`request_id` middleware.** Generate a per-request id if absent; echo it in an `X-Request-ID` response
   header on **every** response (success and error) and inside the error envelope.

## Done means
- `can_publish` reflects active lecturer membership; admins (no memberships) and unassigned lecturers do not
  show `canPublish=true`.
- Negative authz tests green on all eight mutation surfaces: student → 403 (code); admin → 403 **except**
  `metadata` (admin allowed by design); **lecturer with no active membership → 404 `SECTION_NOT_FOUND`**
  (information-hiding path, decision D3=A — NOT 403; the spec's "403" is stale, reconciled in findings-12).
  Every negative asserts **not 401**.
- A forced server error returns the clean envelope (no stack trace), `request_id` present in body **and**
  the `X-Request-ID` header; every response carries `X-Request-ID`.
- `wrapper.ts` 401/403 mapping unchanged (rule 5): 401 → clear session + redirect `/login`; 403 → keep
  session + unauthorized state.
- Backend pytest green (prior count + new, zero regressions under additive). Frontend `tsc` + vitest green.
  `git diff backend/openapi.json` empty (no contract change → no client regen, rule 3).
- Full active Playwright suite green (rule 14). `/review` + `/codex` attached. Branch + PR; **owner merges.**

## Do NOT build
- Do **not** flip the unassigned-lecturer 404 to 403 (weakens info-hiding; D3=A).
- Do **not** drop the legacy `detail` field now (additive only; clean removal is a tracked future FE pass — ADR-061).
- Do **not** add `require_module_access` as a router dependency on mutation routes (redundant; would change
  error codes — finding F6).
- No new features, no migration (membership data already exists; Alembic head stays 0082).
- Do **not** normalize the deliberate `metadata`-allows-admin asymmetry without owner sign-off (finding F3).

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Plan: [[plans/stage-12/12a-api-boundary-hardening]]
- Report: [[steps/stage-12/12a-api-boundary-hardening]]
- Findings: [[steps/findings-12]]
- Architecture: [[architecture/auth-current-user-context]]
