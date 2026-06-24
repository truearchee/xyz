---
type: stage-spec
stage: 12
slug: release-hardening
status: approved
created: 2026-06-22
updated: 2026-06-23
owner: developer
source: .context/attachments/eGLCyy/pasted_text_2026-06-22_20-03-00.txt
---

> **Filed verbatim** from the owner's approved Stage 12 v1.2 spec (source above), preserving all content.
> Stage 12 is worked one sub-session at a time (12a → 12f); each sub-session gets its own focused spec +
> plan + report trio referencing this master. See [[plans/stage-12/12a-api-boundary-hardening]] and the
> kickoff findings [[steps/findings-12]].

# Stage 12 — Release Hardening — Implementation Spec

> **Version:** v1.2 (revised). **For the coding agent.** This is the final stage of the XYZ LMS MVP.
> No new user-facing features. Every unit of work is either *audit → fix* or *decide → document (ADR)*.
> Break it into sub-sessions (12a, 12b, …) and work them one at a time, as usual.

---

## 0. Changes in this revision

> Reviewable diff. All additions are **scale-appropriate** — none introduces a stack, autoscaling, or a
> CI/CD build-out. Each new item carries its own "this is a checkbox/paragraph, not a platform" guardrail.

### v1.2 (this revision)

1. **Smoke timing / real-provider stability (NEW — 12f(b), gate, §8).** v1.1 gated the full browser
   smoke on the **real** K2Think provider, but the quiz/assistant steps hit real generation that is slow
   by design (reasoning route to a 330s timeout; cold quiz pool adds the ~264s-class first-wait per
   Stage 6). Left on the real provider with ordinary timeouts, the smoke can **false-fail** on a
   slow-but-correct generation. v1.2 forces an explicit choice: **(i)** pre-warm + Stage-6-equivalent
   timeouts on the real provider, or **(ii)** run the browser path on the deterministic adapter and
   satisfy rule 11 with a separate focused real-provider smoke (the pattern every prior AI stage used).
   §6 is kept intact under either choice.
2. **Secrets example corrected (12b).** v1.1 attached the `sb_secret_…` format to the **K2Think** key.
   That format is a **Supabase** key; the K2Think/IFM credential is a **Bearer token** to
   `api.k2think.ai` and does not look like `sb_secret_…`. The "no secrets in repo or history"
   requirement is unchanged — it covers all key types — only the example was wrong.
3. **Repo-specific values flagged as confirm-not-assume (§2).** v1.1 introduced concrete repo details
   (ADR-056/057 collision, migration chain `0041 → 0080/0081` and `0033 → 0043`, key formats). These
   are **starting points to verify against the live repo, not asserted facts.** The spec already says
   "confirm the actual head / next free number"; v1.2 states the principle once, globally, so a stale or
   mistaken number is never acted on as truth.

### v1.1

1. **Backups & restore (12f, §7, §8).** v1 covered *deliberate* deletion (12d) but had no story for
   *accidental* loss or corruption. Added managed-Postgres automated backups + object-storage durability
   posture + a documented restore drill. Pairs with — and is bounded by — the D-12-C retention ADR (you
   cannot promise "deleted at end of course" if backups silently retain it).
2. **Rollback / back-out (12f, go-live checklist).** v1's deploy procedure stood things up but had no
   documented back-out, especially for a bad release-phase migration. Added a short rollback section and
   an "if `/canary` fails" branch.
