"""F-4.6c-1 regression: startup recovery must not poison the module engine pool for forked jobs.

A unit test that INJECTS the engine into the reaper cannot catch this — that injection is exactly the
coverage gap that let F-4.6c-1 ship (329→349 green, live gate red). This test exercises the real worker
startup path: the PARENT runs ``asyncio.run(_startup_recovery_async())`` (its own event loop), then a
SEPARATE ``asyncio.run`` — the analogue of an RQ-forked job — issues the first DB call through the
MODULE engine. Before the fix the second loop raised ``RuntimeError: got Future attached to a different
loop`` because startup recovery had connected the module engine in the first loop and the default pool
handed back a dead-loop connection. The fix runs recovery on an isolated NullPool engine, so the module
engine is never connected in the parent.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.recovery import reaper as reaper_module
from app.platform.db import session as db_session_module
from app.workers import worker as worker_module


def test_startup_recovery_does_not_poison_module_engine_for_forked_jobs(monkeypatch) -> None:
    test_url = os.environ["TEST_DATABASE_URL"]
    # Stand in for the real module-level singleton with a DEFAULT-pool engine — the kind that, once
    # connected in the startup loop, hands a dead-loop connection to the next asyncio.run. The fix must
    # leave it untouched. The reaper binds `async_session`/`default_engine` at import (they are None in
    # the test process, where only TEST_DATABASE_URL is set), so patch those bindings too — that is the
    # default path the UNFIXED `run_stuck_row_reaper()` (no args) takes.
    module_engine = create_async_engine(test_url)
    module_factory = async_sessionmaker(module_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_session_module, "engine", module_engine)
    monkeypatch.setattr(db_session_module, "async_session", module_factory)
    monkeypatch.setattr(db_session_module, "DATABASE_URL", test_url)
    monkeypatch.setattr(reaper_module, "default_engine", module_engine)
    monkeypatch.setattr(reaper_module, "async_session", module_factory)
    # settings.* are read-only env-backed properties — drive them via the environment.
    monkeypatch.setenv("REAPER_RUN_AT_STARTUP", "true")
    monkeypatch.setenv("RECONCILE_AT_STARTUP", "false")

    # Loop A — the parent worker process runs startup recovery before worker.work().
    asyncio.run(worker_module._startup_recovery_async())

    # Loop B — the forked-job analogue issues its FIRST DB call through the MODULE engine (and tidies
    # up the MaintenanceRun the reaper wrote + disposes, all in this one loop so the module engine is
    # only ever touched here). Without the fix, startup recovery connected the module engine in loop A
    # and this first call raises RuntimeError: got Future attached to a different loop.
    async def first_job_then_cleanup() -> int:
        async with db_session_module.async_session() as session:
            value = (await session.execute(text("SELECT 1"))).scalar_one()
        async with module_engine.begin() as conn:
            await conn.execute(text("DELETE FROM maintenance_runs"))
        await module_engine.dispose()
        return value

    assert asyncio.run(first_job_then_cleanup()) == 1
