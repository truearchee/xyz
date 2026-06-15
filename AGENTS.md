## Development-memory protocol — read every session

This file is the always-loaded operating contract. The full reference is

`knowledge/dev-workflow.md` — read it once at session start for the detailed

protocol, templates, statuses, naming, and vocabulary. Orientation: `knowledge/STATUS.md`.

### Step 0 — Read narrowly, never scan

At session start read ONLY:

1. This file (AGENTS.md).

2. `knowledge/STATUS.md` — orientation.

3. Your own spec — the entry contract for this session.

4. Only the files your spec explicitly links (named ADRs, named `architecture/`

   files, a named upstream report).


Do NOT read other stages' specs/plans/reports unless your spec names them.

`knowledge/archive/` is history — never treat it as current state.

For the current state of the system, read the CODE, not old reports (sacred rule).


### Implementation mode is gated

1. **No spec, no implementation.** If the developer hands you a document, file it

   into `knowledge/specs/stage-NN/<session>-<slug>.md` (session-spec template,

   preserve all content). Set `status: approved` only after the developer

   confirms scope, then stop and confirm before anything else.

2. **No plan, no code.** Produce `knowledge/plans/stage-NN/<session>-<slug>.md`

   and get it approved. Plan = HOW; spec = WHAT/WHY/DONE. No source edits until approved.

3. **Build only inside spec scope.** Honour the spec's "Do not build" list. Scope

   change → spec `## Amendments`. Never drift silently.

4. **Verify.** Run the spec's verification commands. Capture the real output.

5. **Report from evidence.** Write `knowledge/steps/stage-NN/<session>-<slug>.md`

   from `git diff` + command output, NOT memory.

6. **Maintain links.** Each spec/plan/report carries a `## Linked documents`

   section with wikilinks to the other two (and to any architecture/ or

   decisions/ files referenced):

   ```

   ## Linked documents

   - Spec: [[specs/stage-NN/N.N-slug]]

   - Plan: [[plans/stage-NN/N.N-slug]]

   - Report: [[steps/stage-NN/N.N-slug]]

   ```


(Full protocol, templates, statuses, and naming live in `dev-workflow.md`.)


### Folder convention for decomposed stages

When a stage splits into sub-sessions (e.g. 4.5 → 4.5a/b/c/d), nest them under a

parent folder — do not dump them flat:

```

specs/stage-04/4.5/4.5a-llm-foundation.md

plans/stage-04/4.5/4.5a-llm-foundation.md

steps/stage-04/4.5/4.5a-llm-foundation.md

```

Forward convention (Stage 5 onward). Do not move historical files.


### Step 7 — Close the loop (branch-aware)

On your branch, close the loop ONLY inside your own stage-trio:

- Fill the spec ↔ plan ↔ report links.

- Write your close-out summary inside your report.

- Add an ADR in `decisions/` only if a durable decision was made.

- Update `architecture/` only if source paths changed.


Do NOT touch on a branch: `STATUS.md`, `log.md`, `knowledge/roadmap.md`.

These shared files are updated on `main` during the merge train, never on a

branch — two agents writing them in parallel is a permanent merge conflict.


### Parallel work (Conductor)

You run in an isolated git worktree. Beyond the branch-aware rule above:

- Migrations: use only your stage's assigned block of numbers. Never touch another stage's range.

- OpenAPI client: never merge a regenerated client. Regeneration happens on `main` after merge only.

- `knowledge/` files: edit only your own stage-trio on-branch.

(These mirror the rules Conductor injects via `.conductor/settings.toml`.)


### Sacred rule

Docs are a cache of engineering intent, not a source of truth. When docs and

code/migrations/schema/tests/runtime disagree, **code wins.** Flag the

contradiction and fix the doc. Never bend code to match a stale doc.


### Later changes to completed work

Append a dated line to the report's `## Change history` and bump its `updated:`

field. Amend the spec if the *intent* changed. Supersede (don't delete) if replaced.


### Modifying code from prior completed sessions

When your current session edits files built in an earlier session:

1. Leave the prior session's report unchanged (`status: complete`, historical record).

2. In your current report, add a `## Modified prior sessions` section: which

   session(s), which files, and why.

3. Append to the prior report's `## Change history`:

   `- YYYY-MM-DD HH:MM — [Session X.Y] what changed and why`


This keeps the audit trail clean: each report shows what it originally built; the

change history shows what happened later. No duplication, no competing truths.
