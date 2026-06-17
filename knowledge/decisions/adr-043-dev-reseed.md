# ADR-043 - Dev reseed replaces legacy module backfill (Stage 5.5d)

- **Status:** Accepted (2026-06-17)
- **Stage:** 5.5d
- **Related:** [[specs/stage-05/5.5-module-schedule-section-metadata]],
  [[steps/stage-05/5.5d-dev-reseed]]

## Context
The roadmap originally called for a backfill path for existing dev modules. After 5.5a, in-place
metadata stamping is the wrong mechanism: legacy modules were created from a fixed 4-section template,
while the reference schedule generates 28 lecture/lab sections. No real course schedule reproduces the
legacy shape, and stamping would create fake schedule semantics over structurally wrong data.

The repository and attached Stage 5.5 context do not contain an authoritative per-module schedule map
for the historical dev rows. The "29 modules" reference is a row-count snapshot, not a curriculum
source of truth.

## Decision
1. **Replace, do not stamp.** Dev modules are snapshotted, their dependent rows are deleted, and they
   are recreated through the schedule-driven generation flow.
2. **Use one explicit schedule for dev data.** Every recreated dev module uses the Stage 5.5 reference
   course schedule: 11 May to 26 Jun 2026, Monday/Tuesday/Wednesday lectures, Thursday lab, Friday quiz
   day. This is a dev-data decision, not a production curriculum rule.
3. **Preserve logical ownership and memberships.** The reseed keeps module title, description, owner,
   timezone, active flag, and non-duplicate memberships where possible. Module and section IDs change
   because this is replacement, not migration.
4. **Guard the destructive tool.** The CLI requires `--confirm-dev-reseed`, refuses production/staging,
   refuses non-local DB hosts unless explicitly overridden, and requires Alembic version `0021`.
5. **Seed one 5.5e fixture lab.** The first active recreated module gets a published lab with a
   processable PDF and an attachment `.ipynb`, using real storage-backed `section_assets` rows.

## Consequences
- Dev URLs that include old module or section IDs become stale after reseed.
- Any historical dev content attached to legacy modules is discarded with the throwaway dev DB data.
- 5.5e can rely on schedule-shaped dev modules and a lab fixture with both asset kinds.
- If a real curriculum import appears later, it should replace this dev-data seed with an explicit
  source file or importer.

## Alternatives rejected
- **In-place metadata stamping.** Rejected because it would assign weeks/dates to a 4-section shape no
  schedule produces.
- **Invent per-module schedules.** Rejected because no authored schedule list exists; one explicit
  reference schedule is more reproducible.
- **Run against production/staging.** Rejected outright; this is destructive local dev tooling.
