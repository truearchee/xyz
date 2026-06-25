---
type: session-spec
stage: 12
session: "12d"
slug: privacy-data-retention
status: approved
created: 2026-06-24
updated: 2026-06-24
owner: developer
report: knowledge/steps/stage-12/12d-privacy-data-retention.md
---

# Session 12d — Privacy & Data Retention

> Filed from the approved Stage 12 v1.2 spec ([[specs/stage-12/12-release-hardening]] §5 12d) and the
> owner-approved 12c+12d plan (2026-06-24). **D-12-C is already recorded as
> [[decisions/adr-063-course-lifetime-retention]]** (accepted, `related-session: "12d"`, pre-written during
> 12b's owner-policy resolution). Owner decision **D1=A**: accept adr-063, **create no new ADR** (`064` stays
> next-free), verify it against reality, record the reconciliation. No mechanism is built now
> (deferred-with-owner to go-live).

## Scope & status
| Item | Status |
|---|---|
| D-12-C retention ADR (course-lifetime; cascade-on-delete; backup-retention alignment; mechanism deferred) | **RECORDED — [[decisions/adr-063-course-lifetime-retention]]** (no new ADR; `064` stays next-free) |
| Check 1 — ADR text states all four required points | **PASS** |
| Check 2 — ADR claim ("deleting a course deletes all material") vs live code | **PASS — verdict (a): no course-deletion path exists yet** |
| F-12C-CASCADE — core-spine FK-cascade gap surfaced by Check 2 | **FLAGGED** for the go-live mechanism (see [[specs/stage-12/12c-data-workers-capacity-review]]) |
| Deletion mechanism | **DEFERRED-WITH-OWNER to go-live** (owner = product owner); NOT built now |
| Go-live gate item captured for 12f's `docs/go-live-checklist.md` | **DONE** (findings-12 §7 closeout note) |

## Verification (accept against reality, not the `accepted` label)
**Check 1 — ADR text.** adr-063 states all four required points: course-lifetime retention (`:25-26`);
course-deletion-deletes-all-material (`:26-28`); bounded backup-retention alignment (`:34-40`);
mechanism-deferred-to-go-live (`:43-46`). Matches the locked D-12-C. **PASS.**

**Check 2 — claim vs live code.** **Verdict (a): no course-deletion path exists.** No `DELETE /modules/{id}`
route; the only module-level DELETE removes a membership (`admin.py:192`); course-row deletion exists only in
test/dev teardown (`dev_reseed.py:278-308`, an ordered manual multi-table delete). Consistent with "mechanism
deferred to go-live." **PASS.** Surfaced **F-12C-CASCADE** (the core-spine FKs do not cascade from
`course_modules`) — recorded for the go-live mechanism; not a today-defect (nothing orphans without a delete
path); no schema change now.

## Deferred-with-owner (go-live gate; do NOT build now)
Per adr-063 and master spec §7, the course-deletion retention mechanism is an explicit go-live gate item —
**owner = product owner** — to be enabled **before any real-student data** (seed-only today; no hosting). It
lands in 12f's `docs/go-live-checklist.md`. A closeout note is recorded in findings-12 §7 so it survives until
12f builds that checklist.

## Done means
- Retention ADR recorded incl. backup-retention alignment (met by adr-063); both verification checks pass;
  mechanism explicitly deferred-with-owner + listed for go-live; no mechanism built ⇒ `/review`+`/codex` N/A;
  **full active Playwright suite green (rule 14) — owner merge-time gate.**

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Report: [[steps/stage-12/12d-privacy-data-retention]]
- Decision: [[decisions/adr-063-course-lifetime-retention]]
- Findings: [[steps/findings-12]]
- 12c (data/workers): [[specs/stage-12/12c-data-workers-capacity-review]]
- Architecture: [[architecture/storage]] · [[architecture/transcript-lifecycle]] · [[architecture/db-spine]]
