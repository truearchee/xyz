---
type: adr
stage: "4.9"
status: accepted
created: 2026-06-13
updated: 2026-06-13
related-session: knowledge/specs/stage-04/4.9e-hygiene-closeout.md
---

# ADR-049 — httpx ASGITransport + CORS allow_credentials hygiene (§7)

> Stage 4.9 umbrella §7 (hygiene batch) + §11. Recorded with the 4.9e code.

## Linked documents
- Spec: [[specs/stage-04/4.9e-hygiene-closeout]] · Umbrella: [[specs/stage-04/4.9-frontend-foundation-platform-hygiene]] (§7)
- Findings: [[steps/findings-4.9]] (F-4.9-2 prevention, the §7.4 sibling item)

## Context
Three carried-debt items (umbrella §7) + the §7.4 prevention item the batch grew to. This ADR records the
two backend decisions (§7.1 httpx, §7.2 CORS); §7.3 (the `gen:api` alias) + §7.4 (E2E data-hygiene
prevention) are tooling, recorded in the report + F-4.9-2.

## Decisions
- **§7.1 httpx — MIGRATE to `ASGITransport`, do not pin.** The httpx-deprecated `AsyncClient(app=app, …)`
  shortcut appeared in **three** test files, not one: `backend/tests/conftest.py` (the `auth_client`/`probe`
  fixtures), `backend/tests/test_health.py` (4 direct clients), and `backend/tests/test_sse_probe.py` (the
  `probe_client` fixture on a `create_app()`-built app). All changed to
  `AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. **Behaviour-identical** — both
  run the ASGI app in-process — so the **SAME assertions pass** (not merely the same count), and the
  deprecation clears. Pinning would only defer the break; migrating removes the debt.
  *Acceptance (PROVEN, 4.9e close-out): `pytest -W error::DeprecationWarning` — which makes ANY deprecation
  a hard test failure — gives **421 passed, 0 warnings**; a grep for httpx/ASGI/deprecation lines returns
  none. The first close-out gate caught that fixing conftest alone left 6 warnings (test_health × 4 +
  test_sse_probe × 2) — recorded honestly rather than papered over.*
- **§7.2 CORS — DROP `allow_credentials=True`.** `backend/app/main.py` set it, but auth is **pure Bearer**
  (rule 4): the browser sends `Authorization: Bearer …`, never cookies/credentials cross-origin. So
  `allow_credentials` was unused surface area (and it forbids wildcard origins/methods/headers for no
  benefit). Dropped. *Acceptance: staging + E2E cross-origin flows stay green with credentials disabled* —
  the full active Playwright suite (true cross-origin browser→FastAPI, Stage 4.8 D1) re-run green confirms it.

## Consequences
- One image rebuild needed (both changes are baked into the backend image); verified in the 4.9e close-out
  (pytest 0 httpx warnings + same pass count; full E2E suite green with CORS credentials off).
- No endpoint or schema change (umbrella §3 honored) — config/test only.
- §7.4's `check-orphans.mjs` + the trap-based `run-active-suite.sh` (unconditional teardown) are the
  prevention half (F-4.9-2); demonstrated, not asserted (orphan check fails loud on a seeded orphan).
