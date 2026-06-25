---
type: findings
stage: 12
created: 2026-06-23
updated: 2026-06-24
---

# Stage 12 — Findings & spec/reality reconciliations (rule 10)

> The Stage 12 v1.2 spec states (its §2) that all concrete repo values in it are "starting points to
> confirm, not facts." This note records what was confirmed against the live repo at kickoff, and every
> place the spec's literal text diverges from the code/established invariants. Per the sacred rule
> (AGENTS.md), **code wins**; divergences are reconciled here so they can't resurface in a later review.

## Verified kickoff facts (confirmed against the live repo, 2026-06-23)

| Fact | Confirmed value | Source |
|---|---|---|
| Alembic head — single? | **Yes, single head `0059`** — `0082` is the *intermediate* merge node (`0044`+`0081`), after which Stage 11 chains `0056→0057→0058→0059` | head = `0059_student_forecast_advice.py`; `0082_merge_stage10_stage86_heads.py` (`down_revision=("0044","0081")`) is the merge node, **not** the head; only `0001` has `down_revision=None`. **Corrected in 12c** — the kickoff "single head `0082`" was a static-trace miss (see "Migration head correction" and the 12c migration round-trip below). |
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
No migration needed (head stays 0059).

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
handling** (so the error envelope reaches cross-origin SPAs), **e2e CORS allowlist omits `:3001`** (F-12C-CORS,
below — joins the CORS-finalize cluster), **LLM model-id config reconciliation** (`LLM_DETAILED_MODEL_ID`
versus prompt/deployment `K2-Think-v2`, owner = product owner). + the D-12-C course-deletion mechanism
(F-12C-CASCADE, below).

**12f-deferred, owner = product owner — both of this stage's `F-12C-*` findings:** **F-12C-CORS** (committed
CORS/frontend-port config consistency + the cross-origin Playwright gate) and **F-12C-CASCADE** (the go-live
course-deletion mechanism: core-spine FK cascade migration vs. app-level ordered delete). The product owner
scopes both when 12f lands; neither is a today-defect or a 12c/12d code change.

### F-12C-CORS — committed CORS allowlist omits the stack's own frontend origin `:3001` (found in the 12c/12d merge-time full-suite run, 2026-06-25)
**Surfaced by the owner merge-time gate (rule 14), not a Stage-12 regression** (`git diff origin/main…HEAD` =
no code changes; these gates pass on `main`). Recording it because it is a committed-config defect of the
**"green locally, wrong in the tree"** class — a local `.env` fix turns the run green but leaves the wrong
config shipped.

- **Symptom.** On a fresh clean stack (`.env` = `cp .env.example .env`), every student-facing spec failed at
  login: the browser CORS preflight `OPTIONS /me` from origin `http://localhost:3001` returned **400**, so the
  real `GET /me` never fired and each login bounced back to `/login` (`expect(page).toHaveURL(/\/student$/)`
  timed out ~11s). Direct proof: preflight `Origin: http://localhost:3001` → **400**, `:3000` → **200**.
- **Root cause (committed inconsistency).** The committed stack's browser origin is **`:3001`** —
  `docker-compose.yml:91` maps the frontend `"3001:3000"` in the **base** file (not the e2e overlay). But the
  committed CORS default is **`:3000`-only**: `CORS_ORIGINS` is sourced *solely* from `.env.example:20`
  (`CORS_ORIGINS=http://localhost:3000`) → copied to the gitignored `.env`; neither `docker-compose.e2e.yml`
  nor `.env.e2e` overrides it, and `main.py:33` feeds it straight into `allow_origins`. So `cp .env.example .env`
  + the committed compose port = guaranteed preflight failure for **any** local/e2e run on this compose.
- **Local-only workaround used for this run (NOT committed; `.env` is gitignored).** `.env` `CORS_ORIGINS`
  set to `http://localhost:3000,http://localhost:3001`, backend recreated → preflight 200, suite green. The
  committed defect remains; the override is intentionally not in the tree.
