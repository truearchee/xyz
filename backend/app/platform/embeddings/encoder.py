"""Embedding encoders (Stage 8.2 — promoted verbatim from ``domains/transcripts/embedding_encoder``).

Behavior is byte-identical to the prior module (extraction, not redesign — ADR). The only addition is
``get_encoder()``, the process-wide factory that honors ``EMBEDDING_PROVIDER`` so chunk embedding AND
assistant query embedding share one encoder. The query embedding is LOCAL/in-process (sentence-
transformers or deterministic) — NEVER a metered provider/gateway call (review #6).
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import threading
from typing import Any, Callable, Protocol

from app.platform.embeddings.config import EMBEDDING_DIMENSION

_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}


class EmbeddingConfigurationError(RuntimeError):
    pass


class EmbeddingEncoder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]:
        pass


class SentenceTransformersEmbeddingEncoder:
    def __init__(
        self,
        *,
        model_path: Path,
        expected_revision: str,
        device: str = "cpu",
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._model = _get_cached_sentence_transformer_model(
            model_path=model_path,
            expected_revision=expected_revision,
            device=device,
            model_factory=model_factory,
        )

    def encode(self, texts: list[str]) -> list[list[float]]:
        encoded = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vectors = encoded.tolist()
        return [_validate_vector(vector) for vector in vectors]


class DeterministicEmbeddingEncoder:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_vector(text) for text in texts]


def get_encoder() -> EmbeddingEncoder:
    """Process-wide encoder selected by ``EMBEDDING_PROVIDER`` (``sentence_transformers`` in prod,
    ``deterministic`` in CI/E2E). Both transcript chunk embedding and assistant retrieval call this so
    the query and the chunks are produced by the SAME encoder — that is what makes the deterministic
    identical-text→distance-0 retrieval contract hold end-to-end (review #9)."""
    from app.platform.config import settings  # local import avoids a config↔embeddings import cycle

    if settings.EMBEDDING_PROVIDER == "deterministic":
        return DeterministicEmbeddingEncoder()
    return SentenceTransformersEmbeddingEncoder(
        model_path=settings.EMBEDDING_MODEL_PATH,
        expected_revision=settings.EMBEDDING_MODEL_REVISION,
        device=settings.EMBEDDING_DEVICE,
    )


def validate_model_snapshot(
    *,
    model_path: Path,
    expected_revision: str,
) -> None:
    if not model_path.exists() or not model_path.is_dir():
        raise EmbeddingConfigurationError("embedding model path is unavailable")

    revision_file = model_path / "MODEL_REVISION"
    if not revision_file.exists():
        raise EmbeddingConfigurationError("embedding model revision marker is missing")
    actual_revision = revision_file.read_text(encoding="utf-8").strip()
    if actual_revision != expected_revision:
        raise EmbeddingConfigurationError("embedding model revision mismatch")

    required_any = (
        ("model.safetensors", "pytorch_model.bin"),
        ("tokenizer.json", "vocab.txt"),
    )
    required_files = (
        "config.json",
        "modules.json",
        "tokenizer_config.json",
        "sentence_bert_config.json",
        "1_Pooling/config.json",
    )
    for relative_path in required_files:
        if not (model_path / relative_path).exists():
            raise EmbeddingConfigurationError("embedding model files are incomplete")
    for alternatives in required_any:
        if not any((model_path / relative_path).exists() for relative_path in alternatives):
            raise EmbeddingConfigurationError("embedding model files are incomplete")


def clear_sentence_transformer_model_cache_for_tests() -> None:
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()


def _get_cached_sentence_transformer_model(
    *,
    model_path: Path,
    expected_revision: str,
    device: str,
    model_factory: Callable[..., Any] | None = None,
) -> Any:
    validate_model_snapshot(
        model_path=model_path,
        expected_revision=expected_revision,
    )
    cache_key = (str(model_path.resolve()), expected_revision, device)
    with _MODEL_CACHE_LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        factory = model_factory or _load_sentence_transformer_model
        model = factory(str(model_path), device=device)
        _MODEL_CACHE[cache_key] = model
        return model


def _load_sentence_transformer_model(model_path: str, *, device: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - exercised in image/runtime checks
        raise EmbeddingConfigurationError(
            "sentence-transformers dependency is unavailable"
        ) from exc
    return SentenceTransformer(model_path, device=device)


def _validate_vector(vector: list[float]) -> list[float]:
    if len(vector) != EMBEDDING_DIMENSION:
        raise EmbeddingConfigurationError("embedding dimension mismatch")
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingConfigurationError("embedding vector contains non-finite values")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
        raise EmbeddingConfigurationError("embedding vector is not l2-normalized")
    return [float(value) for value in vector]


def _deterministic_vector(text: str) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < EMBEDDING_DIMENSION:
        digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        values.extend((byte - 127.5) / 127.5 for byte in digest)
        counter += 1
    vector = values[:EMBEDDING_DIMENSION]
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]
