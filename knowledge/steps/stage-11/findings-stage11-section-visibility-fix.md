---
stage: 11
session: section-visibility-fix
slug: section-visibility-fix
status: resolved
date: 2026-06-22
---

# Stage 11 — student section-visibility leak fix (resolves landing F-LAND-1)

Closes the recurrence of the Stage 10.x section-visibility leak class in Stage 11's analytics reads.
The Stage 10 fix (PR #14, commit `46d48bc`) landed on `main` AFTER Stage 11 branched, so Stage 11's
student-facing analytics reads re-introduced the same omission (`publish_status == "published"` /
active-module / active-membership missing). A read-audit surfaced five student-reachable reads; this
fix routes them through the canonical gate (`section_visibility.py`). **Branch:**
`fix/stage11-section-visibility-leak`.

> **Landing update (2026-06-22):** Stage 11 was merged to `main` (PRs #15 `2955721`, #16 `ea4d570`)
> WITHOUT this fix, so the leak is currently **live on `main`**. This fix therefore lands as a **direct
> follow-up PR to `main`** (which already contains Stage 11), not as a fold-in to a pending Stage 11 PR.
> The fix adds no migration; `main` is single-head `0059` and stays so.

## Audience scope (the fix is deliberately narrow)
Lecturers may legitimately see unpublished sections; the gate is applied ONLY to reads that feed a
STUDENT-reachable surface. Lecturer-only reads (`get_assessment_insights`, `_section_labels`,
`list_risk_subjects`) were audited and left unchanged — not over-gated.

## What changed — `backend/app/platform/query/analytics_read.py`
1. **`earliest_topic_deadline_gap`** (was the F-LAND-1 leak) — now routes the
   `StudentTopicMasterySnapshot → ModuleSection` join through `apply_visible_section_gate`. An
   unpublished section's **title** can no longer reach the student `topic_deadline_gap` risk reason /
   recommendation copy, and can no longer be frozen into `StudentRiskSnapshot.risk_reasons` by the
   scheduler. Mirrors `progress_read.list_topic_mastery` (the PR #14 fix).
2. **`get_workload_module_context`** — added `ModuleSection.publish_status == "published"` so a draft
   section's title/type/week/due-date no longer flows into the student workload plan items or the
   `.ics` export. Now matches the already-gated deadline query in `export_student_workload_calendar`
   (generation and export agree).
3. **`get_grade_forecast_inputs`** — grade components on a non-visible section are excluded from the
   student's forecast, **with the carve-out** that a scheme-level component (`module_section_id IS
   NULL`) MUST still count: `or_(module_section_id IS NULL, visible_section_exists(...))`.
4. **`count_missed_recent_quizzes`** — a quiz on a non-visible section no longer counts as "missed"
   (same NULL-section carve-out for module-level recap/exam_prep/mistakes_bank quizzes).
5. **`has_upcoming_work`** — added `publish_status == "published"` so a draft future-dated section no
   longer flips the `inactive_recently` reason / risk tier (revises landing F-LAND-2, see below).
6. **`student_has_module`** — added `CourseModule.is_active` so a deactivated module no longer serves
   student-facing analytics (risk / workload / forecast) to a still-enrolled student.

### `backend/app/platform/query/section_visibility.py`
Factored the canonical predicate into one private `_visible_section_predicates(student_id)` consumed by
both the existing `apply_visible_section_gate` (inner-join shape) and a new `visible_section_exists`
(EXISTS shape) — the latter for the NULL-section carve-out reads (#3, #4) so the gate definition can
never drift between the two shapes.

## F-LAND-2 revised (was "informational — not a leak")
The landing flagged `has_upcoming_work` as intentionally un-gated (it surfaces no title). On owner
direction it is now publish-gated for consistency: although it leaks no section *identity*, a draft
future section silently changes a student's risk tier (drives the `inactive_recently` reason) from
content the student cannot see. The `section_visibility.py` "scheduled-day reads" carve-out still
applies to genuine schedule-date reads; `has_upcoming_work` gates a risk reason, so it is gated.

## Tests — `backend/tests/test_analytics_section_visibility.py` (NEW, 12 tests)
Read-model regression tests against Postgres (mirror PR #14's
`test_progress_topic_mastery_visibility.py`): for each student-reachable read, an unpublished /
inactive-module / lost-membership section's title/metadata/due-date/grade-weight is excluded, while a
NULL-section component/quiz still counts and a visible section still surfaces (positive guards). Plus a
**scheduler recompute** test: a `StudentRiskSnapshot` recomputed (via `run_agent_run`) after the
section is unpublished no longer re-serves the stale leaked title.
**Proven meaningful:** with the fix reverted, 9 of 12 fail (the 3 positive guards still pass) — the
scheduler test shows the leaked title verbatim in the persisted snapshot reason.

## Verification
- **Backend:** `pytest -q` → **809 passed**, 4 skipped, **3 pre-existing host-only env failures**
  unrelated to this change (`test_embedding_platform` sentence-transformers default; two AI-provider
  `*_ai` tests that need a real provider — all three fail identically on unmodified branch code).
  New visibility suite **12 passed**; proven red (9 failed) with the fix reverted.
- **E2E (rule 14, `--workers=1`, deterministic provider, clean DB, local Supabase):** full active
  Playwright **34 passed / 1**, the one failure being `7-glossary` due to `SUPABASE_SERVICE_ROLE_KEY`
  absent from the Playwright process env in this harness invocation (the only spec creating runtime
  users via the GoTrue admin API) — **re-verified GREEN (1 passed)** with the key supplied → effective
  **35/35**. The 11.1 browser gate passed standalone. Every analytics spec the fix touches passed:
  11.1–11.6, 9-my-progress, 10-gamification (incl. Scenario D section-visibility).
  - Env note (rule 10): two recurring local-gate hazards re-confirmed — (a) `docker compose`
    substitutes `${LLM_PROVIDER}` from `.env` (`k2think`), overriding the e2e default `deterministic`;
    re-up with `LLM_PROVIDER=deterministic` exported. (b) A clean single-run reseed was blocked because
    the shared local Supabase has 1008 accumulated auth users (prior gate sessions) exceeding
    `seed.mjs`'s page-1/1000 `listAuthUsers` lookup — a pre-existing test-infra robustness gap, not a
    product issue (flagged, not fixed here).

## Landing
Stage 11 is already on `main` (#15/#16) without this fix — the leak is live on `main`. This ships as a
direct follow-up fix PR onto `main`. Pushed; the owner merges after seeing green.

## Stage 12 backlog (recorded, NOT fixed here)
- **`${LLM_PROVIDER}` `.env`→compose leak** (test-infra): `docker compose` substitutes `${LLM_PROVIDER}`
  from `.env` (`k2think`), silently overriding the e2e default `deterministic`. Workaround: export
  `LLM_PROVIDER=deterministic` before `up`. Needs a durable fix (drop the var from `.env`, or pin it in
  the e2e overlay without substitution).
- **`seed.mjs` `listAuthUsers` page-1/1000 cap**: a fresh reseed fails once the shared local Supabase
  exceeds ~1000 auth users (currently ~1008 from accumulated gate sessions) — the fixture users fall off
  page 1 and `ensureAuthUser` tries to recreate them ("already registered"). Needs a paginated lookup
  (or `?email=` filter) or a clean per-run test-auth strategy. Cleaning the accumulated users requires
  deleting shared `auth.users`, which the safety guard blocks (owner action).
