---
type: adr
stage: "4.9"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.9b-component-library.md
---

# ADR-047 — Component-API contract stability (breaking changes frozen post-4.9; additive allowed)

> Stage 4.9 umbrella §4.2 ("contract stability"). Recorded with the 4.9b code.

## Linked documents
- Spec: [[specs/stage-04/4.9b-component-library]] · Umbrella: [[specs/stage-04/4.9-frontend-foundation-platform-hygiene]]
- Related: [[decisions/adr-046-component-primitive-strategy]] · Design system (records the contracts as-built at 4.9e): [[design-system]]

## Context
The §4.2 library is the highest-leverage deliverable in the stage: Stage 5 (quiz), 7 (glossary), 8
(assistant), 11 (risk rows) all build against these components. A wobbly Button/Card/Badge contract
becomes hundreds of call-site edits later. Stage 5 is the first real consumer; additive growth is
expected and healthy — what causes churn is renames/removals.

## Decision
- **Breaking changes are FROZEN after 4.9 and require an ADR:** prop rename, variant rename, prop/variant
  removal, or a change to an existing prop's type/meaning. Any of these must be justified in a new ADR
  before landing, because they break existing call sites.
- **Additive changes are ALLOWED via the design-system.md changelog (no ADR):** new optional props, new
  variants, new slots. These don't break existing usage.
- **State is carried by explicit props**, never inferred from child order/position (the quiz-option-identity
  principle) — locked uniformly so the habit holds.
- **`design-system.md` carries a version + changelog** (4.9e): a breaking change bumps the version + cites
  its ADR; an additive change appends to the changelog only.

## As-built contracts frozen by this ADR (recorded in design-system.md at 4.9e from shipped code)
Button(`variant`, `size`, `isLoading`, `leftIcon`, …button attrs) · Input(`id`, `label`, `as`, `error`,
`description`, …) · Card / InteractiveCard(`href`|`onClick`) · Badge(`tone`) · Modal(`isOpen`,
`onOpenChange`, `title`, `footer`, `variant`) · Table(`caption`) + SortableHeader(`label`, `direction`,
`onSort`) + `tableRowEmphasis` · ToastProvider + `useToast().show(tone, message)` · EmptyState(`title`,
`description`, `action`, `icon`, `headingLevel`) · LinearProgress(`value`, `label`) / StepProgress(`steps`,
`orientation`) with `PipelineStep = { label, state }`.

## Consequences
- Stage 5+ consumes these as fixed dependencies; it does not fork them. The Progress/Step `failed` state
  and the Badge status-by-text-label rule are the exact things Stage 5 quiz feedback + Stage 11 risk rows
  reuse — built once here.
- The `useToast().show(tone, message)` surface is intentionally minimal; richer options (actions, custom
  duration) are **additive** later (changelog), not a v1 breaking risk.
- Enforcement is social + reviewed (no compiler gate on prop contracts); the ADR requirement + the
  design-system.md changelog are the control.
