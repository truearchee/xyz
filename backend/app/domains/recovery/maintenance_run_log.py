"""Create + finalize a MaintenanceRun row (the observability record every recovery run writes)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.db.models import MaintenanceRun


async def create_maintenance_run(
    factory: async_sessionmaker[AsyncSession],
    *,
    run_type: str,
    mode: str,
    triggered_by_user_id: UUID | None,
) -> UUID:
    async with factory() as session:
        async with session.begin():
            run = MaintenanceRun(
                run_type=run_type,
                mode=mode,
                status="running",
                triggered_by_user_id=triggered_by_user_id,
            )
            session.add(run)
            await session.flush()
            return run.id


async def finalize_maintenance_run(
    factory: async_sessionmaker[AsyncSession],
    run_id: UUID,
    *,
    status: str,
    summary: dict,
    error_message: str | None = None,
) -> None:
    async with factory() as session:
        async with session.begin():
            run = await session.get(MaintenanceRun, run_id)
            if run is None:  # pragma: no cover - defensive
                return
            run.status = status
            run.summary_json = summary
            run.error_message = error_message
            run.completed_at = datetime.now(UTC)
