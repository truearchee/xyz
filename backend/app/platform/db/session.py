import os
from collections.abc import AsyncIterator
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL")
# The DIRECT/session endpoint (Alembic + the maintenance advisory lock). Falls back to DATABASE_URL
# so local single-URL development is unchanged; in staging it is the Supabase direct/session URL
# (adr-041). Read as a module attribute so tests can monkeypatch it.
DIRECT_DATABASE_URL = os.environ.get("DIRECT_DATABASE_URL") or DATABASE_URL


def _pooler_mode() -> bool:
    """Explicit signal that DATABASE_URL is a transaction pooler (e.g. Supabase pgBouncer), driven by
    an env flag — NOT URL/port archaeology. Supabase's direct and transaction-pooler endpoints can
    BOTH listen on :5432, so a port sniff is a latent bug; the deploy sets DATABASE_POOLER=true."""
    return (os.environ.get("DATABASE_POOLER") or "").strip().lower() in {"1", "true", "yes", "on"}


def _pooler_connect_args() -> dict:
    """asyncpg over a transaction pooler: the server-side prepared-statement cache must be disabled,
    and statement names must be unique per connection (the pooler rebinds backends per transaction,
    so a reused name collides). Empty dict off the pooler → identical local behaviour."""
    if not _pooler_mode():
        return {}
    return {
        "connect_args": {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4().hex}__",
        },
        "pool_size": int(os.environ.get("DATABASE_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DATABASE_MAX_OVERFLOW", "0")),
    }


engine = create_async_engine(DATABASE_URL, **_pooler_connect_args()) if DATABASE_URL else None
async_session = (
    async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    if engine is not None
    else None
)


def create_direct_engine() -> AsyncEngine:
    """A NullPool engine on the DIRECT/session endpoint for the two things a transaction pooler breaks:
    Alembic (DDL, multi-statement) and the maintenance advisory lock (session-level
    ``pg_advisory_lock`` is per-connection and is lost when a pooled connection is handed back — see
    adr-041 / ``recovery/locks.py``). NullPool: a fresh real connection per checkout, never returned to
    a pool mid-critical-section. No pooler connect-args here — the direct endpoint is a real session
    and supports prepared statements normally."""
    if not DIRECT_DATABASE_URL:
        raise RuntimeError("DIRECT_DATABASE_URL (or DATABASE_URL) is required")
    return create_async_engine(DIRECT_DATABASE_URL, poolclass=NullPool)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    if async_session is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    async with async_session() as session:
        yield session