- **Proper fix = 12f (committed config, not a runtime-only patch).** Because the `:3001` host port lives in
  the **base** compose, an e2e-overlay-only `CORS_ORIGINS` override is *insufficient* — a plain
  `docker compose up` would still serve `:3001` and reject it. 12f must make the committed default and the
  committed frontend port **agree**; owner picks which side moves:
  - **Preferred — correct `.env.example`** so `CORS_ORIGINS` matches the committed frontend host port (add
    `http://localhost:3001`; keep `:3000` only if a `:3000` surface still exists). One line, fixes base + e2e.
  - **Or reconcile the port instead** — the `3001:3000` mapping carries "gate-standup local change" lineage
    (sibling-port-collision avoidance); if `:3000` is the intended canonical frontend port, restore the
    mapping to `3000:3000` and leave CORS at `:3000`.
  - **Runtime origins list** (backend defaults to localhost dev/e2e ports when `CORS_ORIGINS` unset) is
    acceptable as defense-in-depth but is **not** a substitute for the committed-config agreement above.
  Verify against 12f's cross-origin Playwright gate (the same gate the existing CORS-finalize items defer to).
- **Disposition.** 12f-deferred item; **owner = product owner** (scopes the committed-config fix + the
  cross-origin gate when 12f lands). Listed in the 12f-deferred-items collection above.

### Run-procedure lesson — source `.env.e2e` into the Playwright runner (not a code defect; recorded for the next runner, 2026-06-25)
Captured here per the owner's bookkeeping note because it is **not** clearly recorded against the Stage-8.6b
requirement (the 8.6a/8.6b handoff frames `.env.e2e` only as a *seed* prerequisite). Also folded into the
canonical runbook `knowledge/steps/e2e-run-procedure.md` (where the next runner looks).
- **The Playwright runner process must have `.env.e2e` sourced into its env** (`set -a; . ./.env.e2e; set +a`
  before `npx playwright test`). Most specs read `.env.e2e` from file themselves, but a few — notably
  `7-glossary` — read `SUPABASE_SERVICE_ROLE_KEY` from `process.env` and POST to Supabase admin from the host.
  Unset → `401 no_authorization` on `/auth/v1/admin/users` → a ~17 ms `expect(authId,'… auth id').toBeTruthy()`
  fail. This is the Stage-8.6b "load `.env.e2e` into Playwright for Supabase Admin calls" requirement made
  explicit. `seed.mjs` reads the file directly, so seeding succeeds and hides the gap — it only bites the runner.
- **Companion run-procedure facts** (same 2026-06-25 run; full detail in the runbook): run on host **`:3001`**
  (`PLAYWRIGHT_BASE_URL=http://localhost:3001`); use a genuinely **fresh DB per full-suite run** (`down -v` →
  up → `alembic upgrade head` → seed → run) because `seed.mjs` does not truncate Stage 10/11 derived tables
  (streaks/badges/forecast), so a re-run on a used DB fails `10-gamification` A/D and `11.6`.
- **Result.** With all three applied, the full active Playwright suite ran **35/35 green** (single pass, fresh
  clean stack, head `0059`, run id `e2e-montpellier-stage12-fullrun`, 7.3m) — the owner merge-time rule-14 gate
  for 12c/12d. No product-code defect surfaced (`git diff origin/main…HEAD` empty).

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

## 12c / 12d session — verification & reconciliation (2026-06-24)

**Migration chain (12c) — VERIFIED.** Single Alembic head **`0059`** (43 revisions, no dup IDs; `0082` is the
intermediate merge node). Fresh-DB `upgrade → base → upgrade` round-trip **GREEN** in Docker (default
`xyz_lms`, fresh volume): `alembic heads` = `0059 (head)`; current after upgrade = `0059`, after downgrade =
empty, after re-upgrade = `0059`. No orphaned/duplicate revisions; every migration downgrades cleanly. The
kickoff "single head `0082`" doc-correction is folded into the kickoff table (`:19`) + `:73` and the 12a spec
(`:59`) — narrow scope (owner D2=A); append-only `log.md` and prior-stage `STATUS.md`/`roadmap.md:72`/`8.6d`
left as historical record.

