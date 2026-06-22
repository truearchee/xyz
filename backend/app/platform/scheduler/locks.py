from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


SCHEDULER_LOCK_KEY = 110001


@asynccontextmanager
async def scheduler_advisory_lock(engine: AsyncEngine):
    async with engine.connect() as conn:
        acquired = bool(
            (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULER_LOCK_KEY})).scalar()
        )
        await conn.commit()
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEDULER_LOCK_KEY})
                await conn.commit()
