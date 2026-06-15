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

## Decisions / findings
- Decisions: What was decided and why. Link ADRs where durable decisions were made.
- Findings: Important facts learned during implementation or verification, including rejected alternatives.
- PR: Link the pull request if one exists.

## Risks introduced
None / list.

## Follow-ups
- Loose ends. Create numbered sessions for the real ones.

## Knowledge updates
- Updated knowledge/...

## Modified prior sessions
None / list earlier sessions whose files were changed, which files changed, and why.

## Close-the-loop checklist
- [ ] Spec exists and is `status: approved` (or `done`)
- [ ] Plan existed and was approved before any source edits
- [ ] Stayed in scope; deviations recorded in the report
- [ ] Verification commands run; real output recorded in the report
- [ ] Report written from `git diff` + command output, not memory
- [ ] Links resolve within your own stage-trio (spec ↔ plan ↔ report)
- [ ] Shared files (`STATUS.md`, `log.md`, `roadmap.md`) are updated on main during the merge train, not on a branch / in a worktree
- [ ] `architecture/` updated only if source paths changed
- [ ] ADR added to `decisions/` only if a durable decision was made
- [ ] `open-questions.md` updated if anything is unresolved

## Change history
_Append-only. One dated line per change made after initial completion._
- YYYY-MM-DD — initial completion (commit ...)
