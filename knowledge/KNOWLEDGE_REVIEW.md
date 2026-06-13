# XYZ LMS Knowledge Base — Comprehensive Audit

**Review date:** 2026-06-10
**Reviewer:** Claude Code (claude-sonnet-4-6)
**Scope:** Every file under `knowledge/` — no exceptions
**Method:** Direct file reads; all findings based on actual file content

> **Relocated** 2026-06-13 from repo root → `knowledge/` to sit with the cross-cutting docs (STATUS / log /
> roadmap / open-questions / CODEBASE_REVIEW) per the dev-workflow "Review / audit docs" convention (C-001).

---

## RESOLUTION (2026-06-13) — all 27 carry a rule-13 state

> Resolved by Claude Code (Opus 4.8). **Reality-checked first (sacred rule):** the audit is a 2026-06-10
> snapshot; by 2026-06-13 a post-audit cleanup had already made most fixes (uncommitted). Each item was
> verified against current files/source/git, not re-applied blindly. Commits: **c47e7e4** (bucket 1
> correctness), **c3f640f** (bucket 2 convention), **this commit** (bucket 3 structural + this resolution).
> Rule-13 vocabulary: **fixed / deferred-to-named-session / accepted-with-rationale / rejected.**

| # | Anomaly | Bucket | Rule-13 state | Resolution |
|---|---|---|---|---|
| 1 | S-001 4.2 spec `approved` | 2 | **fixed** | → `done` (c3f640f) |
| 2 | S-002 4.4 spec `fully-verified` | 2 | **fixed** | → `done` |
| 3 | S-012 4.3.5d plan `approved` | 2 | **fixed** | → `executed` |
| 4 | S-013 4.4 plan `approved` | 2 | **fixed** | → `executed` |
| 5 | L-001 log `[blocker]` | 2 | **fixed** | `blocker` defined in dev-workflow + log Format header |
| 6 | L-002 log `[docs]` | 2 | **fixed** | `docs` defined likewise |
| 7 | S-004 4.3.5a spec `approved` | 2 | **fixed** | → `done` |
| 8 | S-005 4.3.5d spec `ready` | 2 | **fixed** | → `done` |
| 9 | S-006 4.3.5e spec `complete` | 2 | **fixed** | → `done` |
| 10 | S-007 E2-B1 spec `complete` | 2 | **fixed** | → `done` |
| 11 | S-008 E2 spec `complete` | 2 | **fixed** | → `done` |
| 12 | S-009 checkpoint-A spec `approved` | 2 | **fixed** | → `done` |
| 13 | S-010 checkpoint-D spec `complete` | 2 | **fixed** | → `done` |
| 14 | S-011 checkpoint-E spec `complete` | 2 | **fixed** | → `done` |
| 15 | H-001 1.0 `commit: ""` | 1 | **fixed** | → `0f8132c` (git-verified) (c47e7e4) |
| 16 | H-002 1.1 `commit: a1b2c3d` | 1 | **fixed** | placeholder **eliminated** → `0f8132c` (git-verified) |
| 17 | H-003 1.1b `commit: ""` | 1 | **fixed** | → `8144529` (Stage 1 FV commit) |
| 18 | H-004 2.2 `commit: ""` | 1 | **fixed** | → `2f922c9` (Session 2.2 commit) |
| 19 | H-005 7 finals omit `commit` | 1 | **fixed** | 7 real SHAs (8860a6e/5f92698/ae8a3c8/77886fd/8a4169c/6361c85/442f221); none unrecoverable |
| 20 | T-001 worker.md embedding gap | 1 | **fixed** | embedding section documents shipped code; verified vs `embedding_encoder.py`; `updated: 2026-06-10` |
| 21 | L-003 1.1b `report:` path | 2 | **fixed** | spec+plan → `knowledge/steps/stage-01/1.1b-browser-gate.md` |
| 22 | F-001 stage `3` vs `"03"` | 2 | **accepted-with-rationale** | bare-int is the 80+-file dominant convention; documented in dev-workflow; mass-rewrite rejected (sacred rule / don't-trade-drift) |
| 23 | F-002 stage-04 plan formats | 2 | **accepted-with-rationale** | same — convention documented, not churned |
| 24 | F-003 step-report formats | 2 | **accepted-with-rationale** | same |
| 25 | C-001 CODEBASE_REVIEW in `knowledge/` | 3 | **fixed** | `knowledge/` confirmed correct (cross-cutting home, documented in dev-workflow); KNOWLEDGE_REVIEW.md **relocated** there to co-locate — inconsistency removed |
| 26 | P-001 `specs/recovery/` single-file folder | 3 | **accepted-with-rationale** | deliberate cross-block strategy doc (not a session; 22 inbound refs); documented exception in dev-workflow; status is prose not frontmatter, so no status fix |
| 27 | Q-001 missing roadmap not in open-questions | 2/3 | **fixed** | roadmap now exists (`knowledge/roadmap.md`, v3); recorded in `open-questions.md`; historical `xyz-lms-final-roadmap-v2` refs in closed docs left as history |
| 28 | non-standard `type:` values (informational) | 2 | **accepted-with-rationale** | defined as accepted extension vocabulary in dev-workflow (intentional recovery/checkpoint/supplemental structure) |
| 29 | extra frontmatter fields (informational) | 2 | **accepted-with-rationale** | defined as accepted fields in dev-workflow |

**Body anomalies not in the numbered 27** (Parts 5–6), for completeness — all **accepted-with-rationale**:
L-004 (recovery `report:`→`archive/` paths: factually-correct structural consequence, documented),
W-001 (folder reference, valid), W-002 (final-report self-`report:` link: template artefact, harmless;
field now in the accepted-frontmatter set), ADR-stage `"4.3.5"` strings (same as the `stage:` convention).

**Summary:** 21 **fixed**, 6 **accepted-with-rationale** (F-001/002/003, P-001, items 28/29), 0 deferred,
0 rejected. No fabricated commit hashes; none genuinely unrecoverable. Audit **CLOSED**.

---

## Part 1 — Knowledge System Overview

### System description

The knowledge system is a structured, append-only documentation layer that tracks engineering intent for the XYZ LMS project. It is defined in `knowledge/dev-workflow.md` and enforces a three-artifact workflow per session: **spec → plan → report**. These artifacts live under `knowledge/specs/`, `knowledge/plans/`, and `knowledge/steps/` respectively, organised by stage folder.

### Five gates (per `dev-workflow.md`)
1. Spec first — no implementation without an approved spec.
2. Plan approved before code — no code without an approved plan.
3. Reports from evidence, not memory — command output must be recorded.
4. No silent scope drift — blockers must be documented before scope changes.
5. Code wins over docs — "Documentation is a cache of engineering intent, not a source of truth. When docs disagree with code…code wins."

### Cross-cutting files
- `knowledge/dev-workflow.md` — system definition and sacred rules
- `knowledge/STATUS.md` — current project status
- `knowledge/log.md` — append-only event log
- `knowledge/open-questions.md` — open and resolved questions
- `knowledge/CODEBASE_REVIEW.md` — live codebase review (placed in `knowledge/`, not repo root)

### Architecture reference files
- `knowledge/architecture/repo-skeleton.md`
- `knowledge/architecture/db-spine.md`
- `knowledge/architecture/auth-current-user-context.md`
- `knowledge/architecture/storage.md`
- `knowledge/architecture/frontend.md`
- `knowledge/architecture/worker.md`

### ADR files
- `knowledge/decisions/adr-003.md` through `knowledge/decisions/adr-024.md` (22 ADRs)

### Templates
- `knowledge/templates/session-spec.md`
- `knowledge/templates/session-plan.md`
- `knowledge/templates/session-report.md`

### Naming convention
Sessions are named `<stage>.<n>-<slug>` (e.g. `1.1-repo-skeleton`, `4.3.5a-client-edge-tracer-bullet`). The recovery block `4.3.5` introduced sub-sessions (`4.3.5a` through `4.3.5e`) and checkpoints (`4.3.5d-B0`, `4.3.5d-checkpoint-A`, etc.), which produced significant structural variation. Archive files under `knowledge/archive/stage-04/` hold superseded detailed checkpoint reports.

---

## Part 2 — Session Inventory

### Stage 01 (Skeleton)

| Session | Spec | Plan | Report | Status |
|---------|------|------|--------|--------|
| 1.0-bootstrap-memory | `knowledge/specs/stage-01/1.0-bootstrap-memory.md` | `knowledge/plans/stage-01/1.0-bootstrap-memory.md` | `knowledge/steps/stage-01/1.0-bootstrap-memory.md` | complete |
| 1.1-repo-skeleton | `knowledge/specs/stage-01/1.1-repo-skeleton.md` | `knowledge/plans/stage-01/1.1-repo-skeleton.md` | `knowledge/steps/stage-01/1.1-repo-skeleton.md` | complete |
| 1.1b-browser-gate | `knowledge/specs/stage-01/1.1b-browser-gate.md` | `knowledge/plans/stage-01/1.1b-browser-gate.md` | `knowledge/steps/stage-01/1.1b-browser-gate.md` | complete |

### Stage 02 (Identity/Access)

| Session | Spec | Plan | Report | Status |
|---------|------|------|--------|--------|
| 2.1-db-spine | `knowledge/specs/stage-02/2.1-db-spine.md` | `knowledge/plans/stage-02/2.1-db-spine.md` | `knowledge/steps/stage-02/2.1-db-spine.md` | complete |
| 2.2-supabase-auth | `knowledge/specs/stage-02/2.2-supabase-auth-current-user-context.md` | `knowledge/plans/stage-02/2.2-supabase-auth-current-user-context.md` | `knowledge/steps/stage-02/2.2-supabase-auth-current-user-context.md` | complete |
| 2.3-admin-flows | `knowledge/specs/stage-02/2.3-admin-flows.md` | `knowledge/plans/stage-02/2.3-admin-flows.md` | `knowledge/steps/stage-02/2.3-admin-flows.md` | complete |
| 2.4-module-base-views | `knowledge/specs/stage-02/2.4-module-base-views.md` | `knowledge/plans/stage-02/2.4-module-base-views.md` | `knowledge/steps/stage-02/2.4-module-base-views.md` | complete |

### Stage 03 (Content/Visibility)

| Session | Spec | Plan | Report | Status |
|---------|------|------|--------|--------|
| 3.1-file-upload | `knowledge/specs/stage-03/3.1-file-upload.md` | `knowledge/plans/stage-03/3.1-file-upload.md` | `knowledge/steps/stage-03/3.1-file-upload.md` | done |
| 3.2-publish-and-notes | `knowledge/specs/stage-03/3.2-publish-and-notes.md` | `knowledge/plans/stage-03/3.2-publish-and-notes.md` | `knowledge/steps/stage-03/3.2-publish-and-notes.md` | done |
| 3.3-student-visibility | `knowledge/specs/stage-03/3.3-student-visibility.md` | `knowledge/plans/stage-03/3.3-student-visibility.md` | `knowledge/steps/stage-03/3.3-student-visibility.md` | complete |

### Stage 04 Primary Sessions

| Session | Spec | Plan | Report | Status |
|---------|------|------|--------|--------|
| 4.1-transcript-upload | `knowledge/specs/stage-04/4.1-transcript-upload.md` | `knowledge/plans/stage-04/4.1-transcript-upload.md` | `knowledge/steps/stage-04/4.1-transcript-upload.md` | complete |
| 4.2-transcript-parse | `knowledge/specs/stage-04/4.2-transcript-parse-segments.md` | `knowledge/plans/stage-04/4.2-transcript-parse-segments.md` | `knowledge/steps/stage-04/4.2-transcript-parse-segments.md` | complete |
| 4.3-transcript-chunking | `knowledge/specs/stage-04/4.3-transcript-chunking.md` | `knowledge/plans/stage-04/4.3-transcript-chunking.md` | `knowledge/steps/stage-04/4.3-transcript-chunking.md` | complete |
| 4.4-embeddings | `knowledge/specs/stage-04/4.4-embeddings.md` | `knowledge/plans/stage-04/4.4-embeddings.md` | `knowledge/steps/stage-04/4.4-embeddings-final-report.md` | fully-verified |

### Stage 04 Recovery Block (4.3.5)

| Session | Spec | Plan | Report | Status |
|---------|------|------|--------|--------|
| 4.3.5 (recovery summary) | `knowledge/specs/recovery/client-edge-recovery-plan.md` | — | `knowledge/steps/stage-04/4.3.5-client-edge-recovery-final-report.md` | complete |
| 4.3.5a-client-edge-tracer | `knowledge/specs/stage-04/4.3.5a-client-edge-tracer-bullet.md` | `knowledge/plans/stage-04/4.3.5a-client-edge-tracer-bullet.md` | `knowledge/steps/stage-04/4.3.5a-client-edge-tracer-final-report.md` | approved (anomaly — see Part 5) |
| 4.3.5b-app-shell | `knowledge/specs/stage-04/4.3.5b-app-shell-role-routing.md` | `knowledge/plans/stage-04/4.3.5b-app-shell-role-routing.md` | `knowledge/steps/stage-04/4.3.5b-app-shell-role-routing-final-report.md` | done |
| 4.3.5c-admin-ui | `knowledge/specs/stage-04/4.3.5c-stage2-admin-ui-backfill.md` | `knowledge/plans/stage-04/4.3.5c-stage2-admin-ui-backfill.md` | `knowledge/steps/stage-04/4.3.5c-admin-ui-final-report.md` | done |
| 4.3.5d-content-ui | `knowledge/specs/stage-04/4.3.5d-stage3-content-ui-backfill.md` | `knowledge/plans/stage-04/4.3.5d-stage3-content-ui-backfill-plan.md` | `knowledge/steps/stage-04/4.3.5d-content-ui-final-report.md` | ready (anomaly — see Part 5) |
| 4.3.5d-B0-upload-helper | `knowledge/specs/stage-04/4.3.5d-B0-stage3-multipart-upload-helper.md` | `knowledge/plans/stage-04/4.3.5d-B0-stage3-multipart-upload-helper-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-B0-upload-helper.md` | done |
| 4.3.5d-B1-section-gen | `knowledge/specs/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair.md` | `knowledge/plans/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-B1-section-generation-repair.md` | done |
| 4.3.5d-E2-B1-url-denial | `knowledge/specs/stage-04/4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md` | `knowledge/plans/stage-04/4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md` | complete (anomaly — see Part 5) |
| 4.3.5d-E2-signed-url | `knowledge/specs/stage-04/4.3.5d-E2-signed-url-revocation-proof-and-cleanup.md` | `knowledge/plans/stage-04/4.3.5d-E2-signed-url-revocation-proof-and-cleanup-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-E2-signed-url-revocation.md` | complete (anomaly — see Part 5) |
| 4.3.5d-checkpoint-A | `knowledge/specs/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes.md` | `knowledge/plans/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-A-report.md` | approved (anomaly — see Part 5) |
| 4.3.5d-checkpoint-B | `knowledge/specs/stage-04/4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui.md` | `knowledge/plans/stage-04/4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-B-report.md` | done |
| 4.3.5d-checkpoint-C | `knowledge/specs/stage-04/4.3.5d-checkpoint-C-publish-unpublish-controls-and-status-separation.md` | `knowledge/plans/stage-04/4.3.5d-checkpoint-C-publish-unpublish-controls-and-status-separation-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-C-report.md` | done |
| 4.3.5d-checkpoint-D | `knowledge/specs/stage-04/4.3.5d-checkpoint-D-student-published-only-view-and-signed-url-open.md` | `knowledge/plans/stage-04/4.3.5d-checkpoint-D-student-published-only-view-and-signed-url-open-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-D-report.md` | complete (anomaly — see Part 5) |
| 4.3.5d-checkpoint-E | `knowledge/specs/stage-04/4.3.5d-checkpoint-E-full-stage3-content-visibility-browser-gate.md` | `knowledge/plans/stage-04/4.3.5d-checkpoint-E-full-stage3-content-visibility-browser-gate-plan.md` | `knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-E-report.md` | complete (anomaly — see Part 5) |
| 4.3.5e-transcript-ui | `knowledge/specs/stage-04/4.3.5e-stage4-transcript-ui-backfill.md` | `knowledge/plans/stage-04/4.3.5e-stage4-transcript-ui-plan.md` | `knowledge/steps/stage-04/4.3.5e-transcript-ui-final-report.md` | complete |

### Stage 04 supplemental step reports (4.4)

| File | Type | Status |
|------|------|--------|
| `knowledge/steps/stage-04/4.3.5e-regression-under-projection.md` | regression-report | passed |
| `knowledge/steps/stage-04/4.4-schema-preflight.md` | checkpoint-report | passed |
| `knowledge/steps/stage-04/4.4-truncation-assessment.md` | checkpoint-report | passed |
| `knowledge/steps/stage-04/4.4-embedding-worker.md` | checkpoint-report | passed |
| `knowledge/steps/stage-04/4.4-browser-gate.md` | checkpoint-report | passed |
| `knowledge/steps/stage-04/4.4-embeddings-final-report.md` | final-report | fully-verified |

---

## Part 3 — Cross-Cutting Files

### `knowledge/dev-workflow.md`
- Defines the three-artifact protocol, five gates, valid spec/plan statuses (`draft | approved | in-progress | done | superseded`), valid log types (`spec | plan | report | decision | fix | note`), and the sacred rule that code wins over docs.
- No anomalies found. This file is the authoritative reference for the entire system.

### `knowledge/STATUS.md`
- Last updated: 2026-06-10 15:20.
- All implemented stages are recorded as FULLY VERIFIED.
- "Next up" section points to Stage 4.5 planning.
- "Known issues" section is populated with 10 valid deferred items.
- No anomalies found.

### `knowledge/log.md`
- 61 entries from 2026-05-29 to 2026-06-10.
- Header specifies valid types: `spec | plan | report | decision | fix | note`.

**Anomaly L-001:** `knowledge/log.md` line 51 — type is `[blocker]`:
> `2026-06-08 15:59  [blocker]  4.3.5d-E2 signed URL revocation proof blocked…`
> `[blocker]` is not in the valid type list defined in the log header.

**Anomaly L-002:** `knowledge/log.md` lines 57–58 — type is `[docs]`:
> `2026-06-09 14:48  [docs]  consolidate 4.3.5 recovery reports…`
> `2026-06-09 15:02  [docs]  consolidate all 4.3.5e findings…`
> `[docs]` is not in the valid type list defined in the log header.

### `knowledge/open-questions.md`
- One resolved entry: queue technology selection (resolved 2026-06-01 using RQ).
- One open entry: module section generation policy, raised 2026-06-07. The question asks whether sections should be schedule-driven, template-driven, or MVP-default. The MVP-default path was used in 4.3.5d-B1 but the policy remains open.
- No anomalies.

### `knowledge/CODEBASE_REVIEW.md`
- **Anomaly C-001:** File is located at `knowledge/CODEBASE_REVIEW.md`, inside the `knowledge/` directory, not at the repo root. The document itself describes it as a codebase review report.
- Content: backend 193 passed, frontend tsc exit 0, migrations 0007, pgvector 0.8.2, 10 DB tables, embeddings 384-dim L2.
- No in-repo roadmap file found (referenced as absent).
- No `platform/llm` or `platform/events` directory (AI/event stages not yet started).
- No frontend unit/component tests.

---

## Part 4 — Template Audit

### `knowledge/templates/session-spec.md`
Standard frontmatter fields: `type`, `stage`, `session`, `slug`, `status`, `created`, `updated`, `owner`, `plan`, `report`.

### `knowledge/templates/session-plan.md`
Standard frontmatter fields: `type`, `stage`, `session`, `slug`, `status`, `created`, `updated`, `spec`, `report`.

### `knowledge/templates/session-report.md`
Standard frontmatter fields: `type`, `stage`, `session`, `slug`, `status`, `created`, `updated`, `spec`, `plan`, `commit`.

### Template compliance findings

**Extra fields observed (not in template) across specs:**
- `4.3.5a-client-edge-tracer-bullet.md` spec: `recovery_plan:`, `baseline_commit:`
- `4.3.5b-app-shell-role-routing.md` spec: `predecessor:`, `roadmap:`
- `4.3.5c-stage2-admin-ui-backfill.md` plan: `approved_by:`, `approved_at:`, `decision:`
- `4.3.5d-stage3-content-ui-backfill.md` spec: `satisfies_stage_gate:`
- `4.3.5d-B0-stage3-multipart-upload-helper.md` spec: `parent_session:`, `unblocks:`, `satisfies_stage_gate:`
- `4.3.5d-B1-stage3-module-section-auto-generation-repair.md` spec: `parent_session:`, `blocks:`, `satisfies_stage_gate:`
- `4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md` spec: `parent_session:`, `blocks:`, `satisfies_stage_gate:`
- `4.3.5d-E2-signed-url-revocation-proof-and-cleanup.md` spec: `parent_session:`, `satisfies_stage_gate:`
- `4.3.5d-checkpoint-A-lecturer-module-detail-notes.md` spec: `checkpoint:`
- `4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui.md` spec: `checkpoint:`, `depends_on:`
- `4.3.5d-checkpoint-C-publish-unpublish-controls-and-status-separation.md` spec: `checkpoint:`
- `4.3.5d-checkpoint-D-student-published-only-view-and-signed-url-open.md` spec: `checkpoint:`, `depends_on:`
- `4.3.5d-checkpoint-E-full-stage3-content-visibility-browser-gate.md` spec: `checkpoint:`, `depends_on:`
- `4.3.5e-stage4-transcript-ui-backfill.md` spec: `closes:`, `historical_checkpoint_*_report:` (multiple), `findings:`
- `4.3.5e-stage4-transcript-ui-plan.md` plan: `historical_checkpoint_a_b_report:`, `historical_checkpoint_c_d_report:`, `historical_checkpoint_e_report:`, `findings:`
- `4.4-embeddings.md` plan: `report:` field points to `4.4-embedding-worker.md` (the worker checkpoint), not a final report
- `3.3-student-visibility.md` spec: redundant `spec:` field in its own spec frontmatter
- `knowledge/archive/stage-04/4.3.5c/4.3.5c-stage2-admin-ui.md`: `adr:` field added to report
- Recovery block final-reports: add `canonical: true` (not in template)

**Non-standard `type:` values observed (not `session-spec`, `session-plan`, `session-report`):**
- `4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md` spec: `type: repair-session-spec`
- `4.3.5d-E2-signed-url-revocation-proof-and-cleanup.md` spec: `type: supplemental-gate-spec`
- `4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui.md` spec: `type: checkpoint-spec`
- `4.3.5d-checkpoint-C-publish-unpublish-controls-and-status-separation.md` spec: `type: checkpoint-spec`
- `4.3.5d-checkpoint-D-student-published-only-view-and-signed-url-open.md` spec: `type: checkpoint-spec`
- `4.3.5d-checkpoint-E-full-stage3-content-visibility-browser-gate.md` spec: `type: checkpoint-spec`
- `4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair-plan.md` plan: `type: repair-session-plan`
- `4.3.5d-E2-signed-url-revocation-proof-and-cleanup-plan.md` plan: `type: supplemental-gate-plan`
- `4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui-plan.md` plan: `type: checkpoint-plan`
- `4.3.5d-checkpoint-C-publish-unpublish-controls-and-status-separation-plan.md` plan: `type: checkpoint-plan`
- `4.3.5d-checkpoint-D-student-published-only-view-and-signed-url-open-plan.md` plan: `type: checkpoint-plan`
- `4.3.5d-checkpoint-E-full-stage3-content-visibility-browser-gate-plan.md` plan: `type: checkpoint-plan`
- `knowledge/steps/stage-04/4.3.5-client-edge-recovery-final-report.md`: `type: final-report`
- `knowledge/steps/stage-04/4.3.5a-client-edge-tracer-final-report.md`: `type: final-report`
- `knowledge/steps/stage-04/4.3.5b-app-shell-role-routing-final-report.md`: `type: final-report`
- `knowledge/steps/stage-04/4.3.5c-admin-ui-final-report.md`: `type: final-report`
- `knowledge/steps/stage-04/4.3.5d-content-ui-final-report.md`: `type: final-report`
- `knowledge/steps/stage-04/4.3.5e-transcript-ui-final-report.md`: `type: final-report`
- `knowledge/steps/stage-04/4.4-embeddings-final-report.md`: `type: final-report`
- `knowledge/steps/stage-04/4.3.5e-regression-under-projection.md`: `type: regression-report`
- `knowledge/archive/stage-04/4.3.5a/4.3.5a-e2e-fixtures.md`: `type: fixture-report`
- `knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-E2-signed-url-revocation.md`: `type: supplemental-gate-report`
- `knowledge/archive/stage-04/4.3.5d/4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md`: `type: repair-session-report`
- `knowledge/archive/stage-04/4.3.5d/findings-4.3.5d.pre-consolidation.md`: `type: findings`
- `knowledge/archive/stage-04/4.3.5c/findings-4.3.5c.pre-consolidation.md`: `type: findings`
- `knowledge/archive/stage-04/4.3.5e/findings-4.3.5e.pre-consolidation.md`: `type: findings`

**Observation:** The proliferation of non-standard types is intentional to represent the recovery block's sub-session and checkpoint structure. The template system was designed for linear sessions and was not extended to cover repair/checkpoint/supplemental patterns.

---

## Part 5 — Content Quality

### Status value anomalies

Valid statuses per `dev-workflow.md`: `draft | approved | in-progress | done | superseded`.

**Anomaly S-001:** `knowledge/specs/stage-04/4.2-transcript-parse-segments.md` — `status: approved`
The session is complete and has a final report. The spec status was never updated from `approved` to `done`. The 4.2 step report explicitly notes: "Spec exists and is `status: approved`", confirming the spec was not updated at closure.

**Anomaly S-002:** `knowledge/specs/stage-04/4.4-embeddings.md` — `status: fully-verified`
`fully-verified` is not a valid status. The spec should be `status: done`.

**Anomaly S-003:** `knowledge/steps/stage-04/4.4-embeddings-final-report.md` — `status: fully-verified`
Same non-standard value in a report context. Reports use `complete` throughout other sessions; `fully-verified` is a project-level stage state, not a per-document status.

**Anomaly S-004:** `knowledge/specs/stage-04/4.3.5a-client-edge-tracer-bullet.md` — `status: approved`
The session is complete. The spec was not updated to `done` at closure.

**Anomaly S-005:** `knowledge/specs/stage-04/4.3.5d-stage3-content-ui-backfill.md` — `status: ready`
`ready` is not a valid status. Closest valid value would be `approved`.

**Anomaly S-006:** `knowledge/specs/stage-04/4.3.5e-stage4-transcript-ui-backfill.md` — `status: complete`
`complete` is not in the valid status list. Valid value would be `done`.

**Anomaly S-007:** `knowledge/specs/stage-04/4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md` — `status: complete`
Same: `complete` is not a valid status.

**Anomaly S-008:** `knowledge/specs/stage-04/4.3.5d-E2-signed-url-revocation-proof-and-cleanup.md` — `status: complete`
Same: `complete` is not a valid status.

**Anomaly S-009:** `knowledge/specs/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes.md` — `status: approved`
The checkpoint is complete. Spec was not updated to `done` at closure.

**Anomaly S-010:** `knowledge/specs/stage-04/4.3.5d-checkpoint-D-student-published-only-view-and-signed-url-open.md` — `status: complete`
`complete` is not a valid status.

**Anomaly S-011:** `knowledge/specs/stage-04/4.3.5d-checkpoint-E-full-stage3-content-visibility-browser-gate.md` — `status: complete`
`complete` is not a valid status.

**Anomaly S-012:** `knowledge/plans/stage-04/4.3.5d-stage3-content-ui-backfill-plan.md` — `status: approved`
The corresponding session is complete. Plan was not updated to `executed`.

**Anomaly S-013:** `knowledge/plans/stage-04/4.4-embeddings.md` — `status: approved`
Session 4.4 is fully verified. Plan was not updated to `executed`.

**Note on archive files:** Files under `knowledge/archive/` consistently use `complete` as status. This is widespread across archive checkpoint reports but is consistent within its own convention. All `type: findings` files use `resolved` or `closed`. These are archived files and the convention difference is less critical than the active spec/plan anomalies.

### Stage number formatting inconsistencies

**Anomaly F-001:** Stage 03 specs and plans use `stage: 3` (integer) rather than `stage: "03"` (quoted string):
- `knowledge/specs/stage-03/3.2-publish-and-notes.md` — `stage: 3`
- `knowledge/specs/stage-03/3.3-student-visibility.md` — `stage: 3`
- `knowledge/plans/stage-03/3.2-publish-and-notes.md` — `stage: 3`
- `knowledge/plans/stage-03/3.3-student-visibility.md` — `stage: 3`

**Anomaly F-002:** Stage 04 primary plans use `stage: 4` (integer); recovery plans use `stage: "04"` (quoted string) or `stage: "4.3.5"` (quoted string):
- `knowledge/plans/stage-04/4.1-transcript-upload.md` — `stage: 4`
- `knowledge/plans/stage-04/4.2-transcript-parse-segments.md` — `stage: 4`
- `knowledge/plans/stage-04/4.3-transcript-chunking.md` — `stage: 4`
- `knowledge/plans/stage-04/4.3.5a-client-edge-tracer-bullet.md` — `stage: 04` (unquoted integer that happens to be valid, but inconsistent)
- `knowledge/plans/stage-04/4.3.5b-app-shell-role-routing.md` — `stage: "04"` (quoted string)

**Anomaly F-003:** Stage 04 step reports use `stage: 4` (integer) inconsistently:
- `knowledge/steps/stage-04/4.1-transcript-upload.md` — `stage: 4`
- `knowledge/steps/stage-04/4.2-transcript-parse-segments.md` — `stage: 4`
- `knowledge/steps/stage-04/4.3-transcript-chunking.md` — `stage: 4`
- `knowledge/steps/stage-02/2.1-db-spine.md` — `stage: 2`
- `knowledge/steps/stage-02/2.3-admin-flows.md` — `stage: 2`
- `knowledge/steps/stage-03/3.1-file-upload.md` — `stage: 3`
- `knowledge/steps/stage-03/3.2-publish-and-notes.md` — `stage: 3`
- `knowledge/steps/stage-03/3.3-student-visibility.md` — `stage: 3`
- `knowledge/steps/stage-02/2.4-module-base-views.md` — `stage: 02`

There is no single consistent convention. Files in the same stage use `2`, `02`, `3`, `03`, `4`, `04`, `"4.3.5"`, and `"4.4"`.

### Plan `report:` link anomalies

**Anomaly L-003:** `knowledge/specs/stage-01/1.1b-browser-gate.md` — `report: "knowledge/steps/1.1b-browser-gate.md"` is missing the `stage-01/` folder prefix. The actual file is at `knowledge/steps/stage-01/1.1b-browser-gate.md`. The matching plan `knowledge/plans/stage-01/1.1b-browser-gate.md` has the same incorrect path.

**Anomaly L-004:** Recovery sub-session specs with `report:` paths pointing to `knowledge/archive/stage-04/...` rather than `knowledge/steps/...`:
- `knowledge/specs/stage-04/4.3.5d-B0-stage3-multipart-upload-helper.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-B0-upload-helper.md`
- `knowledge/specs/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-B1-section-generation-repair.md`
- `knowledge/specs/stage-04/4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-E2-B1-post-unpublish-signed-url-denial-status-repair.md`
- `knowledge/specs/stage-04/4.3.5d-E2-signed-url-revocation-proof-and-cleanup.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-E2-signed-url-revocation.md`
- `knowledge/specs/stage-04/4.3.5d-checkpoint-A-lecturer-module-detail-notes.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-A-report.md`
- `knowledge/specs/stage-04/4.3.5d-checkpoint-B-lecturer-pdf-upload-and-asset-replace-ui.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-B-report.md`
- `knowledge/specs/stage-04/4.3.5d-checkpoint-C-publish-unpublish-controls-and-status-separation.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-C-report.md`
- `knowledge/specs/stage-04/4.3.5d-checkpoint-D-student-published-only-view-and-signed-url-open.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-D-report.md`
- `knowledge/specs/stage-04/4.3.5d-checkpoint-E-full-stage3-content-visibility-browser-gate.md` — `report: knowledge/archive/stage-04/4.3.5d/4.3.5d-checkpoint-E-report.md`

This is a structural consequence of the recovery block: checkpoint-level reports were archived while the canonical session-level final report lives under `knowledge/steps/`. The archive links are factually correct paths; the deviation is from the template convention that `report:` points to `knowledge/steps/`.

### Commit hash anomalies

**Anomaly H-001:** `knowledge/steps/stage-01/1.0-bootstrap-memory.md` — `commit: ""` (empty string).
**Anomaly H-002:** `knowledge/steps/stage-01/1.1-repo-skeleton.md` — `commit: "a1b2c3d"`. This is a placeholder hash (7 hex characters that spell out an obvious pattern), not a real git SHA. No commit with this hash exists in recent log.
**Anomaly H-003:** `knowledge/steps/stage-01/1.1b-browser-gate.md` — `commit: ""` (empty string).
**Anomaly H-004:** `knowledge/steps/stage-02/2.2-supabase-auth-current-user-context.md` — `commit: ""` (empty string).
**Anomaly H-005:** All recovery block final-report files under `knowledge/steps/stage-04/` with `type: final-report` omit the `commit:` field entirely (not blank, just absent from frontmatter). Affected files: `4.3.5-client-edge-recovery-final-report.md`, `4.3.5a-client-edge-tracer-final-report.md`, `4.3.5b-app-shell-role-routing-final-report.md`, `4.3.5c-admin-ui-final-report.md`, `4.3.5d-content-ui-final-report.md`, `4.3.5e-transcript-ui-final-report.md`, `4.4-embeddings-final-report.md`.

### Open-question reference

**Anomaly Q-001:** `knowledge/plans/stage-04/4.2-transcript-parse-segments.md` contains an open-questions note: "xyz-lms-final-roadmap.md is not present in this checkout." This is also noted in `knowledge/plans/stage-04/4.3.5e-stage4-transcript-ui-plan.md` open questions: "The roadmap file `xyz-lms-final-roadmap-v2.md` is referenced by the session but is absent from this checkout." The roadmap file is absent from the repository and is not recorded in `knowledge/open-questions.md`.

### `client-edge-recovery-plan.md` placement

**Anomaly P-001:** `knowledge/specs/recovery/client-edge-recovery-plan.md` is under `knowledge/specs/recovery/` — a folder that exists for this file alone. All other specs are under stage-numbered folders. The file's `status: complete` is not in the valid status list.

---

## Part 6 — Timestamp and Linking Consistency

### Timestamps

**Missing `created` field:**
- `knowledge/steps/stage-04/4.3.5-client-edge-recovery-final-report.md` — no `created:` field in frontmatter
- `knowledge/steps/stage-04/4.3.5a-client-edge-tracer-final-report.md` — no `created:` field in frontmatter
- `knowledge/steps/stage-04/4.3.5b-app-shell-role-routing-final-report.md` — no `created:` field in frontmatter
- `knowledge/steps/stage-04/4.3.5c-admin-ui-final-report.md` — has `created: 2026-06-09`, present

**Missing `updated` field:**
- `knowledge/steps/stage-04/4.3.5-client-edge-recovery-final-report.md` — no `updated:` field

**Stale `updated` date:**
- `knowledge/architecture/worker.md` — `updated: 2026-06-01 19:58`. This file documents the transcript ingestion worker. Session 4.3.5e Part 2 added terminal-state repair to `chunk_service.py` and the change-history in the file records a 4.3.5e update. However, the `updated:` frontmatter field still reads `2026-06-01 19:58`, not the date of the 4.3.5e update. More critically: the file does not describe the embedding worker added in Session 4.4, despite 4.4 making significant worker architecture changes (separate `embedding` queue, `embedding_worker` service, `SentenceTransformersEmbeddingEncoder`).

**Anomaly T-001:** `knowledge/architecture/worker.md` — `updated: 2026-06-01 19:58` — the frontmatter timestamp has not been updated since the initial stage-04 session, despite documented changes in 4.3.5e Part 2 and a structurally significant new worker being added in Stage 4.4 (the embedding worker). The `change history` section within the file records only a 2026-06-01 entry.

### Wikilink linking

Wikilinks (`[[...]]`) are used throughout for cross-referencing. Most links are consistent with actual file paths.

**Anomaly W-001:** Archive files linked from `knowledge/steps/stage-04/4.3.5e-transcript-ui-final-report.md`:
> `- Historical report archive: \`knowledge/archive/stage-04/4.3.5e/\``
This is a folder reference (not a file link). The folder exists with 6 files.

**Anomaly W-002:** `knowledge/steps/stage-04/4.3.5a-client-edge-tracer-final-report.md` — the `report:` field in frontmatter reads `knowledge/steps/stage-04/4.3.5a-client-edge-tracer-final-report.md`, meaning it self-links. This is present in other final-report files. It is likely a template artefact but is technically a self-referential link.

**ADR stage consistency:**
- `knowledge/decisions/adr-023-stage2-admin-module-membership-projection.md` — `stage: "4.3.5"` (string, recovery block notation)
- `knowledge/decisions/adr-024-stage-4-3-post-chunk-terminal-status.md` — `stage: "4.3.5"` (string)
- All other ADRs (adr-003 through adr-022) use numeric stages (e.g., `stage: 3`, `stage: 4`). The two 4.3.5 ADRs are consistent with each other but differ from earlier ADRs.

---

## Part 7 — Health Summary

### Overall health
The knowledge base is functional and production-relevant. Every implemented stage has at least one spec, plan, and report. The archive system is well-organised. The recovery block (4.3.5) produced a significant expansion in structural complexity and non-standard conventions, but all sessions are traceable and the canonical final reports consolidate the evidence.

### Strengths
- Complete spec → plan → report coverage for all implemented sessions.
- Append-only `log.md` is current and provides a coherent project timeline.
- `STATUS.md` is current and accurate as of 2026-06-10.
- ADRs are present for all major architectural decisions (22 ADRs, adr-003 through adr-024).
- Archive system correctly separates superseded checkpoint reports from active canonical reports.
- Browser gate evidence is recorded with real run IDs, command output, and DB queries.
- Recovery block final reports (`canonical: true`) consolidate detailed checkpoint history into navigable single documents.

### Issues requiring attention (by priority)

#### High — protocol violations in active files
1. **Anomaly S-001** — `4.2-transcript-parse-segments.md` spec has `status: approved` for a completed session.
2. **Anomaly S-002** — `4.4-embeddings.md` spec has `status: fully-verified` which is not a valid status value.
3. **Anomaly S-012** — `4.3.5d-stage3-content-ui-backfill-plan.md` plan has `status: approved` for a completed session (should be `executed`).
4. **Anomaly S-013** — `4.4-embeddings.md` plan has `status: approved` for a fully verified session (should be `executed`).
5. **Anomaly L-001** — `log.md` line 51 uses `[blocker]` type, not in the valid type list.
6. **Anomaly L-002** — `log.md` lines 57–58 use `[docs]` type, not in the valid type list.

#### Medium — non-standard status values in active specs
7. **Anomaly S-004** — `4.3.5a` spec has `status: approved` for a complete session.
8. **Anomaly S-005** — `4.3.5d` spec has `status: ready` (non-standard).
9. **Anomaly S-006** — `4.3.5e` spec has `status: complete` (non-standard; should be `done`).
10. **Anomaly S-007** — `4.3.5d-E2-B1` spec has `status: complete`.
11. **Anomaly S-008** — `4.3.5d-E2` spec has `status: complete`.
12. **Anomaly S-009** — `4.3.5d-checkpoint-A` spec has `status: approved` for a complete checkpoint.
13. **Anomaly S-010** — `4.3.5d-checkpoint-D` spec has `status: complete`.
14. **Anomaly S-011** — `4.3.5d-checkpoint-E` spec has `status: complete`.

#### Medium — commit field anomalies
15. **Anomaly H-001** — `steps/stage-01/1.0-bootstrap-memory.md`: `commit: ""` (empty).
16. **Anomaly H-002** — `steps/stage-01/1.1-repo-skeleton.md`: `commit: "a1b2c3d"` (placeholder hash).
17. **Anomaly H-003** — `steps/stage-01/1.1b-browser-gate.md`: `commit: ""` (empty).
18. **Anomaly H-004** — `steps/stage-02/2.2-supabase-auth-current-user-context.md`: `commit: ""` (empty).
19. **Anomaly H-005** — All 7 recovery `final-report` type reports under `steps/stage-04/` omit the `commit:` field entirely.

#### Medium — stale architecture documentation
20. **Anomaly T-001** — `knowledge/architecture/worker.md` (`updated: 2026-06-01 19:58`): does not document the Stage 4.4 embedding worker (separate `embedding` queue, `embedding_worker` Docker service, `SentenceTransformersEmbeddingEncoder`, process-level model cache, embed-only retry config, `EMBEDDING_MODEL_PATH`/`EMBEDDING_DEVICE`/`EMBEDDING_BATCH_SIZE` config vars). The file is structurally stale relative to implemented source.

#### Low — path and naming inconsistencies
21. **Anomaly L-003** — `1.1b-browser-gate.md` spec and plan: `report:` path missing `stage-01/` prefix.
22. **Anomaly F-001** — Stage 03 uses `stage: 3` instead of `stage: "03"`.
23. **Anomaly F-002** — Stage 04 plans use inconsistent stage number formats.
24. **Anomaly F-003** — Stage 02–04 step reports use inconsistent stage number formats.
25. **Anomaly C-001** — `CODEBASE_REVIEW.md` is inside `knowledge/` rather than at repo root.
26. **Anomaly P-001** — `specs/recovery/` is a single-file folder not following the `stage-NN/` convention.
27. **Anomaly Q-001** — Missing roadmap file (`xyz-lms-final-roadmap.md` / `xyz-lms-final-roadmap-v2.md`) not recorded in `open-questions.md`.

#### Low — template deviations (informational)
28. Non-standard `type:` values are widespread in recovery block files. These represent intentional extension of the template to cover checkpoint/repair/supplemental patterns not anticipated by the original template design.
29. Extra frontmatter fields (`checkpoint:`, `satisfies_stage_gate:`, `parent_session:`, etc.) are consistent within the recovery block conventions but absent from templates.

---

## Part 8 — Recovery Block Documentation (4.3.5)

### Overview

The recovery block 4.3.5 was created after stages 1–4.3 were backend-verified but lacked browser proof. Its purpose was to add real browser-→-backend-→-DB verification for every stage. The block ran from 2026-06-03 to 2026-06-09 and produced 5 primary sessions (a–e), 7 sub-sessions (B0, B1, E2-B1, E2, checkpoint-A through checkpoint-E), and one summary recovery plan.

### Entry point

`knowledge/specs/recovery/client-edge-recovery-plan.md` — status: `complete`. This is a standalone summary document with no corresponding plan or report files (not a session in the three-artifact sense). It pre-dates the sessions and records the overall recovery strategy.

### Session sequence and rationale

| Session | Purpose | Outcome |
|---------|---------|---------|
| 4.3.5a | Client edge: GET /me, Supabase auth, E2E fixtures, throwaway /tracer page, Playwright proof | All 15 tracer assertions passed |
| 4.3.5b | App shell: role routing, 401/403 recovery, E2E bridge, token refresh | All 7 shell assertions passed |
| 4.3.5c | Stage 2 admin UI backfill + browser gate | Stage 2 FULLY VERIFIED |
| 4.3.5d | Stage 3 content UI backfill + browser gate | Blocked at Checkpoint 0; required B0 and B1 repairs before resuming |
| 4.3.5d-B1 | Backend repair: module creation auto-generates 4 default sections | Unblocked 4.3.5d |
| 4.3.5d-B0 | Frontend repair: add `upload.ts` multipart helper | Unblocked Checkpoint B |
| 4.3.5d Checkpoints A–E | Lecturer notes, upload, publish, student view, full browser gate | Stage 3 FULLY VERIFIED at Checkpoint E |
| 4.3.5d-E2 | Supplemental: prove post-unpublish signed URL returns 403 | Blocked: found 404 instead of 403 |
| 4.3.5d-E2-B1 | Backend repair: fix signed URL denial status from 404 to 403 | Stage 3 returned to FULLY VERIFIED |
| 4.3.5e | Stage 4.1–4.3 transcript UI backfill + browser gate | Stage 4.1–4.3 FULLY VERIFIED; recovery block COMPLETE |

### Archive structure

All detailed checkpoint reports were consolidated into canonical final-report files under `knowledge/steps/stage-04/`. Source checkpoint reports were archived under `knowledge/archive/stage-04/`:

- `knowledge/archive/stage-04/4.3.5a/` — 2 files: checkpoint report + e2e fixtures report
- `knowledge/archive/stage-04/4.3.5b/` — 1 file: session report
- `knowledge/archive/stage-04/4.3.5c/` — 2 files: session report + pre-consolidation findings
- `knowledge/archive/stage-04/4.3.5d/` — 12 files: checkpoint 0 through E reports, B0, B1, E2-B1 repair reports, E2 supplemental report, pre-consolidation files
- `knowledge/archive/stage-04/4.3.5e/` — 6 files: part 2 through 5 reports + pre-consolidation files

### Known structural anomalies introduced by the recovery block

1. **Recovery sub-session reports point to `archive/` not `steps/`**: Checkpoint-level specs have `report:` links pointing to `knowledge/archive/stage-04/4.3.5d/...` rather than `knowledge/steps/...`. This is technically correct (the files exist) but deviates from template convention.

2. **Non-standard spec types**: `checkpoint-spec`, `repair-session-spec`, `supplemental-gate-spec` — none are in the template `type:` set.

3. **Non-standard plan types**: `checkpoint-plan`, `repair-session-plan`, `supplemental-gate-plan`.

4. **Non-standard `status:` values**: `ready`, `complete`, `fully-verified`, `partially-executed` appear in recovery block files.

5. **`canonical: true` field**: Added to all `final-report` type reports to signal that the canonical active report is the consolidated version, not the archived checkpoint parts.

6. **Findings files (`type: findings`)**: Three `findings-*.pre-consolidation.md` files exist as separate documents (not embedded in a report). These are archived pre-consolidation copies; their active counterparts are now consolidated into the final reports.

7. **`specs/recovery/` folder**: Single-file, non-stage-numbered folder. The recovery plan predates the sessions and has no parallel plan or report.

### Post-recovery findings recorded in final reports

- F-4.3.5c-001: E2E actor `.test` email domain rejected by `EmailStr` validation → fixed by changing E2E domain to `xyz-lms-e2e.dev`
- F-4.3.5d-001: Module creation auto-generation absent → fixed in 4.3.5d-B1
- F-4.3.5d-002: `upload.ts` missing → fixed in 4.3.5d-B0
- F-4.3.5d-003: Lecturer section list DTO too thin for direct status read → resolved by per-section detail fetches
- F-4.3.5d-004: Lecturer notes wrapper method missing → resolved by wrapper extension
- F-4.3.5d-005: Post-unpublish fresh signed URL returned 404 not 403 → fixed in 4.3.5d-E2-B1
- F-4.3.5e-001: No persisted 4.3.5e spec file existed → fixed by persisting spec/plan
- F-4.3.5e-002: Successful parse+chunk left `transcript.status = "chunking"` → fixed in Part 2 (chunk_service.py)
- F-4.3.5e-003: Product status endpoint exposes no segment/chunk counts → accepted non-blocking
- F-4.3.5e-004: Existing transcript frontend code bypassed auth recovery pattern → fixed in Part 3
- F-4.3.5e-005: E2E lacked run manifest, safe teardown, and DB proof helpers → fixed in Part 4

All recovery block findings are resolved or accepted with rationale. No open findings remain.

---

*End of knowledge base audit. Review date: 2026-06-10.*
