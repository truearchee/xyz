# Status

_Last updated: 2026-06-18 — **Stage 8.2 (context resolver + grounded retrieval) — FULLY VERIFIED.** All
gates GREEN: backend 558 pytest, tsc, migration 0033 round-trip (single head), 5 security tests + a focused
/cso pass (0 findings ≥8/10), the 8.2 browser gate, full active Playwright **17/17 (rule 14)**, and the
**real-provider smoke (rule 11)** — model echo `MBZUAI-IFM/K2-Think-v2` on both turns and the real
K2-Think-v2 emitted a valid `isStudyRelated` (true study / false off-topic), validating the R-isStudyRelated
risk on the real model ([[steps/stage-08/8.2-real-provider-smoke]]).
Built: embedder promoted to `platform/embeddings/` + shared `EmbeddingConfig` + `EMBEDDING_PROVIDER`
deterministic mode (ADR-050); assistant worker now runs resolve→retrieve→one-call→ground→snapshot
(ADR-051) — exact pgvector cosine scan scoped to the conversation's STORED section through the 4.7
visibility gate, deterministic threshold (0.35; real-MiniLM in-lecture 0.17–0.21 vs off-lecture 0.89–0.95),
ONE INTERACTIVE gateway call returning a required `isStudyRelated` flag, backend-derived `groundingStatus`
via fixed-precedence `decide_grounding`, server-only generation-time `context_snapshot` (migration **0033**)
→ student-safe "Where did this come from?" basis; frontend neutral "Not from this lecture" label + collapsed
basis disclosure. Verified: migration 0033 round-trip (single head **0033**); backend **558 pytest**
(embedder promotion byte-identical); `tsc` exit 0; 5 security tests (§13) + a focused **/cso** pass (0
findings ≥8/10); **8.2 browser gate** (grounded lecture + LAB, off-lecture labeled general, unrelated
redirect, unassigned 404, safe basis); **full active Playwright 17/17 (rule 14)**. Two transient full-suite
reds were root-caused + fixed (NOT papered over): (1) the shared-`kyiv-backend` image contention re-upped
`ai_worker` onto non-8.2 code mid-suite → baked my code into the unique `kyiv-backend-e2e-hatyai` image +
folded the e2e config into the base compose (LOCAL compose edits — REVERT before commit); (2) a test-timing
race where deterministic embeds completed faster than `4.3.5e`'s intermediate-state poll → the live e2e
stack uses **real MiniLM** (deterministic encoder stays scoped to backend pytest). See
[[steps/stage-08/findings-8.2-gate-image-contention]], [[steps/stage-08/8.2-context-retrieval]]. NO OpenAPI
change (`MessageRead` already exposed `groundingStatus`+`answerBasis`). Below: Stage 8.1 + prior._