3. **12e load methodology made concrete.** Added: limiter/queueing tested against the deterministic
   adapter with injected latency (don't burn real budget proving mechanics) + a *small* real-provider
   confirmation of the pre-warm invariant + an explicit latency/error pass envelope.
4. **Health checks defined as real readiness checks (12f).** "Responds" → must verify DB + Redis
   reachability (readiness), not a static 200. Liveness vs readiness split, scale-appropriately.
5. **D-12-B / D-12-C surfaced at stage kickoff** (was "early in 12b / early in 12d"). The *ask* moves to
   the front so the owner has max lead time; the dependent *implementation* still waits for the lock.
6. **`request_id` echoed in a response header on every response (12a)**, not only in error bodies.
7. **Build-hygiene check: resolved the "fail the build/CI" wording (12b).** Stage 12 builds no CI, so it
   is a build-time assertion (a script that exits non-zero on violation) that *slots into* CI later.
8. **Logging review given concrete pass criteria (12c)** — three explicit conditions.
9. **Secrets-not-in-repo made an explicit 12b check** (incl. git history).
10. **ADR-number collision flag (§3).**
11. **12f smoke seed-vs-live boundary tightened.**

---

## 1. Context & framing

All feature stages (through Stage 11) are merged to `main`. The objective of Stage 12 is a
**production-candidate**: an MVP that is hardened, fully smoke-tested, and **deploy-ready**, at the
scale the MVP actually targets — a single university course, tens of concurrent students, **not**
enterprise scale.

**Deployment status (locked decision D-12-A):** No hosted environment exists yet. **Stage 4.8**
(first hosted deploy) and **Stage 8.3** (SSE streaming) remain **blocked on an external university
hosting decision** and are out of Stage 12's executable scope. Therefore Stage 12 closes the MVP as
*deploy-ready and verified on a production-candidate build* — **not** as live-in-production. The
actual go-live is a tracked deferred item (see §7). Stage 12 absorbs the **deploy-preparation**
deliverables originally parked in 4.8 (repeatable deploy procedure, release-phase migration step,
managed-Postgres extension bootstrap, production-build hygiene) so they are ready the moment hosting
lands.

**Scale discipline (read this first).** Stage 12 is *scale-appropriate* hardening. It explicitly does
**not** build autoscaling, CDN, multi-region, a full observability platform, or a CI/CD system for MVP
launch. "Observability" here means a *logging review*, not a stack. "Backups" means *enabling managed
backups and writing down the restore steps*, not a DR program. "Rollback" means *a documented back-out
paragraph*, not blue/green. If a load check (12e) surfaces a real bottleneck, that becomes a specific,
justified addition recorded as an ADR — never a blanket build-out. When in doubt, prefer "verify and
document" over "build."

---

## 2. Standing rules for this stage (all carry from `knowledge/roadmap.md`)

- **The product owner merges. The agent never merges.** Each sub-session is delivered as a branch +
  PR with all gates green and an independent review attached; the product owner performs the merge.
- **Independent pre-merge review is mandatory for every code change** (not only audits). Run
  `/review` (this session-family) **and** `/codex` (OpenAI CLI, fresh session) on every sub-session
  that changes code. This gate has repeatedly caught bugs the test suite missed; it is non-negotiable.
- **Rule 14 — full active Playwright suite green at every sub-session close.** Inherited green from a
  prior report is not green.
- **Rule 13 — every finding resolves as** fixed-now / deferred-to-named-owner /
  accepted-with-written-rationale / rejected-with-explanation. Unresolved findings block FULLY VERIFIED.
- **Rule 12 — knowledge files and the roadmap status table update in the same commit** that closes the
  stage.
- **Rule 11 — real-provider smoke** where an AI path is exercised end-to-end (12f), asserting the echoed
  model ID matches the configured identifier. (See the 12f smoke-timing decision for *how* this is
  satisfied without making the browser gate flaky.)
- **Rule 10 — stop and escalate.** If audit reality disagrees with this spec, write a findings note to
  `knowledge/steps/findings-12.md` and surface it to the product owner. Do not paper over a surprise
  with a workaround that "makes the test pass" — that usually hides the exact problem the gate exists
  to find.
- **Rule 6 — AI stays behind the LLMGateway boundary; AIRequestLog stores hashes/metadata, never raw
  transcript or student speech.** (Verified in 12b.)
- **Repo-specific values in this spec are starting points, not facts (v1.2).** Any concrete repo detail
  written here — ADR numbers (e.g. the ADR-056/057 collision), migration revisions (e.g. `0041`,
  `0080/0081`, `0033 → 0043`), file paths, key formats — is a **hint to confirm against the live repo**,
  not an asserted truth. Read the code, confirm the real value, and treat a mismatch as a finding
  (rule 10). Never allocate an ADR number, pin a migration head, or edit a file on the strength of a
  number quoted in this document alone.
- **Decisions become numbered ADRs.**
- **Single Alembic head.** If any sub-session adds a migration, continue the chain from `main`'s
  current head; the product owner confirms a single head after each merge.
- **One logical change per commit.**
- **Use `/careful` for destructive work** (the retention/deletion mechanism in 12d, the authz change in
  12a, and any rollback rehearsal that runs a migration `downgrade`). It warns before `rm -rf`,
  `DROP TABLE`, force-push, and `git reset --hard`. This is release-critical code; safety guardrails
  are cheap insurance.

---

## 3. Decisions to confirm with the product owner

> **Timing (v1.1):** surface **D-12-B and D-12-C at Stage 12 kickoff** — before or alongside 12a — not
> "early in 12b / early in 12d." These are owner/policy calls with no code dependency to *raise* them;
> raising both up front gives the owner maximum lead time. Only the dependent *implementation* waits for
> each lock (the signed-URL piece of 12b on D-12-B; 12d on D-12-C).

| ID | Decision | Status | Notes |
|----|----------|--------|-------|
| **D-12-A** | Deployment target | **RESOLVED** — no hosted environment yet | Stage 12 uses the deploy-ready / local-production-candidate form of 12f; real go-live is deferred-with-owner (§7). |
| **D-12-B** | Unpublish / signed-URL access cutoff | **PENDING** — raise at kickoff | When content is unpublished or a transcript replaced, may already-issued download links keep working until they expire (short TTL window), or is instant cut-off required? Bring the current TTL value + a recommendation; record as an ADR. **Default recommendation for MVP: accept a short TTL window (≤ 15 min) with written rationale** — instant revocation adds real complexity for little MVP value. |
| **D-12-C** | Recording / transcript retention | **PENDING** — raise at kickoff | How long are lecture recordings and transcripts kept, and what triggers deletion (end of course? fixed period? manual only)? Privacy/policy decision owned by the product owner. Present 2–3 concrete options; record as an ADR. **The ADR must also state backup-retention alignment** (see 12f backups): if primary data is deleted but backups retain it for N days, that retention window is itself part of the privacy decision. The post-MVP watchlist flags this as required **before any real-student deployment** — recordings of identifiable people stored indefinitely is a policy decision, not a default. |

**ADR numbering (v1.1 flag).** Repo notes show **ADR-056 and ADR-057 referenced by both Stage 8.6 and
Stage 10** (likely a parallel-work collision). Before allocating ADR numbers for D-12-B, D-12-C, the
deploy-readiness decision, the backups/restore decision, and any deviation, **confirm the actual next
free number** (and, if the 056/057 duplication is real, reconcile it or record the reconciliation as a
finding). Per §2, treat these numbers as hints to verify — do not assume the next number from memory.

Do **not** implement the D-12-B or D-12-C dependent pieces until each decision is locked.

---

## 4. Recommended order & dependencies

```
12a  ──►  12b  ──►  12c  ──►  12d  ──►  12e  ──►  12f
(authz +    (security    (data/      (privacy/   (load/      (deploy-readiness
 errors)     + hygiene)   workers)    retention)  perf)        + full smoke)
```

- **At kickoff:** raise **D-12-B** and **D-12-C** to the product owner (§3) so neither blocks later.
- **12a goes first.** It is the only sub-session that changes the core request/response contract
  (authz + error envelope). Everything downstream — especially the 12f smoke — depends on it being
  stable, and it carries the highest regression risk (seeded flows assume role-based publishing
  today). Land it, prove the suite stays green, then build on it.
- **12f goes last.** It is the stage's browser gate and exercises every prior sub-session end-to-end.
- **D-12-B** gates the signed-URL portion of **12b**. **D-12-C** gates **12d**. The rest of each
  sub-session can proceed while the decision is pending; pause only on the dependent piece.
- 12c, 12d, 12e are largely independent of each other and can be reordered if convenient, but keep
  them between 12a/12b and 12f.

Per sub-session: write a focused spec (read the listed files **first**), share for approval,
implement, run the gate, attach the independent review, hand to the product owner to merge.

---

## 5. Sub-sessions

### 12a — API boundary hardening (authorization + error envelope)

*The only sub-session that changes the core request/response contract. Run with `/careful`.*

**Read first (starting points — confirm actual paths in the repo):** the `can_publish` derivation in
the content/authz layer; `GET /me` membership resolution; `frontend/src/lib/api/wrapper.ts` (401/403
mapping); the FastAPI app/exception setup; the E2E/demo seed scripts.

**Work:**
- **Precondition — confirm `GET /me` already resolves active memberships only (rule 4)** before changing
  `can_publish`. The membership set is about to become the publishing source of truth; it must be the
  trusted, active-only set first. If it is not, that is a finding (rule 10), not a silent assumption.
- **`can_publish` → membership-derived.** Today publishing permission is derived from the user's
  global role. Change it so a lecturer can publish/modify content only in modules where they hold an
  **active membership**. Add negative tests: a lecturer with the lecturer role but **no** membership in
  module X cannot publish in module X (expect **403**, session preserved, per rule 5). **Ensure seeded
  demo/E2E lecturers hold the memberships their existing flows need**, so the full active suite still
  passes — this is the main regression risk of the change.
- **Global exception handlers + consistent error envelope.** No raw default 500 bodies; no stack
  traces or internal detail in any error response. One structured shape applied uniformly, e.g.
  `{ "error": { "code", "message", "request_id" } }`. The `request_id` is a **lightweight** correlation
  id (generate per request if one is not already present) so 12c logging can tie a user-visible error to
  a log line — keep it minimal, not an observability framework.
- **Echo `request_id` in a response header on *every* response (v1.1), not only error bodies** — e.g.
  `X-Request-ID`. Support and the smoke (12f) can then grab the id off any response to find the matching
  log line, including for non-error requests. One middleware, reused by the error envelope.
- **Preserve 401/403 semantics (rule 5)** and confirm `wrapper.ts` still maps them correctly (401 →
  clear session / redirect to `/login`; 403 → unauthorized state, session kept). If the error contract
  becomes part of OpenAPI, regenerate and commit the TS client (rule 3).

**Gate:** authz negative tests green; a forced server error returns the clean envelope (verify in the
browser network tab — correct status code, no stack trace, `request_id` present in both body and the
`X-Request-ID` header); `wrapper.ts` 401/403 mapping unchanged; `/review` + `/codex` attached; full
active Playwright suite green.

---

### 12b — Security audit & build hygiene

**Read first:** the shared `section_visibility` helper (`apply_visible_section_gate`) and its call
sites across the content / progress / gamification / analytics read paths; `AIRequestLog` and any
newer log tables; the auth/login path and the deactivation logic (Slice 0); all `NEXT_PUBLIC_E2E_*`
and fault-injection env flags; the signed-URL issuance/TTL code.

**Work:**
- **Run `/cso`** (OWASP Top 10 + STRIDE) across backend and frontend. Zero-noise gate (high-confidence
  findings only); each kept finding carries a concrete exploit scenario.
- **Secrets hygiene (explicit, v1.1 — example corrected in v1.2).** Confirm **no secrets or keys are
  committed** to the repo or present in git history. Cover all key types:
  - the **K2Think / IFM credential** — a **Bearer token** to `api.k2think.ai` (it is **not** an
    `sb_secret_…` value); it must be injected via env only;
  - **Supabase keys** — the `sb_secret_…` / service-role keys;
  - any **database URL containing a password**.
  A hardcoded credential is an OWASP A02/A05 finding, not a footnote; if one is found in history, surface
  it (a leaked credential likely needs rotation with the university/Supabase). This overlaps `/cso` but
  is called out so it is not assumed-covered.
- **Content-visibility gate uniformity (project-specific, HIGH priority).** Verify
  `apply_visible_section_gate` is applied to **every** content-domain read — including mastery,
  progress, gamification, and analytics queries. This leak class (unpublished/unassigned sections
  counting toward reads) **recurred across Stages 8.6, 9, 10, and 11**; a fix was applied, but because
  this bug class came back four times, confirm it is closed **everywhere**, with a test per surface.
  Treat any uncovered read path as a finding, not a footnote.
- **Auth boundary check (Slice 0).** Confirm: inactive/deactivated users cannot log in; a user
  deactivated mid-session loses access on their next request; passwords are stored only as secure
  hashes; there is no `/auth/login` redesign creeping in (rule 4). One test each.
- **Production-build hygiene — automated, not manual.** Verify and then **lock with an automated check**
  that E2E/test hooks and all fault-injection switches are absent/disabled in a production-candidate
  build: `NEXT_PUBLIC_E2E_TEST_HOOKS`, the auth token-override hook, and **every** fault-injection env
  flag. **(v1.1 wording fix — Stage 12 builds no CI):** the check is a **build-time assertion in the
  production-candidate build** — a script that **exits non-zero (fails the build)** if any hook/flag is
  present, invoked by the production build and by the 12f deploy procedure. It is written so it *slots
  into* a CI step unchanged if/when CI exists. (Same principle as the 4.6 "fault injection impossible
  outside E2E" rule; this is the hygiene requirement originally parked in 4.8, applied to the
  production-candidate build.)
- **PII-in-logs check.** Confirm rule 6 held across every AI feature added since 4.5: `AIRequestLog`
  (and any newer log) stores hashes/metadata, **never** raw transcript or student speech.
- **Signed-URL revocation (D-12-B).** Implement the locked decision — either revocation, or the
  accepted-TTL-window ADR with the documented value.

**Gate:** `/cso` clean (or every finding resolved per rule 13); no secrets in repo or history;
visibility-gate tests green on every content surface; auth-boundary tests green; build-hygiene check
green and failing-on-violation; PII check clean; `/codex` on any fix that changed code; full active
Playwright suite green.

---

### 12c — Data, workers & capacity review

*Review-and-verify; fix only where a defect is found.*

**Read first:** the Alembic migration chain head after the Stage 8–11 merges; each RQ queue worker
(embedding / `ai` / agent); the Stage 11 scheduler container and the `AgentRun` enqueue path; the 4.6
stuck-row reaper and storage-reconciliation job; the shared Redis limiter (budgets + priority);
`assessments/service.py::_prewarm`.

**Work:**
- **Migration chain.** Single Alembic head; fresh-DB round-trip (`upgrade → base → upgrade`) green;
  **report the actual head revision in the findings note**; confirm no orphaned or duplicate revisions
  after the Stage 8–11 merges. *(Per §2, repo-note revision numbers — e.g. Stage 10 chaining off `0041`
  to `0080/0081`, and a `0033 → 0043` assistant block — are hints to confirm, not facts: verify the true
  head and that every block reconciles to one head.)*
- **Workers & scheduler.** For each RQ queue **and the Stage 11 scheduler container**: retry policy
  correct, terminal failures observable, no stranded jobs, scheduled jobs actually fire. Specifically:
  **verify the Stage 11 `AgentRun` enqueue path has no "committed run, never-enqueued, no retry" gap**
  (this was a known pre-landing risk — confirm the fix held), and that the 4.6 stuck-row reaper still
  covers `uploaded / parsing / queued` crash states.
- **Rate limiter.** The shared Redis limiter honors its documented budgets (requests/min, tokens/min,
  concurrency: 20 Cerebras / 10 Nvidia RPM, 100k / 105k TPM, concurrency 10 — rule 15) and the
  **priority reservation still gives interactive (assistant) traffic headroom over background jobs.**
- **Storage reconciliation (4.6).** The orphan-reconciliation job runs and reports correctly
  (report-only default, prefix-scoped, deletion-capped, superseded retained).
- **Logging review — with explicit pass criteria (v1.1).** This is a *review*, not a logging stack. It
  passes only when all three hold:
  1. **every unhandled-error path logs at ERROR including the `request_id`** from 12a (traceability);
  2. **no PII in logs** (cross-ref 12b / rule 6 — no raw transcript, student speech, or tokens);
  3. **logs land on durable, platform-captured stdout** (no bespoke sink, no log aggregation stack —
     stdout the deploy host captures is the MVP-appropriate answer).
- **AIRequestLog cost review.** The "tokens by feature by day" query returns a result; sanity-check
  totals against the IFM budgets; flag any feature that is unexpectedly expensive.

**Gate:** fresh-DB migration round-trip green; actual head revision recorded; reconciliation report
produced; cost query returns a result; worker / limiter / scheduler behavior verified by a test or a
documented, reproducible check; logging review passes its three criteria; `/codex` on any code fix;
full active Playwright suite green.

---

### 12d — Privacy & data retention

*Run with `/careful` if a deletion mechanism is built.*

**Read first:** the transcript / recording storage model and storage keys; the 4.6 storage-reconciliation
job (a deletion mechanism should reuse its loss-safe, prefix-scoped patterns).

**Work:**
- Lock **D-12-C** (retention policy ADR). The ADR states the retention period, the deletion trigger,
  **and the backup-retention alignment** (12f) — primary deletion plus a bounded backup window is a
  single coherent privacy decision, not two unrelated ones.
- Implement the **minimum mechanism** to honor it (a retention/deletion job or deletion path), **or**,
  if the decision is to defer the mechanism until go-live, record that as an explicit "gate before any
  real-student data" item with a named owner (rule 13). **Recommended:** since no real student data
  exists yet (no hosting, seeded data only), the *ADR is required now* but the *mechanism may be
  deferred-with-owner* to go-live — as long as the deferral is explicit and lands in the go-live
  checklist (§7). For a university context with real recordings, "indefinite by default with no
  documented decision" is **not** an acceptable end state.

**Gate:** retention ADR recorded (incl. backup-retention alignment); mechanism implemented **or**
explicitly deferred-with-owner and listed in the go-live checklist; `/review` + `/codex` if a mechanism
was built; full active Playwright suite green.

---

### 12e — Load & performance check (scale-appropriate)

**Read first:** `assessments/service.py::_prewarm` → `prewarm_scope_pools` (the D1 pre-warm path); the
quiz-generation "generating" UI state; the limiter queueing behavior.

**Method (v1.1 — make this concrete before running).** Two distinct concerns, tested two distinct ways,
so you neither burn real K2Think budget proving queue mechanics nor skip the one check that needs the
real provider:

- **(A) Limiter / queueing mechanics → deterministic adapter with injected latency.** Drive the realistic
  peak — on the order of **tens of students** starting recap/exam-prep quizzes within a short window —
  through a **scripted concurrency driver** (a pytest/asyncio harness or a small script firing N
  concurrent attempt-starts), with the LLMProvider boundary on the deterministic test adapter configured
  to *simulate* realistic generation latency. This proves the limiter and the "generating" state under
  contention **without** real spend. (Rule 11 does not require a real call to test queueing.)
- **(B) Pre-warm invariant → one small *real*-provider confirmation.** A separate, small real run
  confirming that a **known** exam's pools are warm and a student does **not** pay the ~264s cold
  generation wait. This is the one piece that must touch the real provider; keep it small (the warm-pool
  assertion, not tens of real generations).

**Confirm (pass envelope — v1.1 makes "no deadlock" measurable):**
- the **D1 pre-warm invariant holds** — a *known* exam's pools are warm, so students do **not** pay the
  ~264s cold generation wait (only ad-hoc first recaps do). This invariant is load-bearing for exam-prep
  UX; any regression in the pre-warm path silently reintroduces the 264s wait.
- the limiter **queues gracefully** behind a visible "generating" state rather than erroring or
  deadlocking. **Queue-wait is acceptable and expected — it is not a failure.** Concretely, "graceful"
  means:
  - **known-exam (pre-warmed):** first quiz served promptly, no cold-generation wait;
  - **ad-hoc cold first recap:** spinner up to ~the cold-generation bound (~264s), then result — **no
    request error**;
  - **queued behind the budget:** the request **waits** with the spinner and eventually completes — **no
    HTTP error, no deadlock, no lost request** (the run drains).
- *(Do **not** re-investigate `reasoning_effort`. It is a closed negative finding: low reasoning is
  ~7× faster but roughly halves first-try output validity. Inline reasoning is load-bearing. Skip it.)*
- **Frontend baseline.** Run `/benchmark` on the key student pages (lecture/summary, quiz attempt,
  progress dashboard) to record a Core Web Vitals + page-load baseline for future regression comparison.

**Gate:** peak scenario (A) completes with no errors and no limiter deadlock and meets the pass envelope;
pre-warm confirmation (B) shows warm pools serving without the cold wait; `/benchmark` baseline recorded
in knowledge; full active Playwright suite green.

---

### 12f — Deploy-readiness + full-MVP smoke (the Stage 12 browser gate)

*No hosted environment exists (D-12-A resolved). This sub-session prepares for deployment and proves the
full path on a production-candidate build; it does **not** perform a real hosted deploy.*

**Work:**

**(a) Repeatable, documented deploy procedure (deploy-ready, not yet executed).** Produce a
step-by-step procedure to stand up Postgres (managed), Redis, backend, all three workers (embedding /
`ai` / agent), the **Stage 11 scheduler**, and the frontend. It must include:
  - the **explicit release-phase migration step** — migrations run as a deliberate release phase,
    **never on boot** (deliberate locally, fatal if forgotten hosted);
  - the **managed-Postgres extension bootstrap** (`vector`, `pgcrypto`) so it is automated when hosting
    lands (closes F006). **Note honestly in the procedure that this step is documented but cannot be
    verified against real managed Postgres until hosting exists** — it joins the deferred go-live
    verification (§7);
  - **backups & restore (v1.1) — scale-appropriate.** The procedure must specify: **managed Postgres
    automated backups enabled** (point-in-time recovery if the provider offers it), the **object-storage
    durability/versioning posture** for transcripts/recordings, and a **short, documented restore drill**
    ("how to restore the DB to a point in time; how to recover a deleted object"). This is a *config + a
    written procedure*, not a DR program. The backup retention window must match the **D-12-C** retention
    ADR (you cannot promise deletion at end-of-course if backups keep the data longer). Backups against
    *real* managed PG can only be verified once hosting exists → it joins §7; the *procedure and the
    restore steps* are produced now.
  - **rollback / back-out (v1.1) — scale-appropriate.** A short section covering: how to **revert the
    application version**, and — critically — how to **back out a bad release-phase migration** (the
    Alembic `downgrade` path; every stage already proves fresh-DB `upgrade → downgrade → upgrade`
    round-trips, so the down-revisions exist — document using them under `/careful`). One paragraph plus
    the exact commands, not blue/green.
  - secrets handling and the production CORS origins list;
  - the **`GSTACK_*` env-var note if running under Conductor** (Conductor strips `ANTHROPIC_API_KEY` /
    `OPENAI_API_KEY`; the canonical names must be promoted at runtime) — only if relevant to the deploy
    host.

**(b) Full-MVP end-to-end smoke against a local production-candidate build.** Use a production-like
compose (production build settings, **E2E/test hooks verifiably absent** per 12b). Run the entire path
in a real browser (`/qa`):

  - **Smoke timing / real-provider stability (v1.2 — decide before running this gate).** The live
    browser path hits **real** K2Think generation at the quiz and assistant steps, and that generation is
    slow **by design**: the reasoning route runs to a **330s timeout** and a **cold quiz pool** adds the
    **~264s-class first-wait** observed in Stage 6 (inline reasoning is load-bearing — this latency is
    expected, not a bug). Left on the real provider with ordinary Playwright timeouts, the smoke can
    **false-fail** on a slow-but-correct generation rather than on a real defect. Pick **one** approach
    explicitly and record which in the findings note:
    - **(i) Real provider, pre-warmed + generous timeouts.** Pre-warm the section/exam pool the smoke
      uses (so the quiz step serves from a warm pool, not a cold ~264s generation) and budget
      **Stage-6-equivalent timeouts** (≥ the 330s reasoning bound) on the quiz/assistant waits so a
      slow-but-valid generation passes. **Rule 11 is satisfied by the run itself.**
    - **(ii) Deterministic browser smoke + separate real-provider smoke.** Run the **browser** path on
      the **deterministic LLMProvider adapter** (provider boundary only — the full backend code path
      still runs, identical to 12e(A) and to every prior stage's CI runs) so the gate is stable and fast;
      satisfy **rule 11** with a **separate, focused real-provider call** recorded in
      `knowledge/steps/12f-real-provider-smoke.md`, asserting the echoed model ID matches the configured
      identifier. This is the pattern every prior AI stage used.

      Do **not** leave the full browser path on the real provider with default timeouts. Either choice
      keeps §6 intact: the user-facing flow is still driven live in the browser; only the provider
      boundary differs.

  - **The path:** admin creates module → lecturer adds content + transcript → pipeline completes on the
    workers → brief + detailed summaries → student studies → quiz → **wrong answer recorded as a
    mistake** → glossary save + practice → assistant Q&A → progress + grade forecast → gamification
    (**a completed quiz updates streak/badge via the event path**, not the frontend) → analytics.
  - **Seed-vs-live boundary (v1.1 — be explicit so the agent neither over-builds nor under-covers):**
    - the **student-facing path is driven live in the browser** — study → quiz → wrong-answer mistake →
      glossary save/practice → assistant Q&A → progress/forecast → **the event-driven gamification update
      observed in the UI** → analytics read. This is the path the human watches (§6).
    - **admin/lecturer setup and the Stage 9 / Stage 11 inputs may start from seed** (Stages 9 and 11
      verify against their designed **seeded** flows; live LMS integration stays out of scope). The
      pipeline itself (transcript → workers → summaries) runs **live** on the workers — it is not seeded.
  - Confirm scheduled jobs (reaper, reconciliation, the Stage 11 scheduler) **actually fire** in this
    production-candidate run, and that migrations were applied via the **release-phase step**, not on
    boot.
  - **Verify health endpoints respond — as real readiness checks (v1.1).** Health must verify **DB and
    Redis reachability** (a readiness check), not merely return a static 200 — a health endpoint that
    says "up" while the DB is unreachable is worse than none for go-live. Distinguish **liveness**
    (process is running) from **readiness** (DB + Redis reachable), scale-appropriately; if no real
    health endpoint exists yet, add a minimal one as part of deploy-readiness. Go-live health checks are
    then known-good in advance.

**(c) Assistant step.** Verified in its current **create-then-poll** behavior. **SSE token-streaming
(Stage 8.3) stays deferred** and is **not** a Stage 12 gate — do not test streaming that is not built.
Add a one-line forward note in the deploy procedure: *when hosting lands, 8.3 must validate SSE against
the real hosting proxy early, since buffering proxies are where SSE breaks.*

**(d) Produce `docs/go-live-checklist.md`** — a short, ordered checklist the product owner runs **the
moment hosting is available**, turning the deferred go-live into a single repeatable execution. It must
list, in order: execute the documented deploy procedure → **confirm managed backups are enabled and run
the restore-drill once against real PG (v1.1)** → run the release-phase migration → verify the Postgres
extension bootstrap on real managed PG → confirm all workers + scheduler are up → **verify health
readiness (DB + Redis) on the live environment** → run `/land-and-deploy` for the staging→production
promotion → run `/canary` for the post-deploy watch → **if `/canary` fails, execute the documented
rollback (app revert and/or migration downgrade) (v1.1)** → build & validate **Stage 8.3 SSE** against
the real proxy → enable the **12d retention mechanism** if it was deferred. (See §7.)

**Gate:** the full-MVP smoke passes end-to-end in a real browser **without manual intervention** against
the local production-candidate; the **smoke-timing decision (i or ii) is recorded** and the gate is not
left flaky on the real provider; **rule 11 is satisfied** per that decision (by the run itself, or by the
separate `12f-real-provider-smoke.md`); the deploy procedure is documented (incl. **backups/restore** and
**rollback** sections) and its release-phase migration step is **proven on the production-candidate**;
health endpoints respond **as readiness checks (DB + Redis)**; E2E hooks verifiably absent;
`docs/go-live-checklist.md` produced; full active Playwright suite green.

---

## 6. UI proof obligation (stage level)

A human watches the **entire MVP path** happen in a real browser against the **production-candidate
build** — admin through analytics — with no manual intervention and no test hooks present. The
student-facing flow is driven **live in the browser** end-to-end (study → quiz → wrong-answer mistake →
glossary save/practice → assistant Q&A → progress/forecast → event-driven gamification update →
analytics). "Live" here means the **full backend code path executes for real**; the **LLM provider
boundary** may be the real provider **or** the deterministic adapter per **rule 11** and the 12f(b)
smoke-timing decision — with rule 11 satisfied either by the run itself (option i) or by the separate
focused real-provider smoke (option ii). No test hooks are present in the build (12b).

---

## 7. Deferred-with-owner (blocked on external dependency — rule 13)

The following cannot be executed without university hosting. They are explicitly tracked, **owner =
product owner**, and **must complete before any real-student launch** (collected in
`docs/go-live-checklist.md`):

- Real **staging → production promotion** (`/land-and-deploy`) executing the documented 12f procedure
  against real hosted infra.
- **`/canary`** post-deploy watch and health verification on the live environment.
- **Managed-Postgres extension bootstrap** (`vector`, `pgcrypto`) verified against real managed PG
  (documented in 12f, unverifiable until hosting).
- **Backups verified against real managed PG (v1.1)** — automated backups confirmed enabled and the
  **restore drill executed once** on the real environment (procedure produced in 12f; only verifiable
  with hosting).
- **Rollback rehearsed on the real environment (v1.1)** — at least the migration-downgrade path executed
  once against real hosted infra (commands documented in 12f).
- **Stage 8.3 SSE streaming** built and validated against the real hosting proxy.
- **12d retention mechanism**, if it was deferred rather than built.

---

## 8. Roadmap coverage map (so nothing falls through)

| Roadmap item / carried debt (owner = Stage 12 or 4.8-now-folded-in) | Discharged in |
|---|---|
| `can_publish` derived from role rather than membership | **12a** |
| No custom exception handlers (raw default 500 bodies) / consistent error envelope | **12a** |
| `request_id` correlation in body + `X-Request-ID` header (v1.1) | **12a** |
| Security pass (OWASP + STRIDE) | **12b** |
| Secrets-not-in-repo / no committed credentials (v1.1; example corrected v1.2) | **12b** |
| Content-visibility gate uniformity (recurred 8.6 / 9 / 10 / 11) | **12b** |
| Auth boundary: inactive login, password hashing, mid-session deactivation (Slice 0) | **12b** |
| E2E hooks / fault injection absent from production build (from 4.8) | **12b** |
| Signed URLs valid until TTL after unpublish — decision | **12b / D-12-B** |
| AIRequestLog stores no PII (rule 6 verification) | **12b** |
| Migration review (single head after Stage 8–11) | **12c** |
| Worker retry/failure review; Stage 11 `AgentRun` enqueue gap; scheduler fires | **12c** |
| Rate-limit review (budgets + interactive priority headroom) | **12c** |
| 4.6 storage reconciliation verified | **12c / 12f** |
| Logging / observability review (3 explicit pass criteria, v1.1) | **12c** |
| AIRequestLog cost review (tokens by feature by day vs IFM budgets) | **12c** |
| Transcript/recording retention policy (watchlist: before real-student deploy) | **12d / D-12-C** |
| Load checks (exam-week peak; D1 pre-warm invariant; pass envelope v1.1) | **12e** |
| Smoke real-provider stability / timing decision (v1.2) | **12f** |
| Hosted Postgres extension bootstrap F006 (from 4.8) | **12f (documented) + §7 (verified at go-live)** |
| Backups & restore (v1.1) | **12f (documented) + §7 (verified at go-live)** |
| Rollback / back-out procedure (v1.1) | **12f (documented) + §7 (rehearsed at go-live)** |
| Health readiness checks (DB + Redis, v1.1) | **12f** |
| Release-phase migration step (from 4.8) | **12f** |
| Deployment rehearsal → now deploy-readiness + deferred promotion | **12f + §7** |
| Org/tenancy model ADR | already recorded (ADR-052, single-tenant MVP) — not a Stage 12 item |

---

## 9. Done means (permanent acceptance rule applies)

- 12a–12f gates all green; the full-MVP smoke passes against the **production-candidate build**, with the
  smoke-timing decision recorded and rule 11 satisfied (v1.2).
- Every finding from `/cso`, `/review`, `/codex` resolved per rule 13.
- ADRs recorded for **D-12-B**, **D-12-C**, the deploy-readiness / deferred-go-live decision, the
  **backups & restore decision (v1.1)**, and any deviation — allocated against the **confirmed next free
  ADR number** (§3, §2).
- The §7 go-live items are recorded as deferred-with-owner, blocked on hosting, and collected in
  `docs/go-live-checklist.md` (incl. the v1.1 backups-verify and rollback-rehearsal items).
- Docs current — run `/document-release`; README / ARCHITECTURE / CLAUDE.md reflect the shipped system
  and its **deploy-ready (not-yet-deployed)** status, including the backups/restore and rollback
  procedures.
- Roadmap status table updated in the **same commit** that closes the stage (rule 12): **Stage 12
  marked FULLY VERIFIED (production-candidate; go-live deferred on hosting)**, and **4.8 / 8.3 left as
  blocked-on-hosting** with the deferred-go-live cross-reference.
- Backend tests green, frontend type-check green, OpenAPI client fresh if the contract changed.

---

## 10. Exclusions

No new user-facing features. No live LMS integration (seeded flows only). No SSE/streaming work (8.3
stays deferred until hosting). No real hosted deploy (deferred-with-owner). No autoscaling, CDN,
multi-region, custom domains, full observability platform, log-aggregation stack, DR program, or CI/CD
build-out for MVP launch — deferred to post-MVP unless a 12e load finding specifically justifies one,
recorded as an ADR. **Backups, rollback, and health checks (v1.1) are deliberately the minimum-viable
form** (managed-PG config + a written restore/rollback procedure + a readiness ping) — not a platform.