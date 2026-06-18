"""Shared embedding platform (Stage 8.2). Promoted from ``domains/transcripts`` so chunk generation
and assistant retrieval read the ONE ``EmbeddingConfig`` and share ``get_encoder()``."""

from __future__ import annotations

from app.platform.embeddings.config import (
    DEFAULT_EMBEDDING_CONFIG,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_NORMALIZATION,
    EMBEDDING_VERSION,
    EmbeddingConfig,
)
from app.platform.embeddings.encoder import (
    DeterministicEmbeddingEncoder,
    EmbeddingConfigurationError,
    EmbeddingEncoder,
    SentenceTransformersEmbeddingEncoder,
    clear_sentence_transformer_model_cache_for_tests,
    get_encoder,
    validate_model_snapshot,
)

__all__ = [
    "DEFAULT_EMBEDDING_CONFIG",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL",
    "EMBEDDING_NORMALIZATION",
    "EMBEDDING_VERSION",
    "EmbeddingConfig",
    "DeterministicEmbeddingEncoder",
    "EmbeddingConfigurationError",
    "EmbeddingEncoder",
    "SentenceTransformersEmbeddingEncoder",
    "clear_sentence_transformer_model_cache_for_tests",
    "get_encoder",
    "validate_model_snapshot",
]
