---
type: findings
stage: 12
created: 2026-06-23
updated: 2026-06-23
---

# Stage 12 — Findings & spec/reality reconciliations (rule 10)

> The Stage 12 v1.2 spec states (its §2) that all concrete repo values in it are "starting points to
> confirm, not facts." This note records what was confirmed against the live repo at kickoff, and every
> place the spec's literal text diverges from the code/established invariants. Per the sacred rule
> (AGENTS.md), **code wins**; divergences are reconciled here so they can't resurface in a later review.

## Verified kickoff facts (confirmed against the live repo, 2026-06-23)

| Fact | Confirmed value | Source |
|---|---|---|
| Alembic head — single? | **Yes, single head `0082`** (merge of `0044`+`0081`) | `backend/alembic/versions/0082_merge_stage10_stage86_heads.py` (`down_revision=("0044","0081")`); only `0001` has `down_revision=None`. Fresh-DB round-trip to be run in 12c. |
| Next free migration | **0083** (block 0083–0095 reserved; gaps 0045–0055 & 0060–0079 are intentional parallel-branch numbering, not orphans) | `ls backend/alembic/versions/` |
| Next free ADR number | **061** (highest existing is `adr-060`) | `knowledge/decisions/` |
| Visibility gate helper | `apply_visible_section_gate` @ `backend/app/platform/query/section_visibility.py:24`; seen at `progress_read.py:173`, `gamification_read.py:211,291` — **full audit deferred to 12b** | grep |
| Health endpoints | `/health` + `/health/authed` = static 200 / liveness only; **no DB/Redis readiness** | `backend/app/api/routers/health.py` — 12f adds readiness |
| Migrations on boot? | **No** (manual `alembic upgrade head`, README:20–22; Dockerfile CMD = uvicorn). Already the release-phase posture 12f wants. | `README.md`, `backend/Dockerfile` |
| Test/fault flag inventory (for 12b build-hygiene check) | `NEXT_PUBLIC_E2E_TEST_HOOKS`, `PIPELINE_FAULT_INJECTION_ENABLED`, `PIPELINE_FAULT_INJECTION`, `LLM_FAULT_INJECTION`, `EMBEDDING_PROVIDER=deterministic`, `LLM_PROVIDER=deterministic`, the `window.__xyzE2E` auth token-override hook. **No build-hygiene assertion exists yet.** | config.py, docker-compose.fault.yml, provider.py, frontend `lib/e2e/` |

## ADR numbering collision (pre-existing — not caused by Stage 12)
`adr-048`, `adr-056`, and `adr-057` each have **3 files** in `knowledge/decisions/` (Stage 8.6 / Stage 10 /
Stage 11 parallel branches all claimed the same numbers at commit time). **Resolution:** Stage 12 allocates
ADRs from **061+**; the merged duplicates are **NOT renumbered** (they carry inbound cross-references and are
content-addressed by filename + title). Recorded here as accepted pre-existing debt (rule 13: accepted with
rationale). Owner may override.

## Reframing findings (these change the spec's stated assumptions)

### F1 — `can_publish` is a DISPLAY field; the publish security boundary is ALREADY membership-based
`can_publish` is computed in `guards.py:42-46` (falls back to global role only because `modules.py:63`
hardcodes `can_publish=None`) and surfaced in the `ModuleDetail` DTO (`api/routers/modules.py:37,83`).
**No backend code gates any mutation on it.** Every content mutation already requires an active lecturer
`CourseMembership` via `_get_assigned_lecturer_section` (`content/service.py:100-126`) /
`get_authorized_lecturer_section_context` (`section_context.py:38-46`).
⇒ The roadmap carried-debt line "`can_publish` derived from role rather than membership" (roadmap.md:98) is a
**display bug, not an enforcement hole.** 12a = display-alignment + regression-locking tests, **not** a
vulnerability fix. (Recorded so the stage is not mis-scoped as "we were exposed.")

### F2 / D3 — spec says "unassigned lecturer → 403"; live contract is **404 `SECTION_NOT_FOUND`** [RESOLVED: keep 404]
The codebase deliberately returns **404** for a lecturer acting on a module/section they hold no active
membership in — information-hiding, the established "404 not 403 for unassigned" pattern from Stage 4.7
(`test_transcripts.py:420`, `test_content.py:1936-1938`). Rule 5 only requires "session preserved" (not
logged out), which 404 satisfies; it does **not** mandate 403 over 404, and 404 is strictly more secure.
**Reconciliation (owner-confirmed D3=A):** *spec said 403; code/contract is 404-by-design per Stage 4.7
info-hiding; 404 retained as the canonical 12a assertion.* The spec's "expect 403" wording is stale.

