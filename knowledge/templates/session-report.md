---
type: session-report
stage: NN
session: "N.N"
slug: short-kebab-name
status: complete
created: YYYY-MM-DD
updated: YYYY-MM-DD   # bump on every later change
spec: knowledge/specs/stage-NN/<session>-<slug>.md
plan: knowledge/plans/stage-NN/<session>-<slug>.md
commit: ""           # SHA / PR reference
---

# Session N.N — Report — <Title>

## Linked documents
- Spec: [[specs/stage-NN/N.N-slug]]
- Plan: [[plans/stage-NN/N.N-slug]]
- Report: [[steps/stage-NN/N.N-slug]]

## Summary
What was actually completed.

## Files changed
Grouped: backend / frontend / infra / knowledge. (Source from `git diff --stat`.)

## Verification
| Command | Result | Notes |
|---|---|---|
| `command` | passed/failed | output detail |

## Deviations from spec
None / list (what differed from spec or plan, and why).

## Decisions made
None / "ADR added: decisions/NNNN-...".

## Risks introduced
None / list.

## Follow-ups
- Loose ends. Create numbered sessions for the real ones.

## Knowledge updates
- Updated knowledge/...

## Close-the-loop checklist
- [ ] Spec exists and approved
- [ ] Plan existed and was approved before coding
- [ ] Stayed in scope (deviations noted above)
- [ ] Verification commands run; real output recorded
- [ ] Report written from git diff + output, not memory
- [ ] spec ↔ plan ↔ report links all resolve
- [ ] STATUS.md overwritten; log.md appended
- [ ] architecture/ updated IF source paths changed
- [ ] ADR added IF a durable decision was made
- [ ] open-questions.md updated IF anything unresolved

## Change history
_Append-only. One dated line per change made after initial completion._
- YYYY-MM-DD — initial completion (commit ...)
