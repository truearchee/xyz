---
type: scope-spec
stage: 04
session: "post-4.9-corrective"
slug: summary-verification-inline
status: task-0-complete
created: 2026-06-13
updated: 2026-06-13
owner: developer
note: "Corrective spanning Stage 4.5 (generation) + 4.7 (student surface), surfaced by the 4.9 human close-out. Does NOT reopen or renumber completed stages. Authorizes a per-workstream sub-spec → plan → approval breakdown (§8)."
---

# Post-4.9 Corrective — Student Summary Verification + Inline Presentation (SCOPE SPEC)

> This is the **scope** spec (verbatim from the developer's corrective doc 2026-06-13). Per §8 it authorizes
> a breakdown into per-workstream sub-specs; **no source edits** happen against this doc directly. Recommended
> order: **Task 0** (done — see Result) → **Workstream B** (independent) → **Workstream A** (only if Task 0 step 3 requires).

## Reframing (§0)
The generic content ("First key concept", "Term A — Definition of term A", "A procedure or observation note")
is the **signature of the deterministic LLM test adapter** (rule 11 default in local/CI). The real K2Think
provider only runs when `LLM_PROVIDER=k2think` + a valid `LLM_API_KEY`. So "the summary has no transcript
context" is most likely a property of the dev environment, not a generation defect. **Generation changes
(Workstream A) are GATED on the Task 0 diagnosis.** The inline-presentation change (Workstream B) is true
regardless and proceeds independently.

## Task 0 — DIAGNOSIS GATE — RESULT (2026-06-13)
Steps 1–2 run by the agent (read-only); step 3 is the developer's (needs real-provider credentials).
- **Step 2 — active provider:** `LLM_PROVIDER` is unset in every `.env` → default **`deterministic`**
  (`backend/app/platform/config.py:264`). The running backend has `LLM_API_KEY`/base-url present but NOT
  `LLM_PROVIDER=k2think`, so `get_provider()` (`provider.py:355`) returns **`DeterministicTestProvider`**.
- **Step 1 — `ai_request_logs` (the 2 most-recent summary rows):** `provider_request_id = det-…` (adapter
  signature, `provider.py:291`), `last_provider_status_code = NULL` (no HTTP call), `latency_ms = 0`
  (no round-trip). Whole table is `det-` only. **BUT `prompt_tokens = 13813 / 13709`** — the transcript
  DID reach the prompt (13.8k tokens interpolated); the adapter ignores its input and returns fixed text
  (`completion_tokens` 54/132). So the **transcript→prompt path already works**.
- **Branch taken: (Expected) test adapter was active.** The contextless content is the **documented dev
  default, NOT a 4.5 defect and NOT a 4.9 regression** → F-4.9-7. The real, grounded baseline must come from
  a real-provider run (step 3, developer-owned). Command:
  `LLM_PROVIDER=k2think LLM_API_KEY=<real> docker compose … up -d backend ai_worker` then lecturer re-processes
  the transcript; capture the resulting brief + detailed text.
- **Step 3 RESULT — UPDATE (2026-06-13, later): DONE — real key arrived; branch 1 (no-op).** A real
  K2Think key was placed in `.env`; `MBZUAI-IFM/K2-Think-v2` was curl-confirmed on both routes and the full
  pipeline ran real (AIRequestLog: model echo, http 200, 31.9s/125.5s, `chatcmpl-` ids; brief + detailed
  **about the actual transcript**, not "Term A"; both passed the OutputValidator). **F-4.5-27 RESOLVED**
  (ADR-025 deviation live-verified); **A1 no-op** (brief is an 83-word paragraph). No code change (model was
  already K2-Think-v2). §3A re-secured by forcing `LLM_PROVIDER: deterministic` in `docker-compose.e2e.yml`
  (committed) → dev `.env`=k2think, gate/CI=deterministic. Evidence: [[steps/stage-04/4.5-real-provider-smoke]].
  Workstream A complete → the corrective is CLOSED. *(The earlier BLOCKED result below was the honest
  interim state before the key arrived.)*
- **Step 3 RESULT (2026-06-13, interim): BLOCKED — branch 2 (reachability/credential finding, F-4.5-27 instance).**
  The agent checked the running backend: `LLM_API_KEY=your-llm-api-key-here` — the verbatim `.env.example`
  PLACEHOLDER (`.env`/`.env.e2e` set no real key; `LLM_PROVIDER` unset → `deterministic`). **There is no
  real K2Think credential in this environment**, so a real-provider summary cannot be produced here. The
  agent did NOT fire a doomed request against `api.k2think.ai` with the placeholder key, and did NOT re-run
  the adapter and call it verified. **This reachability state IS the honest outcome** (per the developer's
  branch framing). **Owner: developer.** To run step 3: put a real `LLM_API_KEY` in `.env` (the base URL
  `https://api.k2think.ai` is already set) + set `LLM_PROVIDER=k2think`, confirm the `MBZUAI-IFM/K2-Think-v2`
  deployment is actually accessible (F-4.5-27 noted the intended model was not), restart backend + ai_worker,
  re-process a transcript, capture brief + detailed. Then re-classify Workstream A: no-op (grounded
  paragraph) / model-inaccessible (deeper F-4.5-27) / real defect (still short/contextless). **Restore
  `LLM_PROVIDER=deterministic` after, so the local E2E suite stays on the deterministic pipeline.**

## Workstream A — Generation (Stage 4.5) — CONDITIONAL on Task 0 step 3
- **A1 brief length** — product intent: brief = a single ~4–5-sentence paragraph. **The v1 brief prompt
  ALREADY asks for "ONE short, self-contained paragraph of roughly 60–120 words"**
  (`backend/prompts/brief_summary/v1.yaml:20-21`); the stub returns a fixed 3-sentence paragraph. So A1 is
  **likely a no-op** — confirm against step-3 real output; only a prompt-version bump (+ a min-length
  validator) if the real brief is still too short.
- **A2 grounding** — the transcript→prompt path is proven working (13.8k prompt tokens). With the real
  provider this **evaporates**. Only a real fix if step 3's real output is STILL contextless (would be a
  genuine 4.5 prompt/parse defect). **No frontend work in A.** No change to the detailed section set.

