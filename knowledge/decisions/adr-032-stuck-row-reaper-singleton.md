---
type: adr
stage: "4.6"
status: accepted
created: 2026-06-11
updated: 2026-06-11
related-session: knowledge/specs/stage-04/4.6c-recovery-reaper-reconciliation.md
---

# ADR-032 — Stuck-row reaper: step-aware, RQ/age liveness, singleton, fenced (spec ADR-46-C)

> Spec label "ADR-46-C". Remapped to repo slot adr-032 (same convention as adr-029..031).

## Linked documents
- Spec: [[specs/stage-04/4.6c-recovery-reaper-reconciliation]]
- Report: [[steps/stage-04/4.6c-recovery-reaper-reconciliation]]
- Related: [[adr-031-retry-resume-from-failed-step-fenced]] (fencing), [[architecture/transcript-lifecycle]]

## Context
A worker can die mid-job (OOM/OS kill), leaving an `IngestionJob` `running` forever; an
enqueue-after-commit can fail, leaving a job `queued` that RQ never received, or a transcript `uploaded`
with no parse job. None of these self-heal — the roadmap has tracked stuck-row recovery as deferred debt
since Stage 4.3. Recovery must be idempotent, safe under N concurrent workers, and observable.

## Decision
1. **Callable, idempotent, on-demand.** `run_stuck_row_reaper(...)` runs at worker startup
   (`REAPER_RUN_AT_STARTUP`, default on) and on an admin trigger; 11.1's cron will point at the same
   entrypoint (zero rework). It writes a `MaintenanceRun` row for every execution.
2. **Singleton.** A Postgres `pg_try_advisory_lock` (held on a DEDICATED connection so it survives the
   work's commits and is always explicitly released) — a worker that can't take it skips (no row written).
3. **Step-aware staleness + RQ/age liveness, NO heartbeat columns** (spec §6 allows "or rely on RQ
   registry"). Per-step thresholds (parse/chunk minutes; embed generous; summary = prompt timeout +
   limiter/backoff buffer). embed/summary carry stable RQ job_ids (`embed-{id}`, `summary-*-{id}`) → checked
   via `Job.fetch`; parse/chunk have none → age-only.
4. **Behaviour** (action-capped, fenced):
   - uploaded/queued transcript past the parse threshold with no parse job → re-enqueue parse (idempotent
     via the claim's on-conflict + status guard).
   - queued downstream job past its threshold and not live in RQ → re-enqueue (subsumes the removed
     `reenqueue_summaries.py` backfill, obsolete after the 4.6b DAG decouple).
   - running past its threshold and **confidently** not live (NoSuchJob; or age-only for parse/chunk) →
     mark `failed` + `failure_category='crashed'` (retryable per the 4.6b projection map), **fenced**: re-read
     job + transcript `FOR UPDATE`, re-verify still-running + still-stale + not-superseded before acting.
5. **report_only** mode counts without acting (admin dry-run).

## Consequences
- The pipeline self-heals from crashes/enqueue-misses without manual SQL.
- `crashed` (defined + projection-mapped in 4.6b) finally has a producer.
- Never marks a job crashed on a transient Redis error for embed/summary (only confident-not-live);
  parse/chunk rely on age (thresholds are minutes; re-enqueue is idempotent, so a rare false re-enqueue is
  harmless). Superseded transcripts are fenced out.

## Alternatives rejected
- **Heartbeat columns + worker writes** — more robust but invasive to 4.5-verified loops; the RQ-registry +
  age signal is sufficient and spec-sanctioned.
- **Row-lock-only "singleton"** — doesn't prevent two reapers scanning the whole table at once; the advisory
  lock is the right granularity.
- **One giant transaction** — holds row locks too long and is all-or-nothing; each action is its own fenced txn.
