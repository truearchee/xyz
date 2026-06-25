---
type: session-spec
stage: 12
session: "12c"
slug: data-workers-capacity-review
status: approved
created: 2026-06-24
updated: 2026-06-24
owner: developer
report: knowledge/steps/stage-12/12c-data-workers-capacity-review.md
---

# Session 12c — Data, Workers & Capacity Review

> Filed from the approved Stage 12 v1.2 spec ([[specs/stage-12/12-release-hardening]] §5 12c) and the
> owner-approved 12c+12d plan (2026-06-24). **Review-and-verify; fix only on a real defect.** No migration
> block is assigned (the chain ends at `0059`); a defect needing a schema change is a STOP-and-ask, never a
> self-selected migration number.

## Scope & status
| Item | Status |
|---|---|
| Migration chain — single head, fresh-DB round-trip, no orphans/dups | **VERIFIED** — single head `0059`; `upgrade→base→upgrade` green on a fresh DB |
| Doc correction — kickoff "head 0082" → `0059` | **DONE** — `findings-12` kickoff table + `:73`, `12a` spec `:59` (narrow, owner D2=A) |
| Workers & scheduler — retry, terminal-failure observability, no stranded jobs, scheduled jobs fire, AgentRun gap closed, reaper covers uploaded/parsing/queued | **VERIFIED** — code + 79 targeted tests |
| Rate limiter — documented budgets + interactive headroom | **VERIFIED** — 20/10 RPM, 100k/105k TPM, conc 10, 20% interactive headroom |
| Storage reconciliation (4.6) — report-only/prefix-scoped/deletion-capped/superseded-retained | **VERIFIED** — code + tests |
| Logging review — 3 pass criteria | **VERIFIED — PASS** (ERROR+request_id / no PII / stdout, no aggregation stack) |
| AIRequestLog cost review — "tokens by feature by day" returns a result | **DONE** — query authored, index-backed, runs; sanity-checked vs IFM budgets |
| F-12C-CASCADE — course-deletion FK-cascade gap | **FLAGGED** (not a today-defect) — see below + [[specs/stage-12/12d-privacy-data-retention]] |

## Queue topology (confirm-don't-assume)
The code defines **three** RQ queues — `ingestion`, `embedding`, `ai` (`workers/queues.py:12-14`); there is
**no `agent` queue**. `AgentRun` jobs run on the **`ingestion`** queue via `enqueue_run_agent_if_needed`
(`queues.py:194`). The master spec's "embedding / ai / agent" was shorthand; this is the reviewed reality.

## F-12C-CASCADE — flag for the go-live deletion mechanism (not a today-defect)
adr-063 promises "deleting a course deletes all its material" and its *Consequences* say "the DB half is
FK-cascade from `course_modules`". Reality: the cascade is **mixed**. Stage 9–11 tables (quiz, mistakes,
progress/risk/workload/recommendation/assistant_conversation, grade schemes, glossary) declare
`ondelete="CASCADE"` from `course_modules`; the **core content spine does not** —
`module_sections→course_modules`, `transcripts→module_sections`, `section_assets→module_sections`,
`course_memberships→course_modules` are all `NO ACTION` (`0002_db_spine.py`, `0004_transcripts.py`).
Nothing orphans today (no course-deletion path exists — verified in 12d), so this is **not** a current
defect and needs **no schema change in 12c**. It is recorded so the deferred go-live mechanism is scoped as
**either** a cascade migration on the core-spine FKs (owner-assigned block at go-live) **or** an app-level
ordered delete (the `dev_reseed` pattern) + loss-safe object-store cleanup (reuse the 4.6 reconciliation
patterns). Owner may optionally amend adr-063's *Consequences* wording for accuracy (flag, not self-edit).

## Done means
- Single head confirmed + fresh-DB round-trip green + actual head (`0059`) recorded; queue/limiter/scheduler/
  reaper/reconciliation behavior verified by tests + documented checks; logging review passes its 3 criteria;
  cost query returns a result + sanity-checked; doc correction applied; no code change (review-only) so
  `/codex` is N/A; **full active Playwright suite green (rule 14) — owner merge-time gate.**

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Report: [[steps/stage-12/12c-data-workers-capacity-review]]
- Findings: [[steps/findings-12]]
- 12d (retention): [[specs/stage-12/12d-privacy-data-retention]]
- Architecture: [[architecture/worker]] · [[architecture/transcript-lifecycle]] · [[architecture/llm]] · [[architecture/db-spine]]
