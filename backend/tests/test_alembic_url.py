"""Stage 4.8b (B1) — migrations resolve to the DIRECT/session endpoint, never the pooler (adr-041)."""

from __future__ import annotations

import pytest

from app.platform.db.alembic_url import resolve_migration_url


def test_prefers_direct_over_pooler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIRECT_DATABASE_URL", "postgresql+asyncpg://direct/db")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://pooler/db")
    assert resolve_migration_url("ini://fallback") == "postgresql+asyncpg://direct/db"


def test_falls_back_to_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIRECT_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://pooler/db")
    assert resolve_migration_url("ini://fallback") == "postgresql+asyncpg://pooler/db"


def test_falls_back_to_ini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIRECT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert resolve_migration_url("ini://fallback") == "ini://fallback"
