# XYZ LMS — Development Roadmap v3

**Approach:** Option C — Walking Skeleton, then widen.
**Supersedes:** Roadmap v2. The Client Edge Recovery Plan remains the archived implementation record for 4.3.5.
**Permanent rule:** No backend slice merges without a thin UI slice and a browser-verifiable gate.
**Repo rule (new in v3):** This file lives at `knowledge/roadmap.md`. Its status table is updated **in the same commit** as the work that closes a stage (extension of cross-cutting rule 12). A roadmap living outside the repo drifts — v2 demonstrated this by still reading "4.4 NOT STARTED" after 4.4 shipped at `442f221`.

---

## Governing principle (unchanged)

Do not build horizontally isolated backend layers. Every stage proves a thin vertical path:

```
Browser
→ frontend route / component
→ authenticated API call
→ backend service
→ database / storage / worker
→ observable result back in the browser
```

Backend tests are necessary but not sufficient. A phase gate closes only when the feature is **browser-verifiable**. For infrastructure-heavy work, "UI slice" means a real, browser-observable result (a status, an output, a visibility rule taking effect) — not a museum for vectors.

---

## The UI proof obligation (unchanged)

Every stage carries one line stating the thing a human must be able to *see happen* in a real browser, against the real backend, for the stage to count. A component rendering against a mock does not satisfy it. Only real browser → real backend → real result satisfies it.

---

## Status vocabulary (unchanged)

```
NOT STARTED      — no work begun
BACKEND VERIFIED — backend built + tested. Browser gate NOT passed. This is NOT done.
UI PENDING       — backend verified; browser gate explicitly scheduled
FULLY VERIFIED   — backend AND browser gate both pass (product/infra stages)
DONE             — governance stages where no browser gate applies (Stage 0 only)
```

**BACKEND VERIFIED is not DONE.**

---

## Current reality

