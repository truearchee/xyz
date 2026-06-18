# Findings — Stage 7 (Interactive Glossary & Practice)

Running notes for the parallel-with-Stage-6 build. Newest first.

---

## F-7-6 — post-review follow-up disposition (PARTIAL FIX + LOGGED DEFERRALS)

2026-06-18 Stage 7 review follow-up disposition:

- **Fix now:** enqueue-after-commit failure must compensate glossary definition cache rows and matching
  entries to `failed`, then duplicate-save retry must re-enqueue and allow generation to complete.
- **Fix now:** `entry_type` updates are rejected. Entry type participates in the definition cache key, and
  reclassification is not a Stage 7 feature.
- **Spec correction:** `vocabulary` is not a product type; `term` covers vocabulary words. The locked spec
  entry-type enumeration is corrected to `term | formula | concept`.
- **Accepted, not drift:** the prompt-echo-specific hard rejection is intentionally not implemented under
  D3 because Stage 7 reuses the `BriefSummary` markdown shape and validator. Rich structured glossary
  validation remains a 7.x concern.
- **Deferred:** detail-sheet tabs flattened to an aside is logged for the Stage 12 design pass.
- **Deferred:** missing per-sub-session Stage 7 knowledge trios are logged as docs-cleanup follow-up.
- **Deferred:** browser gate additions for `<4 terms` fallback and MCQ wrong-pick assertions are logged as
  low-priority Playwright follow-up that can fold into the 7d gate run.
- **Already tracked:** 7d quiz-highlight remains the next Stage 7 sub-stage; no action here.

## F-7-1 — `platform/llm` "no-touch" rule is not literally satisfiable; minimal additive extension taken (DECIDED, D2)

The spec's coordination rule 1 ("consume the shared AI pipeline; never modify it") cannot hold for a
*new* AI feature. Verified in code:
- `OutputValidator.validate()` (`platform/llm/validation.py`) dispatches on `output_schema is
  BriefSummary/DetailedSummary/PostClassQuiz` and raises `unsupported_schema` for anything else.
- `GatewayFeature` is a closed `Literal` (`platform/llm/models/prompt.py`).
- `DeterministicTestProvider._render_output()` (`platform/llm/provider.py`) dispatches on prompt name
  and **raises for any unknown prompt** — so CI/e2e would fail for a new prompt with no fixture.
- The prompt renderer requires `{{transcript}}` and only substitutes `{{transcript}}`/`{{section_type}}`.

**Resolution (D2 = proceed + mitigate).** Stage 7 reuses the existing `BriefSummary` output schema
(decision D3), so `validation.py` is **not** changed. The minimal, additive `platform/llm` touches are:
`GatewayFeature` Literal `+'glossary_definition'`, and a `glossary_definition` fixture branch in the
deterministic provider (test-only path, zero prod impact). The language is baked into the rendered
input text (decision B1), so the renderer is **not** changed. No gateway/limiter logic changed.

## F-7-2 — shared CHECK constraints widened; Stage 6 must union at merge (MITIGATED)

Two shared CHECK constraints were widened by drop+recreate (migration `0030`):
`ck_ai_request_logs_feature` (+`glossary_definition`) and `ck_student_activity_events_event_type`
(+`glossary_term_saved`, `glossary_practice_completed`). A CHECK is rewritten wholesale, so **whichever
of Stage 6 / Stage 7 merges second must recreate these with the UNION of both stages' values**, or the
earlier stage's values are silently dropped.

Mitigations in place:
- Source-of-truth tuples on the models: `AI_REQUEST_LOG_FEATURES` (`ai_request_log.py`),
  `STUDENT_ACTIVITY_EVENT_TYPES` (`student_activity_event.py`). The CHECKs are built from them; the
  `EventRecorder` allowlist imports the tuple.
- CI union guard: `tests/test_shared_check_union.py` asserts each live DB CHECK == its model tuple.
- `test_event_recorder.py::test_event_types_match_check_constraint` updated to the union (was pinned to
  `QUIZ_EVENT_TYPES`).
- **Stage 6 does NOT need to touch `ck_ingestion_jobs_job_type`** for glossary — glossary uses the quiz
  pattern (no `IngestionJob`), so that constraint is untouched (one fewer collision than a naive design).

**At merge:** reconcile the two CHECK recreates to the union of Stage 6 + Stage 7 values; the CI union
test fails loudly if a stage's values are dropped.

## F-7-3 — migration block 0030–0031; merge migration expected (D1)

Stage 7 owns `0030` (foundation) + (7b/7c) `0031` (practice). `0029` is left to Stage 6. Both stages
branch off head `0022`. **A small merge migration is expected at branch integration** (re-point the
first Stage-7 migration's `down_revision` to the post-Stage-6 head). Normal parallel-work housekeeping.

## F-7-4 — dev-reseed Alembic pin bumped 0022 → 0030 (prior-session edit)

`app/domains/admin/dev_reseed.py` `EXPECTED_ALEMBIC_VERSION` was `"0022"` (Stage 5.5 head). Bumped to
`"0030"` for the 7a head, per the established per-migration-stage convention. (Will become `"0031"` when
7b's migration lands.) See "Modified prior sessions" in the 7a report.

## F-7-5 — live browser gate + real-provider smoke passed (RESOLVED)

Resolved 2026-06-17 after the `stage-55` stack was stopped and Bucharest owned `:8000`.

Real-provider smoke (synthetic Arabic term; provider override only for this run):
```bash
docker compose run --rm -e LLM_PROVIDER=k2think -e LLM_PROVIDER_BASE_URL=https://api.k2think.ai \
  -v "$PWD/backend:/app" -T backend python scripts/gate7_glossary_smoke.py
# PASS: response model echo MBZUAI-IFM/K2-Think-v2 == expected MBZUAI-IFM/K2-Think-v2;
# route cerebras; status_code 200; parseable BriefSummary definition; arabic-script present;
# finish_reason='length'
```

Browser gate + rule 14:
```bash
PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781717252-stage7 \
  npx playwright test tests/e2e/7-glossary.spec.ts --workers=1
# 1 passed (19.3s)

PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781717291-full \
  npx playwright test --workers=1
# 14 passed (3.2m)
```

The Stage 7 Playwright gate run-scopes its lecturer, primary student, and second student under the
current `E2E_RUN_ID`; teardown removed only manifest-tracked objects after each run. `finish_reason='length'`
is accepted for the smoke because the model-ID echo matched and validation passed, but it is tracked as a
low-priority follow-up to raise `glossary_definition/v1` `max_tokens`.

## Decisions log (confirmed by the tech lead this session)
- **D1:** migrations start at `0030` (use `0030`+`0031`); `0029` is Stage 6's.
- **D2:** proceed with the minimal additive shared-infra edits + the full mitigation set.
- **D3:** reuse the `BriefSummary` markdown shape for definitions; keep
  `detailed_explanation`/`example`/`formula_latex` columns reserved for a 7.x upgrade. Free additions
  taken: the prompt requests an inline example sentence; a cheap script/charset check logs (never
  rejects) an Arabic/Chinese definition that came back in the wrong script.
