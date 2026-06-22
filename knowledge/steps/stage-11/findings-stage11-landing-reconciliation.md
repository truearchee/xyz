---
stage: 11
session: landing
slug: landing-reconciliation
status: flagged-for-owner
date: 2026-06-22
---

# Stage 11 landing — reconciliation findings (rule 10)

Recorded during the three-branch landing (Stage 11 rebased onto main after Stage 10 and Stage 8.6).
The combined backend suite (804 passed) and full active Playwright suite are green; these are non-blocking
findings surfaced for an owner decision, per "flag it, rule 10, don't silently diverge."

## F-LAND-1 (rule 10) — `topic_deadline_gap` student reason does not apply the published-section gate

> **RESOLVED 2026-06-22** (branch `fix/stage11-section-visibility-leak`). `earliest_topic_deadline_gap`
> now routes through `apply_visible_section_gate`. A read-audit found this was NOT the only Stage 11
> recurrence of the leak class — `get_workload_module_context`, `get_grade_forecast_inputs`,
> `count_missed_recent_quizzes`, `has_upcoming_work`, and `student_has_module` had the same omission and
> were all fixed. See [[steps/stage-11/findings-stage11-section-visibility-fix]] for the full fix +
> regression tests. (The "low practical risk" caveat below was the reason it shipped at landing; it is
> now closed regardless.)

**What.** `analytics_read.earliest_topic_deadline_gap()` selects `ModuleSection.title` + `due_at` joined to
`StudentTopicMasterySnapshot` filtered by `ModuleSection.status == "active"` + `due_at` window, but **not**
`ModuleSection.publish_status == "published"`. The returned `title` is surfaced to the **student** in the
`topic_deadline_gap` risk reason's `studentText` (`"<title> could use a little extra time before the
deadline."`).

**Why it matters.** After Stage 8.6 + PR #14, the canonical student section-visibility gate
(`section_visibility.apply_visible_section_gate`, mirrored by `student_summary_read` and
`time_management_read`) requires `publish_status == "published"` — i.e. an unpublished section's **title**
is hidden content for a student everywhere else. `earliest_topic_deadline_gap` diverges: if a
`needs_attention` topic-mastery snapshot existed for an *unpublished* section with a due date in the
window, the student would see that section's title. That is the same leak class PR #14 closed for
`list_topic_mastery`.

**Why the practical risk is low (not a confirmed live leak).**
- A `topic_deadline_gap` requires a `StudentTopicMasterySnapshot` with `status_label == "needs_attention"`
  for the section. A mastery snapshot implies the student was assessed on that section's material, which
  is normally only possible once the section/its quiz is available — an unpublished section with a
  `needs_attention` mastery row is an anomalous state.
- `StudentTopicMasterySnapshot` rows currently have no live production writer (only `progress/seed.py`
  seeds them), and the reference/E2E seed creates **published** sections, so the suite never exercises the
  leak path.

**Recommended fix (owner call).** Add `ModuleSection.publish_status == "published"` to the
`earliest_topic_deadline_gap` query so the student-facing reason respects the same gate as every other
student section read. Left unchanged here to avoid silently altering a student-facing risk surface at
landing time — flagged for an explicit owner decision.

## F-LAND-2 (informational) — `has_upcoming_work` intentionally not publish-gated (NOT a leak)

> **REVISED 2026-06-22.** On owner direction this read IS now publish-gated (see
> [[steps/stage-11/findings-stage11-section-visibility-fix]]). It surfaces no section *identity*, but a
> draft future-dated section silently changes a student's risk tier (it drives the `inactive_recently`
> reason) from content the student cannot see — so it is gated for consistency with the workload /
> calendar deadline reads. The `section_visibility.py` "scheduled-day reads" carve-out still applies to
> genuine schedule-date surfaces; `has_upcoming_work` gates a risk reason, not a schedule date.

`analytics_read.has_upcoming_work()` counts `ModuleSection.status == "active"` with a future `due_at`
regardless of `publish_status`, and gates the `inactive_recently` reason. It surfaces **no title** — only
whether *some* upcoming work exists. This matches `section_visibility.py`'s explicit design note that the
visibility gate "is deliberately NOT applied to the scheduled-day reads (a future class DATE may surface
before its section publishes — a schedule date, not hidden content; by design)."

## F-LAND-3 (informational) — ADR number collision across the three branches

`adr-056` and `adr-057` are each used by THREE different decisions now co-located in `knowledge/decisions/`:
Stage 8.6 (`adr-056-assistant-mode-coordinator`, `adr-057-assistant-mode-routing-budget`), Stage 10
(`adr-056-gamification-course-timezone`, `adr-057-gamification-on-read-evaluation`), and Stage 11
(`adr-056-stage-11-scheduler-risk-contract`, `adr-057-stage-11-recommendation-copy-route`). This is a
pre-existing parallel-development artifact (distinct filenames, so no git conflict, but duplicate ADR
*numbers*). Not renumbered here (the files are referenced across many docs); the new landing ADR uses the
first collision-free number, **adr-060**. Flagged for the owner to decide whether to renumber.

## Confirmed clean (no conflict / no leak)

- **My Progress coexistence:** `ProgressDashboard.tsx` renders Stage 11 `StudentRiskCard` /
  `StudentWorkloadPlanner` / `ForecastAdviceCard` AND Stage 10 `GamificationPanel` (the old
  `gamification-placeholder` is replaced by the real panel). Verified green by the `9-my-progress`,
  `10-gamification`, and `11.6-grade-forecast-advice` specs on the combined stack.
- **Stage 9 AI-free gate:** the merged `9-my-progress.spec.ts` composes PR #14's id-set-diff +
  `ingestion_job_id IS NULL` hardening with Stage 11.6's `feature <> 'grade_forecast_advice'` scoping —
  viewing My Progress triggers no summary/quiz/recommendation AI; forecast-advice AI is the only allowed AI.
- **8.6 shared resolvers** (`assessment_scope_read`, `assistant_retrieval_read`, `student_summary_read`,
  `time_management_read`): untouched by Stage 11 (additive `platform/query/analytics_read.py`); no rebase
  conflict and no overlap.
- **Isolation (rule 8):** the `studied_section` activity read uses the shared `StudentActivityEvent` spine
  by `event_type` only; no gamification import anywhere in `app/domains/analytics/**`, `analytics_read.py`,
  or `app/platform/scheduler/**`.