```
✅ Stage 0     Knowledge system / ADRs / stack lock      DONE
✅ Stage 1     Repo skeleton / KM1                        FULLY VERIFIED  (gate: 4.3.5a)
✅ Stage 2     Identity + access / P0                     FULLY VERIFIED  (gate: 4.3.5b + 4.3.5c)
✅ Stage 3     Content + visibility / P1                  FULLY VERIFIED  (gate: 4.3.5a + 4.3.5d)
✅ Stage 4.1   Transcript upload                          FULLY VERIFIED  (gate: 4.3.5e)
✅ Stage 4.2   Transcript parsing                         FULLY VERIFIED  (gate: 4.3.5e)
✅ Stage 4.3   Transcript chunk persistence               FULLY VERIFIED  (gate: 4.3.5e)
✅ Stage 4.3.5 Client Edge Recovery                       COMPLETE
✅ Stage 4.4   Embeddings                                 FULLY VERIFIED  (gate: 4.4 embedding browser run)
✅ Stage 4.5   AI infrastructure + summary generation   FULLY VERIFIED  (gate: 4.5d browser gate + full E2E + real-provider smoke)
✅ Stage 4.6   Replacement / retry / supersession       FULLY VERIFIED — live browser gate GREEN (full active suite 9/9); two cross-stage-seam regressions found+fixed (F-4.6c-1, F-4.6b-2)
✅ Stage 4.7   Student-facing summaries                   FULLY VERIFIED — gate G1–G9 GREEN; full active suite 11/11 ON MAIN (backend 389); restored Stage 3 visibility E2E; review R1–R3 resolved
Stage 4.8   First hosted deploy (staging)              DEFERRED-WITH-OWNER — blocked on an external university hosting decision (D-12-A); deploy-prep deliverables folded into Stage 12f
Stage 4.9   Frontend foundation + platform hygiene     FRONTEND FOUNDATION MERGED — 4.9g imported the Stage 4.9f monochrome frontend design foundation onto current `main`; stale 4.9 backend/platform/deploy changes were intentionally not imported; Stage 5-9 backend/schema/generated-client behavior remains authoritative; verification green in [[steps/stage-04/4.9g-merge-monochrome-redesign]]
✅ Stage 5   Shared quiz engine + event spine           FULLY VERIFIED — merged to main; migrations 0014–0020; gate 1 browser GREEN; gate 3 real-provider smoke GREEN; backend 442 pytest; frontend tsc green; ADR-040..046; F-5d-1 resolved
✅ Stage 5.5   Module schedule & section metadata       FULLY VERIFIED — gate 5.5e GREEN; reference schedule 28 sections; full active suite 12/12 after reseed; migration chain rebased after Stage 5 main (`0020 -> 0021 -> 0022`)
✅ Stage 6   Complete quiz modes                        FULLY VERIFIED — full active Playwright 14/14 + 5d/6d gates + backend 502 + rule-11 real-provider smoke PASS (264.5s, 16Q, model echo OK). 6e corrective gate proofs + F-6e smoke fix (pool trimmed max_tokens 32000→20000 / count 24→16, reasoning timeout 240→330; root cause = ramble-to-cap ≈ max_tokens/73, not the route). See [[steps/stage-06/6d-real-provider-smoke]] (2026-06-18) + ADR-047 F-6e amendment
✅ Stage 7 core  Glossary 7a–7c                       FULLY VERIFIED — real-provider smoke GREEN (Cerebras/K2-Think-v2 model echo matched; `finish_reason='length'` follow-up logged); Stage 7 browser gate GREEN; full active suite 14/14; 7d quiz-highlight remains unblocked
Stage 8     Assistant                                  IN PROGRESS — ✅ 8.1 FULLY VERIFIED (2026-06-18). 8.1 conversation foundation: assistant domain (conversations/messages), gateway `assistant` feature, lecture entry + chat panel (inline idiom — monochrome system not in code, see findings-design-doc-reality-gap), create-then-poll @ interactive priority (ADR-048), 8.4-ready data shape (ADR-049), migration 0032 (parent 0031 after Stage 7 rebase; single head). Rebased onto Stage 7; merged backend 537 pytest (incl. shared-CHECK union guard); tsc green; client regen. Live gates GREEN: 8.1 browser gate + full active Playwright 16/16 (rule 14) + real-provider smoke (rule 11, model echo MBZUAI-IFM/K2-Think-v2). Env workarounds recorded (supabase edge_runtime 502; shared kyiv-backend image-tag contention with active sibling tokyo) → [[steps/stage-08/findings-8.1-gate-run-blocked]]. ✅ 8.2 FULLY VERIFIED (2026-06-18) — context retrieval/grounding; browser gate + full active Playwright 17/17 (rule 14) + /cso-clean + real-provider smoke (rule 11, model echo MBZUAI-IFM/K2-Think-v2, real isStudyRelated emitted). Exact pgvector scan through the 4.7 visibility gate, backend-derived groundingStatus via fixed-precedence decide_grounding, ONE interactive call + required isStudyRelated flag, generation-time context_snapshot (migration 0033, single head), embedder promoted to platform/embeddings (ADR-050) + grounding architecture (ADR-051); backend 558 pytest; NO OpenAPI change. Gate env: recurred shared-image contention → unique baked image kyiv-backend-e2e-hatyai (local compose edit, revert before commit); deterministic-embed-in-e2e timing race vs 4.3.5e → live e2e on real MiniLM (deterministic encoder scoped to backend pytest) → [[steps/stage-08/findings-8.2-gate-image-contention]]. ✅ **8.4 FULLY VERIFIED (2026-06-19)** for claimed gates — Workspace + floating widget (Option A: navigation/conversation-management only, NO new AI surface). Backend verified: migration 0040 (deleted_at/title_source/last_activity_at + one-active index rebuilt `… AND deleted_at IS NULL`) round-trips single-head 0040; backend 600 pytest incl. 23 new workspace + 28 existing assistant (invariants A–E, keyset, rename/soft-delete, GET-detail, last_activity bumps); client regen; frontend tsc + `next build` green. **Both close-out gates GREEN (ran LOCALLY; test2 untouched, stack on :8005/:3005):** latest full active Playwright **20/20** (rule 14, clean DB `e2e-stage84-review2-env-1781886621`, serial `--workers=1` — both 8.4 specs + 8.1/8.2/9 + every prior 4.x/5/6/7 gate) + rule-11 real-provider smoke (real K2 on assistant/v2, model echo MBZUAI-IFM/K2-Think-v2, isStudyRelated correct); /cso CLEAN (0 findings — every new endpoint routes through require_student + ownership + 4.7-visibility + deleted_at→404; worker resurrection-guarded). The live gate caught + fixed 3 issues, and second external-review repair added the deep-link pending, widget readiness, backend pending-turn, and gone-state guards; mobile keyboard overlap is **not verified/not claimed** → [[steps/stage-08/findings-8.4-gate-run]]. ADR-053 (keyset sibling envelope, rule-10 escalation) + ADR-054 (conversation-management contract); GET `/student/assistant/conversations/{id}` amendment. 8.3 (SSE) deferred to 4.8. ✅ **8.5 FULLY VERIFIED (2026-06-20)** — Save-to-glossary from the assistant: a student highlights a term in a completed assistant reply and saves it through the EXISTING Stage 7 glossary save path with a discriminated `conversation` source. Rule-10 escalation resolved (ADR-055): chat saves feed NO conversation text to the definition prompt (`definition_context=""` → identical to the manual-add AI path; cache key unchanged, input hash identical → no rule-11 smoke). ONE write path (glossary owns the write; assistant read via new `platform/query/assistant_save_source_read`, rule 8); server-verified anti-spoofing (completed assistant message, owned + bound + published/assigned, both selectedText AND the persisted term in-message via a conservative markdown normalizer); idempotent conversation source-attach. Migration 0041 (source_conversation_id/source_message_id FKs + widened CHECK + partial-unique idempotency index) round-trips single-head 0041; `dev_reseed` head pin 0040→0041. Backend **625 pytest** (604 prior + 16 conversation-save negatives + 5 review-hardening tests, incl. the empty-context/cache-collapse proofs); client regenerated (`conversation` variant); frontend **tsc green** + **5 new ConversationView affordance-gating component tests** (present on bound completed-assistant reply; absent on user message / unbound / pending-failed) + unit suite 9/9. Single mount point in shared `ConversationView`→`AssistantAnswerBody` covers inline panel + workspace + widget. Pre-landing **/cso CLEAN** (0 findings, 8/10 gate) + **/review** (Claude adversarial + Codex gpt-5.5 cross-model) applied ONE anti-spoofing hardening — the persisted term must also occur in the message (ADR-055 D4 amend); other flags dismissed with evidence (TOCTOU/validator-alias/normalizer-fuzz). **Live gates GREEN (ran LOCALLY on a CLEAN DB; non-disruptive alt-port stack :8005/:3005 via `.context/8.5-gate.override.yml`, `kyiv-frontend` node:20 container with worcester source bind-mounted, local Supabase :54321, deterministic LLM adapter at the provider boundary):** the 8.5 browser gate `tests/e2e/8.5-assistant-save-to-glossary.spec.ts` PASSED, and the **full active Playwright suite 21/21** (rule 14, serial `--workers=1`, run id `e2e-mqlw0xei-9d1e2ebc`, 11.4m — every prior 4.3.5/4.4/4.5/4.6/4.7/5/5.5/6/7/8.1/8.2/8.4/9 gate + 8.5). **/cso CLEAN** (0 findings); **/review** cross-model (Claude + Codex gpt-5.5) → one anti-spoofing hardening (persisted term must be in the message); **/qa** real-browser drive of the save-from-chat flow CLEAN (0 bugs, no console errors). The live gate caught ONE test-wiring fix (scope save-to-glossary selectors to the assistant reply — the lecture page also renders the summary affordance; commit `011a635`, product code unchanged). No rule-11 smoke (D1). → [[steps/stage-08/findings-8.5-gate-handoff]]. ADR-055. See [[steps/stage-08/8.5-save-to-glossary]], [[steps/stage-08/8.4-assistant-workspace-widget]], [[steps/stage-08/8.2-context-retrieval]], [[steps/stage-08/8.1-conversation-foundation]]. ✅ **8.6a FULLY VERIFIED (2026-06-20)** — assistant **modes** foundation + the first mode = **Homework help** (decisions D1=B 8.6a-only-then-pause, D2=A resume-or-create natural key, D3=A all UX defaults). NO new provider/gateway code (rule 6); ONE call/turn @ interactive priority (rule 15); create-then-poll (no SSE). Coordinator dispatches by `conversation_kind` via a strategy seam (`_MODE_TURN_BUILDERS`; default = lecture behavior extracted VERBATIM — 53 existing assistant tests green; `homework_help` → `_homework_turn`) keeping ONE gateway call + ONE persist/snapshot; kind IMMUTABLE; per-mode snapshot rides the existing `context_snapshot` (`"mode"`/`retrievalScope`); `feature="assistant"` kept (no CHECK widen — mode via `prompt_version` `homework_help/v1`). Homework grounds on the bound MODULE's permitted material via new `retrieve_module_chunks` (ONE exact pgvector scan, NO ANN) or the section scan when narrowed; always coaches (general/redirect/access_denied via shared `decide_grounding`, never context_unavailable). Multi-layer guardrail (L1 prompt sentinel `HOMEWORK_GUARDRAIL_V1` + UNTRUSTED fence; L2 deterministic + L3 adversarial CI on the composed payload; L4 rule-11 smoke). Conversation list/detail/visibility reads + DTOs made section-OR-module aware (section-bound path byte-identical) for module-bound homework; `get_visible_student_module` added. **Route corrected V2/Cerebras/32k** (ADR-057 amend): originally specced Think/Nvidia, but the rule-11 smoke caught K2-Think-v2 on nvidia returning `not_json` (reasons inline + rambles, F-6e); re-run on cerebras PASSED (clean JSON, `finish_reason=stop`, ~8s) — coaching is a focused writing task, same route as the chat. Migration **0042** (kind CHECK +homework_help; `attached_module_id` FK; two homework partial-unique indexes) single-head + fresh-DB round-trip `0041↔0042`; `dev_reseed` pin 0041→0042. Backend **649 pytest** (625 prior + 24 new `test_assistant_modes`); prompt-drift OK; frontend **tsc** + **vitest 9** green; client regen (`createStudentAssistantConversation`). **Live gates GREEN (ran LOCALLY on a CLEAN DB; non-disruptive alt-port stack :8005/:3005 via `.context/8.6a-gate.override.yml`, kyiv `.env`+`.env.e2e` disk-to-disk, local Supabase :54321, deterministic adapter; backend image content-hash-verified to HEAD):** the 8.6a homework gate `tests/e2e/8.6a-assistant-homework.spec.ts` PASSED + **full active Playwright suite 22/22** (rule 14, serial `--workers=1`, run id `e2e-86a-final`, 7.2m — 8.6a + the 8.1/8.2 general-chat regression + 8.4/8.5/9 + every prior 4.3.5/4.4/4.5/4.6/4.7/5/5.5/6/7 gate) + **rule-11 homework smoke PASS** on the cerebras route (model echo `MBZUAI-IFM/K2-Think-v2`; L4 behavioral — both a plain ask AND an injection were coached without the final answer). The live gate caught the route issue (fixed in place) + one test-wiring fix (unique module title vs same-runId reruns). → [[steps/stage-08/findings-8.6a-gate-handoff]]. ADR-056 (coordinator/kind/immutability/snapshot) + ADR-057 (routing/budget + guardrail, route amended). 8.6b and 8.6c are recorded later on this Stage 8 line/addendum. See [[steps/stage-08/8.6a-mode-coordinator-homework]], [[steps/stage-08/8.6-real-provider-smoke]]. ✅ **8.6b FULLY VERIFIED (2026-06-20)** — Exam-prep mode on the 8.6a coordinator seam (conversational only; no saved artifact). Student picks a NAMED `AssessmentScope` (covered weeks read-only via the existing `listStudentExamPrepScopes`) → `exam_prep` conversation; the assistant discusses ONLY that scope grounded in the covered weeks' permitted summaries + a multi-section pgvector scan (`retrieve_sections_chunks`, NO ANN) + the student's Stage 9 weak topics (`list_topic_mastery`), and points to (NEVER generates) the Stage 6 exam-prep quiz with all three precise states live-verified: ready CTA / processing "being prepared" / none "not available yet", sourced FRONTEND-side from the quiz domain. New `platform/query/assessment_scope_read` wraps the SAME eligibility primitives the quiz domain uses — no quiz-domain import (rule 8). New `_exam_prep_turn` builder + the create-dispatch refactor (homework + lecture unchanged); resume-or-create one-active-per-scope (D2). **Route V2/Cerebras/32k** (ADR-057 — applied the 8.6a Think→Cerebras lesson; the rule-11 exam-prep smoke confirmed cerebras: model echo + correct isStudyRelated + scope summary + weak-area reference, no quiz generation). Migration **0043** (kind +exam_prep; `attached_assessment_scope_id` FK; one-active-per-scope index) single-head + fresh-DB round-trip `0042↔0043`; `dev_reseed` pin 0042→0043. Backend **31 mode pytest** (24 homework + 7 exam-prep); drift OK; frontend **tsc** + **vitest 19** green; client regen (scope DTO fields). **Live gates GREEN (alt-port :8005/:3005, clean DB, content-hash-verified unique image):** updated 8.6b browser gate **2/2** + **full active Playwright 24/24** (rule 14, run id `e2e-86b-full-green`, 5.0m — incl. the 8.1/8.2 general-chat regression + 8.6a + 8.4/8.5/9 + every prior gate) + rule-11 exam-prep smoke PASS. The gate surfaced 3 env-only issues fixed in place (test 200/201; shared `kyiv-backend` image-tag race with the parallel Stage 10/11 stacks → unique `dallas-stage86-gate` tag + retag + force-recreate; `next dev` OOM under the shared 7.7 GiB VM → production frontend) and the follow-up full-suite run required loading `.env.e2e` into Playwright for Supabase Admin calls — no product-code bug → [[steps/stage-08/findings-8.6a-gate-handoff]]. ADR-056 + ADR-057 (exam-prep route recorded). 8.6c is recorded in the following addendum. See [[steps/stage-08/8.6b-exam-prep-mode]]
✅ **8.6c FULLY VERIFIED (2026-06-20)** — Time-management assistant mode closes the last Stage 8.6 mode before owner review: conversational-only, one active per student, current-student structured deadlines/progress only (overdue + next 14 days + weak topics + grade/progress summary), day-level advice only, no saved plan/calendar/.ics/Stage 11 artifact, V2/Cerebras route smoke PASS, migration 0044 single head, backend mode pytest 32 + dev-reseed 3 + drift/ruff/py_compile + tsc + vitest 20, standalone 8.6c browser gate and full active Playwright **25/25** on the alt-port stack. Stage 6 screenshot PNG churn fixed by making screenshot capture opt-in. See [[steps/stage-08/8.6c-time-management-mode]], [[steps/stage-08/8.6-real-provider-smoke]].
✅ Stage 9     My Progress                              FULLY VERIFIED — browser gate GREEN; full active Playwright 16/16; backend 542 plus focused progress 18 passed; migrations 0038-0039 now chained after Stage 8.2 head 0033; guarded demo seed reset verified; privacy/no-AI/accessibility assertions hardened, including caller-owned benchmark average plus aggregate-only class comparison
✅ Stage 10    Gamification                               FULLY VERIFIED — Stage 10 gate A/B/C GREEN; full active Playwright 24/24 on clean standard stack; required fault gates green
✅ Stage 11    Proactive analytics                        REBASED ONTO main (head 0082) + RECONCILED — PR open, AWAITING OWNER MERGE (11.1–11.6 all FULLY VERIFIED on the combined code) — Landing: migration chain re-parented to single head `0082 -> 0056 -> 0057 -> 0058 -> 0059` (clean upgrade→base→upgrade); product reconciliation `studied_section` COUNTS AS qualifying activity in `inactive_recently` via a config-backed event-type set, `risk-v1` amended in place (ADR-060); My-Progress `ForecastAdviceCard` coexists with Stage 10 `GamificationPanel`; Stage 9 AI-free gate composes PR #14 id-set-diff + 11.6 forecast-advice scoping; combined verification (unique image, clean DB, deterministic provider): backend **804 pytest**, frontend tsc + **42 vitest**, full active Playwright **33 success + 2 fault**; no rule-11 smoke (deterministic change, no LLM path); one rule-10 flag open (`topic_deadline_gap` publish-gate divergence). Sub-stages: ✅ 11.1 scheduler/risk (incl. the **AgentRun requeue recovery maintenance fix — folded into 11.1, NOT a new stage**); ✅ 11.2 student detail + recommendations; ✅ 11.3 assessment analysis + question insights; ✅ 11.4 workload planner (migration 0058); ✅ 11.5 calendar `.ics` export (cross-timezone/DST gate, no AI/no migration); ✅ **11.6 grade-forecast advice** (migration 0059; AI EXPLAINS the Stage 9 forecast — `calculate_forecast` reused via one `build_forecast_input` path, no new grade math; route `grade_forecast_advice/v1` = K2-Think-v2/cerebras, ADR-059; numeric/contradiction + student-copy-safety validators; tone-neutral advice card; rule-11 smoke passed on its own branch, model echo `MBZUAI-IFM/K2-Think-v2`). Alembic head `0059`.
Stage 12    Release hardening                          IN PROGRESS — 12a–12e FULLY VERIFIED; 12f deploy-readiness (production-candidate, no live deploy — D-12-A; real go-live deferred-with-owner)
```

