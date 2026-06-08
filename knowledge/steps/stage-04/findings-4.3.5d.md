---
type: findings
stage: "4.3.5"
session: "4.3.5d"
slug: stage3-content-ui-backfill
status: open
created: 2026-06-06
updated: 2026-06-08 11:37
spec: knowledge/specs/stage-04/4.3.5d-stage3-content-ui-backfill.md
plan: knowledge/plans/stage-04/4.3.5d-stage3-content-ui-backfill-plan.md
report: knowledge/steps/stage-04/4.3.5d-checkpoint-0-report.md
checkpoint_a_report: knowledge/steps/stage-04/4.3.5d-checkpoint-A-report.md
---

# Findings - 4.3.5d Stage 3 Content UI Backfill

## Linked documents
- Spec: [[specs/stage-04/4.3.5d-stage3-content-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5d-stage3-content-ui-backfill-plan]]
- Report: [[4.3.5d-checkpoint-0-report]]
- Findings: [[findings-4.3.5d]]
- Recovery plan: [[specs/recovery/client-edge-recovery-plan]]
- Architecture: [[architecture/frontend]]
- Repair spec: [[specs/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair]]
- Repair plan: [[plans/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair]]
- Repair report: [[4.3.5d-B1-section-generation-repair]]
- Checkpoint A spec: [[specs/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes]]
- Checkpoint A plan: [[plans/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes-plan]]
- Checkpoint A report: [[4.3.5d-checkpoint-A-report]]
- Upload helper spec: [[specs/stage-04/4.3.5d-B0-stage3-multipart-upload-helper]]
- Upload helper plan: [[plans/stage-04/4.3.5d-B0-stage3-multipart-upload-helper-plan]]
- Upload helper report: [[4.3.5d-B0-upload-helper]]
- Checkpoint B spec: [[specs/stage-04/4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui]]
- Checkpoint B plan: [[plans/stage-04/4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui-plan]]
- Checkpoint B report: [[4.3.5d-checkpoint-B-report]]

## Status
F-4.3.5d-001 is fixed in 4.3.5d-B1. Checkpoint A passed.

Stage 3 remains UI PENDING.

F-4.3.5d-002 is fixed in 4.3.5d-B0. Checkpoint B passed.

## Hard Blocker

### F-4.3.5d-001 - Module creation does not auto-generate sections
Status: fixed in 4.3.5d-B1

Severity: resolved hard blocker

Fixed by commit: 445ac7c

Evidence:
- Original Checkpoint 0 source inspection: `POST /admin/modules` previously created `CourseModule` and owner `CourseMembership`, but no `ModuleSection` rows.
- 4.3.5d-B1 implementation: `backend/app/domains/admin/service.py` now calls `generate_initial_sections` after the new `CourseModule` has an id and before the route commit.
- 4.3.5d-B1 implementation: `backend/app/domains/admin/section_generation.py` defines the temporary `mvp_default` policy and creates four sections: `Lecture 1`, `Lecture 2`, `Lab 1`, and `Assignment 1`.
- Generated sections default to `publish_status="draft"`, `status="active"`, and `lecturer_notes=None`.
- Backend test: `tests/test_admin.py::test_create_module_generates_default_sections`.
- Backend test: `tests/test_content.py::test_generated_sections_use_existing_visibility_rules`.
- Full backend verification: `151 passed, 78 warnings`.
- Frontend/API contract verification: `docker compose exec frontend npx tsc --noEmit` exited 0, and `bash scripts/generate-api-client.sh && git diff --exit-code frontend/src/lib/api` produced no diff.

Original empirical proof from Checkpoint 0:

```text
$ docker compose exec -T backend python - <<'PY'
...
created_module_id=019e9d32-4b6d-7925-a3ff-fbd7744285dc
module_sections_count=0
cleanup=rolled back transaction
PY
```

- Existing E2E fixture inserts `module_sections` directly. See `tests/e2e/fixtures/seed.mjs:271`.

Why this blocked:
- Stage 3 product model requires lecturers to fill predefined sections.
- Lecturers cannot create/delete/reorder sections in MVP.
- Direct section seeding is not valid browser proof for 4.3.5d because it bypasses the product section-generation path.