### F3 — `PATCH …/metadata` intentionally allows admin; publish/notes/assets/transcripts do not
`_get_metadata_edit_section` (`content/service.py:147-154`) permits admin in addition to assigned lecturers
(admins manage schedule metadata); the other mutation surfaces are lecturer-only. Deliberate asymmetry —
**locked as-is** in the negative-test matrix, not "normalized." Flag for owner confirmation only.

### F4 / D2 — error envelope: additive, not clean [RESOLVED: additive now]
Dropping `detail` would break 48+ backend test asserts + 13+ frontend files reading `caught.body.detail`
(two parse it as a 422 validation array). `wrapper.ts` keys 401/403 on `caught.status`, so rule 5 is safe
either way. **Owner-confirmed D2=A:** additive envelope now (add `error` + `X-Request-ID`, keep `detail`);
the clean removal is deferred and tracked in **ADR-061** with a named future frontend-consistency pass.

### F6 — do NOT add `require_module_access` as a router dependency on mutation routes
Redundant (the service enforces under a row lock) and would change error codes (the dependency 404s "Module
not found" before the service's `CONTENT_FORBIDDEN`/`SECTION_NOT_FOUND` fire). Intentionally not done.

### F7 — seeds verified low-risk for the `can_publish` change
All seeded lecturers already hold `status="active"` lecturer memberships: `progress/seed.py:95-96`,
`tests/e2e/fixtures/seed.mjs:248`, `admin/dev_reseed.py` (status carried from snapshot). No seeded lecturer
publishes without an active membership; membership-derived `can_publish` reads `true` for them as before.
No migration needed (head stays 0082).

## Signed-URL unpublish gate — RESOLVED (12b)
`architecture/storage.md` was accurate: the mint path **does** re-validate publish status on every request.
`content/service.py::_resolve_asset_download_ref` (lines 374-382) rejects a student for an unpublished
section (403) or not-published/inactive/not-completed (404). ⇒ **Unpublish blocks future minting**; only an
already-issued signed URL survives, until its ≤5-min TTL expires. The earlier "explore couldn't locate the
gate" was a miss (it looked at the wrong layer). D-12-B therefore reduces to accepting that ≤5-min
already-issued window — recorded in **ADR-062**. No signed-URL code change.

## 12b audit results (2026-06-23)
- **Content-visibility gate uniformity — 3 gaps FOUND + FIXED, 2 verified-safe.** The shared gate (or an
  equivalent published+assigned predicate) holds across 16 student-facing section reads. Three student-facing
  `platform/query/analytics_read.py` reads omitted `publish_status='published'`:
  `earliest_topic_deadline_gap` (**F-LAND-1**, the Stage-11-landing-deferred leak — the unpublished section's
  title reaches the student via `risk.py` `student_text`/`supportingMetrics.topicTitle`),
  `get_workload_module_context` (student workload deadlines), `has_upcoming_work` (student risk boolean).
  **Routed through the canonical `section_visibility` module (owner steer — the leak recurred 4× because the
  predicate was re-typed inline per site):** `earliest_topic_deadline_gap` is a 1:1 section-reference read
  (off the snapshot's `module_section_id`) → now uses **`apply_visible_section_gate`** directly (matching the
  gamification/progress pattern). `get_workload_module_context` + `has_upcoming_work` are 1:many ModuleSection
  enumerations that the 1:1-join gate cannot express, so they use a **new co-located
  `published_active_section_conditions()`** in the SAME `section_visibility.py` (one home for the publish/active
  rule; membership stays caller-enforced — both callers already authorise the student's module access). Locked
  by `test_12b_visibility_gate.py` (one per surface). Practically *masked* today (topic-mastery snapshots are
  seed-only), but structurally closed now.
  **Verified-safe (not leaks):** `_section_labels` (lecturer-facing — lecturers legitimately see their own
  unpublished sections) and `list_published_sections_for_student` (route-gated by `require_module_access`).
  ⇒ **F-LAND-1 is now closed** (was "left for owner decision" at Stage 11 landing).
- **Secrets hygiene — PASS.** `.env` + `.env.e2e` are gitignored; `.env` was never committed to history;
  tracked source contains only env-var *names* (`process.env.SUPABASE_SERVICE_ROLE_KEY` in E2E helpers), no
  secret values; the K2Think credential is env-injected only.
- **Auth boundary (Slice 0 / rule 4) — PASS.** Inactive users → 403 (`dependencies.py:38-42`); identity
  re-resolved from the DB every request (mid-session deactivation loses access next request); no local
  password storage (`AppUser` has no password column; Supabase-delegated via admin API); no `/auth/login`
  (backend only validates Supabase JWTs).
- **PII-in-logs (rule 6) — PASS.** `AIRequestLog` stores hashes/metadata only; `debug_text_truncated` is
  `IS_NON_PROD`-gated and never populated from transcript/prompt text; no logger logs raw transcript/student
  speech/prompt text.

## 12b /cso security pass (OWASP Top 10 + STRIDE) — 2026-06-23
Daily mode, 8/10 zero-noise gate, whole app (backend + frontend), parallel hunters across A01–A10 + STRIDE +
LLM/Phase 7 + deps/Phase 3 + CI/Phase 4 + infra/Phase 5 + skills/Phase 8.
**Result: ZERO CRITICAL / ZERO HIGH / ZERO exploitable findings.** The Stage 12a/12b work verified clean.

Verified-safe highlights:
- **A01 / IDOR — clean.** No student route accepts another person's id; every subject-identifying id
  (conversation/message/attempt/entry/plan/goal/recommendation/scope) is owner-pinned (`student_id == caller`)
  with a pinned 404; lecturer analytics gated to active module membership (no cross-module/tenant). Signed-URL
  mint triple-pins module/section/asset + the publish re-check. Vertical escalation blocked (role guards).
- **A03 injection — clean.** SQLAlchemy bound params throughout (the one JSONB `@>` predicate uses a bound
  `:needle` over a server-side UUID); ZERO `subprocess`/`os.system`/`shell=True`; `.ipynb` validated by
  `json.loads` + shape (no notebook exec); no PDF lib invoked; no `eval`/`exec` of model output.
- **A10 SSRF — clean.** Only outbound clients (LLM provider, Supabase) take env-config URLs + hardcoded paths;
  no user-controlled host/protocol is fetched (the asset `url` is an OUTPUT signed URL).
- **A07 / JWT — clean.** Asymmetric ES256/RS256 via JWKS; signature+exp+aud+iss enforced; no `verify=False`,
  no HS256-confusion vector; boot fails on missing JWKS/issuer.
- **A05 — clean.** The 12a catch-all 500 logs server-side only and returns no trace/`str(exc)`/path;
  `FastAPI(debug)` never True; `CORS_ORIGINS` can't synthesize `["*"]` (default localhost).
- **Phase 7 LLM — clean.** NO system-role prompt and NO tool schema — one user-message completion, so untrusted
  input is structurally confined to the data position (precedent-excluded); homework adds explicit BEGIN/END
  UNTRUSTED fences; `groundingStatus` is server-derived (`decide_grounding`), never parsed from prose; LLM
  output renders via react-markdown with raw-HTML OFF + `disallowedElements` (no XSS); the limiter bounds cost.
- **A02 crypto — clean.** No weak crypto on a security boundary; `random` only for seeded shuffle + backoff
  jitter; UUIDv7 ids, SHA-256 content hashes.
- **Phase 4 CI — N/A** (no `.github/workflows`). **Phase 8 skills — N/A** (no repo-local skills).
- Secrets / auth-boundary / PII-in-logs — PASS (audited earlier this session).

Findings (all LOW hardening / latent debt; rule-13 dispositions):
| # | Finding | Sev | Disposition (rule 13) |
|---|---|---|---|
| 1 | Both Docker images run as root (no `USER`); current images are **dev** (frontend runs `npm run dev`) | LOW | **Deferred → 12f** production-candidate build (non-root `USER` + production frontend `next build/start`); go-live checklist |
| 2 | No `.dockerignore` (`COPY . .`); `.env` confirmed **not** copied (it lives at repo root, outside both build contexts) | LOW | **Deferred → 12f** production-candidate build |
| 3 | `allow_credentials=True` with pure Bearer auth (no cookies) — roadmap 4.9 debt | LOW | **Deferred → 12f** (drop when finalizing production CORS; verify against the cross-origin Playwright gate). Harmless today (origins never wildcard) |
| 4 | No CSP / HSTS / security headers on the frontend (only `nosniff` on downloads) | LOW→MED | **Deferred → 12f** (Next.js `headers()` CSP/HSTS + backend security headers in the production-candidate build/deploy config) |
| 5 | Next.js `15.3.3` behind (`npm audit`: 1 critical + 1 moderate, **all in UNUSED features** — no `next/image`, no middleware, no Server Actions → not reachable) | LOW/INFO | **Deferred-with-owner** — bump in a dep pass / 12f, verify against the full suite. Latent, not currently exploitable |

Minor nit (accepted): a few lecturer/workload ownership-failure paths return **403** rather than the pinned
**404** — a weak enumeration oracle, no data exposure (id is fully owner-checked). Accepted as-is, consistent
with the code-asymmetry decision above.

**No code changes from /cso** (zero exploitable findings; the LOW items belong in the 12f production-candidate
build). **12f must pick up items 1–4** (production Dockerfile non-root + `.dockerignore`, CORS finalize,
security headers); **item 5** is a tracked dep-bump.

## 12b /review + /codex pre-landing review (2026-06-23/24)
Two independent Claude review agents (adversarial + correctness) + a Codex (gpt-5.5) cross-model pass on the
full diff. **No correctness/security bugs found in the core 12a/12b code** — the analytics gate refactor is
provably behavior-preserving (the `CourseMembership` active join is 1:1 via the partial-unique index, so no
fan-out; the extra gate predicates are no-ops on the real path), the error envelope/request-id/`can_publish`
changes are sound, the new tests are non-vacuous. Findings + dispositions:
- **FIXED (review-driven, my code):** (1) `production_hygiene.py` now **requires `LLM_PROVIDER=k2think`** — it
  previously only forbade the explicit `deterministic` value, but the config default is `deterministic` with
  NO boot guard (unlike `EMBEDDING_PROVIDER`), so an unset `LLM_PROVIDER` in prod would serve the test adapter
  to real users and pass hygiene. (2) `request_id.py` now **validates the incoming `X-Request-ID`**
  (`^[A-Za-z0-9._-]{1,128}$`, else generate) — blocks CRLF/oversize/forged reflection. Both with new tests;
  backend **836 passed**.
- **Deferred → 12f (valid, but 12f scope):** Codex's High finding — the hygiene script is built + tested but
  **not yet wired into a build/deploy path**. That wiring is the 12f production-candidate build + deploy
  procedure (`python -m app.platform.production_hygiene` before image build / boot); wiring it into the
  current *dev* Dockerfile would wrongly fail dev builds (`LLM_PROVIDER=deterministic`). Added to the 12f list.
- **Deferred → 12f (pre-existing, flagged):** cross-origin **500s lack CORS headers** (Starlette's
  `ServerErrorMiddleware` is always outermost, so a cross-origin SPA can't read the 500 envelope/`request_id`).
  NOT a regression (500s were already CORS-less); the fix is a deliberate CORS-aware-500 design choice, best
  done with the cross-origin E2E in 12f.
- **Acknowledged, no change:** `errors.py` carries a `str` `detail` straight into `error.code` — intentional
  (preserves the domain CODE constants `CONTENT_FORBIDDEN`/…; the proposed `HTTP_<status>` fix would lose them;
  only framework/ad-hoc human-string details get sentence-codes, which is benign + pre-existing).

## 12f-deferred items collected (for the 12f spec / go-live)
From /cso (5) + /review-codex (2): non-root Docker `USER`, `.dockerignore`, drop `allow_credentials=True`,
CSP/HSTS headers, Next.js dep bump, **wire `production_hygiene` into the prod build/deploy**, **CORS-aware 500
handling** (so the error envelope reaches cross-origin SPAs). + the D-12-C course-deletion mechanism.

## Migration head correction (found running the E2E migration, 2026-06-23)
The kickoff "single head `0082`" was a static-trace miss. The **true single Alembic head is `0059`** — `0082`
is the intermediate merge node (`0044`+`0081`), and Stage 11's `0056→0057→0058→0059` chains *after* it
(`alembic upgrade head` → `0059 (head)`, single head confirmed). Stage 12's reserved block `0083–0095` chains
after `0059` when a migration is needed; 12a/12b add none.

## 12a/12b full Playwright gate (rule 14) — run 2026-06-23 on the owner `.env.e2e` stack
Local Supabase (`host.docker.internal:54321`, real MiniLM embeddings, deterministic LLM), serial `--workers=1`,
28 specs, app DB migrated to head `0059` + standing fixtures seeded. **The gate caught one real bug, now
fixed:** the E2E copy of the Stage 4.7 byte-identical-404 (S2) assertion (`4.7-student-summaries.spec.ts:299`)
broke on the new `error.request_id` — fixed to compare modulo the resource-independent id (the backend pytest
copy was already fixed; this E2E copy was missed). **Every spec passes on a non-saturated VM** (run 1, 7.8m:
33 passed incl. 11.6 + 5.5e; the only failures were the now-fixed 4.7 + a gamification login flake that passes
on retry). Across 4 runs the suite time degraded 7.8m → 25.5m as the shared 7.7 GiB Docker VM saturated,
tipping the two slowest specs (11.6 grade-forecast, 5.5e schedule-UI — both 3-min) over their 180s test
timeout; neither touches 12a/12b code and both pass on a fresh VM. **Two test-harness fixes from the run**
(not product code): `4.7-student-summaries.spec.ts` (S2 modulo-`request_id`) and `seed.mjs` (paginate
`listAuthUsers` past the local project's 1000+ accumulated auth users). **Definitive single-pass 35/35 needs a
fresh VM** — to be confirmed on the owner's merge-time gate run (the env degraded under repeated local runs).

## Still TODO in 12b (owner gate)
- Commit + PR; **owner reviews the staged commits and merges** (agent never merges). The owner re-runs the
  definitive single-pass Playwright on a fresh VM (gate note above).

## 12a implementation discoveries (rule 10 — surfaced during build, full detail in the 12a report)
- **Per-gate denial-code asymmetry — RESOLVED: accepted as-is (owner, 2026-06-23).** For an unassigned
  lecturer, asset upload/replace (`authorize_lecturer_section`) returns **403** "Lecturer is not assigned to
  module", whereas publish/notes/metadata/transcripts return **404 `SECTION_NOT_FOUND`** (`test_content.py:625`
  403 vs `:1198` 404). **Owner decision:** accepted as-is — the UI never exposes unassigned modules to
  non-members, so the scenario is UI-impossible (API-bypass-only edge case); the 403-vs-404 distinction is not
  a meaningful info-hiding gap at single-university MVP scale. **No code change to either path.**
- **Byte-identical-404 (S2) × request_id.** The per-request `request_id` makes error bodies non-byte-
  identical, so the Stage 4.7 S2 test (`test_student_summaries.py:707`) was updated to compare the three
  404s modulo `error.request_id` (resource-independent → leaks no existence signal). The guarantee holds in
  substance. Owner-visible because it touches a prior gate's assertion.
- **Existing negative-authz coverage is already broad** (asset-upload 623-626, metadata 1196-1201,
  publish/notes 1842-1938, transcript upload 418-420, retry 491-506, summaries 1294-1318). 12a added only
  the genuine gaps (unpublish boundary) + the 12a-specific envelope-on-authz proof, rather than duplicating.

## Owner-policy decisions — ALL RESOLVED (2026-06-23)
- **D-12-B** — signed-URL cutoff: **RESOLVED — accept the current 5-min (`SIGNED_READ_URL_TTL_SECONDS=300`)
  window** with written rationale; the mint already blocks future minting (see the resolved contradiction
  above). **ADR-062.**
- **D-12-C** — recording/transcript retention: **RESOLVED — course-lifetime retention.** Material is kept
  while the `course_modules` row exists; deleting the course cascade-deletes all associated material
  (recordings/transcripts/summaries/assets). Rationale: students revise after the course ends, so retention
  tracks the course lifecycle. Backup-retention alignment: course deletion removes primary data immediately;
  the bounded managed-PG / object-store backup window is the documented residual retention (12f). Mechanism
  **deferred-with-owner to go-live** (seed-only data now) → go-live checklist. **ADR-063.**
- **Code-asymmetry (403↔404)** — **RESOLVED — accepted as-is** (see the per-gate denial-code asymmetry
  finding above): UI-impossible scenario, immaterial at MVP scale. No code change.

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- 12a spec: [[specs/stage-12/12a-api-boundary-hardening]]
- 12a plan: [[plans/stage-12/12a-api-boundary-hardening]]