**Workers / scheduler / limiter / reconciliation / logging (12c) — VERIFIED** (code review + **79 targeted
tests passed**: limiter, recovery, scheduler, worker, startup-recovery, error-envelope). Real queue topology
is `ingestion`/`embedding`/`ai` (no `agent` queue; AgentRun runs on `ingestion`). The Stage 11 AgentRun
"committed-but-never-enqueued, no retry" gap stays **closed** (both call sites — scheduler `service.py:56`,
manual API `analytics.py:51` — use the idempotent `enqueue_run_agent_if_needed`; next-tick reconciliation
re-enqueues a stranded `queued` run). The 4.6 reaper covers `uploaded`/`parsing`/`queued` (+ quiz/pool
`generating`). Limiter budgets confirmed from live config: 20 Cerebras / 10 Nvidia RPM, 100k/105k TPM,
concurrency 10, 20% interactive headroom. Reconciliation: report-only default, prefix-scoped, deletion-capped
(50), superseded retained, missing-refs reported-not-fixed. Logging passes all 3 criteria (ERROR+`request_id`
on the unhandled path; no PII — hashes only; stdout, no aggregation stack).

**AIRequestLog cost review (12c) — DONE.** "Tokens by feature by day" query authored (index-backed
`ix_ai_request_logs_feature_created_at`), runs, returns a result (0 rows on the current seed-only DB; correct
per-feature/day aggregation confirmed on a rolled-back illustrative dataset). Sanity vs IFM budgets:
`summary_detailed` heaviest (~15–16.5k tokens/call, matching rule 15's ~13–18k; ~6 calls/min before the 105k
Nvidia TPM binds); one call per summary/quiz; **no feature unexpectedly expensive.**

