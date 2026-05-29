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
- [ ] `spec ↔ plan ↔ report` links all resolve (YAML frontmatter + wikilinks)
- [ ] `STATUS.md` overwritten with current state
- [ ] `log.md` appended with a single summary line
- [ ] `architecture/` updated **only if** source paths changed
- [ ] ADR added to `decisions/` **only if** a durable decision was made
- [ ] `open-questions.md` updated if anything is unresolved

---

## Naming convention

| Part | Rule |
|---|---|
| `stage` | Roadmap stage number (01–05). Zero-padded. |
| `session` | `<stage>.<n>` — e.g. `1.1`, `1.2`, `2.1`. Monotonically increasing within a stage. |
| `slug` | Short kebab-case description — e.g. `repo-skeleton`, `auth-jwt`, `db-migrations`. |
| Full filename | `<session>-<slug>.md` — e.g. `1.1-repo-skeleton.md` |

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

## Cross-cutting files

| File | Rule |
|---|---|
| `STATUS.md` | Overwrite at the end of every session. Keep it current-state only. |
| `log.md` | Append one line per session. Never edit old lines. |
| `open-questions.md` | Add questions cheaply. Promote to ADR when durable; mark resolved with link. |
| `architecture/` | Update only when source paths actually change. Do not speculatively edit. |
| `decisions/` | One ADR per durable, cross-cutting decision. Do not add ADRs for local implementation choices. |

---

## Sacred rule

Documentation is a **cache of engineering intent, not a source of truth.**

When docs disagree with code, migrations, schemas, tests, or runtime behaviour, **code wins.**
If you find a contradiction: flag it, fix the *doc*, and record the fix in `log.md`.
Never bend code to match a stale doc. Never write a report from memory.
