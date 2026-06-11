# Open questions

Decision inbox. Capture unresolved questions here cheaply. Promote to an ADR in
`decisions/` only when the decision is durable; then mark the question resolved with a
link to the ADR.

Format: `- [ ] <question> — raised YYYY-MM-DD (#stage.session)`

---

- [x] Queue tech for Stage 4 worker sessions resolved to RQ on Redis per locked roadmap guidance and existing Stage 1 worker service — resolved 2026-06-01 by [[decisions/adr-017-ingestion-job-worker-spine]] (#4.2)
- [ ] Replace the temporary MVP default module-section generation policy with schedule-driven or template-driven generation, or explicitly accept the default as longer-lived — raised 2026-06-07 (#4.3.5d-B1)
- [x] Confirm the `summarizing` overallState added to the transcript projection (intermediate between `embedded` and `summarized`, for the passive "generating" badge §13), or fold it back into `embedded` — kept; 4.5b rests at `summarizing` when brief is done and detailed is deferred (`ENABLE_DETAILED_SUMMARY=false`) — resolved 2026-06-11 (#4.5b)
- [ ] Gate 2.A authority-hash residual: the Stage 4.5 spec embeds no reference roadmap hash, so the check is presence + v3 + obligation-consistency; the recorded SHA-256 is the baseline of record for future drift detection — raised 2026-06-10 (#4.5a)
- [ ] No cross-cutting "rules 1–15" document exists in-repo; the Stage 4.5 spec/roadmap cite rule numbers whose authoritative text lives only in `knowledge/roadmap.md` §"Cross-cutting rules" — confirm that is the canonical source — raised 2026-06-10 (#4.5a)
- [x] `rate_limited` is treated as a terminal `failed` (failure_category=rate_limited) in 4.5a; in-call backoff under the limiter and product re-drive are deferred — confirm the 4.5b/4.6 home — 4.5b adds in-call bounded backoff (limiter-full + provider 429) recorded in-row, terminal on exhaustion; product re-drive stays 4.6 (F-4.5-31) — resolved 2026-06-11 (#4.5b)
- [ ] `AIRequestLog.ingestion_job_id` is NOT NULL in 4.5a (all callers are job-tied summaries); Stage 8 assistant gateway calls will need it nullable (migration) — raised 2026-06-10 (#4.5a)
- [ ] **Stage 4.6 entry requirements** surfaced by the 4.5d close-out: (a) the AI worker runs `worker.work()` without `with_scheduler=True`, so the bounded RQ retry for `invalid_output` is scheduled but never re-drives — 4.6 owns the lecturer retry action + queued/stuck-row sweeper (F-4.5-47); (b) per-request fault injection (replacing global `LLM_FAULT_INJECTION`, which can't express inject→clear→succeed in one run) — raised 2026-06-11 (#4.5d)
- [ ] No static type checker (mypy/pyright) is configured; the 4.5b type-check gate is `compileall` + full pytest collection. Introduce a real type-check pass in Stage 4.9 hygiene — raised 2026-06-11 (#4.5b, spec §15/§16)
- [x] `steps.summary_detailed` uses the established no-job sentinel `not_started`; a distinct `pending` value (passive "generating" affordance) is a 4.5d UI/contract decision — **resolved: keep `not_started`** as the data sentinel; the lecturer UI maps it to a friendly label (no enum/OpenAPI contract change) — resolved 2026-06-11 (#4.5d, F-4.5-41)
- [ ] `AIRequestLog.backend_used` is the REQUESTED route, not response-verifiable — the provider does not echo the served backend; `backend_route_source='requested'` records this, flips to `provider_echoed` if/when the provider ever echoes the route (per-backend budget rests on this assumption at single-model scale) — raised 2026-06-11 (#4.5b, F-4.5-28); see [[decisions/adr-025-routing-split]]
- [ ] Intended models `K2-V2-Instruct` (brief) + `K2-Think-v0` (detailed) are inaccessible; 4.5b/4.5c run BOTH summaries on the one verified `K2-Think-v2` (brief=default route, detailed=use_nvidia route — Option A nominal route separation) — switch back on access (config + prompt-version bump, no Python change) and run the deferred dual-model gate-2.B — raised 2026-06-11 (#4.5b/#4.5c, F-4.5-27/F-4.5-39); see [[decisions/adr-025-routing-split]]