_Prior — 2026-06-18 — **Stage 8.1 FULLY VERIFIED** (branch `stage-81-83`, rebased onto Stage 7).
8.1 conversation foundation built: new `assistant` domain (conversations + messages), gateway `assistant`
feature (AssistantAnswer schema + validator branch, no refusal-rejection; deterministic provider branch;
`prompts/assistant/v1.yaml`), lecture entry point + thin chat panel in the **existing inline idiom**
(monochrome design system is NOT in code — see [[steps/stage-08/findings-design-doc-reality-gap]]),
create-then-poll interactive turn via the `ai` queue at interactive priority (ADR-048), 8.4-ready
conversation-list data shape with a `lecture_default` partial-unique index (ADR-049), migration **0032**
(block 0032–0037). Verified: backend **514 pytest** (incl. 14 new assistant tests; 2 prior failures fixed
= prompt-drift + dev_reseed EXPECTED_ALEMBIC_VERSION 0025→0032), `tsc --noEmit` exit 0, OpenAPI client
regenerated. **Rebased onto Stage 7** (single head **0032**, `0025→0030→0031→0032`, round-trip clean;
merged backend **537 pytest** incl. the shared-CHECK union guard; fixed a rebase bug where 0032 dropped
`glossary_definition` from the feature CHECK). **All live gates GREEN:** 8.1 browser gate; **full active
Playwright 16/16 (rule 14)**; **real-provider smoke (rule 11)** model echo `MBZUAI-IFM/K2-Think-v2`.
**Stage 8.1 FULLY VERIFIED.** Two env workarounds (recorded, NOT committed): local Supabase `edge_runtime`
502 (disabled to start it) and shared `kyiv-backend` image-tag contention with the **active sibling
`tokyo`** workspace (pinned my compose to a unique tag so Conductor's mid-suite recreates use my image) —
[[steps/stage-08/findings-8.1-gate-run-blocked]]. **Env hazard for the owner:** the `kyiv-backend` tag is
shared across all running workspaces; give each a unique tag / source mount. Next: 8.2 (grounding). See
[[steps/stage-08/8.1-conversation-foundation]]. Below: prior Stage 7 + Stage 6._

_Prior — 2026-06-18 — **Stage 7 core (7a–7c: glossary foundation + flashcards + multiple-choice).** Full active
E2E suite green (14/14) after fixing an admin module-list ordering bug; branch `stage-7` rebased onto main;
migrations re-chained `0025 → 0030 → 0031`; shared `ck_ai_request_logs_feature` + `GatewayFeature`/CHECKSUMS
unioned (Stage 6 `quiz_pool` + Stage 7 `glossary_definition`, `test_shared_check_union` guards). Stage 8.1
re-unioned the same shared infra to add `assistant`._

_Prior — 2026-06-18 — **Stage 6 CLOSED — FULLY VERIFIED** (owner-signed-off; on branch `stage-6`).
F-6e fixed the rule-11 smoke and the roadmap row is flipped. The 6e smoke "hard
timeout" was re-diagnosed live: the provider is healthy (~73–76 completion-tok/s on both routes), but
K2-Think-v2 reasons inline and rambles to fill `max_tokens`, so `stream:false` wall-clock ≈
`max_tokens`/73 → 32000 meant ~440s (over 540 under variance). **Fix:** `quiz_pool_generation/v1`
`max_tokens` 32000→**20000** + count 24→**16**; validator floor 16→**12**; `POOL_TARGET_SIZE` /
`_DETERMINISTIC_POOL_SIZE` →16; `LLM_DETAILED_TIMEOUT_SECONDS` 240→**330**, lease TTL 300→**360**; rule-11
smoke made retry-aware (mirrors `AI_RQ_RETRY_MAX`). **Smoke PASS** on attempt 1: model echo
`MBZUAI-IFM/K2-Think-v2`, 16 questions valid, **264.5s** (< 330 timeout). Full green set: backend **502
passed**, drift guard OK, host ruff clean, `tsc` clean, 5d gate **1 passed**, 6d gate **1 passed**, full
active Playwright **14 passed**. **Deviates from the owner's stated Steps 2/3/7** (max_tokens 20000 not
4000; route kept nvidia not cerebras; timeout 330 not 240) — all evidence-backed; the roadmap row stays
**IN PROGRESS** until the owner reviews the smoke timing + these deviations (per the standing "don't flip
until I've seen the smoke timing"). See [[steps/stage-06/6d-real-provider-smoke]] (2026-06-18 section) and
ADR-047's F-6e amendment. Below are prior Stage 6 summaries._

Stage 7a delivers the personal glossary foundation: save terms (highlight-from-summary + manual add),
**async AI definitions in the student's preferred language through the EXISTING `platform/llm` gateway**
(no new AI infra), server-side dedup, a shared definition cache with cross-student collapse, folders
(+ "Unsorted"), archive-style delete, personal-scoping 404, `glossary_term_saved` events, KaTeX, RTL,
and the language-preference setting.

## Confirmed decisions (this session)
- **D1** migrations start at `0030` (use `0030`+`0031`); `0029` left to Stage 6; merge migration expected.
- **D2** proceed with the minimal additive shared-infra edits + full mitigation set (source-of-truth
  enum tuples, union-aware CHECK migrations, CI union test, findings note).
- **D3** reuse the `BriefSummary` markdown shape for definitions; structured columns reserved for 7.x.

## Verification (Stage 7a–7c)
```bash
docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q
# 498 passed, 138 warnings   (Stage 5 baseline 442; +56 glossary/practice/me/union tests)

# migration round-trip (base→head→base→head): test_db_spine::test_migration_round_trip — passed
# dev DB xyz_lms migrated to head 0031; dev-reseed pin = 0031

cd frontend && npx tsc --noEmit
# exit 0

docker compose run --rm -e LLM_PROVIDER=k2think -e LLM_PROVIDER_BASE_URL=https://api.k2think.ai \
  -v "$PWD/backend:/app" -T backend python scripts/gate7_glossary_smoke.py
# PASS: response model echo MBZUAI-IFM/K2-Think-v2 == expected MBZUAI-IFM/K2-Think-v2;
# status_code 200; parseable BriefSummary definition; arabic-script present; finish_reason='length'

PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781717252-stage7 \
  npx playwright test tests/e2e/7-glossary.spec.ts --workers=1
# 1 passed (19.3s)

PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781717291-full \
  npx playwright test --workers=1
# 14 passed (3.2m)
```

## Verification (Session 7e review fixes)
```bash
docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q \
  tests/test_glossary_save.py tests/test_glossary_practice.py tests/test_glossary_unit.py
# 20 passed in 3.37s

docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q
# 500 passed, 138 warnings in 62.31s

PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781766005-stage7e5 \
  npx playwright test --workers=1
# 12 passed, 2 failed (4.3.5c admin module row refresh; 5.5e admin module row refresh)
```

## Verification (admin module-list ordering bugfix — #7e-adminfix, 2026-06-18)
Root cause of the two 7e reds: `service.list_modules` ordered `created_at, id` ASC with default
`limit=50` and no pagination UI, so a just-created module fell off page 1 once >50 `course_modules`
accumulated (86 in dev `xyz_lms`, mostly E2E residue from interrupted runs). Fix: order newest-first
(`created_at DESC, id DESC`). No data was cleaned to pass. Backend image rebuilt + container recreated
(the live :8000 stack runs a baked image with no source mount).
```bash
docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q
# 500 passed

# isolated rerun of the two previously-failing specs (seeded manifest, same E2E_RUN_ID):
PLAYWRIGHT_BASE_URL=http://localhost:3001 \
  npx playwright test tests/e2e/4.3.5c-stage2-admin.spec.ts tests/e2e/5.5e-ui-browser-gate.spec.ts --workers=1
# 2 passed

# full active suite (rule 14):
PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-orderfix-full \
  npx playwright test --workers=1
# 14 passed (2.8m)
```
Follow-ups logged in `open-questions.md` (#7e-adminfix): admin pagination-envelope debt
(owner developer; trigger Stage 12 hardening or before any deploy where module count can exceed one
page), sibling `list_users` sharing the ASC+fixed-limit pattern (flagged, not fixed), and E2E
teardown/reset hardening so interrupted runs stop leaving residue. Rule-14 full-suite green is now
satisfied (14/14).

## NOT done — remaining for Stage 7
- **7d** quiz-highlight. It is no longer blocked on Stage 6 coordination; Stage 6 is closed, so this is
  the next unblocked sub-stage.
- Low-priority follow-up: the real-provider glossary smoke returned `finish_reason='length'`; raise the
  glossary definition prompt `max_tokens` so real definitions do not truncate mid-sentence.

## Merge coordination
- Stage 7 still carries the CHECK-union guard (`test_shared_check_union.py`) for any integration with
  adjacent stage branches. `ingestion_jobs` is untouched by Stage 7.

## Stage 7 documents
- Stage spec: [[specs/stage-07/7-glossary]]
- 7e review-fixes spec/plan/report: [[specs/stage-07/7e-review-fixes]], [[plans/stage-07/7e-review-fixes]], [[steps/stage-07/7e-review-fixes]]
- 7a report: [[steps/stage-07/7a-glossary-foundation]]
- 7b/7c report: [[steps/stage-07/7bc-glossary-practice]]
- Findings: [[steps/findings-stage-07]]
- Decisions: [[decisions/adr-047-glossary-subject-folder-separation]], [[decisions/adr-048-glossary-definition-cache-collapse]]

## Prior
- 2026-06-17 — **Stage 5.5 FULLY VERIFIED**, migration chain rebased (`0021`→`0022`), dev reseed expected
  Alembic `0022` (now bumped to `0030` by Stage 7a). See git history + per-stage trios.
- 2026-06-12 — **Stage 4.7** student summaries FULLY VERIFIED on main (`0e0654f`).
- **Stage 5** FULLY VERIFIED (quiz engine + event spine; ADRs 040–046).

## Open risks
- **7d** still needs its own implementation/gate.
- **Glossary definition truncation follow-up** — smoke passed, but `finish_reason='length'` means the
  prompt budget is tight for the current provider behavior.
- **Shared CHECK/migration reconciliation** if adjacent stage branches are integrated (mitigations above).

## Environment note
Local stack: db/redis internal-only; `backend` host `:8000`,
`frontend` host `:3001`. Tests run via `docker compose run --rm -v "$PWD/backend:/app" backend pytest`
(live code mounted over the editable install; no published port). Frontend `tsc`/codegen run on the host
(`frontend/node_modules` installed; `LLM_PROVIDER=deterministic`).
