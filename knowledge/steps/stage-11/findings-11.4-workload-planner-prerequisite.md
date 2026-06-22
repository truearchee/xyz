---
type: findings
stage: 11
session: "11.4"
slug: workload-planner-prerequisite
status: resolved
created: 2026-06-20
updated: 2026-06-20
owner: developer
---

# Findings — 11.4 Workload Planner Prerequisite

## Summary
Resolved by owner decision on 2026-06-20. Stage 11.4 had been blocked before implementation planning because the
required Slice 5 "6-phase planning algorithm" was referenced but not pinned in the available workspace documents
or attachment.

The Stage 11 master spec explicitly says to confirm the exact six phases against Slice 5 before coding, and to
stop and escalate if Slice 5 does not pin them. I did not find the phase list, so I am stopping rather than
inventing planning order.

## Evidence
- `knowledge/specs/stage-11/11-proactive-ai-agent-analytics.md:233-237` defines 11.4 as a deterministic
  six-phase workload planner and says to stop if Slice 5 does not pin the phases.
- `.context/attachments/BxO09z/pasted_text_2026-06-20_11-06-13.txt:211-215` contains the same Stage 11.4
  prerequisite text from the original attachment.
- `knowledge/roadmap.md:662-664` says Stage 11 scope includes a "6-phase planning algorithm" and places 11.4
  after assessment analysis, but does not name or order the six phases.
- `knowledge/design-plan.md:161-163` only names a workload planner calendar seed surface; it does not define
  algorithm phases.

Searches run:

```bash
rg -n "11\\.4|Workload|workload|planner|Slice 5|six-phase|6-phase|phase" \
  knowledge/specs knowledge/plans knowledge/steps knowledge/roadmap.md knowledge/design-plan.md

rg -n "6-phase|six-phase|six phase|planning algorithm|WorkloadPlan|Workload Plan|workload plan|Slice 5|Phase 1|Phase one|phase one|availabilityVersion|availability version|study days|max study minutes" \
  -S . --glob '!frontend/node_modules/**' --glob '!backend/.venv/**' --glob '!backend/openapi.json' --glob '!.git/**'

rg -n "6-phase|six-phase|six phase|planning algorithm|WorkloadPlan|workload plan|availability|Phase 1|Phase 2|Phase 3|Phase 4|Phase 5|Phase 6|Slice 5" \
  .context/attachments/BxO09z/pasted_text_2026-06-20_11-06-13.txt
```

Result: references to the existence of a six-phase algorithm were found; the six phase names/order were not.

## Resolution
The owner provided and confirmed the exact six phases, in order:

1. GATHER
2. BUILD TASKS
3. PRIORITIZE
4. LAY OUT
5. RESOLVE OVERFLOW
6. EMIT

The owner also locked three algorithm choices:
- nearest-deadline-first priority;
- bounded soft-cap overflow;
- whole-remaining-course horizon.

The full algorithm is now recorded in [[specs/stage-11/11.4-workload-planner]] and
[[decisions/adr-058-stage-11-workload-planner-algorithm]].

## Original Decision Needed
Owner had to provide the exact six phases, in order, before the 11.4 plan could be completed.

The rest of the 11.4 contract remains locked:
- deterministic and reproducible;
- read-only student plan;
- availability is the only student input;
- every item traces to a real deadline or detected gap;
- stored effort estimate on each item;
- inputs are Stage 5.5 deadlines, 11.1 risk snapshot/reasons, Stage 9 forecast, and availability;
- no AI;
- no Stage 10 reads;
- no draggable/edit/mark-done/accept-reject interactions.

## Blocked Work
This blocker is resolved. Implementation remains gated by owner approval of
[[plans/stage-11/11.4-workload-planner]].
