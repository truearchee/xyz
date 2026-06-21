---
type: session-report
stage: 10
session: "10"
slug: gamification
status: fully-verified
created: 2026-06-20
updated: 2026-06-20
spec: knowledge/specs/stage-10/10-gamification.md
plan: knowledge/plans/stage-10/10a-foundation.md
commit: ""
---

# Stage 10 — Report — Gamification (10a foundation → 10b badges → 10c UI + gate)

> One continuous session delivered all three sub-sessions; this report covers 10a–10c.

## Linked documents
- Spec: [[specs/stage-10/10-gamification]]
- Plan: [[plans/stage-10/10a-foundation]]
- Report: [[steps/stage-10/10a-foundation]]
- ADRs: [[decisions/adr-056-gamification-course-timezone]] · [[decisions/adr-057-gamification-on-read-evaluation]]
- Roadmap: [[roadmap]]

## Summary
Built the unified **Learning streak** + four **badge families**, **derived/evaluated on read** from
`StudentActivityEvent` + the Stage 5.5 schedule + Stage 9 snapshots, **never awarded by the frontend**,
**idempotent + sticky**. Filled the Stage 9 My Progress placeholder with a Tailwind `GamificationPanel`.
**FULLY VERIFIED** on 2026-06-20: backend/type/unit verification green, Stage 10 browser gate A/B/C green,
and the clean standard-stack rule-14 run passed **24/24**. Post-review hardening on 2026-06-20 fixed the
concurrent-first-read `newBadgeIds` race, populated `nextScheduledDay` from a real future schedule lookup,
removed the unrelated Stage 6 screenshot churn from the merge surface, and updated architecture docs.

Owner decisions **A/A/A** (with refinements): flashcard volume = **distinct local days with a completed
flashcard session** (no per-card event exists; farm-proof; honestly relabelled); **`COURSE_TIMEZONE`
platform setting** (single IANA, DST-aware, default UTC; required hosted config at Stage 4.8); **Tailwind
panel** (no new inline-style debt). `studied_section` kept as a **content-domain** event (rule 7).

## Files changed
**Backend (new):** `app/domains/gamification/{__init__,streak,catalog,badges,schemas,service}.py`;
`app/platform/query/gamification_read.py`; `app/platform/events/studied_section.py` (the shared
`record_studied_section` helper); `app/platform/db/models/{student_badge,student_streak_state}.py`;
`app/api/routers/gamification.py`; `alembic/versions/0080_gamification_event_type.py` +
`0081_student_badge_and_streak_state.py`; `scripts/reconcile_gamification.py`;
`tests/test_gamification_{streak,service,studied_section,api}.py`.
**Backend (edited):** `app/platform/config.py` (`COURSE_TIMEZONE`); `pyproject.toml` (`tzdata`);
`app/platform/db/models/__init__.py`; `app/platform/db/models/student_activity_event.py` +
`app/platform/events/{recorder,__init__}.py` (`studied_section`); `app/domains/student_summaries/service.py`
(emit `studied_section` on the real student section read — the live-gate fix; the content-domain hook was
tried then reverted, so `content/service.py` + `content` router are net-unchanged); `app/main.py` (register
router); `app/domains/admin/dev_reseed.py` (`EXPECTED_ALEMBIC_VERSION` 0041→0081);
`tests/conftest.py` (truncate new tables); `tests/test_shared_check_union.py` (studied_section).
**Frontend (new):** `features/gamification/GamificationPanel.tsx` + `.test.tsx`; regenerated
`lib/api/services/GamificationService.ts` + `lib/api/models/{GamificationRead,EarnedBadgeRead,LockedBadgeRead,ProgressItemRead}.ts`.
**Frontend (edited):** `lib/api/index.ts` + `lib/api/wrapper.ts` (`api.gamification`);
`features/progress/ProgressDashboard.tsx` (render `<GamificationPanel/>` in the placeholder slot).
**Infra/knowledge:** `.env.example` (`COURSE_TIMEZONE`); `.context/stage10.override.yml`;
spec/plan/ADRs/architecture/roadmap/STATUS/log/open-questions; `tests/e2e/10-gamification.spec.ts`.

