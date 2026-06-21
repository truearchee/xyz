# Status

_Last updated: 2026-06-20 — **Stage 10 (Gamification): FULLY VERIFIED on branch `stage-10-gamification` (not merged).** Post-review hardening is complete: `newBadgeIds` is now based on rows actually inserted by `INSERT ... ON CONFLICT DO NOTHING RETURNING`, `nextScheduledDay` is populated from the next scheduled lecture/lab date, unrelated Stage 6 screenshot churn is restored out of the merge surface, and architecture docs are updated. Reverified on the rebuilt backend image and a fresh DB: Alembic `0041 → 0080 → 0081`, single head `0081`, downgrade/upgrade round-trip clean, `test_shared_check_union` green, full backend `660 passed`, frontend `tsc` clean + unit `12 passed`, and rule-14 full active Playwright **`24 passed (6.4m)`** with `PLAYWRIGHT_BASE_URL=http://localhost:3001`, `E2E_RUN_ID=e2e-stage10-reviewfix-20260620234724`, `.env.e2e` exported. `origin/main` was fetched and is still the branch base (`4756f722...`), so there was no rebase delta before this report. Stage 10 is still not merged._

## Current branch
- Branch: `stage-10-gamification`
- Target branch: `origin/main`
- Migration block: **0080–0081** (reassigned 0048→0060→**0080** per the Stage 10/11 coordination note — Stage 11 climbs from 0056 and owns 0057–0079; Stage 8.6 took 0042). Chain `… → 0041 → 0080 → 0081`; single head `0081`. Develop chained off `0041`; the SECOND branch to merge rebases onto the new head, re-runs the Alembic round-trip, and confirms one head.

## Stage 10 delivered (one Learning streak + badges, on-read, event-derived)
- **Decisions A/A/A (owner-confirmed):** flashcard volume = **distinct local days with a completed flashcard session** (no per-card event exists; farm-proof; honest label) — [[decisions/adr-057-gamification-on-read-evaluation]]; **`COURSE_TIMEZONE` platform setting** (single IANA, DST-aware, default UTC; required hosted config at 4.8) — [[decisions/adr-056-gamification-course-timezone]]; **Tailwind panel** (no new inline-style debt).
- **Streak (derived on read, pure fn):** consecutive scheduled class days with any qualifying activity; today-not-yet-broken, neutral no-class days, `nextScheduledDay` from the nearest future scheduled lecture/lab, `occurred_at`-as-activity-day; monotonic `longest_streak` persisted in `student_streak_state`. Statuses active / needs_activity_today / broken / no_scheduled_day.
- **Badges (on read, persisted, sticky, idempotent):** code catalog (14 badges, 4 families), pure `evaluate_badges`, `INSERT … ON CONFLICT DO NOTHING RETURNING`; `newBadgeIds` is derived from rows actually inserted by the current read. `scope_id` non-null sentinel for global. `topic_mastered` reuses Stage 9 `status_label='strong'` (no invented threshold); volume badges count DISTINCT source items.
- **`studied_section` (content-domain-owned, rule 7):** emitted on the student section-summary GET, deduped per student+section+configured-tz local day via a deterministic `uuid5` source_id reusing `UNIQUE(event_type, source_id)`; savepoint-wrapped so the read never breaks but failures are logged + retryable; CHECK widened additively (`0080`) + union CI guard extended.
- **platform/query primitives** (`gamification_read.py`, read-only, additive — reusable by Stage 11): `scheduled_class_days`, `next_scheduled_class_day`, and `engagement_days` (the single "showing up" source of truth) + badge-metric loaders.
- **API:** `GET /student/gamification` (student-only 403-gated, no `student_id` param, `Cache-Control: private, no-store`). Client regenerated (`GamificationService` + 4 models). `GamificationPanel` fills the Stage 9 placeholder (kept `data-testid="gamification-placeholder"` so the Stage 9 spec still passes).
- **Reconcile tool** `scripts/reconcile_gamification.py` (dev/verification CLI, not HTTP) — rebuilds expected badges from events via the SAME `evaluate_badges` and asserts stored ⊇ qualified.

## Verification
- Alembic: fresh DB `upgrade head` ran `… 0041 → 0080 → 0081`; `alembic heads` → `0081 (head)`; `downgrade 0041 → upgrade head` round-trip clean.
- Backend `pytest`: full suite green (the 1 dev_reseed head-pin advanced 0041→0081 → fixed); **new gamification suites:** `test_gamification_streak` 13, `test_gamification_service` 14, `test_gamification_studied_section` 3, `test_gamification_api` 5 = **35** + `test_shared_check_union` (studied_section assertion). Includes the milestone-keys-off-`longest_streak`-held-after-a-later-break trap, studied_section recording-failure-is-logged (visible, not swallowed), concurrent first-read `newBadgeIds`, and `nextScheduledDay` assertions. Full backend rerun after review fixes: **660 passed**. `reconcile_gamification.py` → "reconcile OK" from the original Stage 10 gate.
- Client regenerated from the live OpenAPI (only `index.ts` + 5 new gamification files); frontend `tsc` exit 0; `test:unit` **12 passed** (incl. 3 new `GamificationPanel` tests); zero NEW `check:inline-styles`/`check:design-tokens` violations (the gate stays repo-red from the 396 Stage-12 backlog; Stage 10 added none and removed the placeholder's inline section).
- E2E gate `tests/e2e/10-gamification.spec.ts` authored and green; full active suite lists **24 tests / 19 files** and the post-review clean-stack rule-14 rerun passed **24/24** (`24 passed (6.4m)`, run id `e2e-stage10-reviewfix-20260620234724`).

## Remaining before merge
- Stage 10's FULLY VERIFIED product gate is closed by the clean full-suite `24 passed (6.4m)` rerun above. The branch has not been merged; this status is the requested pre-merge report point.

## Known-state notes
- Shared `kyiv-backend` image tag picked up a sibling's migration `0042` and stamped the dev DB; isolated via `.context/stage10.override.yml` (unique `da-nang-stage10-backend` image + source bind-mount) + a dev-DB reset (Stage 8.2 pattern).
- `dev_reseed.EXPECTED_ALEMBIC_VERSION` advanced `0041 → 0081`; **re-pin at merge** if the rebased head changes.

## Stage 10 documents
- Spec: [[specs/stage-10/10-gamification]]
- Plan: [[plans/stage-10/10a-foundation]]
- Report: [[steps/stage-10/10a-foundation]]
- ADRs: [[decisions/adr-056-gamification-course-timezone]] · [[decisions/adr-057-gamification-on-read-evaluation]]

## Prior
- 2026-06-20 — Stage 8.5 Save-to-Glossary from the assistant FULLY VERIFIED (migration 0041); 625 backend pytest; full Playwright 21/21.
- 2026-06-19 — Stage 8.4 Assistant Workspace + floating widget FULLY VERIFIED (0040); PR #10. Stage 4.9g monochrome redesign merged.
- 2026-06-18 — Stage 9 My Progress FULLY VERIFIED (0038-0039); Stage 8.2 + 8.1; Stage 7 core; Stage 6 + 5.5 + 5.