---

## Completed stages 0 → 4.4 (compressed)

v3 compresses completed stages. Their full definitions, gates, and reports live in the per-stage `knowledge/specs|plans|steps` trios and `STATUS.md` — that is the authority for finished work; duplicating it here is how drift happens. Their browser gates remain **live assertions**: under new rule 14 the full active E2E suite re-runs at every stage close.

**Carried debt from completed stages — each item has an owner and a payment date:**

```
Transcript recovery for stuck rows (uploaded/parsing/queued crash states)   → Stage 4.6
Storage orphan cleanup after failed deletes/replacements                    → Stage 4.6 (reconciliation job)
Stage 3 content-visibility E2E spec archived, not in active suite           → restored as Stage 4.7 hard prerequisite
Browser-gate assertions pinned to overall terminal state, not steps          → Stage 4.5 hard prerequisite
Status badge polling model (2.5s / 60s hard timeout)                        → reworked in Stage 4.5d
week_number / session_date / due_at columns exist but never populated;
fixed 4-section template instead of schedule-driven generation              → Stage 5.5
Frontend: legacy inline-style surfaces and missing shared primitives         → Stage 4.9g imported the monochrome token/component foundation; remaining platform hygiene stays separate
httpx ASGI-shortcut deprecation (83 warnings; future upgrade breaks suite)  → Stage 4.9 hygiene batch
CORS allow_credentials=True unnecessary with pure Bearer auth               → Stage 4.9 hygiene batch
No client-regen alias in frontend/package.json (F008)                       → Stage 4.9 hygiene batch
Hosted Postgres extension bootstrap not automated (F006)                    → Stage 4.8
Signed URLs remain valid until TTL after unpublish                          → RESOLVED in Stage 12 (ADR-062 — accept ≤5-min already-issued TTL; future minting blocked)
can_publish derived from role rather than membership                        → RESOLVED in Stage 12a (display-only derivation, NOT an enforcement hole — F1)
No custom exception handlers (raw default 500 bodies)                       → RESOLVED in Stage 12a (global error envelope, ADR-061); 12f adds CORS-aware 5xx
No roadmap file in repo (F001)                                              → fixed by this document + repo rule above
Next.js 15.3.3 npm-audit findings (1 critical + 1 moderate; latent, not exploitable)  → deferred-with-owner, post-stage dependency pass (12f D3=B)
Quiz-pool ad-hoc first-recap ~264s first-wait (F-6e). OPEN, but the two quick
levers are now CLOSED as tested-not-viable: (a) reasoning_effort=low alone →
~38s but first-try validity ~75%→~33%; (b) reasoning_effort=low + json_object
on nvidia tested 2026-06-18 (7-run probe): REFUTED — 14% first-try / ~46%
within retry, worse than full-reasoning's 75% (low reasoning satisfies the
JSON format with minimal content, ~1 question — json_object guarantees
well-formed JSON, not correct content, so it is NOT a viable reliability lever
for the low path; deep reasoning is load-bearing for output completeness).
Genuinely-remaining lever = a true writing-class model, but per provider docs
that route (cerebras/Instruct) supports NEITHER json_object NOR reasoning_effort
— a separate, larger investigation, not a quick switch.                      → Stage 4.8 hosted-config pass / later quiz-perf tune
```

**Load-bearing invariant (F-6e):** exam-prep UX acceptability **depends on D1 pre-warm firing** at
AssessmentScope create/update (`assessments/service.py::_prewarm` → `prewarm_scope_pools`). It is what
keeps a *known* exam off the ~264s pool-generation wait (only ad-hoc first recaps pay it; reuse covers
everyone after). **Any future change to the pre-warm path must preserve this** — a regression there
silently reintroduces the 264s wait on exams. See ADR-047's F-6e amendment + [[steps/stage-06/6d-real-provider-smoke]].

Nothing in the completed work needs reverting. The provenance CHECK constraint, pinned model revision baked into the image, enqueue-after-commit, partial-unique one-active indexes, and the 401/403 boundary are correct and stay.

---

## Cross-cutting rules

Rules 1–5, 7–10, and 13 carry forward from v2 unchanged in substance:

### 1. Every stage has a browser gate
Backend scope, thin UI scope, UI proof obligation, browser gate, exclusions, knowledge updates. No backend-only acceptance.

### 2. Frontend can be thin, never fake
Plain forms and ugly tables are acceptable. Mocked frontend state, fake successes, hardcoded roles, and frontends pretending a backend feature exists are not.

### 3. Generated API client stays authoritative
OpenAPI change → regenerate TypeScript client → commit → consume via generated client or centralized wrapper. The only sanctioned direct-`fetch` exception remains `frontend/src/lib/api/upload.ts`.

### 4. Auth model stays unchanged
Supabase browser login → Bearer token → backend JWT validation → `GET /me` resolves app context (active memberships only). No `/auth/login` without an intentional redesign.

### 5. 401 and 403 are handled differently
401 → clear session, redirect to `/login`. 403 → keep session, render unauthorized state. Never redirect to login on 403.

### 6. AI is infrastructure, not feature code — AMENDED in v3
No direct model calls from feature services, ever:
```
LLMProvider → PromptRegistry → ContextBuilder → RateLimiter → AIRequestLog → OutputValidator
```
v3 additions:
- The provider stack lives in **`platform/llm`** — it is infrastructure consumed by domains. The `backend/app/ai/` placeholder is migrated or deleted in 4.5a.
- The `LLMProvider` interface defines **both `complete()` and `stream()` from day one**. `stream()` may raise NotImplemented until Stage 8.3, but the boundary shape is fixed now so Stage 8 pressure never becomes a reason to bypass the gateway. The deterministic test adapter implements the same interface.
  - **Annotation (4.5a, [[decisions/adr-028-llm-gateway-provider-separation]]):** the public `complete()`/`stream()` contract lives on **`LLMGateway`**, not `LLMProvider`. `LLMProvider` is a thin transport adapter (`send`/`stream_raw`); the gateway owns render/budget/limit/log/validate so a provider can never be invoked outside the chain. Intent preserved and strengthened.
- Every AI-generated artifact carries the **embedding-style provenance set**: `modelId`, `promptVersion`, `backendUsed`, source checksum / input hash, `generatedAt` — enforced by DB constraints where practical — plus an idempotency key per job and a one-active partial-unique index for in-flight jobs of that type. This closes v2 open item #2: the fields are confirmed for all AI tables.
- **AIRequestLog stores metadata and hashes, never raw transcript payloads.** Transcripts contain student speech; duplicating prompts into a log table creates a second PII store. Content hash plus optional truncated debug text only.
- Hard rule preserved: **AIRequestLog table + write path exist BEFORE the first K2Think call.**

### 7. Event spine starts in Stage 5
`StudentActivityEvent` lives in `platform/events`. Source action and event insert commit in the same DB transaction. Idempotency `source_id` points to the action instance. Gamification consumes events; it never owns them.

### 8. platform/query is read models only
Cross-domain reads live in `platform/query`; never business decisions. Domains own their writes and never import each other.

### 9. Testing standard for every browser gate
Real browser, real backend, real DB — no mocks on the critical path. Separate browser contexts for roles. True cross-origin CORS. Session asserted via `getSession()` + `GET /me`. E2E Supabase allowlisted; prefixed `e2e/{runId}/` storage keys; cleanup deletes only that prefix.

