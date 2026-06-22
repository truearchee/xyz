# ADR-058 - Stage 11 Workload Planner Algorithm

Date: 2026-06-20

## Status
Accepted

## Context
Stage 11.4 builds a deterministic, student-facing workload planner. The Stage 11 master spec required the exact
Slice 5 six-phase planning algorithm before implementation and explicitly blocked agents from inventing an
algorithm.

The prerequisite was resolved by owner decision on 2026-06-20. The owner locked the planner around three choices:
- Priority: nearest deadline first.
- Overflow: `max_study_minutes_per_day` is a soft cap, exceeded only by a bounded config-backed allowance when
  needed to meet a deadline.
- Horizon: plan the entire remaining course, meaning all remaining deadlines plus current gaps through course end.
- Legacy fallback: only when course end is genuinely unknown; use the later of the latest known remaining deadline
  and the config-backed fallback horizon, record provenance, and never override or truncate a resolvable course
  end.

## Decision
Stage 11.4 uses this deterministic six-phase algorithm:

1. **GATHER.** Pin `sourceCutoffAt`, then collect from now through course end: all remaining assessed sections
   with `due_at`, current weak-topic gaps from the latest 11.1 risk snapshot/reasons, student availability with
   `availabilityVersion`, and the Stage 9 forecast. The task set is finite and bounded by deadlines plus gaps.
2. **BUILD TASKS.** Create one task per upcoming deadline and one task per weak topic. Each task carries a stored
   config-backed effort estimate and a reason of `deadline` or `gap`. If a weak topic also has an upcoming
   assessment, merge it into one deadline-linked task. MVP scope creates exactly one reinforcement task per
   current gap and does not invent spaced-repetition expansion.
3. **PRIORITIZE.** Sort deadline-bound tasks by effective deadline ascending. Gap-only tasks come last, ordered by
   gap severity descending, then by a stable id. No ordering tie may depend on database or runtime iteration order.
4. **LAY OUT.** Walk the priority order and place estimated minutes only on the student's selected study days, in
   the preferred window, up to `max_study_minutes_per_day` before applying overflow. Deadline-bound work must be
   scheduled before its deadline using configured window start/end times; same-day slots after `due_at` are not
   eligible. Large tasks may split across multiple available days.
5. **RESOLVE OVERFLOW.** Deadline-bound tasks that cannot fit under the daily cap may exceed relevant days up to a
   config-backed allowance such as `PLAN_DAILY_OVERFLOW_PERCENT`. If even that capacity cannot fit the task before
   the deadline, schedule as much as physically fits before the deadline and mark affected items/tasks `tight=true`
   with an honest message. Gap-only tasks never trigger overflow; they fill spare capacity and spill to later free
   days. The planner never fabricates capacity, drops a task silently, or schedules beyond the configured overflow
   bound. If zero minutes fit before a deadline, the planner still emits a tight unscheduled residual item so the
   task remains visible rather than disappearing.
6. **EMIT.** Persist a new `WorkloadPlan` and `WorkloadPlanItem[]`. Each item stores date/window, topic or
   section, estimate, reason, and `tight` when applicable. Timed items store start/end timestamps; a tight
   unscheduled residual item may have null start/end and an explicit message. The plan carries `algorithmVersion`,
   `inputHash`, `availabilityVersion`, and `sourceCutoffAt`; regenerating supersedes the prior active plan and
   marks the new plan `isActive`.

All thresholds, estimate defaults, and overflow allowances are config-backed. Changing them requires an
`algorithmVersion` bump. The UI is read-only and list-first; no drag, edit, accept/reject, or mark-done controls
exist in 11.4.

`sourceCutoffAt` is persisted as reproducibility metadata but is not itself a hash ingredient. The `inputHash`
hashes the gathered source data, availability values/version, risk snapshot identity/reasons, forecast context,
and planner config so repeated regenerations with identical inputs can produce the same hash.

## Consequences
- The planner is reproducible from persisted plan metadata, availability version, input hash, and source cutoff.
- Physically impossible deadlines remain visible and honest through `tight=true` instead of being dropped or
  overpromised.
- The data model must persist estimates and reasons on plan items; the frontend must not hardcode display
  estimates.
- Stage 11.4 needs persisted student availability and workload-plan tables. Under the current migration cap, the
  planned migration is `0058` with `down_revision="0057"`.
- Stage 11.5 can export from the persisted plan items without recalculating the planner.
- Legacy modules with unknown `ends_on` use the later of the latest known remaining deadline and a config-backed
  finite fallback horizon, recorded in provenance, so the task set remains finite without hiding known future
  deadlines.

## Linked documents
- Spec: [[specs/stage-11/11.4-workload-planner]]
- Plan: [[plans/stage-11/11.4-workload-planner]]
- Report: [[steps/stage-11/11.4-workload-planner]]
- Master spec: [[specs/stage-11/11-proactive-ai-agent-analytics]]
- Finding: [[steps/stage-11/findings-11.4-workload-planner-prerequisite]]
