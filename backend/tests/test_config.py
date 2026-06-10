import pytest

from app.platform.config import Settings, SettingsError


def test_cors_origins_default(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    s = Settings()
    assert s.CORS_ORIGINS == ["http://localhost:3000"]


def test_cors_origins_single(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    s = Settings()
    assert s.CORS_ORIGINS == ["http://localhost:3000"]


def test_cors_origins_multiple(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000,https://staging.example.com",
    )
    s = Settings()
    assert s.CORS_ORIGINS == ["http://localhost:3000", "https://staging.example.com"]


def test_embedding_config_defaults(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL_PATH", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL_REVISION", raising=False)
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)
    monkeypatch.delenv("EMBEDDING_WORKER_CONCURRENCY", raising=False)
    monkeypatch.delenv("EMBEDDING_DEVICE", raising=False)

    s = Settings()

    assert str(s.EMBEDDING_MODEL_PATH).endswith(
        "/sentence-transformers/all-MiniLM-L6-v2"
    )
    assert s.EMBEDDING_MODEL_REVISION == (
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    )
    assert s.EMBEDDING_BATCH_SIZE == 16
    assert s.EMBEDDING_WORKER_CONCURRENCY == 1
    assert s.EMBEDDING_DEVICE == "cpu"


@pytest.mark.parametrize(
    ("env_name", "env_value", "property_name", "message"),
    [
        (
            "EMBEDDING_BATCH_SIZE",
            "0",
            "EMBEDDING_BATCH_SIZE",
            "EMBEDDING_BATCH_SIZE must be greater than zero",
        ),
        (
            "EMBEDDING_WORKER_CONCURRENCY",
            "not-int",
            "EMBEDDING_WORKER_CONCURRENCY",
            "EMBEDDING_WORKER_CONCURRENCY must be an integer",
        ),
        (
            "EMBEDDING_DEVICE",
            "cuda",
            "EMBEDDING_DEVICE",
            "EMBEDDING_DEVICE must be cpu",
        ),
    ],
)
def test_embedding_config_rejects_invalid_values(
    monkeypatch,
    env_name,
    env_value,
    property_name,
    message,
):
    monkeypatch.setenv(env_name, env_value)
    s = Settings()

    with pytest.raises(SettingsError, match=message):
        getattr(s, property_name)
