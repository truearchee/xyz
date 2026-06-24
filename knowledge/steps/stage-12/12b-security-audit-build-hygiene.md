---
type: session-report
stage: 12
session: "12b"
slug: security-audit-build-hygiene
status: in-progress
created: 2026-06-23
updated: 2026-06-23
owner: developer
spec: knowledge/specs/stage-12/12b-security-audit-build-hygiene.md
---

# Report — Session 12b — Security Audit & Build Hygiene

> Status: **audits done; the one code fix (visibility-gate uniformity) implemented + verified; `/cso`,
> the build-hygiene script, and `/review`+`/codex` remain.** Run in parallel with the 12a gate per owner
> directive. Not merged — the owner merges. Written from audit output + `git diff` + captured test runs.

## Audits (read-only) — results
- **Secrets hygiene — PASS.** `.env`/`.env.e2e` gitignored; `.env` never committed (history clean); tracked
  source has only env-var *names* (`SUPABASE_SERVICE_ROLE_KEY` referenced in E2E helpers), no secret values.
- **Auth boundary (Slice 0 / rule 4) — PASS** (A1–A4): inactive→403 (`dependencies.py:38-42`); per-request
  DB identity resolution (mid-session deactivation loses access next request); no local password storage
  (Supabase-delegated); no `/auth/login` (JWT-validation only).
- **PII-in-logs (rule 6) — PASS** (B1–B4): `AIRequestLog` stores hashes/metadata only; `debug_text_truncated`
  is `IS_NON_PROD`-gated; no raw transcript/student-speech/prompt text logged.
- **Signed-URL (D-12-B) — DECIDED, ADR-062.** Verified the mint path re-validates publish on every request
  (`content/service.py:374-382`) ⇒ **unpublish blocks future minting**; only already-issued URLs survive to
  the ≤5-min TTL. Accepted with rationale; **no code change**. (Resolves the kickoff doc-vs-code contradiction
  in favour of the storage doc.)

## Code fix — content-visibility gate uniformity (the marquee 12b item)
The shared `apply_visible_section_gate` (or an equivalent published+assigned predicate) holds across 16
student-facing section reads. The audit found **3 ungated student-facing reads** in
`backend/app/platform/query/analytics_read.py`, each returning/counting unpublished sections:
- `earliest_topic_deadline_gap` (line 633) — **F-LAND-1** (Stage-11-landing-deferred): an unpublished
  section's title reaches the student via `risk.py:202` `student_text` + `supportingMetrics.topicTitle`.
- `get_workload_module_context` (line 417) — unpublished section deadlines feed the student workload planner.
- `has_upcoming_work` (line 613) — unpublished future work flips the student risk boolean.

