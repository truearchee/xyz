"""Stage 4.8 (B1, MF3) — pooler-aware engine builder + direct-engine factory.

The pooler discriminator is an EXPLICIT setting (DATABASE_POOLER), never inferred from the URL/port
(Supabase direct + transaction-pooler endpoints can both be :5432). These are pure-function tests —
no DB connection is opened.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import NullPool

from app.platform.db import session as session_module


def test_pooler_mode_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_POOLER", raising=False)
    assert session_module._pooler_mode() is False
    assert session_module._pooler_connect_args() == {}  # local behaviour unchanged


def test_pooler_mode_on_disables_statement_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_POOLER", "true")
    assert session_module._pooler_mode() is True
    kwargs = session_module._pooler_connect_args()
    connect_args = kwargs["connect_args"]
    assert connect_args["statement_cache_size"] == 0
    name_func = connect_args["prepared_statement_name_func"]
    assert callable(name_func)
    assert name_func() != name_func()  # unique per call → no collision across pooled backends
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 0


def test_pooler_mode_respects_explicit_pool_sizing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_POOLER", "true")
    monkeypatch.setenv("DATABASE_POOL_SIZE", "3")
    monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "2")
    kwargs = session_module._pooler_connect_args()
    assert kwargs["pool_size"] == 3
    assert kwargs["max_overflow"] == 2


def test_create_direct_engine_requires_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_module, "DIRECT_DATABASE_URL", None)
    with pytest.raises(RuntimeError):
        session_module.create_direct_engine()


def test_create_direct_engine_uses_nullpool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_module, "DIRECT_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db"
    )
    engine = session_module.create_direct_engine()
    # NullPool: a fresh real connection per checkout — the advisory lock is never handed back mid-reap.
    assert isinstance(engine.sync_engine.pool, NullPool)
