---
type: architecture
stage: 04
created: 2026-06-05
updated: 2026-06-05 15:42
related-session: knowledge/specs/stage-04/4.3.5b-app-shell-role-routing.md
---

# Frontend Architecture

## Linked documents
- Spec: [[specs/stage-04/4.3.5b-app-shell-role-routing]]
- Plan: [[plans/stage-04/4.3.5b-app-shell-role-routing]]
- Report: [[steps/stage-04/4.3.5b-app-shell-role-routing]]
- Recovery plan: [[specs/recovery/client-edge-recovery-plan]]
- Architecture: [[architecture/auth-current-user-context]]

## Route structure
The root `frontend/src/app/layout.tsx` owns global providers only. The public auth page lives under `(auth)/login` and renders without the AppShell. Protected app pages live under `(app)` and are wrapped by `ProtectedAppLayout` plus `AppShell`.

Route groups do not change public URLs. Current public app routes are `/login`, `/admin`, `/lecturer`, `/student`, `/unauthorized`, and `/tracer`.

## Session state
`SessionProvider` is the browser source for frontend auth state. It reads Supabase browser session state, calls backend `GET /me`, and exposes app context from the backend response. Role routing and guards use the `/me` role only; frontend code must not decode JWT claims or read Supabase metadata for product role.

Session states are `loading`, `unauthenticated`, `authenticated`, and `forbidden`. The `forbidden` state means Supabase has a session but backend app access is not available, so the UI renders standalone `AccessDenied` without AppShell.

## Routing and shell
Root `/` redirects authenticated users to role home (`/admin`, `/lecturer`, `/student`) and unauthenticated users to `/login`. `ProtectedAppLayout` redirects unauthenticated users to `/login`, keeps forbidden users out of AppShell, and performs segment-safe role-prefix checks for app routes.

Wrong-role navigation to `/admin`, `/lecturer`, or `/student` redirects to `/unauthorized` with `router.replace()` inside `useEffect`. `/unauthorized` is exempt from the guard to avoid loops and renders inside AppShell for authenticated users with a link to their correct role home.

## API wrapper behavior
The frontend wrapper keeps generated OpenAPI client traffic on the existing generated request path. `OpenAPI.TOKEN` remains an async resolver, so every protected call retrieves the current Supabase session token at request time instead of caching access tokens globally.

`401` responses sign out through Supabase, redirect the browser to `/login`, and surface `AuthRequiredError`. `403` responses do not sign out and do not redirect; they surface `ForbiddenError` with status `403` for callers and E2E hooks.

## E2E bridge and tracer
`NEXT_PUBLIC_E2E_TEST_HOOKS=true` enables a browser-only `window.__xyzE2E` bridge for Playwright. It exposes Supabase session helpers, wrapper-backed `/me` and `/admin/users` calls with serializable result envelopes, and a single-use forced bearer-token override for deterministic 401 testing. The bridge is not registered unless the flag is exactly `true`.

`/tracer` is retained for recovery only. It is route-gated in `frontend/src/app/tracer/page.tsx`; when `NEXT_PUBLIC_TRACER_ENABLED !== "true"`, the route returns Next.js `notFound()` before rendering the client tracer component.
