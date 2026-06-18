# Status

_Last updated: 2026-06-18 — **Stage 7 core (7a–7c: glossary foundation + flashcards + multiple-choice) remains implemented.** Session 7e review fixes are committed; the full active E2E suite is now green (14/14) after fixing the real root cause of the two inherited reds — an admin module-list ordering bug (newly created modules fell off page 1 once >50 modules accumulated). Branch `stage-7` rebased onto current `origin/main` `fb4c932` (after Stage 6 + design-files merged); migrations re-chained linearly `0025 → 0030 → 0031` (0030 down_revision 0022→0025) and the shared `ck_ai_request_logs_feature` CHECK + `GatewayFeature`/CHECKSUMS unioned to include both Stage 6 `quiz_pool` and Stage 7 `glossary_definition` (test_shared_check_union guards it). 7d quiz-highlight remains as the next unblocked sub-stage now that Stage 6 is closed._

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
