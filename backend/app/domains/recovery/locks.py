"""Singleton advisory lock for maintenance runs (ADR-46-C).

Both recovery jobs are idempotent but NOT safe to run concurrently across N worker containers, so each
acquires a Postgres session-level advisory lock; a worker that can't take it skips (writes no
MaintenanceRun — it isn't a run). The lock is held on a DEDICATED connection for the whole run: a
session-level advisory lock would otherwise be lost when the work session commits and returns its
connection to the pool, and would even leak to the next pool user if not explicitly released — so we
pin one connection, hold the lock on it, and always ``pg_advisory_unlock`` before it returns to the pool.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


# Fixed bigint keys (advisory lock keys are global per database; nothing else uses these).
_LOCK_KEYS: dict[str, int] = {
    "stuck_row_reaper": 460001,
    "storage_reconciliation": 460002,
}


@asynccontextmanager
async def maintenance_advisory_lock(engine: AsyncEngine, name: str):
    """Yield ``acquired: bool``. When True, the caller holds the singleton lock for ``name``."""
    key = _LOCK_KEYS[name]
    async with engine.connect() as conn:
        acquired = bool(
            (
                await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})
            ).scalar()
        )
        await conn.commit()  # end the autobegun txn; the session-level lock persists on this connection
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                await conn.commit()
