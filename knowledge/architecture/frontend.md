---
type: architecture
stage: 04
created: 2026-06-05
updated: 2026-06-22
related-session: knowledge/specs/stage-04/4.3.5c-stage2-admin-ui-backfill.md
---

# Frontend Architecture

## Linked documents
- Spec: [[specs/stage-04/4.3.5b-app-shell-role-routing]]
- Plan: [[plans/stage-04/4.3.5b-app-shell-role-routing]]
- Spec: [[specs/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Stage 3 final report: [[4.3.5d-content-ui-final-report]]
- ADR: [[decisions/adr-023-stage2-admin-module-membership-projection]]
- Spec: [[specs/stage-04/4.3.5e-stage4-transcript-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5e-stage4-transcript-ui-plan]]
- Transcript final report: [[4.3.5e-transcript-ui-final-report]]
- Recovery final report: [[4.3.5-client-edge-recovery-final-report]]
- Recovery plan: [[specs/recovery/client-edge-recovery-plan]]
- Architecture: [[architecture/auth-current-user-context]]
- Spec: [[specs/stage-05/5.5e-ui-browser-gate]]
- Report: [[steps/stage-05/5.5e-ui-browser-gate]]
- Spec: [[specs/stage-09/9-my-progress-dashboard]]
- Report: [[steps/stage-09/9-my-progress-dashboard]]
- Spec: [[specs/stage-10/10-gamification]]
- Report: [[steps/stage-10/10a-foundation]]
- ADR: [[decisions/adr-056-gamification-course-timezone]]
- ADR: [[decisions/adr-057-gamification-on-read-evaluation]]
- Spec: [[specs/stage-11/11.1-roster-risk-scheduler]]
- Report: [[steps/stage-11/11.1-roster-risk-scheduler]]
- Spec: [[specs/stage-11/11.2-student-detail-recommendations]]
- Report: [[steps/stage-11/11.2-student-detail-recommendations]]
- Spec: [[specs/stage-11/11.3-assessment-analysis-question-insights]]
- Report: [[steps/stage-11/11.3-assessment-analysis-question-insights]]
- Spec: [[specs/stage-11/11.4-workload-planner]]
- Report: [[steps/stage-11/11.4-workload-planner]]
- Spec: [[specs/stage-11/11.5-calendar-ics-export]]
- Report: [[steps/stage-11/11.5-calendar-ics-export]]

## Route structure
The root `frontend/src/app/layout.tsx` owns global providers only. The public auth page lives under `(auth)/login` and renders without the AppShell. Protected app pages live under `(app)` and are wrapped by `ProtectedAppLayout` plus `AppShell`.

Route groups do not change public URLs. Current public app routes are `/login`, `/admin`, `/lecturer`, `/student`, `/student/progress`, and `/unauthorized`.

Session 4.3.5d Checkpoint A adds the lecturer module detail route `/lecturer/modules/[moduleId]`. It is a protected lecturer route under `(app)` and renders `frontend/src/features/content/lecturer/LecturerModuleDetail.tsx`.

Session 4.3.5d Checkpoint D adds the student module detail route `/student/modules/[moduleId]`. It is a protected student route under `(app)` and renders `frontend/src/features/content/student/StudentModuleDetail.tsx`.

Stage 9 adds the student progress route `/student/progress`. It is a protected student route under
`(app)` and renders `frontend/src/features/progress/ProgressDashboard.tsx`.

Stage 11 adds analytics widgets to existing routes rather than adding new pages:
`LecturerRosterRiskPanel` mounts on `/lecturer/modules/[moduleId]`, and `StudentRiskCard` mounts on
`/student/modules/[moduleId]` and `/student/progress`. Stage 11.3 adds `LecturerAssessmentInsightsPanel`
to `/lecturer/modules/[moduleId]`. Stage 11.4 adds `StudentWorkloadPlanner` to
`/student/modules/[moduleId]` and `/student/progress`.

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

## Stage 3 lecturer Checkpoint C UI
Session 4.3.5d Checkpoint C adds section visibility controls to `/lecturer/modules/{moduleId}`:

- `SectionPublishControl.tsx` renders visible section `publishStatus` text and a section-title-labeled publish/unpublish button.
- `LecturerModuleDetail.tsx` calls `api.content.publishSection` or `api.content.unpublishSection`, then re-fetches module, section, and asset data before rendering the new status.
- `frontend/src/lib/api/wrapper.ts` exposes `api.content.unpublishSection`; `api.content.publishSection` already existed.
- Publish/unpublish mutation failures render `role="alert"` in the section control.

Status ownership remains split: `SectionPublishControl` renders section visibility state with `data-testid="section-publish-status-{sectionKey}"`, while `SectionAssetRow` renders each asset processing state with `data-testid="section-asset-processing-status-{assetId}"`. Checkpoint C intentionally does not add student pages, signed URL opening, backend changes, or section create/delete/reorder controls.

## Stage 3 student Checkpoint D UI
Session 4.3.5d Checkpoint D adds the student published-only module detail route:

- `/student` assigned-module cards link to `/student/modules/{moduleId}`.
- `frontend/src/features/content/student/StudentModuleDetail.tsx` loads module metadata through `api.modules.get`, then loads the backend student-visible section list through `api.content.listSections`.
- Student section visibility is server-authoritative. The component does not fetch lecturer/all-section data and does not frontend-filter draft/unpublished sections as the authority.
- For each returned section, `StudentModuleDetail.tsx` loads `StudentSectionDetail` through `api.content.getSection`.
- `StudentSectionView.tsx` renders section order/type/title, lecturer notes, and published asset rows.
- `StudentAssetRow.tsx` calls `api.content.getAssetDownloadUrl` and opens the returned signed URL. It does not construct storage URLs or expose raw storage keys.
- Signed URL request failures render `role="alert"`.
- Student pages intentionally do not render upload, replace, publish, unpublish, edit-notes, create, delete, or reorder controls.

## Stage 3 browser gate
Session 4.3.5d Checkpoint E verified the complete Stage 3 UI path end to end with separate lecturer and student browser contexts:

- Lecturer logs in, opens a product-created assigned module, and sees generated sections from backend section generation.
- Lecturer notes, PDF upload, asset-level replace, invalid upload rejection, publish, and separate publish/processing status rendering all work through the current UI.
- Student logs in separately, opens the same assigned module, and sees only the published section returned by the backend student response.
- Student opens the PDF through `api.content.getAssetDownloadUrl`; the UI does not construct storage URLs.
- Authenticated student upload to the content upload endpoint returns 403 and leaves the `/me` session active.
- Stage 3 Content + Visibility is FULLY VERIFIED after this gate.

## Stage 4 transcript Checkpoint A/B UI
Session 4.3.5e Part 3 adds the thin lecturer transcript UI surface for Stage 4.1-4.3:

- `frontend/src/lib/api/upload.ts` exposes `uploadTranscript(...)` as the transcript-specific multipart helper. It uses the same controlled direct-`fetch()` exception as PDF upload, sends multipart field `file`, and posts to `/modules/{moduleId}/sections/{sectionId}/transcript`.
- `frontend/src/lib/api/wrapper.ts` exposes `api.transcripts.getActive(moduleId, sectionId)` through generated `TranscriptsService.getSectionTranscript` and existing auth recovery.
- `frontend/src/features/content/lecturer/SectionTranscriptControl.tsx` loads the active transcript on mount, treats `404 TRANSCRIPT_NOT_FOUND` as the normal no-transcript state, uploads `.vtt` and `.txt` files, and handles `409 TRANSCRIPT_ALREADY_EXISTS` with a safe existing-transcript message.
- `frontend/src/features/content/lecturer/TranscriptStatusBadge.tsx` renders transcript status with `role="status"` and polls the backend while status is non-terminal. Polling stops on `completed`, `failed`, timeout, or unmount.
- `frontend/src/features/content/lecturer/LecturerModuleDetail.tsx` mounts `SectionTranscriptControl` only for `lecture` and `lab` sections. Assignment and supplementary sections render no transcript control.
- The old unmounted `frontend/src/features/transcripts/*` bypass path was removed so transcript reads and uploads have one mounted frontend path with wrapper/upload-helper auth recovery.

Transcript status remains separate from section visibility and asset processing status. Transcript selectors use `section-transcript-*`, section publish state uses `section-publish-status-*`, and asset processing state uses `section-asset-processing-status-*`.

The transcript UI renders only `TranscriptMeta` metadata: original file name, MIME type, file size, and status. It does not render raw transcript text, parsed segments, chunks, storage keys, checksums, retry/replacement controls, or student transcript surfaces.

## Stage 4 transcript browser gate
Session 4.3.5e Part 5 verifies Stage 4.1-4.3 through Playwright:

- A run-scoped module is created through the real admin module API, which triggers backend section generation for `Lecture 1`, `Lecture 2`, `Lab 1`, and `Assignment 1`.
- Lecturer and student use separate browser contexts and Supabase sessions.
- Lecturer uploads VTT through the lecture-section transcript control and TXT through the lab-section transcript control.
- `TranscriptStatusBadge` reaches `Transcript processing completed` from backend status polling; the test also uses DB-only reads to prove parse and chunk jobs completed and segment/chunk counts are greater than zero.
- Assignment sections render no transcript control; backend upload to assignment returns `422 SECTION_TYPE_UNSUPPORTED`.
- A second upload to an active transcript section returns `409 TRANSCRIPT_ALREADY_EXISTS`.
- Reloading the lecturer module page shows existing active transcript status without presenting replacement UI.
- Student UI renders no transcript controls, student upload/status API calls return 403, the student session remains active, and no raw transcript text/segment/chunk fields are exposed.

No product endpoint was added for segment/chunk counts. Count proof remains test-only.

## Stage 5.5e schedule and lab UI
Session 5.5e extends the existing thin admin/lecturer/student surfaces for schedule metadata:

- `CreateModuleForm.tsx` collects course dates, week-start day, quiz day, and weekday pattern, then calls
  the admin preview endpoint before enabling create. The preview response is the server dry-run from the
  same generator used by persisted creation.
- `AdminModulesPanel.tsx` renders resolver-backed by-week rows from
  `GET /admin/modules/{moduleId}/sections/by-week` with `includeUnstamped=true`; it does not regroup a
  client-side section list.
- `LecturerModuleDetail.tsx` renders an assigned-lecturer by-week view from
  `GET /modules/{moduleId}/sections/by-week`, plus `SectionMetadataEditor` for stored week/date/lab
  deadline edits.
- `SectionUploadControl.tsx` accepts `.ipynb` only for lab sections and can send upload-time `dueAt`
  through the controlled multipart helper.
- Student section views display lab deadlines. `StudentAssetRow.tsx` routes `assetKind='processable'`
  through signed URLs and `assetKind='attachment'` through the authenticated backend download endpoint.

Section add/delete/reorder remains absent from the UI. The 5.5e browser gate asserts those controls are
not present and backend mutation routes are absent/rejected.

## Stage 9 My Progress UI
Stage 9 adds a thin current-student dashboard at `/student/progress`:

- `frontend/src/app/(app)/student/page.tsx` links to My Progress from the student home.
- `frontend/src/app/(app)/student/progress/page.tsx` mounts `ProgressDashboard`.
- `frontend/src/features/progress/ProgressDashboard.tsx` calls `api.progress.getDashboard`,
  `api.progress.getModule`, and `api.progress.setTargetGrade` through the generated client wrapper.
- The dashboard renders module cards, a target-grade select with auto-save, the six deterministic
  forecast labels, an expandable calculation explanation, text fallback for trend data, topic mastery
  rows, and privacy-safe benchmark copy.
- It follows the current inline-style idiom because the Stage 4.9 Tailwind/shared component system is
  not present in this checkout.

## Stage 10 Gamification UI
Stage 10 fills the My Progress gamification slot with `frontend/src/features/gamification/GamificationPanel.tsx`.
The panel is mounted by `ProgressDashboard`, keeps the existing `data-testid="gamification-placeholder"`
selector for Stage 9 compatibility, and calls `api.gamification.get()` through the generated-client
wrapper (`GET /student/gamification`).

The panel renders the server-owned streak status, earned badges, locked badge progress, and progress
items from the gamification response. It never awards badges or mutates streak state client-side;
`newBadgeIds` remains an API signal for one-time celebration behavior and is not an authority for
persistence.
## Stage 11.1 risk UI
Stage 11.1 adds `frontend/src/features/analytics/`:

- `LecturerRosterRiskPanel` calls `api.analytics.getLecturerRosterRisk(moduleId)` and displays
  `Needs support: N`, tier filtering, student rows, deterministic reason text, and exact cited metric
  key/value pairs.
- `StudentRiskCard` calls `api.analytics.getStudentRisk(moduleId)` and renders only the deterministic
  gentle `studentText` reasons. It does not render the `riskTier`, peer data, or lecturer labels even
  though the backend response carries the internal tier for consistency.
- The API wrapper remains the only product path for analytics calls; no direct browser `fetch()` was added.

## Stage 11.2 recommendation UI
Stage 11.2 extends `frontend/src/features/analytics/`:

- `LecturerRosterRiskPanel` can open a recommendation detail modal for an owned student. The modal renders
  deterministic reasons/metrics, lecturer draft copy, student nudge preview, and exactly Copy draft / Mark acted /
  Dismiss. There is no Send button and no send endpoint in the analytics client.
- `StudentRecommendationNudge` mounts in the My Progress `Where you stand` surface as the primary student nudge.
- `StudentRecommendationBanner` mounts on the student dashboard as a secondary, at-most-one active nudge.
- Student nudges are dismissible through `Not now` and do not use modals, push, email, toast, peer copy, or risk
  labels.
- The UI renders deterministic template text immediately while AI copy is pending or unavailable; student surfaces
  do not expose AI machinery.

## Stage 11.3 assessment insight UI
Stage 11.3 adds `LecturerAssessmentInsightsPanel` under `frontend/src/features/analytics/`:

- It calls `api.analytics.getLecturerAssessmentInsights(moduleId)` through the generated client wrapper.
- It renders aggregate-only question stats, most-missed ordering, wrong-option distractor counts/rates, topic
  mastery rows, and explicit unavailable/small-cohort messages.
- It mounts on the existing lecturer module detail page and adds no student-facing route.
- It does not render or receive student names, emails, IDs, attempt rows, AI copy, peer comparisons, or risk labels.

The browser gate asserts exact visible values against a seeded asymmetric distribution and scopes privacy checks to
the assessment panel because the same lecturer module page also contains legitimate roster-risk student rows from
Stage 11.1.

## Stage 11.4 workload planner UI
Stage 11.4 adds `StudentWorkloadPlanner` under `frontend/src/features/analytics/`:

- It calls the analytics wrapper workload methods generated from OpenAPI for availability read/update, active
  plan read, and plan generation.
- It mounts on the student module detail page as the module-specific planning surface and on My Progress as a
  compact selected-module planning surface.
- Availability controls are the only editable region: weekday checkboxes, preferred-window select, daily-minute
  number input, Generate/Regenerate, and Update availability.
- Plan items render from stored backend values: date/window/start/end when scheduled, label, estimate minutes,
  reason, tight badge, and tight message.
- Plan rows contain no edit, done, drag, accept/reject, mark-complete, or item mutation affordance. The 11.4
  browser gate asserts the absence of those controls and draggable rows.
- The compact My Progress mount avoids the word "Save" in the availability button so the existing Stage 9
  target-grade auto-save/no-Save-button assertion remains true.

## Stage 11.5 calendar export UI
Stage 11.5 extends `StudentWorkloadPlanner` with a snapshot download action:

- The planner renders `Download calendar snapshot` only after an active plan is loaded.
- `frontend/src/lib/api/wrapper.ts` exposes `api.analytics.downloadWorkloadPlanCalendar(planId)` as a controlled
  authenticated attachment download helper. It follows the existing wrapper auth contract: 401 redirects to login,
  while 403 surfaces `ForbiddenError` without signing the student out.
- The generated OpenAPI client includes the new export route, but the mounted UI uses the wrapper helper because
  browser blob downloads need filename/header handling.
- The action creates a local object URL, clicks a temporary anchor, and revokes the object URL after download.
- The export button does not add plan-item edit, done, drag, accept/reject, mark-complete, or auto-reschedule
  controls.

## E2E bridge and run teardown
`NEXT_PUBLIC_E2E_TEST_HOOKS=true` enables a browser-only `window.__xyzE2E` bridge for Playwright. It exposes Supabase session helpers, wrapper-backed `/me` and `/admin/users` calls with serializable result envelopes, and a single-use forced bearer-token override for deterministic 401 testing. The bridge is not registered unless the flag is exactly `true`.

Session 4.3.5e Part 4 removes the temporary `/tracer` recovery route and deletes `NEXT_PUBLIC_TRACER_ENABLED` from active source/runtime config. `NEXT_PUBLIC_E2E_TEST_HOOKS` and the E2E bridge remain for the Stage 4.1-4.3 browser gate.

Run-scoped E2E cleanup is handled by:

- `tests/e2e/fixtures/run-manifest.mjs` for `tests/e2e/.runs/{runId}.json` manifests and artifact-recording helpers.
- `tests/e2e/fixtures/teardown.mjs` for manifest-only cleanup.
- `tests/e2e/fixtures/seed.mjs` for static standing fixture setup plus empty run-manifest creation.

Teardown refuses unsafe targets, deletes only manifest-recorded IDs plus child rows derived from manifest-owned module/section IDs, deletes exact backend-shaped storage object keys, preserves standing seed actors unless manifest-owned, accepts app-created UUIDv7 IDs, and is idempotent.
