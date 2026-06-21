---
type: finding
stage: "cross-branch"
slug: topic-mastery-visibility
status: handoff
created: 2026-06-21
updated: 2026-06-21
owner: truearche
---

# Topic mastery visibility hand-off

## Linked documents
- Related spec: [[specs/stage-08/8.6d-topic-mastery-visibility]]
- Related plan: [[plans/stage-08/8.6d-topic-mastery-visibility]]
- Related report: [[steps/stage-08/8.6d-topic-mastery-visibility]]
- Stage 9 report: [[steps/stage-09/9-my-progress-dashboard]]

## Principle
Any read of topic mastery or section-derived topic rows that feeds student-visible output, LLM prompt
context, student-facing recommendation copy, workload-planner output, or student-facing audit snapshots must
filter to `ModuleSection.publish_status == "published"` in addition to active/member/module gates.

## Fixed in Dallas
The Stage 8.6 Dallas branch fixes the shared Stage 9 helper:

- `backend/app/platform/query/progress_read.py:160-176` — `list_topic_mastery()` now requires
  `ModuleSection.publish_status == "published"`.

This closes current-branch consumers:

- `backend/app/domains/progress/service.py:143` — Stage 9 My Progress topic rows.
- `backend/app/domains/assistant/generation_service.py:893` — Stage 8.6b exam-prep weak topics.
- `backend/app/platform/query/time_management_read.py:197` — Stage 8.6c time-management weak topics.

## Still needs fixing when branches rebase

### Stage 10 — `stage-10-gamification` / `da-nang`
Direct read outside `list_topic_mastery()`:

- `stage-10-gamification:backend/app/platform/query/gamification_read.py:276-284` reads
  `StudentTopicMasterySnapshot` directly for `topic_mastered` badge eligibility and filters only
  `student_id` + `status_label == "strong"`.

Risk: a hidden-section mastery row can still grant or preserve `topic_mastered` eligibility. This is not a
title leak, but it is still student-visible behavior derived from unpublished content.

Recommended fix: join `ModuleSection` and require `ModuleSection.publish_status == "published"` and
`ModuleSection.status == "active"`, or extract/use a shared visible-topic helper.

### Stage 11 — `stage-11-ai-analytics` / `baghdad`
Direct read outside `list_topic_mastery()`:

- `stage-11-ai-analytics:backend/app/platform/query/analytics_read.py:627-656`
  (`earliest_topic_deadline_gap`) joins `ModuleSection` but filters only active due-window rows, not
  published rows.
- `stage-11-ai-analytics:backend/app/domains/analytics/service.py:847-866` places the returned title into
  `RiskMetrics.topic_gap_title`.
- `stage-11-ai-analytics:backend/app/domains/analytics/risk.py:190-218` turns that title into
  `topic_deadline_gap` lecturer/student text.
- `stage-11-ai-analytics:backend/app/domains/analytics/workload.py:262-291` and
  `stage-11-ai-analytics:backend/app/domains/analytics/recommendations.py:399-536` can carry the same reason
  into workload-planner and recommendation surfaces.

Risk: a hidden section title can flow into risk reasons, recommendations, and workload planner output.

Recommended fix: add the published-section predicate to `earliest_topic_deadline_gap()` and any other direct
topic-mastery/section reads that feed student-visible analytics. If Stage 11 continues adding such reads,
prefer extracting a shared visible-topic helper instead of repeating predicates.

## Merge coordination note
The Dallas shared-helper fix does not automatically reach Stage 10/11 direct reads. Those branches should
apply the same predicate during their rebase or before landing.
