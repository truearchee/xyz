---
type: architecture
stage: 04
created: 2026-06-05
updated: 2026-06-08 11:37
related-session: knowledge/specs/stage-04/4.3.5c-stage2-admin-ui-backfill.md
---

# Frontend Architecture

## Linked documents
- Spec: [[specs/stage-04/4.3.5b-app-shell-role-routing]]
- Plan: [[plans/stage-04/4.3.5b-app-shell-role-routing]]
- Report: [[steps/stage-04/4.3.5b-app-shell-role-routing]]
- Spec: [[specs/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Report: [[4.3.5c-stage2-admin-ui]]
- Spec: [[specs/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes]]
- Plan: [[plans/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes-plan]]
- Report: [[4.3.5d-checkpoint-A-report]]
- Spec: [[specs/stage-04/4.3.5d-B0-stage3-multipart-upload-helper]]
- Plan: [[plans/stage-04/4.3.5d-B0-stage3-multipart-upload-helper-plan]]
- Report: [[4.3.5d-B0-upload-helper]]
- Spec: [[specs/stage-04/4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui]]
- Plan: [[plans/stage-04/4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui-plan]]
- Report: [[4.3.5d-checkpoint-B-report]]
- ADR: [[decisions/adr-023-stage2-admin-module-membership-projection]]
- Recovery plan: [[specs/recovery/client-edge-recovery-plan]]
- Architecture: [[architecture/auth-current-user-context]]

## Route structure
The root `frontend/src/app/layout.tsx` owns global providers only. The public auth page lives under `(auth)/login` and renders without the AppShell. Protected app pages live under `(app)` and are wrapped by `ProtectedAppLayout` plus `AppShell`.

Route groups do not change public URLs. Current public app routes are `/login`, `/admin`, `/lecturer`, `/student`, `/unauthorized`, and `/tracer`.

Session 4.3.5d Checkpoint A adds the lecturer module detail route `/lecturer/modules/[moduleId]`. It is a protected lecturer route under `(app)` and renders `frontend/src/features/content/lecturer/LecturerModuleDetail.tsx`.

## Session state
`SessionProvider` is the browser source for frontend auth state. It reads Supabase browser session state, calls backend `GET /me`, and exposes app context from the backend response. Role routing and guards use the `/me` role only; frontend code must not decode JWT claims or read Supabase metadata for product role.

Session states are `loading`, `unauthenticated`, `authenticated`, and `forbidden`. The `forbidden` state means Supabase has a session but backend app access is not available, so the UI renders standalone `AccessDenied` without AppShell.

## Routing and shell
Root `/` redirects authenticated users to role home (`/admin`, `/lecturer`, `/student`) and unauthenticated users to `/login`. `ProtectedAppLayout` redirects unauthenticated users to `/login`, keeps forbidden users out of AppShell, and performs segment-safe role-prefix checks for app routes.

Wrong-role navigation to `/admin`, `/lecturer`, or `/student` redirects to `/unauthorized` with `router.replace()` inside `useEffect`. `/unauthorized` is exempt from the guard to avoid loops and renders inside AppShell for authenticated users with a link to their correct role home.

## API wrapper behavior
The frontend wrapper keeps generated OpenAPI client traffic on the existing generated request path. `OpenAPI.TOKEN` remains an async resolver, so every protected call retrieves the current Supabase session token at request time instead of caching access tokens globally.

`401` responses sign out through Supabase, redirect the browser to `/login`, and surface `AuthRequiredError`. `403` responses do not sign out and do not redirect; they surface `ForbiddenError` with status `403` for callers and E2E hooks.

## Stage 2 product UI
Session 4.3.5c replaced the Stage 2 placeholders with thin product surfaces:

- `/admin` renders feature-level user and module management panels from `frontend/src/features/admin/users/` and `frontend/src/features/admin/modules/`.
- Admin UI calls backend data only through `frontend/src/lib/api/wrapper.ts` and the generated OpenAPI client.
- Admin user flows list users, create lecturer/student users, deactivate users, and reset passwords.
- Admin module flows list modules, create modules with owner lecturers, assign lecturer/student users, list real module members through `GET /admin/modules/{module_id}/members`, and remove active memberships from that real member list.
- Lecturer and student home pages render `frontend/src/features/modules/AssignedModulesList.tsx`, which calls `GET /modules` through the wrapper and remains read-only.

Do not decode JWT claims for frontend role. Do not add direct `fetch()` calls outside the generated request/upload helpers or approved wrapper paths.

## Stage 3 lecturer Checkpoint A UI
Session 4.3.5d Checkpoint A adds the first Stage 3 lecturer content UI slice:

- `/lecturer` assigned-module cards link to `/lecturer/modules/{moduleId}`.
- `frontend/src/features/content/lecturer/LecturerModuleDetail.tsx` loads module metadata through `api.modules.get`, section list rows through `api.content.listSections`, and per-section detail through `api.content.getSection`.
- Per-section detail is used to render `publishStatus` and `lecturerNotes` without a backend projection change.
- `frontend/src/features/content/lecturer/SectionNotesEditor.tsx` edits lecturer notes and calls `api.content.updateNotes`.
- Notes save re-fetches backend data before displaying persisted state, and save failures render `role="alert"`.
- Checkpoint A intentionally does not add upload, replace, publish/unpublish controls, student content views, signed URL opening, section create/delete/reorder controls, or backend changes.

## Stage 3 multipart upload helper
Session 4.3.5d-B0 adds `frontend/src/lib/api/upload.ts` as the controlled direct-`fetch()` exception for browser multipart uploads. Product pages and components still must not call `fetch()` directly.

The helper uses the same generated-client base URL and token resolver through `OpenAPI.BASE` and `OpenAPI.TOKEN`. It attaches `Authorization: Bearer <access_token>`, sends `FormData` field `file`, and intentionally does not set `Content-Type` so the browser supplies the multipart boundary.

The helper exposes `uploadSectionAsset(...)` and `replaceSectionAsset(...)`, returning the generated `SectionAssetResponse`. It preserves wrapper-aligned auth behavior: `401` signs out and redirects to `/login`, while `403` surfaces `ForbiddenError` without clearing the Supabase session.

## Stage 3 lecturer Checkpoint B UI
Session 4.3.5d Checkpoint B extends `/lecturer/modules/{moduleId}` with section asset upload and replacement:

- `LecturerModuleDetail.tsx` loads section assets through `api.content.listAssets` after section list/detail reads.
- `SectionUploadControl.tsx` selects a file and calls the B0 `uploadSectionAsset(...)` helper.
- `SectionAssetList.tsx` renders backend asset rows and the no-files state.
- `SectionAssetRow.tsx` renders filename, file metadata, asset `processingStatus`, and an asset-id-scoped replace control that calls B0 `replaceSectionAsset(...)`.
- Upload and replace success paths re-fetch backend module/section/asset data before rendering success.
- Upload and replace failures render `role="alert"`.

The section `publishStatus` badge remains on the section header. Asset `processingStatus` remains on each asset row and uses asset-id-specific test IDs. Checkpoint B intentionally does not add publish/unpublish controls, student module pages, signed URL opening, or backend changes.

## E2E bridge and tracer
`NEXT_PUBLIC_E2E_TEST_HOOKS=true` enables a browser-only `window.__xyzE2E` bridge for Playwright. It exposes Supabase session helpers, wrapper-backed `/me` and `/admin/users` calls with serializable result envelopes, and a single-use forced bearer-token override for deterministic 401 testing. The bridge is not registered unless the flag is exactly `true`.

`/tracer` is retained for recovery only. It is route-gated in `frontend/src/app/tracer/page.tsx`; when `NEXT_PUBLIC_TRACER_ENABLED !== "true"`, the route returns Next.js `notFound()` before rendering the client tracer component.
