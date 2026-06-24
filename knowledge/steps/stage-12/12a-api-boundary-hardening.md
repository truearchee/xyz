---
type: session-report
stage: 12
session: "12a"
slug: api-boundary-hardening
status: implemented-pending-gate
created: 2026-06-23
updated: 2026-06-23
owner: developer
spec: knowledge/specs/stage-12/12a-api-boundary-hardening.md
plan: knowledge/plans/stage-12/12a-api-boundary-hardening.md
---

# Report — Session 12a — API Boundary Hardening

> Status: **code-complete; local gates green; live Playwright + independent review pending the owner's
> E2E env (not run here).** Not merged — the product owner merges. Written from `git diff` + captured
> command output, not memory.

## What shipped

### 1. `can_publish` → membership-derived (display alignment)
- `backend/app/platform/query/modules.py` — `get_active_module_access` now selects `CourseMembership.role`
  (the query already JOINs membership + filters `status='active'`); `ModuleAccessRow.can_publish: bool|None`
  → `membership_role: str`.
- `backend/app/platform/auth/guards.py` — `can_publish = (current_user.role == "lecturer" and access.membership_role == "lecturer")`,
  dropping the global-role-only fallback. This **mirrors the enforcement gate exactly**
  (`content/service.py:100,111` `_get_assigned_lecturer_section` requires global lecturer role AND an active
  `lecturer` membership). `ModuleDetail.can_publish` stays `bool` → **no OpenAPI change** (verified identical).
- **Finding F1 (recorded):** `can_publish` is a DISPLAY field only — no backend code gates a mutation on it.
  The publish boundary was *already* membership-enforced at the service layer. So this is display-alignment,
  not a vulnerability fix. The prior global-role derivation over-reported `canPublish=true` for a global-role
  lecturer holding only a non-lecturer membership in the module; now corrected.