**Fix (routed through the canonical `section_visibility` module — owner steer, since this leak recurred 4×
from inline per-site re-implementation):**
- `earliest_topic_deadline_gap` is a 1:1 section-reference read (off the snapshot's `module_section_id`) →
  now uses **`apply_visible_section_gate`** directly (the explicit `ModuleSection` join was removed; the gate
  adds it + the full published/active/active-membership predicate), matching the gamification/progress pattern.
- `get_workload_module_context` + `has_upcoming_work` are **1:many `ModuleSection` enumerations** that the
  1:1-join gate cannot express (it joins `ModuleSection` once via a section-id column). To avoid a fresh inline
  predicate, a new **`published_active_section_conditions()`** was added to the SAME `section_visibility.py`
  (one canonical home for the publish/active section rule); membership stays caller-enforced (both callers
  already authorise the student's module access — `_require_student_module` / per-student risk).

Practically masked today (topic-mastery snapshots are seed-only — `progress/seed.py`), but now **structurally
closed**. **F-LAND-1 is closed.** Verified-safe (left unchanged): `_section_labels` (lecturer-facing; lecturers
legitimately see their own unpublished sections) and `list_published_sections_for_student` (route-gated by
`require_module_access`).

**Test:** `backend/tests/test_12b_visibility_gate.py` — one per surface (query layer): a published + an
unpublished section are created; the unpublished is asserted absent from workload deadlines, upcoming-work
detection, and the topic-deadline gap.

## Production-build hygiene gate (fail-on-flag)
`backend/app/platform/production_hygiene.py` — a pure (no app imports / no DB) build-time assertion that
exits non-zero if any E2E/test hook or fault-injection switch is enabled in a production-candidate build.
Covers the full flag inventory (findings-12): `NEXT_PUBLIC_E2E_TEST_HOOKS`, `NEXT_PUBLIC_TRACER_ENABLED`,
`PIPELINE_FAULT_INJECTION_ENABLED`, `PIPELINE_FAULT_INJECTION`, `LLM_FAULT_INJECTION`,
`LLM_PROVIDER=deterministic`, `EMBEDDING_PROVIDER=deterministic`. Runnable as `python -m
app.platform.production_hygiene` (for the 12f deploy procedure) and slots into a CI step unchanged;
`find_violations(env)` is unit-tested. (Complements the existing boot-time guards in `config.py`/`provider.py`
which already refuse deterministic providers in prod/staging.) The 12f deploy procedure will invoke it before
the frontend build and before backend boot. Verified in-container: exit 1 on a violating env (clear message),
exit 0 on a prod-safe env.

## Verification (captured)
- **Backend full suite: `830 passed`** (`docker compose exec backend pytest -q`, 251s) — 814 (12a) + 3
  visibility + 13 hygiene, zero regressions. The visibility refactor did not break any seeded analytics test
  (seeded sections are published); the gate-consumer suites (gamification/progress) stay green.
- Targeted: `test_12b_visibility_gate.py` + `test_production_hygiene.py` + `test_analytics_*` +
  `test_workload_planner.py` + `test_gamification_api.py` + `test_progress_api.py` all green.
- `py_compile` clean on the changed source.

## `/cso` OWASP+STRIDE pass — DONE (zero exploitable findings)
Daily mode, 8/10 zero-noise gate, whole app, parallel hunters across A01–A10 + STRIDE + LLM/Phase 7 + deps +
CI + infra + skills. **Zero CRITICAL / zero HIGH / zero exploitable findings** — the 12a/12b work verified
clean (error envelope leaks nothing; IDOR/access-control airtight; LLM trust boundary safe — no system-role
prompt, no tool schema, output via react-markdown raw-HTML-off; no injection/SSRF; JWT solid). Full
verified-safe ledger + the 5 LOW hardening findings (all **deferred to 12f** production-candidate build —
non-root Docker `USER`, `.dockerignore`, drop `allow_credentials=True`, CSP/HSTS headers; + a Next.js dep
bump) are in [[steps/findings-12]]. Report artifact: `.gstack/security-reports/2026-06-23-stage12b-cso.json`.

## Owner decisions — ALL RESOLVED (2026-06-23)
- **D-12-B** signed-URL — accept the 5-min TTL window (**ADR-062**); no code.
- **D-12-C** retention — **course-lifetime** (deleting the course deletes its material); mechanism
  deferred-with-owner to go-live; **ADR-063**.
- **Code-asymmetry** (403↔404) — **accepted as-is** (UI never exposes unassigned modules; immaterial at MVP
  scale). No code change.

## Remaining 12b work (owner gate)
- `/review` (Claude) + `/codex` (OpenAI, fresh session) on the 12b code change.
- Full active Playwright suite (owner supplies `.env.e2e`).
- Owner reviews the staged commits and merges (agent never merges).

## Modified prior sessions
- Stage 11 — `backend/app/platform/query/analytics_read.py`: routed the three student-facing reads
  (`get_workload_module_context`, `has_upcoming_work`, `earliest_topic_deadline_gap`) through the canonical
  visibility predicate (closes F-LAND-1; they were leaking/counting unpublished sections).
- Stage 10.x — `backend/app/platform/query/section_visibility.py`: added `published_active_section_conditions()`
  (the section-level half of the gate, for 1:many `ModuleSection` enumerations that the 1:1-join
  `apply_visible_section_gate` cannot express) so the publish/active rule keeps ONE canonical home.

## Linked documents
- Spec: [[specs/stage-12/12b-security-audit-build-hygiene]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]]
- Decision: [[decisions/adr-062-signed-url-ttl-acceptance]]
- Architecture: [[architecture/storage]] · [[architecture/auth-current-user-context]]
