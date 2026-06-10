# Open questions

Decision inbox. Capture unresolved questions here cheaply. Promote to an ADR in
`decisions/` only when the decision is durable; then mark the question resolved with a
link to the ADR.

Format: `- [ ] <question> — raised YYYY-MM-DD (#stage.session)`

---

- [x] Queue tech for Stage 4 worker sessions resolved to RQ on Redis per locked roadmap guidance and existing Stage 1 worker service — resolved 2026-06-01 by [[decisions/adr-017-ingestion-job-worker-spine]] (#4.2)
- [ ] Replace the temporary MVP default module-section generation policy with schedule-driven or template-driven generation, or explicitly accept the default as longer-lived — raised 2026-06-07 (#4.3.5d-B1)
- [ ] Confirm the `summarizing` overallState added to the transcript projection (intermediate between `embedded` and `summarized`, for the passive "generating" badge §13), or fold it back into `embedded` — raised 2026-06-10 (#4.5a)
- [ ] Gate 2.A authority-hash residual: the Stage 4.5 spec embeds no reference roadmap hash, so the check is presence + v3 + obligation-consistency; the recorded SHA-256 is the baseline of record for future drift detection — raised 2026-06-10 (#4.5a)
- [ ] No cross-cutting "rules 1–15" document exists in-repo; the Stage 4.5 spec/roadmap cite rule numbers whose authoritative text lives only in `knowledge/roadmap.md` §"Cross-cutting rules" — confirm that is the canonical source — raised 2026-06-10 (#4.5a)
- [ ] `rate_limited` is treated as a terminal `failed` (failure_category=rate_limited) in 4.5a; in-call backoff under the limiter and product re-drive are deferred — confirm the 4.5b/4.6 home — raised 2026-06-10 (#4.5a)
- [ ] `AIRequestLog.ingestion_job_id` is NOT NULL in 4.5a (all callers are job-tied summaries); Stage 8 assistant gateway calls will need it nullable (migration) — raised 2026-06-10 (#4.5a)