### 2. Global error envelope + request-id middleware (additive — D2=A / ADR-061)
- New package `backend/app/platform/http/`:
  - `request_id.py` — pure-ASGI `RequestIdMiddleware` (NOT `BaseHTTPMiddleware`, to avoid the
    state-propagation/contextvar pitfalls and to keep the id on `scope["state"]` for the exception
    handlers, including the catch-all 500 that runs in `ServerErrorMiddleware` outside the user-middleware
    stack). Reads/generates `X-Request-ID` (uuid7), echoes it on **every** response. `get_request_id()`
    accessor with generate-on-miss fallback.
  - `errors.py` — three handlers: `StarletteHTTPException` (catches FastAPI's subclass too),
    `RequestValidationError` (422), and a catch-all `Exception` (500). Envelope
    `{"error": {"code","message","request_id"}}`; the catch-all 500 emits the clean `error`-only body with
    **no stack trace / no `str(exc)`** and logs server-side with the request_id.
- `backend/app/main.py` — registers the middleware (outermost user middleware, after CORS) + the three
  handlers.
- **Additive (D2=A):** the legacy `detail` field is preserved verbatim alongside the new `error` object, so
  the 13+ frontend `body.detail` readers (incl. the two 422-array parsers) and the existing tests keep
  working. `error.code` carries the existing domain CODE strings verbatim (`CONTENT_FORBIDDEN`,
  `SECTION_NOT_FOUND`, …) and lifts the assistant's structured `detail={"code":…}` dicts.

### 3. Tests
- `backend/tests/test_error_envelope.py` (new, no DB): forced-500 clean envelope + no-leak + header;
  additive 403 envelope; dict-detail preservation + code-lift; 422 array preserved + envelope;
  `X-Request-ID` echo / generate / success-path header / real `/health` route.
- `backend/tests/test_modules.py` — `test_lecturer_with_student_membership_can_publish_false` (the
  display-alignment behavioural change).
- `backend/tests/test_content.py` — `test_unpublish_authz_membership_boundary` (the genuine gap: publish/notes
  were covered, unpublish wasn't) + `test_authz_denial_carries_error_envelope_and_request_id` (ties the
  envelope to real domain authz denials: `error.code`/`request_id` + `X-Request-ID` header + additive
  `detail` + never-401).

## Findings (rule 10) — full set in [[steps/findings-12]]
- **F1** — `can_publish` display-only; boundary already membership-enforced (above).
- **F2 / D3** — spec said "unassigned lecturer → 403"; live contract is **404 `SECTION_NOT_FOUND`**
  (info-hiding, Stage 4.7 pattern). 404 retained as canonical; stale-spec reconciliation recorded.
- **F4 / D2** — additive envelope (keep `detail`); clean removal deferred to a tracked future FE pass (ADR-061).
- **Per-gate code asymmetries discovered (existing contract, NOT changed):** asset upload/replace
  (`authorize_lecturer_section`) returns **403** "Lecturer is not assigned to module" for an unassigned
  lecturer, whereas publish/notes/metadata/transcripts return **404 `SECTION_NOT_FOUND`** for the same case.
  This is a pre-existing inconsistency in info-hiding posture across surfaces; locked as-is by the existing
  tests (`test_content.py:625` vs `:1198`). Flagged for the owner; not in 12a scope to normalize.
- **F3** — `PATCH …/metadata` intentionally allows admin; other mutations don't. Locked as-is.
- **F6** — did NOT add `require_module_access` as a router dependency on mutation routes (redundant; would
  change error codes).
- **Byte-identical-404 (S2) interaction:** the per-request `request_id` makes error bodies non-byte-identical.
  The Stage 4.7 S2 info-hiding test (`test_student_summaries.py:707`) was updated to compare the three 404s
  **modulo `error.request_id`** (which is resource-independent and so leaks nothing about existence). The
  guarantee — the three responses are indistinguishable by resource — is preserved in substance.

## Verification (captured output)
- **Backend full suite: `814 passed` in 344s** (`docker compose exec backend pytest -q`), zero failures
  (804 prior + 10 new). Targeted run of the changed/affected files: `184 passed`.
- **Frontend: `tsc --noEmit` clean; `vitest` 9 files / `31 passed`.** No frontend source changed.
- **OpenAPI: live `app.openapi()` byte-identical to committed `backend/openapi.json`** → no contract change,
  no client regen (rule 3 satisfied).
- All new/changed Python files `py_compile` clean.

## NOT run here (remaining gates — owner E2E env required)
- **Full active Playwright suite (rule 14)** — requires `.env.e2e` with real Supabase credentials (absent in
  this workspace). The additive envelope + `X-Request-ID` header are transparent to existing specs, and the
  `can_publish` display value stays `Allowed` for the seeded (membership-holding) lecturers, so no spec is
  expected to break — but this must be RUN before FULLY VERIFIED, on the owner's E2E stack as every prior
  stage's gate was.
- **`/review` (Claude) + `/codex` (OpenAI, fresh session)** — mandatory independent pre-merge review.
- **Manual browser network-tab check** — 403 envelope + `X-Request-ID`, forced-500 clean body, `/me` header,
  401 still redirects to `/login`.
- **Commit + PR; the product owner merges (agent never merges).** Commit sequencing in the plan §H.

## Modified prior sessions
- Session 4.x/auth — `backend/tests/test_auth.py`, `backend/tests/test_me.py`,
  `backend/tests/test_admin.py`: full-body `response.json() == {"detail": …}` equality asserts on **error**
  responses converted to `["detail"]` subscript form (the additive `error` key makes full-equality break;
  the `detail` value assertion is preserved).
- Session 4.7 — `backend/tests/test_student_summaries.py`: the `{"detail": …}` equality asserts subscripted,
  and the S2 byte-identical-404 comparison (`:707`) updated to compare modulo `error.request_id` (rationale
  above). Product behaviour unchanged; the info-hiding guarantee preserved.

## Linked documents
- Spec: [[specs/stage-12/12a-api-boundary-hardening]]
- Plan: [[plans/stage-12/12a-api-boundary-hardening]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]]
- Decision: [[decisions/adr-061-additive-error-envelope]]
- Architecture: [[architecture/auth-current-user-context]]
