import os
from pathlib import Path
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import engine

router = APIRouter()

# backend root holds alembic.ini + the alembic/ tree (health.py is app/api/routers/health.py).
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: cheap, unauthenticated, and intentionally FREE of any DB/Redis dependency so a
    transient infra blip does not turn into a restart loop (spec §7.K). Readiness is /health/ready."""
    return {"status": "ok", "service": "xyz-lms-backend"}


@router.get("/health/authed")
async def authed_health(
    current_user: Annotated[CurrentUserContext, Depends(get_current_user)],
) -> dict[str, str]:
    return {
        "status": "ok",
        "user_id": str(current_user.user_id),
        "role": current_user.role,
        "email": current_user.email,
    }


async def _database_ok() -> bool:
    if engine is None:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _redis_ok() -> bool:
    try:
        client = aioredis.from_url(os.environ["REDIS_URL"])
        try:
            await client.ping()
        finally:
            await client.aclose()
        return True
    except Exception:
        return False


def _expected_head() -> str:
    """The single migration head from the filesystem. Raises if there are branched heads (so a
    branched tree surfaces as not_ready, never a silent 'matches one of two')."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


async def _applied_revision() -> str | None:
    """The applied alembic revision, or None when the alembic_version table does not exist yet
    (a fresh/un-migrated DB — the legitimate 4.8a state). UndefinedTable → None, NOT a 500."""
    if engine is None:
        return None
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none()
    except ProgrammingError:
        return None  # UndefinedTableError (no schema migrated) → readiness red, not a crash


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """Readiness: DB reachable + Redis reachable + alembic_version == head. Returns 503 (not 500) for
    every failure mode, including the un-migrated DB that 4.8a deliberately ships before 4.8b runs the
    release migration. Liveness (/health) stays green throughout."""
    checks: dict[str, str] = {}
    ready = True

    if await _database_ok():
        checks["database"] = "ok"
    else:
        checks["database"] = "unavailable"
        ready = False

    if await _redis_ok():
        checks["redis"] = "ok"
    else:
        checks["redis"] = "unavailable"
        ready = False

    try:
        applied = await _applied_revision()
        expected = _expected_head()
        if applied is None:
            checks["migrations"] = "no_schema"  # alembic_version absent → not migrated (4.8a)
            ready = False
        elif applied != expected:
            checks["migrations"] = "behind_head"
            ready = False
        else:
            checks["migrations"] = "head"
    except Exception:
        checks["migrations"] = "error"  # incl. branched heads from get_current_head()
        ready = False

    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "checks": checks},
        status_code=200 if ready else 503,
    )