## Verification
| Command | Result | Notes |
|---|---|---|
| `alembic upgrade head` (fresh dev DB) | passed | ran `… 0041 → 0080 → 0081` |
| `alembic heads` | `0081 (head)` | single head; re-confirmed after post-review fixes |
| `alembic downgrade 0041 && alembic upgrade head` | passed | my migrations round-trip; re-run on a fresh DB after post-review fixes |
| `pytest tests/test_gamification_streak.py` | 13 passed | pure streak edges |
| `pytest tests/test_gamification_service.py` | 14 passed | primitives (incl. tz/day-end), award/idempotent/sticky/anti-farm, **concurrent first-read `newBadgeIds` returns inserted rows only**, `nextScheduledDay`, topic/module, reconcile==stored, studied_section engagement, **milestone keys off longest_streak (held after a later break)** |
| `pytest tests/test_gamification_studied_section.py` | 3 passed | once-per-day dedup + **read-survives-on-error AND the failure is logged (visible, not swallowed)** |
| `pytest tests/test_gamification_api.py` | 5 passed | 403 lecturer/admin, 200 shape + no-store, `nextScheduledDay`, award through event path |
| `pytest tests/test_gamification_service.py tests/test_gamification_api.py tests/test_shared_check_union.py` | 21 passed | post-review targeted rerun in rebuilt backend container |
| `pytest tests/test_shared_check_union.py` | passed | studied_section in the live CHECK union |
| `pytest` (full backend suite) | **660 passed, 0 failed** (174s) | rebuilt backend image; includes post-review gamification coverage |
| `python scripts/reconcile_gamification.py` | "reconcile OK" | recompute reproduces stored |
| `scripts/generate-api-client.sh` (from live OpenAPI) | clean | only `index.ts` + 5 new gamification files |
| `npx tsc --noEmit` (frontend) | exit 0 | incl. the new panel + test |
| `npm run test:unit` (frontend) | 12 passed | incl. 3 new `GamificationPanel` tests |
| `check:inline-styles` / `check:design-tokens` | no NEW violations | gate stays repo-red (Stage 12 backlog); panel is Tailwind-clean; removed the placeholder's inline section |
| `npx playwright test --list` | 24 tests / 19 files | Stage 10 Scenarios A/B/C discovered (rule-14 active suite) |
| `set -a; source .env.e2e; set +a; E2E_RUN_ID=e2e-stage10-full-clean-20260620230826 PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1` | **24 passed (6.3m)** | clean standard stack, app DB reset, migrated to `0081`, standing seed run, workers recreated; includes Stage 10 A/B/C and the required 4.5d/4.6d fault gates |
| `set -a; source .env.e2e; set +a; E2E_RUN_ID=e2e-stage10-reviewfix-20260620234724 PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1` | **24 passed (6.4m)** | post-review rerun after `newBadgeIds`/`nextScheduledDay` fixes, fresh DB reset, `0041 → 0080 → 0081` round-trip, standing seed, route prewarm |

## Security acceptance (criteria met by construction + tests; `/cso` pass pending)
- **No frontend-reachable endpoint creates a `StudentActivityEvent` arbitrarily** — `studied_section` is
  emitted server-side with a server-derived `uuid5` source_id + server clock; `student_id` is
  token-derived, never a body field. (`test_gamification_studied_section`)
