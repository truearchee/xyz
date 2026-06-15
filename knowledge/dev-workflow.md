# Development Workflow

This file is the authoritative reference for the development-memory loop. Read it at the
start of every session. It governs how all work is planned, executed, and recorded.

---

## The core loop (one session = one unit of work)

Every session produces exactly **three linked artifacts**, all sharing the same path tail
`stage-NN/<session>-<slug>.md`:

```
knowledge/specs/stage-NN/<session>-<slug>.md   ← WHAT + WHY + done-criteria
knowledge/plans/stage-NN/<session>-<slug>.md   ← HOW (produced in planning mode)
knowledge/steps/stage-NN/<session>-<slug>.md   ← what actually happened (the report)
```

These three form a cluster. By the end of a session every file cross-links the other two
by both YAML frontmatter field and Obsidian wikilink.

---

## Step-by-step session protocol

### 1. Orient
Read `knowledge/STATUS.md` and the relevant spec before touching anything.
If `STATUS.md` is stale, ask the developer to clarify before proceeding.
Read narrowly: only your spec and the files it explicitly links. Do not scan the
knowledge tree. `knowledge/archive/` is history — never treat it as current state.

### 2. File the spec
If the developer hands you a document:
- Copy/reformat it into `knowledge/specs/stage-NN/<session>-<slug>.md` using the
  `templates/session-spec.md` template.
- Preserve all developer content — do not paraphrase or omit.
- Set `status: approved` only after the developer confirms scope.
- Do not start planning until the spec is approved.

### 3. Plan (no code without an approved plan)
- Produce `knowledge/plans/stage-NN/<session>-<slug>.md` from `templates/session-plan.md`.
- Set `status: proposed`.
- Present the plan. Wait for explicit developer approval before writing any source code.
- On approval, set `status: approved` and update the spec's `plan:` frontmatter field.

### 4. Build (inside scope only)
- Work only within what the spec lists under **Build** and **Source paths likely touched**.
- Honour the **Do not build** list — it is the scope guard.
- If scope must change, add a dated entry to the spec's `## Amendments` section.
  Never silently drift.

### 5. Verify
- Run every command listed in the spec's **Verification** section.
- Capture the real output. Do not paraphrase or fabricate.

### 6. Report from evidence
Write `knowledge/steps/stage-NN/<session>-<slug>.md` from:
- `git diff --stat` (files changed)
- `git diff` or commit SHAs (what changed)
- Actual command output from step 5

**Never write a report from memory.** If you did not run the command, say so.

### 7. Close the loop
Complete all items in the report's **Close-the-loop checklist**:

- [ ] Spec exists and is `status: approved` (or `done`)
- [ ] Plan existed and was approved before any source edits
- [ ] Stayed in scope; deviations recorded in the report
- [ ] Verification commands run; real output recorded in the report
- [ ] Report written from `git diff` + command output, not memory
- [ ] Links resolve within your own stage-trio (spec ↔ plan ↔ report)
- [ ] Shared files (`STATUS.md`, `log.md`, `roadmap.md`) are updated on **main
      during the merge train** — NOT on a branch / in a worktree (parallel rule)
- [ ] `architecture/` updated **only if** source paths changed
- [ ] ADR added to `decisions/` **only if** a durable decision was made
- [ ] `open-questions.md` updated if anything is unresolved

---

## Naming convention

| Part | Rule |
|---|---|
| `stage` | Roadmap stage number (01–12). Zero-padded. |
| `session` | `<stage>.<n>` — e.g. `1.1`, `1.2`, `2.1`. Monotonically increasing within a stage. |
| `slug` | Short kebab-case description — e.g. `repo-skeleton`, `auth-jwt`, `db-migrations`. |
| Full filename | `<session>-<slug>.md` — e.g. `1.1-repo-skeleton.md` |
| Decomposed stage | Sub-sessions nest under a parent folder: `stage-NN/<parent>/<parent><letter>-<slug>.md` — e.g. `stage-04/4.5/4.5a-llm-foundation.md`. Forward convention (Stage 5+); don't move historical files. |

---

## Status lifecycles

### Spec
`draft` → `approved` → `in-progress` → `done` → `superseded`

### Plan
`proposed` → `approved` → `executed`

### Report
`complete` (only one valid status; write it once, amend via change history)

### Superseding
When work is replaced rather than finished:
1. Set `status: superseded` on the old file.
2. Add `superseded-by: knowledge/specs/stage-NN/<new-session>-<slug>.md`.
3. Never delete history.

