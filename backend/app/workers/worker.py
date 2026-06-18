import asyncio
import logging
import os
import sys

from redis import Redis
from rq import Queue, Worker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.platform.embeddings import validate_model_snapshot
from app.platform.config import settings
from app.workers.queues import AI_QUEUE_NAME, EMBEDDING_QUEUE_NAME, INGESTION_QUEUE_NAME

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    queue_name = _queue_name()
    if queue_name == EMBEDDING_QUEUE_NAME:
        _validate_embedding_worker_startup()
    if queue_name == AI_QUEUE_NAME:
        _validate_ai_worker_startup()
    redis_url = os.environ["REDIS_URL"]
    connection = Redis.from_url(redis_url)
    worker = Worker([Queue(queue_name, connection=connection)], connection=connection)
    logger.info("Worker ready. Listening on %s queue.", queue_name)
    _run_startup_recovery()
    worker.work()


def _run_startup_recovery() -> None:
    """Stage 4.6c: run the stuck-row reaper (and, if enabled, storage reconciliation) once at startup.
    Both are singleton-locked (only one of the N workers executes; the rest skip). A recovery error must
    NEVER stop the worker from starting, so it is best-effort."""
    try:
        asyncio.run(_startup_recovery_async())
    except Exception:  # pragma: no cover - defensive; recovery never blocks worker boot
        logger.exception("Startup recovery failed; continuing to start the worker")


async def _startup_recovery_async() -> None:
    """Run startup recovery on an ISOLATED NullPool engine — the module-level engine singleton must
    NEVER be connected in the parent worker process (F-4.6c-1). RQ forks a child per job; a parent-side
    pooled asyncpg connection (bound to this startup event loop) would be inherited by the fork and fail
    every job's first DB call with "got Future attached to a different loop". NullPool keeps no
    fork-inheritable connection, and we dispose the isolated engine before `worker.work()` forks. The
    invariant is structural ("recovery uses its own engine"), not "remember to dispose in the right
    order". See [[findings-4.6-gate]] / adr-032; flag for 11.1's parent-side scheduler hooks."""
    from app.platform.db import session as db_session_module

    if db_session_module.DATABASE_URL is None:
        return

    recovery_engine = create_async_engine(db_session_module.DATABASE_URL, poolclass=NullPool)
    recovery_factory = async_sessionmaker(
        recovery_engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        if settings.REAPER_RUN_AT_STARTUP:
            from app.domains.recovery.reaper import run_stuck_row_reaper

            result = await run_stuck_row_reaper(
                session_factory=recovery_factory, engine=recovery_engine
            )
            logger.info("Startup reaper result: %s", result)
        if settings.RECONCILE_AT_STARTUP:
            from app.domains.recovery.reconciliation import run_storage_reconciliation
            from app.platform.storage import get_storage_provider

            storage = await get_storage_provider()
            result = await run_storage_reconciliation(
                storage, session_factory=recovery_factory, engine=recovery_engine
            )
            logger.info("Startup reconciliation result: %s", result)
    finally:
        await recovery_engine.dispose()


def _queue_name() -> str:
    if len(sys.argv) <= 1:
        return INGESTION_QUEUE_NAME
    if sys.argv[1] == "embedding":
        return EMBEDDING_QUEUE_NAME
    if sys.argv[1] == "ingestion":
        return INGESTION_QUEUE_NAME
    if sys.argv[1] == "ai":
        return AI_QUEUE_NAME
    raise SystemExit("worker queue must be ingestion, embedding, or ai")


def _validate_embedding_worker_startup() -> None:
    _ = settings.EMBEDDING_BATCH_SIZE
    _ = settings.EMBEDDING_WORKER_CONCURRENCY
    validate_model_snapshot(
        model_path=settings.EMBEDDING_MODEL_PATH,
        expected_revision=settings.EMBEDDING_MODEL_REVISION,
    )


def _validate_ai_worker_startup() -> None:
    # PromptRegistry loads + validates all prompt files; a malformed/missing prompt is a boot
    # failure (spec §6.4). The provider config is verified here too.
    from app.platform.llm.registry import get_prompt_registry

    get_prompt_registry()
    if settings.LLM_PROVIDER == "k2think" and not settings.LLM_API_KEY:
        raise SystemExit("LLM_API_KEY is required when LLM_PROVIDER=k2think")


if __name__ == "__main__":
    main()
