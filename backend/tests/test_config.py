from app.platform.config import Settings


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