### 10. Stop-and-escalate
When plan and reality disagree, stop and write a findings note to `knowledge/steps/findings-{stage}.md`. A workaround that "makes the test pass" usually hides the exact problem the gate was built to find.

### 11. AI testing at the provider boundary — AMENDED in v3
CI/normal Playwright runs may use a deterministic LLMProvider test adapter **at the provider boundary only** — the full code path still runs (AIRequestLog written, provenance stored, output validated). Before any AI stage is FULLY VERIFIED, one dedicated E2E smoke runs against the **real** configured K2Think provider, recorded in `knowledge/steps/{stage}-real-provider-smoke.md`.
v3 additions: the real-provider smoke **asserts the model ID echoed in the response matches the configured identifier** (the IFM reference warns deployment aliases may differ from documented IDs). If the K2 reasoning level (Low/Medium/High) is a real request parameter — confirm at onboarding — it is part of the provider signature and logged per request.

### 12. Knowledge updates are mandatory in every session — AMENDED in v3
Every session lists exact files to update; knowledge files update in the same commit as code. v3 addition: **this roadmap's status table is part of those mandatory updates** for any stage-closing session.

### 13. Finding resolution
A finding is resolved only as: fixed in the current block / deferred to a named session / accepted with written rationale / rejected with explanation. Unresolved findings block FULLY VERIFIED.

### 14. Full E2E suite at every stage close — NEW in v3
The **entire active Playwright suite** re-runs when a stage closes, not just the new gate. Green inherited from a prior session's report is not green. **An archived spec is a deleted spec** — if an assertion matters (e.g. "students never see unpublished content"), it lives in the active suite or it does not exist.

### 15. AI capacity is budgeted in three dimensions; request count is sacred — NEW in v3
The K2 reference's "token volume is not the constraint" holds for chat-sized requests only. A full-transcript summary carries ~13–18k prompt tokens; at Nvidia's 105k TPM that is an effective ceiling of ~5 such calls/minute — TPM binds before RPM. Therefore:
- All AI calls pass through a **shared Redis limiter, per backend**, budgeting **requests/min** (20 Cerebras / 10 Nvidia), **tokens/min** (100k / 105k — prompt tokens computed before the call; completions capped by an explicit per-prompt `max_tokens` stored in the PromptRegistry), and **concurrency** (10).
- The limiter takes a **priority parameter** from day one so interactive traffic (Stage 8 assistant) keeps reserved headroom over background jobs — even while the MVP uses only the background priority.
- 429 backoff happens **inside the call path under the limiter**. RQ job retries are reserved for provider 5xx and invalid-output failures.
- Feature design minimizes call count: **one call per summary, one call per quiz generation — never per chunk, never per question.**

---

## Stage 4.5 — AI Infrastructure + Summary Generation

**Status:** ✅ FULLY VERIFIED (2026-06-11). 4.5a (platform/llm foundation) → 4.5b (first real K2Think
call, gate 2.B) → 4.5c (detailed summary, routing split live) → 4.5d (lecturer UI + browser gate +
full E2E + real-provider smoke). All three close-out gates green: full active E2E suite
([[steps/stage-04/4.5d]]), forced-fault browser coverage, and the real-provider smoke
([[steps/stage-04/4.5d-real-provider-smoke]] — PASS, model-ID echo matched on both routes, rule 11).
adr-025/026/027/028 recorded. Open (accepted-with-trigger, non-blocking, rule 13): F-4.5-27
(intended models inaccessible — switch-back = config/prompt edit), F-4.5-28 (backendUsed not
response-verifiable). Carry-forward to Stage 4.6: F-4.5-47 (RQ scheduler / per-request fault injection).

**Goal:** build the complete AI provenance and capacity infrastructure *before* the first K2Think call, then generate brief and detailed summaries.

**Hard prerequisites (block the stage from starting):**
```
1. IFM API key live and verified; exact model identifiers confirmed against the
   deployment (aliases may differ from docs); reasoning-level parameter semantics
   confirmed with IFM. Onboarding lead time is real — verify now, not at 4.5d.
2. Existing browser-gate assertions pinned to step-level facts
   (e.g. steps.embed === 'completed'), with a recorded regression run — so 4.5
   ADDS a pipeline step instead of rewriting prior gates. This ends the
   terminal-state churn (chunked → embedded → summarized) permanently.
3. Status projection supports per-step failure: "embeddings succeeded, summary
   failed" must be representable and visible. Stage 4.6 retry keys off this.
```

