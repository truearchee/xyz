# ADR-048 — Glossary definitions: reuse BriefSummary, collapse on the cache row, no IngestionJob

**Status:** Accepted (Stage 7a, 2026-06-17). Confirmed with the tech lead as decisions D2/D3.
**Context:** Definitions are AI-generated through the *existing* `platform/llm` gateway. The spec says
"don't modify `platform/llm`," but the gateway's validator + feature label + deterministic provider are
closed unions (see [[findings-stage-07]] F-7-1). Glossary has no transcript, so the summary
`IngestionJob` model does not fit; the generation is also *shared across students* (a cache), unlike a
per-student quiz attempt.

## Decision
1. **Reuse the `BriefSummary` (`{"text": ...}`) output schema** for definitions — one markdown blob
   (KaTeX-capable). Light validation (non-empty / not-refusal) is exactly the spec's stated check, so
   `validation.py` is **not** changed. The only additive `platform/llm` edits: `GatewayFeature`
   `+'glossary_definition'` and a deterministic-provider fixture (test-only). Structured
   `detailedExplanation`/`example`/`formulaLatex` columns are reserved for a 7.x structured upgrade.
2. **No `IngestionJob`.** Glossary mirrors the *quiz* async pattern: `ContextRefs.ingestion_job_id=None`,
   enqueue-after-commit, AIRequestLog `feature='glossary_definition'`. `ingestion_jobs` is untouched (so
   `ck_ingestion_jobs_job_type` is not a Stage-6 collision point).
3. **The `glossary_definition_cache` row is the cross-student concurrency primitive.** UNIQUE
   `(cache_key, prompt_version)` is the spec's "one-active index keyed on the cache key." On a miss the
   first saver inserts a `pending` cache row (`ON CONFLICT DO NOTHING`) and enqueues the only job;
   racing savers attach their entry and wait. The job re-checks the cache at start, then **fans the
   single generated definition out to every pending entry sharing the key** → two students racing the
   same term/subject/language ⇒ ONE model call. Cache HIT ⇒ no call.
4. **Language is baked into the rendered input** (not a template slot — the renderer is unchanged), so
   it is captured by `rendered_prompt_hash` + `input_content_hash` (provenance). The language soft-check
   (script/charset heuristic for ar/zh) **logs a warning, never rejects** — bilingual technical
   definitions would otherwise trip naive detectors into spurious retries.

## Consequences
Minimal shared-surface footprint; the `TranslationService` abstraction keeps the provider swappable.
A terminal generation failure leaves the cache row + entries in `failed` (not a perpetual spinner); a
later save of the same term re-triggers it. No glossary stuck-row reaper in 7a (RQ retries handle
transients); a dedicated retry endpoint is deferred to 7.x.