**D-12-C / ADR-063 reconciliation (12d).** D-12-C was already recorded as **`adr-063`** (`accepted`,
`related-session: "12d"`, pre-written during 12b's owner-policy resolution). Owner decision **D1=A**: accept
adr-063, **create no new ADR — `064` remains next-free**. Verified against reality (not the `accepted` label):
**Check 1** (ADR text states all four required points: course-lifetime retention; course-deletion-deletes-all;
bounded backup-retention alignment; mechanism-deferred-to-go-live) **PASS**; **Check 2** (the "deleting a
course deletes all material" claim vs live code) **PASS — verdict (a): no course-deletion path exists yet**
(no `DELETE /modules/{id}`; only `admin.py:192` removes a membership; course-row deletes only in
`dev_reseed.py:278-308` teardown), consistent with the deferred mechanism.

**F-12C-CASCADE (12c/12d, rule 13 — flagged for go-live, NOT a today-defect).** adr-063's *Consequences* "the
DB half is FK-cascade from `course_modules`" overstates today's schema. The core content spine —
`module_sections→course_modules`, `transcripts→module_sections`, `section_assets→module_sections`,
`course_memberships→course_modules` — is `NO ACTION` (`0002_db_spine.py`, `0004_transcripts.py`); only the
Stage 9–11 tables cascade from `course_modules`. Nothing orphans today (no delete path), so **no schema change
in 12c/12d**. **Disposition (12f-deferred item; owner = product owner):** the deferred go-live deletion mechanism must use **either** a cascade migration
on the core-spine FKs (owner-assigned migration block at go-live) **or** an app-level ordered delete (the
`dev_reseed` pattern) + loss-safe, prefix-scoped object-store cleanup (reuse the 4.6 reconciliation patterns).
**Amended (owner-approved, 2026-06-24):** adr-063's *Consequences* DB-half line now states the accurate FK
state — Stage 9–11 tables cascade from `course_modules`; the core content spine
(`module_sections`/`transcripts`/`section_assets`/`course_memberships`) is currently `NO ACTION`; the go-live
deletion mechanism requires **either** a cascade migration on the core-spine FKs (owner-assigned block) **or**
an app-level ordered delete (`dev_reseed` pattern) + object-store cleanup. The original "the DB half is
FK-cascade from `course_modules`" overstated the schema. Everything else in adr-063 is unchanged.

## §7 go-live closeout note (carried to 12f's `docs/go-live-checklist.md`)
**Enable the course-deletion retention mechanism before any real-student data** — owner = product owner;
honor adr-063 (D-12-C); scope per F-12C-CASCADE above. Seed-only today (no hosting), so deferred-with-owner;
this note keeps it tracked until 12f builds the go-live checklist (joins the §7 deferred list — master spec
§7 item 7 + the 12f-deferred-items list above).

## 12e session — load & performance check (2026-06-25)

**Measure-and-verify; test-only.** The only code is `backend/tests/test_12e_load_perf.py` (a pytest harness).
**No product code, no migration (head stays `0059`), no new ADR (`064` stays next-free).** Roadmap status NOT
flipped (Stage 12 closes at 12f). Full report: [[steps/stage-12/12e-load-performance-check]].

**Confirm-don't-assume re-verified live:** `alembic heads` = **`0059 (head)`** (single, in-container);
limiter budgets pinned by a test to the rule-15 values (**20/10 RPM, 100k/105k TPM, conc 10, 20% headroom**);
queues `ingestion`/`embedding`/`ai` (AgentRun on `ingestion`); next-free ADR **`064`**; no migration.

**Step 0 — student wait-state: EXISTS, not built.** A clear "generating" state already ships
(`QuizAttemptPanel.tsx:175-189` "Generating your quiz." + bounded polling; exam-prep 3-state CTA
`StudentQuizModesPanel.tsx:435-455`). 12e asserts it holds under contention; **no UI added, no finding** (load
did not break it).

**(A) limiter queues an exam-week peak — GREEN.** Real `RedisRateLimiter` + deterministic provider
**explicitly injected** (else `gateway.py:325-329` bypasses the limiter) + injected `to_thread` send latency.
Measured at N=16 concurrent pool generations / background budget 4: **peak in-flight = 4** (never exceeded the
budget), **35 total backoffs** (queued calls waited then proceeded — `AIRequestLog.rate_limit_backoff_count`),
**16/16 `ready`, 0 `failed`** (no error / deadlock / lost request; run drains). Wait-state edge proven: a
contended `start_pooled_attempt` stays `generating` then `try_assemble_attempt_async` resolves it.

**(B1) D1 pre-warm invariant — GREEN.** Real `prewarm_scope_pools` → `ready` pool; warm-section start serves
with **no new generation enqueued** (no ~264s cold wait); cold section's first start enqueues the job. The
F-6e load-bearing invariant holds.

**(D) rule-14 full Playwright — RAN GREEN (2026-06-25, owner `.env.e2e` stack, head `0059`).** Fresh clean
stack on `:8000`/`:3001` (stopped the sibling `montpellier` stack to free the ports), run id
`e2e-stockholm-12e-1782380955`: **34 passed / 1 failed single-pass; the 1 confirmed a flake → effective
35/35.** The failure was the documented `10-gamification` Scenario-A login-redirect flake (`signIn` timed out
at `/login`; B/C/D passed same helper) — passed in 4.9s on `--last-failed`. **Not a 12e regression**
(test-only). (Fresh-workspace note: `npm install` + chromium were needed; `node_modules` was absent so `npx`
had grabbed a mismatched temp Playwright.)

**(C) `/benchmark` CWV baseline — RECORDED (2026-06-25).** gstack browse daemon, authenticated student, three
key pages. LCP 260–312 ms / CLS 0–0.021 / FCP 40–56 ms (all **good**); full load ≤ 265 ms. JS ~5–6 MB is the
**dev build** (`npm run dev`) — re-baseline on the production frontend (12f). Table in the report.

**(B2) provider-only real-call smoke — PASS (2026-06-25, real `api.k2think.ai`).** Owner supplied the real key
in `.env`; ran `backend/scripts/gate3_quiz_pool_smoke.py`. **Owner-approved amendment after pre-landing
review:** B2 is intentionally a provider-only rule-11 confirmation (model echo + clean parseable
`GeneratedQuizPool`), not a duplicate DB-backed pre-warm proof. The DB-backed
`prewarm_scope_pools -> ready -> warm start/no cold wait` proof lives in **B1** above; B1+B2 together
discharge the invariant at single-course MVP scale. **Rule 11 OK:** echo `MBZUAI-IFM/K2-Think-v2` == expected
(the prompt-declared model), attempt 1, **247.6s** (< 330s), `finish_reason=stop`, 16-question pool.
Model-id reconciliation is tracked for **12f**: `.env` `LLM_DETAILED_MODEL_ID=K2-Think-v0` differs from the
prompt/deployment id `K2-Think-v2` (feeds the pool-identity tuple, not the rule-11 echo). Owner disposition:
not a 12e defect; product owner aligns `.env`/prompt/deployment model ids in 12f.
[[steps/stage-12/12e-real-provider-smoke]].

**Decisions/observations (no defect, no ADR):**
- (A) driver = service-level `generate_section_pool_async` (owner-approved Q1 default).
- Binding dimension = **concurrency** (rpm/tpm set ample) so the queue drains in ~1s as leases release. rpm/tpm
  are **window-based** (free only as the 60s window slides); sustained saturation beyond
  `LLM_RATE_LIMIT_MAX_ELAPSED_MS` (default 30s) terminates as `rate_limited` → pool `failed` (bounded failure +
  retry affordance, not an infinite spinner). Recorded; not 60s-load-tested by choice.
- **Limiter is bypassed for a non-injected deterministic provider** (`gateway.py:325-329`) — so normal
  deterministic CI/E2E never exercises the Redis limiter; only an injected-provider harness does. Not a defect
  (keeps CI off Redis); recorded as a testing-boundary note; owner declined to formalize as an ADR.
- **No new bottleneck found** ⇒ no ADR-justified addition (scale discipline); no prior-stage code modified.

**Owner flag dispositions (confirmed 2026-06-25, rule 13):**
1. **Limiter bypassed for a non-injected deterministic provider** (`gateway.py:325-329`) → **testing-boundary
   note, NO ADR.** By-design (it keeps normal CI/E2E runs off Redis); now documented here and in the 12e
   report. **ADR `064` stays free.** Disposition: accepted / by-design / documented.
2. **Window-based rpm/tpm saturation terminating as a bounded `rate_limited` past ~30s**
   (`LLM_RATE_LIMIT_MAX_ELAPSED_MS`) → **accepted as-is.** The bounded failure + retry affordance is the
   correct behavior; a **60s sustained-overload test is NOT required** at single-course MVP scale.
   Disposition: accepted with written rationale (rule 13).
3. **B2 provider-only smoke vs DB-backed pre-warm proof** → **accepted with owner approval.** B1 proves the
   DB-backed `prewarm_scope_pools -> ready -> warm start/no cold wait` mechanics; B2 proves the real K2Think
   provider returns a clean `GeneratedQuizPool` with the prompt-model echo. No new combined real-provider DB
   run required at MVP scale. Disposition: accepted with written rationale.

**Pre-merge review (`/review` + `/codex`).** Claude adversarial = ship-as-is (limiter proof sound,
assertions non-vacuous). Codex caught 2 real test-quality issues, both **fixed** test-only: (1) the
`redis_client` fixture **skipped** when Redis was down → an acceptance proof could go green without running
the limiter check → now **fails loudly** (Redis required, matches plan Q3); (2) `latency_s` timing-sensitive
→ lease hold raised to `0.15s` so peak saturation + backoff are deterministic. Re-verified 4/4 baked; full
backend suite **852 passed**. Detail in [[steps/stage-12/12e-load-performance-check]].

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- 12a spec: [[specs/stage-12/12a-api-boundary-hardening]]
- 12a plan: [[plans/stage-12/12a-api-boundary-hardening]]
- 12c spec / report: [[specs/stage-12/12c-data-workers-capacity-review]] · [[steps/stage-12/12c-data-workers-capacity-review]]
- 12d spec / report: [[specs/stage-12/12d-privacy-data-retention]] · [[steps/stage-12/12d-privacy-data-retention]]
- 12e spec / plan / report: [[specs/stage-12/12e-load-performance-check]] · [[plans/stage-12/12e-load-performance-check]] · [[steps/stage-12/12e-load-performance-check]]
- 12e real-provider smoke (B2, owner-run): [[steps/stage-12/12e-real-provider-smoke]]
- D-12-C decision: [[decisions/adr-063-course-lifetime-retention]]
