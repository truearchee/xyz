---
type: session-spec
stage: 12
session: "12b"
slug: security-audit-build-hygiene
status: in-progress
created: 2026-06-23
updated: 2026-06-23
owner: developer
report: knowledge/steps/stage-12/12b-security-audit-build-hygiene.md
---

# Session 12b — Security Audit & Build Hygiene

> Filed from the approved Stage 12 v1.2 spec ([[specs/stage-12/12-release-hardening]] §5 12b), narrowed to
> the **non-signed-URL** scope per the owner directive (2026-06-23): proceed with 12b in parallel with the
> 12a gate; the signed-URL piece is bounded to what D-12-B unblocks (ADR only, no revocation code).

## Scope & status
| Item | Status |
|---|---|
| Secrets-not-in-repo / history (K2Think Bearer, Supabase keys, DB-URL passwords) | **AUDITED — PASS** (`.env`/`.env.e2e` gitignored, `.env` never committed, only env-var *names* in tracked E2E files) |
| Auth boundary (inactive login blocked, mid-session deactivation, password hashing/Supabase-delegated, no `/auth/login`) | **AUDITED — PASS** (A1–A4) |
| PII-in-logs (rule 6 — AIRequestLog hashes only; `debug_text` IS_NON_PROD-gated) | **AUDITED — PASS** (B1–B4) |
| **Content-visibility gate uniformity** (recurred 8.6/9/10/11) | **AUDITED + FIXED** — 3 analytics_read gaps closed (incl. F-LAND-1), test per surface |
| Signed-URL revocation (D-12-B) | **DECIDED — ADR-062** (accept ≤5-min TTL; future minting already blocked; no code) |
| Production-build hygiene assertion script (fail-on-flag) | **DONE** — `app/platform/production_hygiene.py` (runnable + unit-tested) |
| `/cso` OWASP+STRIDE pass | **DONE** — zero CRITICAL/HIGH/exploitable; 5 LOW hardening gaps deferred to 12f (findings-12) |
| `/review` + `/codex` on the code change | **TODO** (owner pre-merge gate) |

## Content-visibility fix (the marquee item)
`apply_visible_section_gate` (or an equivalent published+assigned predicate) was verified across 16
student-facing section reads; the audit found **3 ungated student-facing analytics reads** in
`platform/query/analytics_read.py` that returned/counted unpublished sections:
- `earliest_topic_deadline_gap` (**F-LAND-1**, Stage-11-landing-deferred) — an unpublished section's title
  reaches the student via `risk.py` `student_text` / `supportingMetrics.topicTitle`;
- `get_workload_module_context` — unpublished section deadlines feed the student workload planner;
- `has_upcoming_work` — unpublished future work flips the student risk boolean.
Each gained `ModuleSection.publish_status == "published"`. Currently *masked* in practice (topic-mastery
snapshots are seed-only), but structurally closed now + locked by `test_12b_visibility_gate.py`.
**Verified safe (not leaks):** `_section_labels` (lecturer-facing — lecturers legitimately see their own
unpublished sections) and `list_published_sections_for_student` (route-gated by `require_module_access`).

## Held for the product owner (do NOT act)
- **Code-asymmetry** (asset-upload 403 vs publish 404 for an unassigned lecturer) — owner decision; likely a
  separate small "unify to 404" commit with its own `/codex` (candidate first 12b commit).
- **D-12-C** retention — owner policy; ADR-now / mechanism-deferred shape agreed; await the target policy.

## Done means
- `/cso` clean (or every finding resolved per rule 13); secrets/auth/PII audits recorded; visibility-gate
  closed everywhere with a test per surface; build-hygiene assertion script green and failing-on-violation;
  D-12-B ADR recorded; `/review` + `/codex` on the code change; full active Playwright suite green (rule 14).

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Report: [[steps/stage-12/12b-security-audit-build-hygiene]]
- Findings: [[steps/findings-12]]
- Decision: [[decisions/adr-062-signed-url-ttl-acceptance]]
- Architecture: [[architecture/auth-current-user-context]] · [[architecture/storage]]
