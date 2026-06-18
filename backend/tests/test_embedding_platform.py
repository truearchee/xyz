"""Promoted embedding platform — compatibility + determinism contract (Stage 8.2, reviews #5/#9).

Locks the behavior the assistant retrieval depends on after extracting the encoder from
``domains/transcripts`` to ``platform/embeddings``:
  - the shared ``EmbeddingConfig`` matches the transcript-chunk CHECK (dim 384, normalization 'l2')
    and the legacy module-level constants (no consumer re-hardcodes the geometry);
  - the deterministic encoder emits 384-d L2-normalized vectors satisfying that CHECK, and obeys the
    distance contract the CI/E2E grounding gate relies on (identical text → distance 0; different text
    → ~orthogonal, distance ≈ 1);
  - ``get_encoder()`` honors ``EMBEDDING_PROVIDER`` and rejects ``deterministic`` in prod/staging.
"""

from __future__ import annotations

import math

import pytest

from app.platform.config import SettingsError, settings
from app.platform.embeddings import (
    DEFAULT_EMBEDDING_CONFIG,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_NORMALIZATION,
    EMBEDDING_VERSION,
    DeterministicEmbeddingEncoder,
    SentenceTransformersEmbeddingEncoder,
    get_encoder,
)


def _cosine_distance(a: list[float], b: list[float]) -> float:
    # pgvector `<=>` for L2-normalized vectors == 1 - dot product.
    return 1.0 - sum(x * y for x, y in zip(a, b, strict=True))


def test_default_config_matches_chunk_check_and_legacy_constants() -> None:
    # These exact values are enforced by ck_transcript_chunks_embedding_provenance (dim 384, 'l2')
    # and by the retrieval same-model filter (model name + version). A drift here would silently
    # exclude every chunk from retrieval.
    assert DEFAULT_EMBEDDING_CONFIG.dimension == 384
    assert DEFAULT_EMBEDDING_CONFIG.normalization == "l2"
    assert DEFAULT_EMBEDDING_CONFIG.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert DEFAULT_EMBEDDING_CONFIG.embedding_version == "embedding-v1"
    assert DEFAULT_EMBEDDING_CONFIG.distance_metric == "cosine"
    # Legacy aliases stay in lock-step (embedding_service.py still stamps these as provenance).
    assert EMBEDDING_DIMENSION == DEFAULT_EMBEDDING_CONFIG.dimension
    assert EMBEDDING_MODEL == DEFAULT_EMBEDDING_CONFIG.model_name
    assert EMBEDDING_NORMALIZATION == DEFAULT_EMBEDDING_CONFIG.normalization
    assert EMBEDDING_VERSION == DEFAULT_EMBEDDING_CONFIG.embedding_version


def test_deterministic_encoder_satisfies_chunk_check_geometry() -> None:
    encoder = DeterministicEmbeddingEncoder()
    vector = encoder.encode(["photosynthesis converts light to chemical energy"])[0]
    assert len(vector) == EMBEDDING_DIMENSION  # == 384, the Vector(384) column + CHECK
    assert all(math.isfinite(v) for v in vector)
    norm = math.sqrt(sum(v * v for v in vector))
    assert math.isclose(norm, 1.0, rel_tol=1e-9, abs_tol=1e-9)  # 'l2'


def test_deterministic_distance_contract_identical_zero_different_orthogonal() -> None:
    encoder = DeterministicEmbeddingEncoder()
    q = encoder.encode(["what is gradient descent"])[0]
    same = encoder.encode(["what is gradient descent"])[0]
    other = encoder.encode(["the mitochondrion is the powerhouse of the cell"])[0]

    # Identical text → distance 0 (well under the 0.35 threshold → grounded in the E2E gate).
    assert math.isclose(_cosine_distance(q, same), 0.0, abs_tol=1e-9)
    # Different text → ~orthogonal, distance ≈ 1 (well above threshold → general_not_from_lecture).
    assert _cosine_distance(q, other) > 0.8


def test_get_encoder_honors_embedding_provider_deterministic(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert isinstance(get_encoder(), DeterministicEmbeddingEncoder)


def test_get_encoder_sentence_transformers_is_default(monkeypatch) -> None:
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    assert settings.EMBEDDING_PROVIDER == "sentence_transformers"
    # The model snapshot is baked into the backend image, so the real branch constructs the ST encoder.
    encoder = get_encoder()
    assert isinstance(encoder, SentenceTransformersEmbeddingEncoder)


def test_deterministic_embedding_rejected_in_production(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(SettingsError, match="not allowed in prod"):
        _ = settings.EMBEDDING_PROVIDER


def test_invalid_embedding_provider_rejected(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    with pytest.raises(SettingsError, match="must be"):
        _ = settings.EMBEDDING_PROVIDER