## Workstream B — Inline Presentation (Stage 4.7 revision) — proceed independently
- **B1 (firm):** one section block, one page, in order: header · lecturer notes · files · brief · detailed.
  Remove the "View summaries →" separate-page hop.
- **B2 (product decision — owner):** Option 1 (recommended) brief always inline + detailed inline but
  COLLAPSIBLE in place (no navigation); Option 2 both fully expanded inline. Either satisfies B1.
- **B3 constraints (no regress):** security (unpublished → 404, unassigned → 404, raw transcript never
  reachable); §4.3 processing/unavailable states reused; built from the 4.9 component library (Card /
  EmptyState / existing markdown render), token-only, no new public components; read projection may include
  /lazy-load summary content (NOT a schema change).
- **B4 anti-regression:** update the 4.7 student-summary E2E to assert the INLINE location IN THE SAME
  COMMIT (do NOT loosen); preserve the security assertions; rollback-not-loosen stance (revert layout, never
  weaken the test).

## Scope exclusions (§4)
No reopening/re-verifying 4.9; no change to the detailed section set; no lecturer summary editing; no
quiz/glossary/assistant; the "Save notes no-feedback" nit is a separate small finding; no new AI feature.

## Findings (this corrective) — rule-13
- **F-4.9-7** (filed in findings-4.9) — real-provider summary path not human-verified end-to-end here;
  local default = deterministic adapter. **RESOLVED (diagnosis):** Task 0 steps 1–2 confirm the adapter;
  contextless content is the dev default, NOT a 4.9 regression. Residual: step 3 real-provider run (developer).
- **F-C1 (Stage 4.5 generation)** — brief length sentence→paragraph. **CONDITIONAL** (v1 prompt already
  asks for a 60–120w paragraph) → Workstream A1, gated on Task 0 step 3.
- **F-C2 (Stage 4.5 generation)** — transcript grounding. **LIKELY NO-OP** (path proven) → Workstream A2,
  gated on Task 0 step 3.
- **F-C3 (Stage 4.7 surface)** — separate summary page → inline single block. **OPEN** → Workstream B.
- **F-C4 (frontend nit)** — "Save notes" gives no UI confirmation (lecturer side). **OPEN — out of this
  corrective's scope**, logged for a future small frontend pass.
- **F-C5 (Stage 4.5 / ops, reachability)** — was BLOCKED (placeholder key). **RESOLVED 2026-06-13:** real key
  placed in `.env`; `K2-Think-v2` live-verified end-to-end (both routes); real grounded summaries produced +
  validator-conformant. Workstream A closed as **branch 1 (no-op)** — no code change needed. F-4.5-27 closed.
  Evidence: [[steps/stage-04/4.5-real-provider-smoke]]. **Residual:** the exposed key must be ROTATED (§7).

## Workflow (§8)
Each workstream gets its own sub-spec → implementation plan → developer approval BEFORE any source edits.
This doc authorizes that breakdown. Order: Task 0 (done) → Workstream B → Workstream A (if step 3 requires).