Resolution:
- Added a backend/product path that creates predefined `ModuleSection` records during admin module creation.
- 4.3.5d may resume at Checkpoint A.

## Prerequisite Blockers

### F-4.3.5d-002 - Missing multipart upload helper
Status: fixed in 4.3.5d-B0

Severity: resolved prerequisite blocker

Fixed by commit: 2f5ba50

Evidence:
- `frontend/src/lib/api/upload.ts` exists.
- `uploadSectionAsset(...)` supports `POST /modules/{module_id}/sections/{section_id}/assets`.
- `replaceSectionAsset(...)` supports `PUT /modules/{module_id}/sections/{section_id}/assets/{asset_id}`.
- The helper attaches the current Supabase bearer token via existing `OpenAPI.TOKEN` configuration.
- The helper uses `FormData` field `file` and does not manually set multipart `Content-Type`.
- The helper returns the generated `SectionAssetResponse` type.
- 401 signs out and redirects to `/login`; 403 surfaces `ForbiddenError` without signing out.
- Direct fetch scan allows only generated API core and `frontend/src/lib/api/upload.ts`.
- Frontend verification passed: `docker compose exec frontend npx tsc --noEmit` and `docker compose exec frontend npx next build`.
- Generated client freshness passed with no generated model/service/core/index drift.

Resolution: the approved multipart helper has been restored for Checkpoint B upload/replace UI work.

Checkpoint impact: Checkpoint B is unblocked from the upload-helper prerequisite. Stage 3 remains UI PENDING until the full 4.3.5d browser gate passes.

## Implementation Gaps After Blocker Resolution

### F-4.3.5d-003 - Lecturer read projection may be too thin
Status: addressed for Checkpoint B without backend projection change

Severity: resolved implementation prerequisite for Checkpoint B

Evidence:
- `GET /modules/{module_id}/sections` exists and role-splits lecturer/student responses through `list_module_sections`. See `backend/app/api/routers/content.py:75` and `backend/app/domains/content/service.py:163`.
- Lecturer list rows include `id`, `title`, `type`, `orderIndex`, `hasAssets`, and `hasNotes`, but not `publishStatus` or asset `processingStatus`. See `backend/app/platform/query/content_read.py:167` and `frontend/src/lib/api/models/SectionListItem.ts:5`.
- Lecturer detail includes `publishStatus` but not assets. See `frontend/src/lib/api/models/SectionDetail.ts:5`.
- Asset list includes asset `processingStatus`, but requires a separate per-section asset-list call. See `frontend/src/lib/api/models/SectionAssetResponse.ts:5`.
- Checkpoint A avoided a backend projection change by loading lecturer section detail per section. This provides `publishStatus` and `lecturerNotes` for the notes UI.
- Checkpoint B avoided a backend projection change by loading assets through the existing lecturer-only asset-list endpoint, `GET /modules/{module_id}/sections/{section_id}/assets`.
- Browser smoke proved asset `processingStatus` rendered separately from section `publishStatus` on product-generated sections.

Resolution: Checkpoint B uses per-section asset-list calls. No read projection change was required.

### F-4.3.5d-004 - Frontend wrapper does not expose full Stage 3 content surface
Status: partially addressed through Checkpoint B

Severity: implementation prerequisite

Evidence:
- Generated `ContentService` exposes list sections, get section, list assets, upload, signed URL, replace, notes, publish, and unpublish. See `frontend/src/lib/api/services/ContentService.ts:23`, `:77`, `:106`, `:140`, `:172`, `:208`, `:239`, and `:267`.
- Before Checkpoint A, `frontend/src/lib/api/wrapper.ts` exposed `getAssetDownloadUrl`, `getSection`, `listSections`, `publishSection`, and `uploadAsset`, but not list assets, replace asset, update notes, or unpublish.
- Checkpoint A added `api.content.updateNotes` and `api.modules.get` to support lecturer module detail and notes editing.
- Checkpoint B added `api.content.listAssets` for backend re-fetch after upload/replace.
- Checkpoint B uses `frontend/src/lib/api/upload.ts` for upload and asset-level replace instead of adding generated multipart methods to the wrapper.
- Checkpoint B removed stale feature-level upload/replace exports from `frontend/src/features/content/api/assets.ts` so `frontend/src/lib/api/upload.ts` is the lecturer UI upload/replace helper surface.