**Backend scope:** `platform/llm` (LLMProvider with `complete()` + `stream()` signatures; deterministic test adapter); PromptRegistry over a versioned flat-file `/prompts` directory — loaded and validated at startup, exposing name, version, content, `max_tokens`, model, backend, reasoning level (this closes v2 open item #1: **flat files, not a DB table** — git gives review/audit/deploy semantics free; the registry abstraction keeps a DB swap open post-MVP); the rule-15 Redis limiter; `AIRequestLog`; dedicated `ai` RQ queue + worker container (mirroring the embedding-worker isolation pattern); OutputValidator; `GeneratedLectureSummary`; brief + detailed generation as **two separate IngestionJob types** (`generate_brief_summary`, `generate_detailed_summary` — already enumerated in Slice 2); dev re-enqueue script.

**Key design locks (deviations recorded as ADRs):**
```
Routing split (ADR — deviates from Slice 2's Think-for-both):
  brief summary    → K2-V2-Instruct via Cerebras  (plain writing task; 32k context
                     fits a full transcript; separate rate budget)
  detailed summary → K2-Think-v0 via Nvidia        (reasoning task; 128k context)
  The two jobs draw on SEPARATE backend budgets and run concurrently; the brief
  summary lands in the UI while the detailed one is still generating.

Generation shape: ONE call per summary over the FULL normalized transcript text.
  Never map-reduce over chunks — chunks are Stage 8 retrieval infrastructure.
  A 90-minute lecture (~13–18k tokens) fits both models and the 65,536 request cap.

AIRequestLog row: feature, modelId, promptVersion, backendUsed, reasoning level,
  prompt/completion/total tokens (from the response usage field), latency, status
  (succeeded | failed | rate_limited | invalid_output), attempts, idempotency key,
  context refs (transcriptId, sectionId), input content hash, optional truncated
  debug text. Index (feature, created_at) — "tokens by feature by day" must be one
  query; this is the cost dashboard until real observability exists.

Provenance + idempotency mirror the embedding pattern: GeneratedLectureSummary
  carries sourceTranscriptChecksum + input hash + provenance set; the one-active
  partial-unique index pattern (migration 0007) extends to both summary job types.

Failure contract: a terminally failed summary job leaves a clean, retryable
  IngestionJob + AIRequestLog linkage. That record is the contract Stage 4.6's
  lecturer retry consumes. The 4.5 dev re-enqueue script is a development tool,
  not the product retry path.

Prompts carry the semantic filtering: normalization is structural-only by design,
  so the prompt explicitly instructs ignoring greetings, mic checks, admin
  announcements, small talk (Slice 2's list). The detailed-summary OutputValidator
  asserts the required section structure is present (Overview, Key Concepts,
  Important Definitions, Main Explanations, Examples, Exam-Relevant Points, Lab
  notes if applicable) — not merely non-empty text.

Backfill: transcripts completed before 4.5 will lack summaries. Dev path: the
  re-enqueue script. Product path: Stage 4.6 lecturer retry. Decided here so it
  never becomes an improvised migration.
```

**Thin UI scope:** lecturer sees summary generation status; lecturer views brief and detailed summaries. **Status badge rework (4.5d):** backoff polling, no 60-second hard timeout (limiter queueing + long completions + 429 backoff routinely exceed it), passive "generating" state, per-step failure display without stack traces.

**UI proof obligation:** the lecturer triggers the pipeline and *reads a real AI-generated summary* in the browser, produced through the logged AI infrastructure.

**Browser gate:**
```
Lecturer uploads transcript → parsed/chunked/embedded → both summary jobs run
→ AIRequestLog rows created → summaries stored with full provenance
→ lecturer sees brief summary first, detailed summary when ready
→ a forced invalid output is rejected, retried, and logged
```

**Sub-sessions (specs written before implementation):**
```
4.5a  platform/llm foundation: provider, registry, limiter, AIRequestLog,
      ai queue/worker, test adapter, dev re-enqueue script.
      HARD GATE: no K2Think call exists before this session lands.
4.5b  Brief summary generation (V2 / Cerebras) + ADR for the routing split
4.5c  Detailed study summary generation (Think / Nvidia) + section validator
4.5d  Lecturer summary UI, status badge rework, browser gate,
      real-provider smoke (rule 11, with model-ID assertion)
```

**Done means:** AIRequestLog exists before the first call; both summaries generated through the full stack; provenance + token usage stored; deterministic adapter used in CI at the provider boundary only; real-provider smoke recorded; full E2E suite green (rule 14); browser observes the result.

**Exclusions:** no quiz/glossary/assistant generation, no lecturer editing of summaries, no student visibility (4.7), no streaming transport (8.3 — interface only), no map-reduce summarization.

---

## Stage 4.6 — Replacement / Retry / Supersession

**Status:** IN PROGRESS. **4.6a foundation BACKEND VERIFIED** (2026-06-11): lifecycleState migration +
lineage (`is_active` removed), one-active + one-pending indexes, section-locked pending creation +
`tryActivatePendingTranscript` atomic swap, `transcripts/domain/summary_eligibility` + read-only
`ActiveTranscriptSummaryResolver`, per-row provenance stamps, env-gated pipeline fault harness; backend
305 passed, migration 0010 round-trips on a fresh DB, frontend `tsc` clean. See
[[specs/stage-04/4.6a-lifecycle-supersession-foundation]] / [[steps/stage-04/4.6a-lifecycle-supersession-foundation]],
[[decisions/adr-029-transcript-replacement-atomic-swap]], [[decisions/adr-030-summary-eligibility-domain-resolver-split]].
**4.6b retry BACKEND VERIFIED** (2026-06-11): lecturer retry endpoint
(`POST …/transcript/{transcriptId}/retry`) resumes from the earliest failed step over the DAG; summaries
decoupled to fork from parse (embed failure no longer blocks summaries); every destructive write fenced
against superseded/stale attempts; sanitized `failureCategory` + `retryable` on the status projection;
migration 0011 (failure-category enum + parse one-active index). Backend 329 passed, fresh-DB round-trip,
tsc clean. See [[specs/stage-04/4.6b-retry-fencing-failure-taxonomy]] /
[[steps/stage-04/4.6b-retry-fencing-failure-taxonomy]], [[decisions/adr-031-retry-resume-from-failed-step-fenced]].
**4.6c recovery BACKEND VERIFIED** (2026-06-11): stuck-row reaper (step-aware, RQ-registry/age liveness,
fenced `crashed` producer, singleton-locked, startup + admin trigger) + loss-safe storage reconciliation
(report-only default, grace window, prefix-scoped, deletion-capped, superseded retained, missing reported
never auto-fixed) + `MaintenanceRun` table (migration 0012) + admin maintenance endpoints. Backend 344
passed, fresh-DB round-trip, tsc clean. See [[specs/stage-04/4.6c-recovery-reaper-reconciliation]] /
[[steps/stage-04/4.6c-recovery-reaper-reconciliation]], [[decisions/adr-032-stuck-row-reaper-singleton]],
[[decisions/adr-033-storage-reconciliation-loss-safe]].
**4.6d lecturer UI + preview endpoint BUILT** (2026-06-11): active-summary preview endpoint (lecturer-only,
over the resolver, `hasPendingReplacement`, NO student surface) + lecturer Replace (inline confirm +
double-replacement warning) / Retry / per-step states / sanitized reason / "new version processing" badge on
the 4.5d surface; browser-gate spec (`4.6d-replace-retry.spec.ts`: retry flow + replacement continuity) +
the deterministic fencing pytest; fixed the cross-stage e2e breaks (4.3.5e 409→pending, db.mjs
lifecycle_state). Verified: backend 349 passed, frontend tsc clean, client regen, 9 e2e specs compile.
See [[specs/stage-04/4.6d-lecturer-ui-browser-gate]] / [[steps/stage-04/4.6d-lecturer-ui-browser-gate]].
**Stage 4.6 FULLY VERIFIED** (2026-06-11): the live browser gate ran GREEN — full active Playwright suite
**9/9** (4.3.5b/c/e, 4.4, 4.5d-summary-browser, 4.5d-summary-fault ×2, 4.6d replacement-continuity + retry)
against a backend image content-hash-verified against branch HEAD. The gate caught + fixed **two
cross-stage-seam regressions** that per-session "backend verified" structurally could not (both lived
between sessions): **F-4.6c-1** (4.6c startup recovery poisoned the fork-per-job module engine pool →
isolated NullPool engine + `tests/test_worker_startup_recovery.py`) and **F-4.6b-2** (4.6a activation
trigger orphaned by the 4.6b DAG decouple → every leaf attempts idempotent activation + 3 ordering tests).
Deferred: **F-4.6d-3** (C-lite read-contract violation in the post-retry status path → owner 4.6d-P1;
production-masked). See [[findings-4.6-gate]] + [[decisions/adr-032-stuck-row-reaper-singleton]]
(pre-fork connection-clean invariant). Dev `xyz_lms` migrated 0009→0012 at cutover. Closes Stage 4.6.

**Goal:** make transcript replacement and failed-processing recovery safe and observable.

**Backend scope:** replace active transcript (old superseded, new active); **retry covers all five job types** — parse / chunk / embed / generate_brief_summary / generate_detailed_summary; retry idempotency; stale-summary detection via `sourceTranscriptChecksum` mismatch; replacement triggers full regeneration; no mixed old/new student state; failure-reason persistence; recovery for the deferred stuck-row states (uploaded / parsing / queued after crash or enqueue failure); **storage reconciliation job** — periodic diff of object-store keys against DB keys, reporting and cleaning orphans (replacement multiplies the orphaning opportunities; this debt gets an owner here).

**Thin UI scope:** lecturer replace-transcript button; retry-failed-processing button; old/new active status; per-step failed/retrying/completed states.

**UI proof obligation:** the lecturer forces a failure, clicks retry in the browser, watches it reach completed; then replaces a transcript and sees only the new one active with regenerated summaries.

**Browser gate:**
```
Upload → step forced to fail → lecturer clicks retry → reaches completed
Replace transcript → old superseded → new active → summaries regenerate
→ student-visible state never mixes old and new
```

**Testability rule (carried):** failure steps use deterministic E2E-only fault injection or seeded failed-job records — never random failure or manual DB edits. Fault injection must be impossible outside E2E/test environments.

**Done means:** replacement and retry safe; no duplicate segments/chunks/summaries from retry; reconciliation job runs and reports; browser verifies both flows; full suite green.

**Exclusions:** no transcript editing, no speaker correction, no Zoom import, no summary approval workflow.

---

## Stage 4.7 — Student-Facing Summaries

**Status:** ✅ **FULLY VERIFIED** (2026-06-12, human-stamped after P1 assertion-strength audit + Steps 1–3
on main). Spec v1.1 (LOCKED): 4.7a backend boundary (`StudentSummaryAccessPolicy` §5; §6 precedence with
corruption≠supersession pinned; scoped module-level read model; §8.3 hygiene; migration 0013) + 4.7b thin
student UI (4 per-slot states, bounded polling, react-markdown raw-HTML-off). **Verified ON MAIN:** backend
**389 passed**; full active Playwright suite **11/11** (9 success serial + 2 fault); G1–G9 met. **P1 (Stage 3
content-visibility E2E) restored to the active suite + green, no drift.** Review R1 (sentinel canary
strengthened — proven non-vacuous), R2 (the `--workers=1` need classified CAPACITY: embed RQ-retries
3×[30,120,300]s → non-terminal, GAP ruled out; non-blocking), R3 (row-3 unit test added) all resolved.
ADR-034..039. Landed via two attributable merges: 4.6d-P1 (`fe9d924`) → 4.7 (`0e0654f`). Dev `xyz_lms` at
0013. See [[steps/stage-04/4.7a-student-summary-read-policy]],
[[steps/stage-04/4.7b-student-page-browser-gate]], [[steps/stage-04/4.7-stage3-restore]].

**Hard prerequisite (MET):** the Stage 3 content-visibility E2E spec is **restored to the active suite** —
re-authored as `tests/e2e/4.7-stage3-content-visibility.spec.ts` (no committed spec existed) and green
as-is against the current contract. "Students never see unpublished content" now has a live browser
regression before the student surface was extended.

**Backend scope:** student-facing summary read projection; published-section and assigned-module enforcement; processing/unavailable fallback states; no raw transcript exposure.

**Thin UI scope:** student lecture/lab page; brief + detailed summary display; processing state; unavailable state.

**UI proof obligation:** a student opens a published lecture and *reads both summaries* — and cannot see the raw transcript or any unpublished section.

**Browser gate:**
```
Student opens published lecture/lab → sees brief + detailed summary
→ does NOT see raw transcript → unpublished section hidden
→ unassigned student cannot access summary (404, not 403)
```

**Done means:** summaries visible only when allowed; fallbacks clean; restored Stage 3 spec passing in the active suite; full suite green.

**Exclusions:** no quiz generation, no glossary, no student AI chat, no transcript viewer.

---

## Stage 4.8 — First Hosted Deploy (Staging) — NEW in v3

**Status:** DEFERRED-WITH-OWNER (D-12-A — no hosted environment; blocked on an external university hosting decision). Its deploy-prep deliverables (release-phase migration, managed-PG `vector`/`pgcrypto` bootstrap, secrets, repeatable deploy script, hosted CORS origins, environment hygiene) are **folded into Stage 12f** and produced there as a documented procedure proven on a local production-candidate build. The first real hosted deploy + Stage 8.3 SSE remain deferred-with-owner (`docs/go-live-checklist.md`).

**Why here:** after 4.7 the pipeline exercises every infrastructure component end-to-end (DB, storage, three worker types, AI provider, migrations) — the natural first hosted smoke. Stage 12 as the first deployment rehearsal is a classic trap, and there is one specific technical forcing function: **SSE breaks under buffering proxies, and discovering that during Stage 8.3 is expensive.** Platform constraints get discovered here, cheaply.

**Backend / infra scope:** hosted environment for Postgres (managed, with `vector` + `pgcrypto` bootstrap — closes F006), Redis, backend, all three workers, frontend; **explicit release-phase migration step** (migrations do not auto-run on boot — deliberate locally, fatal if forgotten hosted); secrets handling; repeatable deploy script; hosted CORS origins; **environment hygiene** — `NEXT_PUBLIC_E2E_TEST_HOOKS` and all fault-injection flags absent/disabled in hosted builds (same principle as the Stage 4.6 fault-injection rule, applied to the token-override hook).

**Thin UI scope:** none new — the existing product, served from a hosted URL.

**UI proof obligation:** the full lecturer→student summary path runs in a real browser **against the staging URL**, including one real K2Think-generated summary.

**Browser gate:**
```
Against staging: admin creates module → lecturer uploads transcript
→ pipeline completes on hosted workers → student reads both summaries
→ health endpoints green → migration step ran as a release phase
```

**Done means:** repeatable deploy documented; extension bootstrap automated; E2E hooks verifiably absent; smoke recorded in knowledge.

**Exclusions:** production hardening, autoscaling, CDN, custom domains, observability stack, CI/CD beyond the deploy script (all Stage 12 territory).

---

## Stage 4.9 — Frontend Foundation + Platform Hygiene — NEW in v3

**Status:** NOT STARTED.

**Why here:** Stages 5–8 are the heavy student-facing UI (quiz attempt flow, glossary, assistant workspace). Building three stages of UI in inline styles with zero unit tests means repainting and retro-testing all of it at Stage 12. The thin 4.5d/4.7 panels were cheap to build either way; the quiz UI is not.

**Scope:**
```
Styling system: adopt Tailwind. App shell + shared components restyled; full
  retroactive repaint NOT required; all Stage 5+ UI must use it.
Unit test harness: Vitest. First real tests target the highest-value logic:
  wrapper.ts auth recovery (401/403 mapping), status badge step mapping,
  SessionProvider state transitions.
Hygiene batch (one tidy-up commit):
  - pin httpx deliberately or migrate tests to ASGITransport (the 83 deprecation
    warnings mean a future upgrade breaks the suite)
  - drop CORS allow_credentials=True or keep it with a written justification
    (pure Bearer auth does not need it)
  - add a client-regen alias to frontend/package.json (F008)
```

**UI proof obligation / browser gate:** per rule 14 — the **full existing E2E suite green after the restyle**, type-check green, unit tests running in CI. The gate proves the restyle broke nothing.

**Exclusions:** visual redesign, design polish, component-library buildout beyond immediate needs.

---

## Stage 5 — Shared Quiz Engine + Event Spine

**Status:** ✅ **FULLY VERIFIED** on branch `spec-5` (not yet merged). 5a schema/event spine, 5b
generation/recovery, 5c HTTP surface, 5d student UI + browser and real-provider gates, and 5e review
fixes are complete. Latest verification recorded in [[steps/stage-05/5e-review-finding-fixes]]:
backend `442 passed`; frontend `tsc --noEmit` exit 0; Gate 1 browser and Gate 3 real-provider smoke both
green. Merge-time caveat: migration block 0014-0020 collides with sibling 0014-0016 work and must be
renumbered/rebased before landing on `main`.

**Goal:** shared MCQ engine + the platform activity event spine.

**Backend scope (v2 carried):** `QuizDefinition`, `QuizAttempt`, `QuizQuestion`, `AnswerOption`, `StudentAnswer`; `MistakeRecord` minimum schema (`retake_correct_count`, `show_in_retake_prefix`, `source_quiz_definition_id`, `source_question_snapshot`); post-class quiz availability after detailed summary; attempt created on start; AI question generation through the 4.5 infrastructure; validation; shuffling (correctness on option identity, never display letter); immediate submission; mistake creation; `StudentActivityEvent` in `platform/events` with atomic insert and idempotency keys.

**v3 additions:**
```
Generation shape: ONE AI call per quiz generation — never per question (rule 15).
Structured output via FUNCTION/TOOL CALLING (the API supports it): schema
  enforcement at the provider beats regex-parsing free text before the
  OutputValidator even runs.
Pagination envelope: the first large lists land here (attempts, mistake bank).
  Define the standard envelope now; every later list (glossary, conversations,
  events) reuses it. Retrofitting pagination at Stage 7 is the wrong time.
Schema future-proofing: questions belong to attempts (locked, correct), but the
  schema must NOT preclude a Stage 6 question POOL per QuizDefinition (generate
  into a pool, sample fresh combinations per attempt). Flag in the spec; the
  decision itself is Stage 6's.
```

**Thin UI scope:** student sees post-class quiz available; starts; answers; immediate feedback; completes; sees score. Built on the 4.9 styling system.

**UI proof obligation:** a student answers a question and sees correct/incorrect feedback *immediately* in the browser — and a wrong answer visibly becomes a recorded mistake.

**Browser gate:**
```
Student opens lecture/lab with completed summary → post-class quiz available
→ starts attempt → generated questions appear → answers → immediate feedback
→ wrong answer creates mistake → completed_quiz event inserted
  (same transaction as the score)
```

**Exclusions:** recap/exam-prep/mistakes-bank modes; retake-reinforcement UX; leaderboards; graded exams.

---

## Stage 5.5 — Module Schedule & Section Metadata — NEW in v3

**Status:** ✅ **FULLY VERIFIED** (2026-06-17, branch `stage-55`). 5.5a fixed-template replacement is
committed at `76f496f` (schedule required, 0020 schedule provenance, 28-section oracle). 5.5b e2e
suite rework is committed at `ab017db` (observed 10-red run mapped, fixes applied,
`playwright --list` clean, quarantine 0), and 5.5b feature work is committed at `5a7fb15`
(metadata-edit endpoint + D13 recompute guard + `platform/query` stored-week resolver; backend
**413 passed**, ruff clean). 5.5c is committed at `adbd507` (`section_assets.asset_kind` migration
`0021`, lab `.ipynb` attachments, backend streaming downloads with `nosniff`, upload-time lab
`dueAt`, no-pipeline DB assertion; backend **418 passed**, ruff clean, frontend `tsc --noEmit`
clean). 5.5d is committed at `991e1db`: no per-module dev schedule map exists, so all recreated dev
modules use the reference schedule; the actual dev run migrated `stage-55` DB to `0021`, replaced
16 modules, generated 448 stamped sections, removed all legacy template titles, and seeded one
published lab with processable PDF + attachment notebook assets. 5.5e is committed at `5b00f04`:
thin admin/lecturer/student UI and browser gate prove schedule preview/create, resolver-backed by-week
views, metadata edit, lab PDF + `.ipynb` upload with `dueAt`, student deadline display, and
`assetKind` download routing. Final verification: Stage 5.5 browser gate GREEN; reference schedule
exactly **28 sections** (21 lectures, 7 labs, 0 Friday, 7 weeks); full active Playwright suite
**12/12 passed** after reseed; backend **424 passed**; ruff clean; frontend `tsc --noEmit` exit 0;
fresh DB migration upgrade→base→upgrade round-trip originally passed on the pre-merge branch, and
5.5g rebased the migration chain after Stage 5 merged: Stage 5 main ends at `0020`, Stage 5.5 schedule
config is now `0021`, and lab attachment asset kind is now `0022`. The post-rebase Alembic round-trip
passed and `alembic heads` reports a single `0022 (head)`. ADR-040, ADR-041, ADR-042, ADR-043. See
[[steps/stage-05/5.5a-schedule-generation]],
[[steps/stage-05/5.5b-metadata-edit-and-week-resolver]],
[[steps/stage-05/5.5c-lab-attachments]],
[[steps/stage-05/5.5d-dev-reseed]],
[[steps/stage-05/5.5e-ui-browser-gate]], and
[[steps/stage-05/5.5g-migration-chain-rebase]].
**May run in parallel with Stage 5** (admin domain, not quiz domain). **Hard prerequisite for Stage 6**;
also feeds Stage 8.6 (time management) and Stage 11 (calendar seeding).

**Why:** `week_number`, `session_date`, `due_at` exist in the schema but are never populated — module creation emits a fixed 4-section template, not the schedule-driven structure Slice 1 specifies. Recap quizzes (date range), exam-prep quizzes (covered weeks), assistant time-management, and the agent's calendar all resolve scope through exactly these fields. Without this session, Stage 6 stops at a findings note in its first week.

**Backend scope:** module creation accepts schedule parameters (course dates, lecture days, lab days) driving section generation; admin can set/edit `week_number` / `session_date` / `due_at` per section; **dev reseed replaces existing modules with reference-schedule modules**; week→sections resolution query in `platform/query`.

**Thin UI scope:** admin schedule fields on module creation; per-section metadata editing in the admin UI.

**UI proof obligation:** an admin sets schedule values in the browser and a week-scoped query visibly resolves the correct sections.

**Browser gate:**
```
Admin creates module with schedule → sections carry week/date metadata
→ admin edits a section's week → coveredWeeks=[7,8] resolves exactly the
  right sections → lecturer/student views unchanged
```

**Exclusions:** lecturer section creation/delete/reorder (still excluded per Slice 1), timetable UI, calendar features (Stage 11).

---

## Stage 6 — Complete Quiz Modes

**Status:** ✅ **FULLY VERIFIED** (2026-06-18). Sub-sessions 6a–6d implemented; closure was unflipped
after review found the 6d gate skipped core proof obligations and failed-pool retry was unwired
([[specs/stage-06/6e-corrective-closure]]). Corrective session 6e fixed those (full retake-prefix-drop +
bank-persistence browser proof, wired failed-pool retry through the UI, exam-prep event + retake-reuse
assertions, ORM CHECK aligned). The final blocker — the rule-11 real-provider smoke "hard timeout" — was
re-diagnosed live (F-6e): K2-Think-v2 reasons inline and rambles to fill `max_tokens`, so `stream:false`
wall-clock ≈ `max_tokens`/~73 tok/s; 32000 ≈ 440s crossed 540 under variance. Fixed by trimming the
request (`max_tokens` 32000→20000, count 24→16, validator floor 16→12) and setting the reasoning-route
timeout 240→330 (lease TTL 360); the rule-11 smoke is retry-aware (mirrors `AI_RQ_RETRY_MAX`).
**Smoke PASS** (264.5s, 16Q, model echo `MBZUAI-IFM/K2-Think-v2`); full active Playwright 14/14; 5d/6d
gates green; backend 502. Route kept nvidia (cerebras = same speed; `use_nvidia` performance-inert) and
`reasoning_effort=low` evaluated + rejected for now (7× faster but halves output validity). See
[[steps/stage-06/6d-real-provider-smoke]] (2026-06-18) + ADR-047 F-6e amendment. **Carried debt:** the
~264s ad-hoc-recap first-wait (reasoning_effort future-opt) + the load-bearing D1 pre-warm invariant are
both recorded in the carried-debt ledger above.
**Prerequisite satisfied:** Stage 5.5 is FULLY VERIFIED.

**Backend scope (v2 carried):** `recap_period`, `exam_prep`, `mistakes_bank`; assessment scope by covered weeks (`AssessmentScope`); mistake-review prefix; retake reinforcement (`retakeCorrectCount`; prefix flag flips false after 2 correct retake answers; mistake stays in the bank).

**v3 addition — capacity decision (ADR required):**
```
The exam-week math: 30 students each starting a 6-section recap
= 180 Nvidia calls ≈ 18 minutes of queue at 10 RPM.
Resolve via question pool + per-attempt sampling (generate per section into a
pool; sample fresh combinations per attempt — preserves "retakes get new
questions" while cutting calls by an order of magnitude), OR explicitly accept
queue-wait UX with a visible generating state. Decide here; Stage 5's schema
was kept compatible with either answer.
```

**UI proof obligation:** a student retakes a quiz, sees missed questions first, answers one correctly twice across retakes, sees it drop from the prefix — while still finding it in the mistakes-bank quiz.

**Browser gate:**
```
Original quiz with mistakes → retake starts with mistake-review prefix
→ 2 correct retake answers → mistake leaves prefix → remains in bank
Lecturer defines covered weeks → exam-prep quiz draws from scoped summaries
```

**Exclusions:** formal grading, lecturer question bank, proctoring, adaptive engine, generation from raw transcript.

---

## Stage 7 — Interactive Glossary & Practice

**Status:** 7a (foundation) + 7b (flashcards) + 7c (multiple-choice) **FULLY VERIFIED** on branch `stage-7` (migrations `0030`+`0031`). Backend **498 passed**; migration round-trip green; frontend `tsc` exit 0; real-provider smoke GREEN against `https://api.k2think.ai/v1/chat/completions` with Cerebras route and response model echo `MBZUAI-IFM/K2-Think-v2` matching the configured prompt model; Stage 7 browser gate GREEN (`1 passed`); full active E2E suite GREEN (`14 passed`). Smoke note: `finish_reason='length'`, so a low-priority follow-up is open to raise glossary definition `max_tokens`. 7d (quiz-highlight) is the remaining sub-stage and is now unblocked because Stage 6 is closed. See [[steps/stage-07/7a-glossary-foundation]], [[steps/stage-07/7bc-glossary-practice]], [[steps/findings-stage-07]], [[decisions/adr-047-glossary-subject-folder-separation]], [[decisions/adr-048-glossary-definition-cache-collapse]].

**Scope as v2 / Slice 6:** folders, entries, source references, definition cache (key: normalizedTerm + subjectId + entryType, invalidated on promptVersion change — which aligns exactly with the flat-file PromptRegistry), review state, flashcards with hardcoded intervals, Learn/Test MCQ reusing Stage 5 mechanics, server-side duplicate detection, `TranslationService` abstraction + K2Think adapter, glossary activity events, `<SaveToGlossary>` shared component, KaTeX integrated early.

**v3 notes:** definition generation uses the configured glossary prompt model (`MBZUAI-IFM/K2-Think-v2`
in the Stage 7 core smoke) via the Cerebras route through the shared limiter and `ai` queue — no new
infrastructure; cache-hit = no model call is the primary cost control; 500-char context cap enforced
server-side; entry lists use the Stage 5 pagination envelope.

**UI proof obligation:** a student highlights text in a real summary, saves it, watches the AI definition fill in asynchronously, then practises that term — all in the browser.

**Browser gate:** as v2 (save → duplicate check → entry appears → definition job → status updates → flashcards → Learn/Test → activity event).

**Exclusions:** as v2 (no shared glossary, no transcript sources, no OCR, no advanced SRS, no AI auto-saving).

---

## Stage 8 — Personal AI Assistant

**Status:** NOT STARTED.

**Backend scope (v2 carried):** conversations, folders, messages, context snapshots, tool actions; server-side context resolver; retrieval service; SSE streaming (the sanctioned FastAPI direct-path exception); mode coordinator; history; save-to-glossary action.

**v3 additions:**
```
8.3 implements the SSE TRANSPORT over the provider stream() that has existed
  since 4.5a — no provider rewrite, no gateway bypass. Validate SSE against the
  STAGING proxy (4.8) early in 8.3; buffering proxies are where SSE dies.
Assistant calls use the INTERACTIVE priority in the shared limiter — the
  headroom reserved since 4.5a is consumed here for the first time.
ContextBuilder enforces per-mode token budgets: 32k (V2 / general chat) vs
  128k (Think / reasoning modes) per the routing table.
Retrieval: exact pgvector scan under module/transcript filters — candidate
  sets are small at MVP scale. NO ANN index (IVFFlat/HNSW) until real query
  patterns justify one; adding it later is an ADR.
```

**Sub-sessions (as v2):** 8.1 conversation/history foundation → 8.2 context resolver + retrieval → 8.3 SSE streaming → 8.4 lecture breakdown + floating widget → 8.5 save-to-glossary → 8.6 homework/exam/time-management modes (8.6 consumes Stage 5.5 schedule data). Each gets its own spec and browser gate before the next begins.

**UI proof obligation:** a student on a lecture page asks a question and sees the answer *stream in token by token* — grounded in that lecture's context, with no access to unpublished material.

**Exclusions:** as v2 (no unrestricted chatbot, no autonomous slide switching, no auto-solving, no lecturer chat monitoring, no voice/video).

---

## Stage 9 — My Progress Dashboard

**Status:** ✅ FULLY VERIFIED (2026-06-18). Stage 9 shipped the My Progress dashboard with deterministic grade forecasting, target-grade persistence, progress/mastery snapshots, privacy-safe aggregate class benchmarking, and a seeded E2E demo path. It was rebased after Stage 8.2 so migrations `0038` and `0039` follow assistant head `0033`; the single-tenant MVP decision is ADR-052 because Stage 8 already owns ADR-050 and ADR-051.

**v3 addition — ADR checkpoint at stage entry:** before Stages 9–11 add their table wave (~15 tables), record an ADR on the **institution/organization model**. "Single-tenant for MVP" is an acceptable answer — but it must be a recorded decision, not an accident, because retrofitting tenancy across that many tables later is a rewrite.

**Scope as v2 / Slice 7:** progress and topic-mastery snapshots, `CourseGradeScheme` (boundaries in DB, never hardcoded; F/U/WF as distinct fail types), `GradeComponent` (weights sum to 100%), grade records, **deterministic forecast engine** (`requiredRemainingAverage = (target − current) / remainingWeight`), goals, anonymized class-average benchmarking, seeded data on production-like schemas, placeholder gamification section.

**UI proof obligation:** a student picks a target grade and sees a deterministic forecast — including a clearly shown "impossible" result when the math says so.

**Exclusions:** as v2 (no live LMS integration, no rankings, no named comparisons, no mental-health diagnosis).

---

## Stage 10 — Gamification

**Status:** ✅ **FULLY VERIFIED** (2026-06-20; merged to main 2026-06-21). One unified Learning streak
and four badge families, derived/evaluated **on read**, reproducible from `StudentActivityEvent` + Stage 5.5
schedule + Stage 9 snapshots, **never awarded by the frontend**, idempotent + sticky. Decisions A/A/A
(flashcard volume = distinct local days with a completed flashcard session; `COURSE_TIMEZONE` platform
setting; Tailwind panel) — ADR-056, ADR-057. Migrations **0080** (event-type CHECK widen +
`studied_section`, content-domain-owned) + **0081** (`student_badges` + `student_streak_state`), chained
off `0041`; fresh-DB `upgrade → downgrade 0041 → upgrade` round-trips to a single head `0081`. Backend
full suite green incl. **35 new gamification tests** (pure streak edges, query primitives incl. tz/day-end
boundary, on-read award + idempotency + stickiness + distinct-source anti-farm, concurrent first-read
`newBadgeIds`, `nextScheduledDay`, topic/module rules, reconcile == stored, studied_section once-per-day +
read-survives-on-error, API 403/shape/award) + the shared-CHECK union guard; `reconcile_gamification.py`
runs clean. Frontend: client regenerated
(`GamificationService`), `GamificationPanel` (Tailwind, **zero new inline-style/design-token
violations**), `tsc` clean, **12/12 vitest** (incl. 3 new panel tests). **Live browser gate RAN GREEN**
on a real Supabase-backed stack (owner-provided `.env`/`.env.e2e`; isolated alt-port `da-nang-stage10-*`
images on :8025/:3025, production-built frontend to fit the 7.7 GiB Docker VM shared with sibling
workspaces): `tests/e2e/10-gamification.spec.ts` **Scenarios A/B/C all pass**. The gate CAUGHT a real
wrong-endpoint bug — `studied_section` was hooked on the content route the student UI never calls; fixed
by moving the emission to the real student-summary read (`student_summaries.get_student_section_detail`)
via the shared `platform/events.record_studied_section` helper, content hook reverted, re-verified
(19 backend tests). **Final rule-14 full active suite: 24/24 PASSED** on the standard clean single-workspace
stack after rebuilding `kyiv-backend:latest` from this workspace source (`sha256:5165e220…`), resetting the
app DB, migrating to `0081`, exporting `.env.e2e`, seeding standing users, recreating workers, and prewarming
Next routes. Command: `E2E_RUN_ID=e2e-stage10-full-clean-20260620230826 PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1`
→ **`24 passed (6.3m)`**. The required fault-injection gates were green in that run: `4.5d invalid_output`
and `4.5d invalid_input` recreated `ai_worker`; `4.6d retry` recreated `embedding_worker`; all used the
fresh `kyiv-backend` image. Earlier 21/24 isolated-run failures were environment/image-tag contention, now
resolved by the clean-stack proof. Post-review hardening then re-ran the fresh-DB Alembic round-trip,
confirmed single head `0081`, ran full backend `660 passed`, frontend `tsc` + unit `12 passed`, updated
architecture docs, and reran the full active Playwright suite:
`E2E_RUN_ID=e2e-stage10-reviewfix-20260620234724 PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1`
→ **`24 passed (6.4m)`**. 7-glossary needed the standard `.env.e2e` export (it reads
`process.env.SUPABASE_SERVICE_ROLE_KEY`) — included in the final runs. **Parallel-with-Stage-11:** event consumer only, no scheduler; Stage 10 is the `0080→0081` mainline migration segment, and the next branch that lands must re-run the Alembic round-trip + full Playwright suite after rebasing. Carry-forward:
`COURSE_TIMEZONE` is required hosted config at Stage 4.8. See [[specs/stage-10/10-gamification]],
[[plans/stage-10/10a-foundation]], [[steps/stage-10/10a-foundation]],
[[decisions/adr-056-gamification-course-timezone]], [[decisions/adr-057-gamification-on-read-evaluation]].

Streaks (timezone-aware, scheduled-day-based attendance), badges, progress — all consumed from `StudentActivityEvent`, reproducible from events, never awarded by the frontend. Gate: a completed quiz visibly updates streak and badge progress in My Progress via the event path.

---

## Stage 11 — Proactive AI Agent & Analytics

**Status:** IN PROGRESS. 11.1 (roster risk + scheduler), 11.2 (student detail + recommendations), and 11.3
(assessment analysis + question insights) are **FULLY VERIFIED**. Current Alembic head remains `0057`; 11.3 added
no migration and no AI. Latest 11.3 evidence: backend `661 passed`; frontend type-check + unit `12 passed`; 11.3
browser gate `1 passed`; final full active Playwright `24 passed (8.4m)`. Remaining Stage 11 sub-sessions are not
started. See [[steps/stage-11/11.1-roster-risk-scheduler]], [[steps/stage-11/11.2-student-detail-recommendations]],
[[steps/stage-11/11.2-real-provider-smoke]], [[steps/stage-11/11.3-assessment-analysis-question-insights]], and
[[steps/stage-11/findings-11.1-gate-run]].

**v3 addition:** the backend scope explicitly includes a **scheduler component** (rq-scheduler or a cron container). RQ alone cannot express "daily 6:00 AM recalculation" or "48-hour pre-deadline check" — every 11.x spec that assumes scheduled triggers depends on this existing, so it lands in 11.1.

**Scope as v2 / Slice 5:** `AgentRun`, performance/risk snapshots, recommendations, assessment analysis + question insights, internal calendar, availability settings, workload plans/items; deterministic risk classification (every label traceable to `riskReasons` + `supportingMetrics`); 6-phase planning algorithm; `.ics` export; **AI explains deterministic output — it never calculates risk or grades**; no auto-sent messages; estimates stored on records, not hardcoded.

**Sub-sessions (as v2):** 11.1 roster + risk (+ scheduler) → 11.2 student detail + recommendation draft → 11.3 assessment analysis → 11.4 workload planner → 11.5 .ics export → 11.6 grade-forecast advice. Deterministic rules land before AI explanation layers.

**Exclusions:** as v2 (no live LMS metrics, no Google OAuth, no autonomous messages, no black-box scoring, no auto-rescheduling).

---

## Stage 12 — Release Hardening

**Status:** IN PROGRESS — 12a–12e FULLY VERIFIED; **12f closes the stage as deploy-ready / production-candidate** (D-12-A: no hosted environment yet; the real staging→production promotion is deferred-with-owner — see §7 of the master spec and `docs/go-live-checklist.md`).

**Backend scope (v2 carried + v3 additions):** security pass; authorization review (**including the `can_publish` role-vs-membership derivation**); migration review; worker retry/failure review; rate-limit review; load checks; logging/observability; deployment rehearsal — **documented and proven on a local production-candidate build (D-12-A); 4.8 never executed (no hosting), so the real staging→production promotion is deferred-with-owner**, out of Stage 12's executable scope.
v3 additions:
```
Global exception handlers / consistent error envelope (no raw default 500 bodies)
Signed-URL revocation decision: implement revocation, or accept the TTL window
  with written rationale (finding-resolution vocabulary applies)
Verify the 4.6 storage reconciliation job in the rehearsal
Verify E2E hooks and fault injection are absent from the production build
AIRequestLog cost review: tokens by feature by day, against IFM budgets
```

**Browser gate (end-to-end smoke):** the full MVP path — admin → lecturer content + transcript → pipeline → summaries → student studies → quiz → mistake → glossary → assistant → progress → gamification → analytics — runs in a real browser against the production-candidate environment without manual intervention. Stages 9 and 11 verify against their designed seeded flows (live LMS integration remains explicitly out of scope).

---

## Post-MVP watchlist (triggers, not tasks)

```
Embeddings → separate table keyed (chunk, model, revision, version)
                                      when a second embedding model arrives
Second StorageProvider (R2/S3)        when hosting economics demand it
Signed-URL revocation                 if the Stage 12 TTL acceptance is revisited
Transcript retention/deletion policy  BEFORE any real-student deployment —
                                      recordings of identifiable people stored
                                      indefinitely is a policy decision, not a default
DeepL translation adapter             post-MVP per Slice 6 (adapter swap only)
Shared glossary save entry-type picker
                                      small dedicated follow-up for summary + chat saves
Zoom import                           as a source adapter into the SAME pipeline
Multi-institution model               per the Stage 9 ADR
OpenAI embeddings option              if retrieval quality demands (Slice 5 note)
```

---

## Updated stage ordering

```
✅ 0 → ✅ 1 → ✅ 2 → ✅ 3 → ✅ 4.1 → ✅ 4.2 → ✅ 4.3 → ✅ 4.3.5 → ✅ 4.4 → ✅ 4.5
✅ 4.5  AI infrastructure + summaries     (4.5a → 4.5b → 4.5c → 4.5d)  FULLY VERIFIED
4.6  Replacement / retry / supersession / reconciliation        ← next
4.7  Student-facing summaries             (prereq: Stage 3 spec restored)
4.8  First hosted deploy (staging)
4.9  Frontend foundation + hygiene
5    Quiz engine + event spine
5.5  Module schedule & section metadata   (parallel-OK with 5; blocks 6)
6    Complete quiz modes                  (prereq: 5.5; capacity ADR)
7    Glossary
8    Assistant                            (8.1 → 8.6)
9    My Progress                          (entry ADR: org model)
10   Gamification
11   Proactive analytics                  (11.1 → 11.6; scheduler in 11.1)
12   Release hardening
```

---

## What changed from v2

**Added:** Stage 4.8 staging deploy (first hosted smoke before SSE work, not at Stage 12); Stage 4.9 frontend foundation + hygiene batch; Stage 5.5 schedule metadata (unblocks Stages 6, 8.6, 11); rule 14 (full active E2E suite at every stage close; archived specs are dead specs); rule 15 (three-dimension AI capacity budget with priority headroom; request-count frugality); Stage 4.5 fully redesigned with hard prerequisites (IFM key verification, step-level gate pinning, per-step failure projection) and locked design decisions (platform/llm location, complete+stream interface, flat-file PromptRegistry, Redis limiter, metadata-only AIRequestLog, routing split brief→V2/Cerebras + detailed→Think/Nvidia, single-call summaries, in-call 429 handling, dedicated ai queue/worker, backfill answer); Stage 5 function-calling and pagination-envelope requirements with pool-compatible schema; Stage 6 capacity ADR; Stage 8 staging-SSE validation, exact-scan retrieval, context budgets; Stage 9 org-model ADR checkpoint; Stage 11 scheduler component; Stage 12 error envelope, can_publish review, signed-URL decision, cost review; post-MVP watchlist; carried-debt ledger with owners; repo rule placing this file in knowledge/ with mandatory status updates.

**Changed:** completed stages 0–4.4 compressed to a debt ledger plus pointers — specs/STATUS.md remain the authority for finished work; the roadmap's job is forward guidance; v2's two open items closed (prompts = flat files via registry; AI provenance fields confirmed and generalized into amended rule 6).

**Preserved:** the governing principle, UI proof obligations, status vocabulary, all v2 cross-cutting rules in substance, risk-based ordering 4.5→4.6→4.7 (tested the alternative: 4.6's retry scope includes summary jobs and can't precede them; 4.7 before 4.6 exposes students to mixed states during replacement), AIRequestLog-before-first-call, event spine design, the permanent acceptance rule.

---

## Permanent acceptance rule (unchanged, one addition)

A stage is done only when *all* hold:

```
Backend tests pass
Frontend type-check passes
OpenAPI client is fresh (regenerated + committed if the contract changed)
A thin (real, not fake) UI slice exists
The UI proof obligation is demonstrable in a real browser
The Playwright/browser gate passes
The FULL active E2E suite passes (rule 14)            ← new in v3
Knowledge files updated in the same commit (incl. this roadmap's status table)
No out-of-scope backend work slipped in
```

A backend feature without a passing browser gate is not done. It is waiting to surprise you later — usually at the least convenient possible moment.

---

**Next action:** verify the IFM API key and model identifiers (Stage 4.5 hard prerequisite #1 — it has external lead time), commit this file as `knowledge/roadmap.md`, then proceed to **Stage 4.5a**.
