"""Shared embedding configuration (Stage 8.2 — promoted from ``domains/transcripts``).

``EmbeddingConfig`` is the ONE source of truth for embedding geometry + provenance, read by BOTH
transcript chunk generation (Stage 4.4) and assistant retrieval (Stage 8.2). Promoted to ``platform``
so the assistant never re-hardcodes MiniLM-L6 / 384 / l2 / embedding-v1 and so a future model swap is a
single edit (ADR — embedding promotion). Extraction only: the values are byte-identical to the prior
``domains/transcripts/embedding_encoder`` constants.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str
    dimension: int
    normalization: str
    embedding_version: str
    distance_metric: str = "cosine"


# MiniLM-L6-v2 — the model snapshot baked into the backend image (Stage 4.4). pgvector compares chunk
# vectors with cosine distance (``<=>``); vectors are L2-normalized so cosine == dot product.
DEFAULT_EMBEDDING_CONFIG = EmbeddingConfig(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    dimension=384,
    normalization="l2",
    embedding_version="embedding-v1",
    distance_metric="cosine",
)

# Backwards-compatible module-level aliases. The chunk-embed writer stamps these as provenance on every
# chunk REGARDLESS of which encoder produced the vector, so a deterministic CI/E2E encoder still yields
# rows that satisfy the chunk CHECK (dim 384, normalization 'l2') and the retrieval same-model filter
# (``embedding_model`` / ``embedding_version``) — provenance parity (review #9).
EMBEDDING_MODEL = DEFAULT_EMBEDDING_CONFIG.model_name
EMBEDDING_DIMENSION = DEFAULT_EMBEDDING_CONFIG.dimension
EMBEDDING_NORMALIZATION = DEFAULT_EMBEDDING_CONFIG.normalization
EMBEDDING_VERSION = DEFAULT_EMBEDDING_CONFIG.embedding_version
