---
type: session-spec
stage: NN
session: "N.N"
slug: short-kebab-name
status: draft        # draft → approved → in-progress → done → superseded
created: YYYY-MM-DD
updated: YYYY-MM-DD
owner: developer
plan: ""             # knowledge/plans/stage-NN/<session>-<slug>.md  (fill when plan exists)
report: ""           # knowledge/steps/stage-NN/<session>-<slug>.md  (fill when report exists)
---

# Session N.N — <Title>

## Linked documents
- Spec: [[specs/stage-NN/N.N-slug]]
- Plan: [[plans/stage-NN/N.N-slug]]
- Report: [[steps/stage-NN/N.N-slug]]

## Goal
One sentence: what must be true when this is done.

## Why now
Context / motivation. How it serves the roadmap stage.

## Read first
- knowledge/...
- (the 3–5 files an agent must read before touching this; keep it minimal)

## Source paths likely touched
- backend/...
- frontend/...

## Build
- Task 1 (intent level — the HOW belongs in the plan)
- Task 2

## Do not build
- Explicit out-of-scope items (this is the scope guard — agents love side quests)

## Data model changes
None / list.

## API changes
None / list.

## Worker / job changes
None / list.

## Authz rules
None / list.

## Verification
Commands that prove it works, with expected results.
- `command` → expected

## Knowledge updates required
- knowledge/steps/... (report — always)
- knowledge/architecture/... (only if source paths change)

## Done means
Concrete, verifiable outcome.

## Amendments
_Add dated entries here if scope changes mid-flight. Do not silently edit the sections above._
