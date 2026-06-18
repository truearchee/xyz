from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.platform.embeddings import (
    EMBEDDING_DIMENSION,
    DeterministicEmbeddingEncoder,
    EmbeddingConfigurationError,
    SentenceTransformersEmbeddingEncoder,
    clear_sentence_transformer_model_cache_for_tests,
    validate_model_snapshot,
)
from app.domains.transcripts.embedding_service import expected_embedding_input_hash


MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def test_deterministic_embedding_encoder_returns_384_normalized_finite_values() -> None:
    encoder = DeterministicEmbeddingEncoder()

    first = encoder.encode(["hello world"])[0]
    second = encoder.encode(["hello world"])[0]

    assert first == second
    assert len(first) == EMBEDDING_DIMENSION
    assert all(math.isfinite(value) for value in first)
    assert math.isclose(
        math.sqrt(sum(value * value for value in first)),
        1.0,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def test_embedding_input_hash_is_stable_and_canonical() -> None:
    first = expected_embedding_input_hash(
        chunk_text="hello world",
        model_revision=MODEL_REVISION,
        chunking_version="chunk-v1-no-overlap-180w",
    )
    second = expected_embedding_input_hash(
        chunking_version="chunk-v1-no-overlap-180w",
        model_revision=MODEL_REVISION,
        chunk_text="hello world",
    )

    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("chunk text", {"chunk_text": "changed"}),
        ("embedding model", {"embedding_model": "different-model"}),
        ("model revision", {"model_revision": "different-revision"}),
        ("normalization", {"embedding_normalization": "none"}),
        ("chunking version", {"chunking_version": "chunk-v2"}),
    ],
)
def test_embedding_input_hash_changes_when_payload_inputs_change(
    field: str,
    kwargs: dict[str, str],
) -> None:
    base = {
        "chunk_text": "hello world",
        "model_revision": MODEL_REVISION,
        "chunking_version": "chunk-v1-no-overlap-180w",
    }
    changed = {**base, **kwargs}

    assert expected_embedding_input_hash(**base) != expected_embedding_input_hash(**changed), field


def test_model_snapshot_validation_rejects_missing_path(tmp_path) -> None:
    with pytest.raises(EmbeddingConfigurationError, match="path is unavailable"):
        validate_model_snapshot(
            model_path=tmp_path / "missing",
            expected_revision=MODEL_REVISION,
        )


def test_model_snapshot_validation_rejects_revision_mismatch(tmp_path) -> None:
    model_path = _write_valid_model_snapshot(tmp_path)
    (model_path / "MODEL_REVISION").write_text("wrong\n", encoding="utf-8")

    with pytest.raises(EmbeddingConfigurationError, match="revision mismatch"):
        validate_model_snapshot(
            model_path=model_path,
            expected_revision=MODEL_REVISION,
        )


@pytest.mark.parametrize(
    "missing_paths",
    [
        ("model.safetensors",),
        ("tokenizer.json",),
        ("model.safetensors", "pytorch_model.bin"),
        ("tokenizer.json", "vocab.txt"),
    ],
)
def test_model_snapshot_validation_rejects_incomplete_file_sets(
    tmp_path,
    missing_paths: tuple[str, ...],
) -> None:
    model_path = _write_valid_model_snapshot(tmp_path)
    for relative_path in missing_paths:
        path = model_path / relative_path
        if path.exists():
            path.unlink()

    if missing_paths in {("model.safetensors",), ("tokenizer.json",)}:
        validate_model_snapshot(
            model_path=model_path,
            expected_revision=MODEL_REVISION,
        )
    else:
        with pytest.raises(EmbeddingConfigurationError, match="files are incomplete"):
            validate_model_snapshot(
                model_path=model_path,
                expected_revision=MODEL_REVISION,
            )


def test_sentence_transformers_model_is_cached_per_process(tmp_path) -> None:
    clear_sentence_transformer_model_cache_for_tests()
    model_path = _write_valid_model_snapshot(tmp_path)
    loads: list[tuple[str, str]] = []

    class FakeEncoded:
        def tolist(self) -> list[list[float]]:
            return [[1.0, *([0.0] * (EMBEDDING_DIMENSION - 1))]]

    class FakeModel:
        def encode(self, *_args, **_kwargs) -> FakeEncoded:
            return FakeEncoded()

    def fake_factory(path: str, *, device: str) -> FakeModel:
        loads.append((path, device))
        return FakeModel()

    try:
        first = SentenceTransformersEmbeddingEncoder(
            model_path=model_path,
            expected_revision=MODEL_REVISION,
            device="cpu",
            model_factory=fake_factory,
        )
        second = SentenceTransformersEmbeddingEncoder(
            model_path=model_path,
            expected_revision=MODEL_REVISION,
            device="cpu",
            model_factory=fake_factory,
        )

        assert first.encode(["hello world"]) == second.encode(["hello world"])
        assert loads == [(str(model_path), "cpu")]
    finally:
        clear_sentence_transformer_model_cache_for_tests()


def _write_valid_model_snapshot(tmp_path) -> Path:
    model_path = tmp_path / "model"
    (model_path / "1_Pooling").mkdir(parents=True)
    for relative_path in (
        "config.json",
        "modules.json",
        "tokenizer_config.json",
        "sentence_bert_config.json",
        "1_Pooling/config.json",
        "model.safetensors",
        "pytorch_model.bin",
        "tokenizer.json",
        "vocab.txt",
    ):
        (model_path / relative_path).write_text("{}", encoding="utf-8")
    (model_path / "MODEL_REVISION").write_text(MODEL_REVISION + "\n", encoding="utf-8")
    return model_path