---

## Vocabulary & conventions

> Canonicalized 2026-06-13 (knowledge-audit close-out). The three-artifact templates cover linear sessions;
> the 4.3.5 recovery block + supplemental gates needed documented extensions. Per the sacred rule
> (code/reality wins), these record the **established** vocabulary rather than churn 80+ historical files to a
> narrower literal.

### Log entry types (`log.md`)
`spec | plan | report | decision | fix | note | blocker | docs` — matches the `log.md` Format header.
`blocker` = a session halted on an unresolved finding; `docs` = a knowledge-only consolidation/maintenance entry.

### Document `type:` values
- **Canonical (linear sessions):** `session-spec`, `session-plan`, `session-report`.
- **Accepted extensions** (recovery / supplemental / consolidation — intentional structure the linear template
  can't express): `checkpoint-spec`/`-plan`/`-report`, `repair-session-spec`/`-plan`/`-report`,
  `supplemental-gate-spec`/`-plan`/`-report`, `final-report` (a consolidated canonical report; carries
  `canonical: true`), `regression-report`, `fixture-report`, `findings`, `architecture`, `adr`, `scope-spec`,
  `stage-spec`. New work uses the canonical three unless it is genuinely one of these.

### Accepted extra frontmatter fields
Beyond the template set, accepted where meaningful: `checkpoint`, `parent_session`, `depends_on`, `blocks`,
`unblocks`, `closes`, `satisfies_stage_gate`, `predecessor`, `recovery_plan`, `baseline_commit`, `roadmap`,
`canonical`, `findings`, `superseded-by`, `inputs`, `umbrella`, `scope-spec`, `note`, `related-session`, and
`historical_*_report:` pointers. Reuse these; do not invent new fields casually.

### `stage:` field
A bare number for a whole stage (`stage: 4`) — the dominant form across 80+ files — or a **quoted string** for
a sub-stage / recovery identifier that is not a plain number (`stage: "4.3.5"`). Both bare and quoted
whole-stage forms appear historically and are accepted; do not mass-rewrite them.

### Review / audit + roadmap docs
Project-level review/audit docs (`CODEBASE_REVIEW.md`, `KNOWLEDGE_REVIEW.md`) and `roadmap.md` are
**cross-cutting knowledge docs that live in `knowledge/`**, alongside `STATUS.md` / `log.md` / `open-questions.md`.

### `specs/recovery/`
`knowledge/specs/recovery/client-edge-recovery-plan.md` is a deliberate exception: the cross-block 4.3.5
recovery STRATEGY doc (predates the sub-sessions; no single plan/report sibling). Not a session spec → lives
outside the `stage-NN/` session tree. Documented exception, not drift.

---

## Cross-cutting files

| File | Rule |
|---|---|
| `STATUS.md` | Current-state only. Updated on **main during the merge train**, not on a branch. |
| `log.md` | One line per session, appended on **main during the merge train**. Never edit old lines. |
| `open-questions.md` | Add questions cheaply. Promote to ADR when durable; mark resolved with link. |
| `architecture/` | Update only when source paths actually change. Do not speculatively edit. |
| `decisions/` | One ADR per durable, cross-cutting decision. Do not add ADRs for local implementation choices. |

---

## Parallel work & merge train

From Stage 5 onward, work runs in parallel Conductor worktrees — one agent per
workspace, each on its own branch. Git isolates files; it does not isolate shared
knowledge files or the database. Therefore:

- **Branch-local:** your own stage-trio (spec/plan/report), your source code,
  your migrations (using your stage's assigned number block).
- **Main-only (developer, during the merge train):** `STATUS.md`, `log.md`,
  `roadmap.md` status table, and OpenAPI client regeneration.
- **Merge train per stage close:** merge → migrate → regenerate OpenAPI client →
  full active E2E suite → update STATUS/roadmap/log on main → next merge.

These rules are injected into every Conductor agent via `.conductor/settings.toml`.
This section is their constitutional record; the settings file is their enforcement.

---

## Sacred rule

Documentation is a **cache of engineering intent, not a source of truth.**

When docs disagree with code, migrations, schemas, tests, or runtime behaviour, **code wins.**
If you find a contradiction: flag it, fix the *doc*, and record the fix in `log.md`.
Never bend code to match a stale doc. Never write a report from memory.
