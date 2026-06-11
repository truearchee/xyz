"""Storage reconciliation — loss-safe by construction (ADR-46-D).

Diffs object-store keys against the transcript DB rows. REPORT-ONLY by default; cleanup is a separate,
explicitly-enabled action (flag + ``mode='cleanup'``), prefix-scoped, grace-windowed, deletion-capped.
Superseded transcripts are RETAINED (their storage_key is referenced → never an orphan). A DB ref with
no object is a potential data-loss case: reported loudly, NEVER auto-fixed. Every run writes a
MaintenanceRun.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domains.recovery.locks import maintenance_advisory_lock
from app.domains.recovery.maintenance_run_log import (
    create_maintenance_run,
    finalize_maintenance_run,
)
from app.platform.config import settings
from app.platform.db.models import Transcript
from app.platform.db.session import async_session, engine as default_engine
from app.platform.storage.base import StorageProvider


logger = logging.getLogger(__name__)


def _is_transcript_object(key: str) -> bool:
    return "/transcripts/" in key and "/assets/" not in key


async def run_storage_reconciliation(
    storage: StorageProvider,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    engine: AsyncEngine | None = None,
    triggered_by_user_id: UUID | None = None,
    mode: str = "report_only",
    scope_prefix: str | None = None,
    now: datetime | None = None,
) -> dict | None:
    """Run reconciliation under its singleton lock. Returns the summary dict, or None if the lock was held."""
    factory = session_factory or async_session
    eng = engine or default_engine
    if factory is None or eng is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    async with maintenance_advisory_lock(eng, "storage_reconciliation") as acquired:
        if not acquired:
            return None
        return await _run_reconciliation(
            storage,
            factory,
            triggered_by_user_id=triggered_by_user_id,
            mode=mode,
            scope_prefix=scope_prefix,
            now=now or datetime.now(UTC),
        )


async def _run_reconciliation(
    storage: StorageProvider,
    factory: async_sessionmaker[AsyncSession],
    *,
    triggered_by_user_id: UUID | None,
    mode: str,
    scope_prefix: str | None,
    now: datetime,
) -> dict:
    run_id = await create_maintenance_run(
        factory,
        run_type="storage_reconciliation",
        mode=mode if mode in ("report_only", "cleanup") else "report_only",
        triggered_by_user_id=triggered_by_user_id,
    )
    summary: dict = {}
    try:
        prefix = scope_prefix or settings.RECONCILIATION_MANAGED_PREFIX
        max_objects = settings.RECONCILIATION_MAX_OBJECTS
        listed = await storage.list_objects(prefix=prefix, max_objects=max_objects)
        capped = len(listed) >= max_objects
        transcript_objects = [obj for obj in listed if _is_transcript_object(obj.key)]

        async with factory() as session:
            db_keys = {
                key
                for key in (
                    await session.execute(select(Transcript.storage_key))
                ).scalars().all()
                if key
            }

        grace_cutoff = now - timedelta(seconds=settings.RECONCILIATION_GRACE_WINDOW_SECONDS)
        orphans = [
            obj
            for obj in transcript_objects
            if obj.key not in db_keys and obj.created_at < grace_cutoff
        ]

        cleanup = mode == "cleanup" and settings.RECONCILIATION_CLEANUP_ENABLED
        deleted_keys: list[str] = []
        if cleanup:
            for obj in orphans[: settings.RECONCILIATION_DELETION_CAP_PER_RUN]:
                await storage.delete_object(key=obj.key)
                deleted_keys.append(obj.key)
                logger.info("Reconciliation deleted orphan object", extra={"storage_key": obj.key})

        # Missing refs only when the listing is COMPLETE (not capped) AND full managed scope — else a
        # partial / narrowed listing would raise false data-loss alarms.
        listed_keys = {obj.key for obj in transcript_objects}
        missing_refs: list[str] = []
        if not capped and scope_prefix is None:
            missing_refs = sorted(key for key in db_keys if key not in listed_keys)

        summary = {
            "mode": mode,
            "scanned_objects": len(listed),
            "transcript_objects": len(transcript_objects),
            "db_keys": len(db_keys),
            "orphans_found": len(orphans),
            "deleted": len(deleted_keys),
            "deleted_keys": deleted_keys,
            "missing_refs": len(missing_refs),
            "missing_ref_keys": missing_refs[:50],
            "capped": capped,
            "cleanup_enabled": settings.RECONCILIATION_CLEANUP_ENABLED,
        }
        if missing_refs:
            logger.warning(
                "Storage reconciliation found %d DB ref(s) with no object — POTENTIAL DATA LOSS; "
                "never auto-fixed: %s",
                len(missing_refs),
                missing_refs[:10],
            )
        await finalize_maintenance_run(factory, run_id, status="completed", summary=summary)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("storage reconciliation failed")
        await finalize_maintenance_run(
            factory, run_id, status="failed", summary=summary, error_message=str(exc)[:500]
        )
    return {"run_id": str(run_id), **summary}
