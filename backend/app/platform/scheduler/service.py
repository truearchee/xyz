from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domains.analytics.service import get_or_create_agent_run
from app.platform.config import settings
from app.platform.scheduler.locks import scheduler_advisory_lock
from app.workers.queues import agent_run_status_is_requeueable, enqueue_run_agent_if_needed

logger = logging.getLogger(__name__)


async def run_scheduler_forever(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
) -> None:
    logger.info("Scheduler ready. Polling every %s seconds.", settings.SCHEDULER_POLL_SECONDS)
    while True:
        if settings.SCHEDULER_ENABLED:
            try:
                await scheduler_tick(session_factory=session_factory, engine=engine)
            except Exception:  # pragma: no cover - defensive process guard
                logger.exception("Scheduler tick failed")
        await asyncio.sleep(settings.SCHEDULER_POLL_SECONDS)


async def scheduler_tick(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    now: datetime | None = None,
) -> bool:
    async with scheduler_advisory_lock(engine) as acquired:
        if not acquired:
            logger.debug("Scheduler tick skipped; another instance holds the lock.")
            return False
        scheduled_for = daily_scheduled_for(now or datetime.now(UTC))
        async with session_factory() as session:
            run, created = await get_or_create_agent_run(
                session,
                trigger_type="scheduled_daily",
                scope_type="all",
                scope_id=None,
                scheduled_for=scheduled_for,
                triggered_by_user_id=None,
                algorithm_version=settings.RISK_ALGORITHM_VERSION,
            )
            await session.commit()
            if run.scheduled_for <= datetime.now(UTC) and agent_run_status_is_requeueable(run.status):
                _job_id, enqueued = enqueue_run_agent_if_needed(run.id)
                if enqueued:
                    logger.info("Enqueued scheduled AgentRun %s for %s", run.id, run.scheduled_for)
                else:
                    logger.debug("Scheduled AgentRun %s already has a live RQ job.", run.id)
            return created


def daily_scheduled_for(now: datetime) -> datetime:
    tz = ZoneInfo(settings.INSTITUTION_TIMEZONE)
    local = now.astimezone(tz)
    scheduled_local = local.replace(
        hour=settings.SCHEDULER_DAILY_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    if scheduled_local > local:
        scheduled_local = scheduled_local - timedelta(days=1)
    return scheduled_local.astimezone(UTC)
