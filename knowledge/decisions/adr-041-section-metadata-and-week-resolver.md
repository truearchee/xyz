# ADR-041 — Section metadata edits + stored-week resolver (Stage 5.5b)

- **Status:** Accepted (2026-06-16)
- **Stage:** 5.5b
- **Related:** [[specs/stage-05/5.5-module-schedule-section-metadata]] (D3, D4, D5, D8, D13),
  [[steps/stage-05/5.5b-metadata-edit-and-week-resolver]]

## Context
Stage 5.5a stamps generated lecture/lab sections with `week_number` and `session_date`. Stage 6 quiz
scope resolution consumes stored week metadata, so 5.5b needs two boundaries:

1. a tightly scoped edit endpoint for metadata curation; and
2. a read-only resolver that Stage 6 can consume without importing admin/write-domain code.

The dangerous case is silent date/week drift: changing `session_date` while leaving a stale
`week_number` would corrupt future quiz scope. The opposite danger is over-deriving: if the resolver
recomputes week from date at read time, past explicit curation decisions become unstable.

## Decision
1. **Stored week remains authoritative at read time (D3).** `resolve_sections_by_weeks(...)` reads
   `ModuleSection.week_number` and `session_date`; it never recomputes from dates.
2. **D13 applies only at metadata edit time.** PATCHing `sessionDate` without `weekNumber` recomputes
   `week_number` from the module's stored course anchor. PATCHing both fields honors the explicit
   `weekNumber`. PATCHing `weekNumber` alone leaves `sessionDate` untouched.
3. **The edit endpoint is whitelisted.** Only `weekNumber`, `sessionDate`, and `dueAt` are accepted;
   extra fields are rejected by schema validation. Structure (`type`, `orderIndex`, `title`,
   `courseModuleId`, `publishStatus`) is not patchable.
4. **Authorization follows the content boundary.** Admins may edit a valid module/section pair.
   Assigned lecturers may edit active lecture/lab sections in their assigned modules. Student role denial
   returns 403; cross-module or unassigned lecturer access returns 404 to avoid existence leaks.
5. **`dueAt` is lab-only in 5.5b.** Lecture `dueAt` edits return 422. Clearing a lab `dueAt` remains
   allowed because P-1 chose nullable deadlines.
6. **`platform/query` owns the read model.** `section_week_resolver.py` returns section IDs plus
   metadata only. It mutates nothing, does not join summaries, and does not decide student visibility.
7. **`include_unstamped=False` is a Stage 6 safety default.** Null week/date metadata is excluded by
   default so empty, holiday, or uncurated rows cannot enter quiz scope. `include_unstamped=True` is
   reserved for admin curation views and returns active lecture/lab rows including null metadata.

## Consequences
- Stage 6 must call the resolver in default mode, then apply student access, publish status, and
  completed detailed-summary filters before creating a quiz definition.
- Admin/lecturer curation can repair null or anomalous metadata without rebuilding section structure.
- A future UI may use `include_unstamped=True` to surface rows that need correction, but should not use
  that mode for quiz-generation scope.

## Alternatives rejected
- **Resolver recomputes week from `session_date`.** Rejected because D3 says curated stored week is the
  source of truth and must remain stable for future scopes.
- **Silently ignore unknown patch fields.** Rejected because it makes structural edit attempts look
  successful.
- **Return 403 for unassigned/cross-module lecturers.** Rejected to preserve the locked no-existence-leak
  convention for resources outside the caller's module boundary.