Remaining resolution: expose unpublish wrapper methods before the checkpoint that requires those behaviors.

## Contract Map

### Stage 3 write-path surface
Status: present in backend/generated client.

Evidence:
- Upload: `POST /modules/{module_id}/sections/{section_id}/assets`, generated method `uploadAssetModulesModuleIdSectionsSectionIdAssetsPost`.
- Replace: `PUT /modules/{module_id}/sections/{section_id}/assets/{asset_id}`, generated method `replaceAssetModulesModuleIdSectionsSectionIdAssetsAssetIdPut`.
- Notes: `PATCH /modules/{module_id}/sections/{section_id}/notes`, generated method `updateNotesModulesModuleIdSectionsSectionIdNotesPatch`.
- Publish: `POST /modules/{module_id}/sections/{section_id}/publish`, generated method `publishModulesModuleIdSectionsSectionIdPublishPost`.
- Unpublish: `POST /modules/{module_id}/sections/{section_id}/unpublish`, generated method `unpublishModulesModuleIdSectionsSectionIdUnpublishPost`.
- List assets: `GET /modules/{module_id}/sections/{section_id}/assets`, generated method `listAssetsModulesModuleIdSectionsSectionIdAssetsGet`.

### Lecturer and student read contracts
Status: present, with lecturer projection caveat.

Evidence:
- Lecturer `GET /modules/{module_id}/sections` returns active sections for the module, including drafts/unpublished, because `list_lecturer_section_rows` filters `ModuleSection.status == "active"` and not `publish_status`. See `backend/app/platform/query/content_read.py:167`.
- Student `GET /modules/{module_id}/sections` filters server-side to `ModuleSection.publish_status == "published"` and `status == "active"`. See `backend/app/platform/query/content_read.py:205`.
- Student section detail returns lecturer notes and completed assets for a published section. See `backend/app/platform/query/content_read.py:286`.

### Signed URL contract
Status: present.

Evidence:
- Endpoint: `GET /modules/{module_id}/sections/{section_id}/assets/{asset_id}/download-url`.
- Generated method: `getAssetDownloadUrlModulesModuleIdSectionsSectionIdAssetsAssetIdDownloadUrlGet`.
- Service checks student access against section `published`, section `active`, and asset `completed`; lecturers are allowed for assigned, non-archived sections. See `backend/app/domains/content/service.py:209`.
- Signed URL TTL comes from `SIGNED_READ_URL_TTL_SECONDS`, and the response gets `Cache-Control: no-store`. See `backend/app/domains/content/service.py:239` and `backend/app/api/routers/content.py:120`.

### Two-status-field contract
Status: separate fields confirmed.

Evidence:
- `SectionDetail.publishStatus` is generated from backend `SectionDetail.publish_status`.
- `SectionAssetResponse.processingStatus` is generated from backend `SectionAssetResponse.processing_status`.
- Upload and replace set `processing_status="completed"` immediately in the MVP. See `backend/app/domains/content/service.py:341` and `backend/app/domains/content/service.py:431`.

## Required follow-up
Proceed to Checkpoint B - lecturer PDF upload + asset-level replace UI.

Completed UI checkpoint: 4.3.5d Checkpoint B - Lecturer PDF upload + asset-level replace UI.

Resolved backend repair: Session 4.3.5d-B1 - Stage 3 Module Section Auto-Generation Repair.

Completed UI checkpoint: 4.3.5d Checkpoint A - Lecturer module detail + notes.

Future decision still open: how should module creation know what sections to create after the temporary MVP default is replaced?

| Option | Description | Tradeoff |
|---|---|---|
| Schedule-driven | Admin supplies lecture/lab/assignment schedule fields; backend generates sections from schedule | Best product fit, more backend/API work |
| Template-driven | Admin selects a predefined module template that creates sections | Clean and scalable, needs template model or seed |
| Minimal MVP default | Backend creates a small default section set | Fastest, but less faithful to schedule-based spec |

Recommendation: prefer schedule-driven if the current data model already has enough course date / lecture day / lab day fields. Use minimal MVP default only if explicitly recorded as temporary.