- **No endpoint grants a badge or sets a streak** — `GET /student/gamification` is read-only-by-contract;
  badge inserts are server-decided (metric≥threshold from the caller's own events); reconcile is a CLI,
  not HTTP; `longest_streak` is `greatest(stored, computed)`. No POST awards anything.
- **No cross-student / score spoofing** — the endpoint takes no `student_id` param; all reads filter on
  the token's student. Scores are read from server-emitted `completed_quiz`/`perfect_quiz_score` events,
  never trusted from the client. **403** for lecturer/admin (`test_gamification_api`).

## Deviations from spec
- **Migration block 0048→0080/0081** per the mid-session Stage 10/11 coordination note (Stage 11 owns
  0057–0079). Recorded in spec/plan.
- **E2E Scenario A** drives the today-engaging action via a real in-browser **summary open**
  (`studied_section`, the real serving path) rather than driving the full Stage-5 quiz-generation UI
  (disproportionate for the gamification gate); the 10 distinct quizzes are seeded events and the
  quiz→event→badge path is covered by `test_gamification_api::test_student_award_through_event_path`. The
  streak increase + `streak_3`/`quizzes_10` award + idempotent reload + UI visibility are all asserted.
- **`flashcard` badge** relabelled to days-based (no per-card event exists) — owner-approved D1.

## Decisions made
- ADR-056 (gamification course timezone) + ADR-057 (on-read event-derived evaluation + studied_section
  read-records-an-event).

## Risks introduced
- **Merge with Stage 11:** event-type CHECK widen (additive, union CI guard) + migration rebase. The
  second branch in rebases onto the new head, re-runs the Alembic round-trip, re-pins
  `dev_reseed.EXPECTED_ALEMBIC_VERSION`, and re-runs the full Playwright suite (rule 14).
- **On-read recompute** scans events/schedule since enrollment (bounded, MVP-scale; "exact scan until
  justified"). Monotonic `longest_streak` persisted so it stays O(1) + survives a break.

## Follow-ups
- **`/cso`** security pass; **`/review`** + **`/qa`** pre-landing (recommended in the spec; not a remaining Stage 10 product-gate blocker).
- **Stage 4.8 carry-forward:** `COURSE_TIMEZONE` required in the hosted env list (open-questions).

## Live browser gate run (2026-06-20)
Ran on a real Supabase-backed stack (owner-delivered `.env`/`.env.e2e`; isolated to dodge the shared
`kyiv-backend` tag + occupied `:8000`/`:3000`): unique `da-nang-stage10-backend` image + workers on
:8025, production-built `da-nang-frontend` on :3025 (next dev OOM-killed under the 7.7 GiB Docker VM
shared with `baghdad`/`dallas` siblings → switched to `next build`/`start`, ~130 MiB), `COURSE_TIMEZONE=UTC`,
clean DB + seeded standing users.
- **Preflight:** stack up, single head `0081`, auth 200 (Supabase token → backend JWKS → endpoint 200).
- **Stage 10 gate GREEN:** `tests/e2e/10-gamification.spec.ts` **Scenarios A/B/C all pass**.
- **The gate caught a real bug (fixed + re-verified):** `studied_section` was hooked on the content
  route `get_module_section_detail` (`/student/modules/{id}/sections/{id}`), which the student UI never
  calls — the real path is `student_summaries.get_student_section_detail` (`GET /student/sections/{id}`).
  Moved the emission there via the new shared `platform/events.record_studied_section` helper (so a
  content-serving domain records it without a cross-domain import, rule 8), reverted the content hook,
  re-verified 19 backend tests. ADR-057 updated.
- **Earlier rule-14 full active suite: 21/24** in one isolated run. The only 3 failures were the fault-injection
  gates — `4.5d-summary-fault` (invalid_output, invalid_input) + `4.6d retry` — which self-recreate the
  `ai_worker` via the SHARED base-compose `kyiv-backend` image; under the active sibling stacks that isn't
  this workspace's code and races the isolated `s10-ai` worker, so the forced faults don't inject. **Not
  Stage 10 code:** the same `4.6d` file's non-fault test (replacement-continuity) passes, as do every
  read/UI/pipeline/embedding/glossary/assistant/progress gate + the 3 Stage 10 scenarios.
- **7-glossary** initially failed (`lecturer auth id` undefined) — it reads
  `process.env.SUPABASE_SERVICE_ROLE_KEY` directly, so it needs the standard `.env.e2e` export (the
  harness convention); **passes** with the env exported.
- **Final clean-stack run (standard compose): 24/24 PASSED.** Rebuilt `kyiv-backend:latest` from this
  workspace source (`sha256:5165e22042f73e7ce06fcf1b9c9061d8d83ec7c9f02cbf56f325bba710a9f843`);
  confirmed workers no longer contained stale assistant fields; reset app DB (`docker compose down -v`);
  brought up `docker compose up -d --no-build`; migrated to `0081`; ran the standing seed; recreated
  workers; prewarmed `/login`, `/student`, `/student/progress`, `/lecturer`, `/admin`; then ran:
  `set -a; source .env.e2e; set +a; E2E_RUN_ID=e2e-stage10-full-clean-20260620230826 PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1`
  → **`24 passed (6.3m)`**. Fault evidence in that same run: `4.5d invalid_output` passed after
  `ai_worker` recreations; `4.5d invalid_input` passed after `ai_worker` recreations; `4.6d retry`
  passed after `embedding_worker` recreations. **Stage 10 FULLY VERIFIED; not merged.**

## Knowledge updates
- Spec/plan/ADRs (this stage); architecture docs; roadmap Stage 10 line + table; STATUS.md; log.md; open-questions.md.

## Close-the-loop checklist
- [x] Spec exists and approved
- [x] Plan existed and approved before coding
- [x] Stayed in scope (deviations noted)
- [x] Verification commands run; real output recorded
- [x] Report written from git diff + output
- [x] spec ↔ plan ↔ report links resolve
- [x] STATUS.md overwritten; log.md appended
- [x] architecture/ updated (`db-spine`, `frontend`, `auth-current-user-context`)
- [x] ADRs added (056, 057)
- [x] open-questions.md updated (Stage 4.8 carry-forward)
- [x] **Live browser gate RAN: Stage 10 Scenarios A/B/C GREEN; rule-14 full active suite 24/24 GREEN** (clean standard stack; required fault gates green)

## Modified prior sessions
- Stage 8.5 — `backend/app/domains/admin/dev_reseed.py`: advanced `EXPECTED_ALEMBIC_VERSION` 0041→0081 (Stage 10 migrations moved the head). Re-pin at merge.
- Stage 9 — `frontend/src/features/progress/ProgressDashboard.tsx`: replaced the gamification placeholder `<section>` with `<GamificationPanel/>` (kept the `gamification-placeholder` testid so the Stage 9 E2E assertion still passes).
- Stage 5 — `backend/tests/conftest.py`: added `student_badges` + `student_streak_state` to the test truncation set.
- Stage 8.2 — `backend/app/domains/student_summaries/service.py`: `get_student_section_detail` now emits the `studied_section` engagement event (via `platform/events.record_studied_section`) — the real student section-read path (live-gate fix; the content-domain hook was tried first then reverted, so `content/service.py` + `content` router net-unchanged).
- Stage 2 — `knowledge/architecture/db-spine.md` and `knowledge/architecture/auth-current-user-context.md`: documented Stage 10's gamification tables, event CHECK widen, next-schedule read primitive, and student-only gamification route boundary.
- Stage 4 — `knowledge/architecture/frontend.md`: replaced the stale "non-functional gamification placeholder" note with the shipped `GamificationPanel` behavior.

## Change history
- 2026-06-20 — initial completion (BACKEND VERIFIED; live browser gate authored, pending Supabase E2E stack).
- 2026-06-20 — live browser gate RAN on the owner-provided Supabase stack: Stage 10 Scenarios A/B/C GREEN; rule-14 21/24. Gate caught + fixed the `studied_section` wrong-endpoint bug (moved emission to `student_summaries.get_student_section_detail` via `platform/events.record_studied_section`; content hook reverted; ADR-057 updated; 19 backend tests re-verified). 3 fault-injection gates (4.5d×2, 4.6d-retry) env-blocked by the shared `kyiv-backend` tag in that isolated stack; 7-glossary needed the `.env.e2e` export. Superseded by the final 24/24 clean standard-stack run below. Not merged.
- 2026-06-20 23:12 — final clean standard-stack rule-14 run passed **24/24** (`E2E_RUN_ID=e2e-stage10-full-clean-20260620230826`, `PLAYWRIGHT_BASE_URL=http://localhost:3001`, `.env.e2e` exported, `24 passed (6.3m)`). Required fault gates all green: `4.5d invalid_output`, `4.5d invalid_input`, and `4.6d retry`; worker recreations used freshly rebuilt `kyiv-backend:latest` (`sha256:5165e220…`). Stage 10 flipped to FULLY VERIFIED; not merged.
- 2026-06-20 23:54 — post-review hardening complete: `newBadgeIds` now comes from `INSERT ... ON CONFLICT DO NOTHING RETURNING`, with a concurrent first-read regression test; `nextScheduledDay` now comes from `platform/query.gamification_read.next_scheduled_class_day`, with service/API tests; unrelated Stage 6 screenshot churn restored out of the worktree; architecture docs updated. Reverified on rebuilt backend image + fresh DB: Alembic `0041 → 0080 → 0081`, single head `0081`, downgrade/upgrade round-trip passed, `test_shared_check_union` passed, full backend `660 passed`, frontend `tsc` clean + unit `12 passed`, rule-14 full Playwright `24 passed (6.4m)` (`E2E_RUN_ID=e2e-stage10-reviewfix-20260620234724`). Not merged.
