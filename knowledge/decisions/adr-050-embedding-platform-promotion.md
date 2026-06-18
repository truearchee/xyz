---
type: adr
stage: "8"
status: accepted
created: 2026-06-18
updated: 2026-06-18
related-session: knowledge/specs/stage-08/8.2-context-retrieval.md
---

# ADR-050 — Promote the embedder to `platform/embeddings/` + `EMBEDDING_PROVIDER` deterministic mode

## Linked documents
- Spec: [[specs/stage-08/8.2-context-retrieval]]
- Plan: [[plans/stage-08/8.2-context-retrieval]]
- Report: [[steps/stage-08/8.2-context-retrieval]]
- Calibration: [[steps/stage-08/8.2-retrieval-threshold-calibration]]

## Context
Stage 8.2's assistant retrieval is the first consumer of transcript embeddings outside the Stage 4.4
ingestion pipeline. The encoder + the embedding geometry constants (`MiniLM-L6`, dim 384, `l2`,
`embedding-v1`) lived in `domains/transcripts/embedding_encoder.py`. Architecture rule 8 forbids the
assistant domain importing another domain, and the assistant must NEVER re-hardcode the geometry — query
and chunk vectors have to be produced by the SAME model or cosine distances are meaningless. CI/E2E also
needs deterministic, download-free embeddings so the grounded-vs-general outcome is reproducible.

## Decision
- **Extract (not redesign)** the encoder to `platform/embeddings/`: `EmbeddingConfig`
  (`model_name, dimension, normalization='l2', embedding_version, distance_metric='cosine'`) +
  `DEFAULT_EMBEDDING_CONFIG`, `SentenceTransformersEmbeddingEncoder`, `DeterministicEmbeddingEncoder`,
  `validate_model_snapshot`, and `get_encoder()`. Behavior is byte-identical; the old module-level
  constants are kept as aliases of the config so `embedding_service.py` is unchanged. Stage 4.4 imports
  (transcripts chunk-embed, worker startup, 5 test files) re-point to `platform/embeddings`.
- **One shared `EmbeddingConfig`.** Both chunk generation (4.4) and assistant retrieval (8.2) read the
  same config; the retrieval scan's same-model filter compares against `DEFAULT_EMBEDDING_CONFIG`.
- **`EMBEDDING_PROVIDER` env mode** (mirrors `LLM_PROVIDER`): `sentence_transformers` (default; real
  MiniLM) or `deterministic` (CI/E2E; hash-based identical-text→distance-0, different→≈1). `get_encoder()`
  honors it; the embed worker passes no explicit encoder so both chunk and query embedding follow it.
  `deterministic` is **rejected in prod/staging** so a misconfigured deploy can never serve garbage
  retrieval.
- **Provenance parity.** The embed writer stamps `embedding_model`/`version`/`dimension`/`normalization`
  from the config REGARDLESS of which encoder ran, so deterministic-mode chunks still satisfy the chunk
  CHECK (dim 384, `l2`) and the 4.4 gate (asserts provenance + dim 384, not vector values) stays green.

## Consequences
- The assistant never hardcodes the embedding geometry; a model swap is a single `EmbeddingConfig` edit
  that moves the stored-filter and the query encoder together.
- The query embedding is LOCAL/in-process (sentence-transformers or deterministic), never a metered
  gateway/provider call — so one student question = exactly one gateway call (the answer).
- Touching Stage 4.4 code is the main blast radius; guarded by a compat/determinism test
  (`tests/test_embedding_platform.py`) and a full active-suite + 4.4-embedding-browser re-run, both green
  under `EMBEDDING_PROVIDER=deterministic`.

## Refinement (8.2 live gate) — deterministic mode scoped to backend pytest, NOT the browser E2E
Review #9 envisioned `EMBEDDING_PROVIDER=deterministic` in CI/E2E. In practice deterministic embeds (plus
the deterministic LLM summaries) make the ingestion pipeline complete so fast that prior-stage transcript
specs lose a timing race: `4.3.5e` waits for the INTERMEDIATE chunk-completed projection state, but the
transcript reaches terminal `summarized` before the browser's first poll → timeout (the product is
correct; the test's assumption isn't). So: the deterministic ENCODER + `EMBEDDING_PROVIDER` mode ship as
specified and are used by **backend pytest** (`tests/conftest.py`, in-process, no model load) — where the
8.2 grounding tests seed deterministic chunk vectors and need deterministic query vectors. The **live
browser E2E stack uses real MiniLM** (leave `EMBEDDING_PROVIDER` unset), which is still deterministic for
identical text (distance 0 → grounds on a verbatim chunk; off-lecture distance >1.0 → general) but
preserves the pipeline-timing realism the whole suite was written against. See
[[steps/stage-08/findings-8.2-gate-image-contention]].

## Alternatives considered
- Leave the encoder in `domains/transcripts` and have the assistant import it — violates rule 8.
- A separate assistant-only encoder — would risk query/chunk geometry drift (meaningless distances).
- Force `groundingStatus`/answers in CI instead of deterministic embeddings — would stop exercising the
  real scan/threshold/gateway chain; rejected (review #9 keeps everything but the vector values real).
