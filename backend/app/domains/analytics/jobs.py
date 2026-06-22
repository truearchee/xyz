from __future__ import annotations

import asyncio
from uuid import UUID

from app.domains.analytics.service import run_agent_run
from app.platform.db.session import async_session


def run_agent(run_id: str) -> None:
    asyncio.run(_run_agent_async(UUID(run_id)))


async def _run_agent_async(run_id: UUID) -> None:
    if async_session is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    async with async_session() as session:
        await run_agent_run(session, run_id=run_id)
