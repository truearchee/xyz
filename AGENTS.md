## Development-memory protocol — read every session

Full details: `knowledge/dev-workflow.md`. Orientation: `knowledge/STATUS.md`.

### Implementation mode is gated
1. **No spec, no implementation.** If the developer hands you a document to work from,
   file it into `knowledge/specs/stage-NN/<session>-<slug>.md` (reformat to the
   session-spec template, preserve all of their content), set `status: approved`, and
   confirm scope before doing anything else.
2. **No plan, no code.** Enter planning mode first (the developer often invokes `/plan`).
   Produce `knowledge/plans/stage-NN/<session>-<slug>.md` and get it approved. The plan
   says HOW; the spec says WHAT/WHY/DONE. Do not start editing source until the plan is approved.
3. **Build only inside spec scope.** Honour the spec's "Do not build" list. If scope must
   change, add an entry to the spec's `## Amendments` — never drift silently.
4. **Verify.** Run the spec's verification commands. Capture the real output.
5. **Report from evidence.** Write `knowledge/steps/stage-NN/<session>-<slug>.md` from
   `git diff` + command output, NOT memory. Record deviations, risks, follow-ups.
6. **Maintain Obsidian links.** Every spec, plan, and report has a `## Linked documents`
   section with wikilinks to the other two. Format:
   ```md
   ## Linked documents
   - Spec: [[specs/stage-NN/N.N-slug]]
   - Plan: [[plans/stage-NN/N.N-slug]]
   - Report: [[steps/stage-NN/N.N-slug]]
   ```
   Omit whichever don't exist yet. Update this section as each is created. By session end,
   all three files reference each other, and the Obsidian graph shows the trio as a
   connected cluster. Also link to any architecture/ or decisions/ files referenced.
7. **Close the loop.** Fill the spec↔plan↔report links, overwrite `STATUS.md`, append a
   line to `log.md`. Update `architecture/` only if source paths changed; add an ADR in
   `decisions/` only if a durable decision was made; update `open-questions.md` if anything
   is unresolved.

### Sacred rule
Docs are a cache of engineering intent, not a source of truth. When docs and
code/migrations/schema/tests/runtime disagree, **code wins.** Flag the contradiction and
fix the doc. Never bend code to match a stale doc.

### Later changes to completed work
Append a dated line to the report's `## Change history` and bump its `updated:` field.
Amend the spec if the *intent* changed. Supersede (don't delete) if the work is replaced.

### Modifying code from prior completed sessions

When your current session edits files that were built and completed in an earlier session:

1. **Leave the prior session's report unchanged.** It remains `status: complete` as a historical record.
2. **In your current session's report**, add a `## Modified prior sessions` section listing:
   - Which session(s) you modified
   - Which files you changed
   
   - Why you changed them

   Example:
```markdown
   ## Modified prior sessions
   - Session 1.1 — `backend/app/main.py`: added auth middleware
   - Session 1.1 — `.env.example`: added SUPABASE_URL variable
```

3. **Append to the prior session's report** a line in its `## Change history` section:
```markdown
   - YYYY-MM-DD HH:MM — [Session X.Y] what changed and why
```

This keeps the audit trail clean: each session's report shows what it originally built,
and the change history shows what happened to those files later. No file duplication,
no competing versions of truth.
