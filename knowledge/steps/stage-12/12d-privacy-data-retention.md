---
type: session-report
stage: 12
session: "12d"
slug: privacy-data-retention
status: done
created: 2026-06-24
updated: 2026-06-24
owner: developer
spec: knowledge/specs/stage-12/12d-privacy-data-retention.md
---

# Report — Session 12d — Privacy & Data Retention

> Status: **complete; no new ADR, no code.** D-12-C was already recorded as
> [[decisions/adr-063-course-lifetime-retention]] (pre-written during 12b, `related-session: "12d"`). Owner
> decision **D1=A**: accept adr-063; verify against reality; record the reconciliation. Owner gate remaining:
> full active Playwright (rule 14) + merge.

## Outcome
- **No new ADR.** adr-063 discharges D-12-C and meets the 12d gate. **`064` stays next-free** (consistent with
  the 048/056/057 no-renumber decision). Creating ADR-064 would have duplicated an accepted ADR.

## Verification (against reality, not the `accepted` label)
- **Check 1 — ADR text: PASS.** adr-063 states all four required points and matches the locked D-12-C:
  course-lifetime retention (`:25-26`); course-deletion-deletes-all-material (`:26-28`); bounded
  backup-retention alignment (`:34-40`); mechanism-deferred-to-go-live (`:43-46`).
- **Check 2 — claim vs live code: PASS, verdict (a) "no course-deletion path exists yet".** No
  `DELETE /modules/{id}`; the only module-level DELETE removes a membership (`admin.py:192`); course-row
  deletion exists only in test/dev teardown (`dev_reseed.py:278-308`). Consistent with "mechanism deferred to
  go-live." (FK-cascade map confirmed across `db/models/*`: Stage 9–11 tables cascade from `course_modules`;
  the core content spine does not — see F-12C-CASCADE.)
- Both checks pass ⇒ accept adr-063, no new ADR.

## F-12C-CASCADE (flagged; not a today-defect)
adr-063's *Consequences* "the DB half is FK-cascade from `course_modules`" overstates today's schema: the core
content spine (`module_sections`/`transcripts`/`section_assets`/`course_memberships`) is `NO ACTION`, not
CASCADE (`0002_db_spine.py`, `0004_transcripts.py`). Nothing orphans today (no delete path), so no schema
change now. The go-live mechanism must use **either** a cascade migration on the core-spine FKs
(owner-assigned migration block at go-live) **or** an app-level ordered delete (the `dev_reseed` pattern) +
loss-safe, prefix-scoped object-store cleanup (reuse 4.6). Owner may optionally amend adr-063's *Consequences*
wording (flag, not self-edit). Recorded in findings-12.

## Deferred-with-owner (go-live)
The course-deletion retention mechanism is an explicit go-live gate item — **owner = product owner** — to be
enabled **before any real-student data** (seed-only today). It lands in 12f's `docs/go-live-checklist.md`;
a closeout note in findings-12 §7 carries it until then. **Not built now** (per the spec hold; 12f scope).

## Verification (captured)
- No code, no migration, no new ADR. Doc-only.
- Full active Playwright (rule 14) is the owner merge-time gate.

## Linked documents
- Spec: [[specs/stage-12/12d-privacy-data-retention]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Decision: [[decisions/adr-063-course-lifetime-retention]]
- Findings: [[steps/findings-12]]
- 12c: [[steps/stage-12/12c-data-workers-capacity-review]]
