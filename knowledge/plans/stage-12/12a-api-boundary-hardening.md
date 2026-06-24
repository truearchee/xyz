---
type: session-plan
stage: 12
session: "12a"
slug: api-boundary-hardening
status: approved
created: 2026-06-23
updated: 2026-06-23
owner: developer
spec: knowledge/specs/stage-12/12a-api-boundary-hardening.md
report: knowledge/steps/stage-12/12a-api-boundary-hardening.md
---

# Plan — Session 12a — API Boundary Hardening

> HOW for [[specs/stage-12/12a-api-boundary-hardening]]. Decisions D1/D2/D3 = A (owner-confirmed
> 2026-06-23). Grounded in the kickoff exploration recorded in [[steps/findings-12]]. Run with `/careful`;
> one logical change per commit; branch + PR; **owner merges (agent never merges)**.

## A. `can_publish` → membership-derived  (commit 1)
- `backend/app/platform/query/modules.py` `get_active_module_access` (~L42-54): add `CourseMembership.role`
  to the SELECT (query already JOINs membership + filters `status=="active"`). Replace the always-`None`
  `can_publish` on `ModuleAccessRow` (L18,59-64) with `role: str`.
- `backend/app/platform/auth/guards.py:42-46`: `can_publish = (access.role == "lecturer")`; drop the
  `current_user.role == "lecturer"` global-role fallback.
- Mapping: publish = active **lecturer** membership in the module; student membership → `False`. Admins have
  no memberships (`me.py:72-78`) so never reach this path (404 at `require_module_access`).
- `ModuleDetail.can_publish` stays `bool` → no OpenAPI shape change.
- Test: a lecturer-member sees `canPublish=true`; a student-member sees `false` (display-alignment unit/api test).

## B. Enforcement audit → negative-test matrix  (commit 3)
Boundary verified already-uniform (all eight surfaces gate active lecturer membership at the service layer:
`content/service.py:100-126`; transcripts `section_context.py:38-46`). Deliverable = lock with tests, **do
not add** router-level `require_module_access` (finding F6 — redundant + changes codes).

Matrix — surfaces × actors:
| surface | router | student | admin | lecturer (no active membership) |
|---|---|---|---|---|
| publish | content.py:387 | 403 CONTENT_FORBIDDEN | 403 | 404 SECTION_NOT_FOUND |
| unpublish | content.py:405 | 403 | 403 | 404 |
| notes (PATCH) | content.py:347 | 403 | 403 | 404 |
| metadata (PATCH) | content.py:367 | 403 | **200 (admin allowed — lock)** | 404 |
| asset upload | content.py:280 | 403 | 403 | 404 |
| asset replace | content.py:314 | 403 | 403 | 404 |
| transcript upload | transcripts.py:76 | 403 TRANSCRIPT_FORBIDDEN | 403 | 404 SECTION_NOT_FOUND |
| transcript retry | transcripts.py:145 | 403 | 403 | 404 |
- Every negative asserts **not 401**. The 404 cases target the **deliberate `SECTION_NOT_FOUND` info-hiding
  path** (real published section in a module the actor lacks active membership in), not an incidental
  missing-row 404. Reuse `test_content.py` helpers (`_create_user/_create_module/_create_membership/_headers`).

## C. Error envelope + request-id middleware  (commit 2)
New package `backend/app/platform/http/`:
- `request_id.py` — `BaseHTTPMiddleware`: read incoming `X-Request-ID` or generate `uuid7()` (from `uuid6`,
  already a dep); stash on `request.state.request_id`; set the `X-Request-ID` response header on every
  response (2xx + error). `get_request_id(request)` helper with a generate-on-miss fallback.
- `errors.py` — three handlers registered in `main.py:create_app` (after CORS, request-id middleware
  outermost):
  1. `StarletteHTTPException` → `{ "error": { "code", "message", "request_id" } }` **plus** preserve the
     original `detail` (additive) and original `headers`. `error.code` ← `str` `detail` verbatim
     (`CONTENT_FORBIDDEN`, `SECTION_NOT_FOUND`, `TRANSCRIPT_FORBIDDEN`, `"Insufficient permissions"`, …);
     for non-`str` detail (assistant dict / 422 list) use code `HTTP_<status>` and keep the original `detail`.
  2. `RequestValidationError` (422) → keep standard `{"detail":[...]}` and add `error` (FE 422-array parsers
     keep working).
  3. catch-all `Exception` (500) → `{"error":{"code":"INTERNAL_ERROR","message":"Internal server error",
     "request_id":…}}`, **no stack trace / no `str(exc)`**; `logger.exception(..., extra={"request_id"})`.

## D. Additive contract (D2=A) + ADR-061
Keep `detail`; add `error` + `X-Request-ID` everywhere. Error bodies already typed `any` in the generated
client ⇒ **no client regen**; verify `git diff backend/openapi.json` empty. Convergence conditions:
(1) all NEW/CHANGED code reads `error`, never `detail`; (2) write **ADR-061 — additive error envelope** with
the deferred clean-cut owner/stage = a future frontend-consistency pass (drop `detail`, declare `ErrorEnvelope`
schema, regen client, migrate the 13+ FE `body.detail` readers incl. the two 422-array parsers) + add to the
carried-debt ledger.

## F. Tests  (commit 2 + 3)
- `backend/tests/test_error_envelope.py` (new): forced-500 → exactly the clean envelope, no secret/traceback
  substring, `X-Request-ID` header == `error.request_id`; a 403 path → `error.code` correct + `detail` still
  present; `X-Request-ID` echo (sent id round-trips; absent → generated); `GET /health` carries `X-Request-ID`.
- Negative-authz matrix (B).

## G. Verification (the 12a gate)
1. `docker compose up -d` then `docker compose exec backend pytest tests/test_content.py tests/test_transcripts.py tests/test_transcript_retry.py tests/test_error_envelope.py -q` → then full `pytest -q`.
2. `npm --prefix frontend run typecheck` + `npm --prefix frontend test`.
3. `git diff --stat backend/openapi.json` → expect empty.
4. Full active Playwright serial: `npx playwright test --workers=1` (rule 14, deterministic LLM adapter stack).
5. Browser network tab: 403 → envelope + `X-Request-ID`, no stack trace; forced 500 → clean `error`-only body;
   `GET /me` → `X-Request-ID`; 401 → redirect `/login` (rule 5 intact).
6. `/review` + `/codex` (fresh session) attached.

## Commit sequencing (one logical change each, `/careful`)
1. `can_publish` membership derivation (modules.py + guards.py) + display-alignment test.
2. request-id middleware + error-envelope handlers + `main.py` wiring + `test_error_envelope.py`.
3. negative-authz matrix fill across the eight surfaces.

## Open / findings to surface (rule 10)
F1 boundary already correct (display-alignment, not a hole); F2/D3 spec-403-vs-code-404 reconciled (keep 404);
F3 metadata-allows-admin asymmetry locked as-is; F4/D2 additive envelope; F6 no redundant router dependency;
F7 seeds low-risk (active lecturer memberships exist). See [[steps/findings-12]].

## Linked documents
- Spec: [[specs/stage-12/12a-api-boundary-hardening]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Report: [[steps/stage-12/12a-api-boundary-hardening]]
- Findings: [[steps/findings-12]]
