import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import async_session
from app.workers.queues import get_redis_connection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
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


async def _check_database() -> bool:
    """True if a trivial query succeeds against the application database."""
    if async_session is None:
        return False
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # pragma: no cover - exercised via the readiness route
        logger.warning("Readiness: database check failed", exc_info=True)
        return False


def _check_redis() -> bool:
    """True if Redis answers PING."""
    try:
        return bool(get_redis_connection().ping())
    except Exception:  # pragma: no cover - exercised via the readiness route
        logger.warning("Readiness: redis check failed", exc_info=True)
        return False


@router.get("/health/ready", include_in_schema=False)
async def readiness() -> dict[str, object]:
    """Real readiness probe (12f): 200 only when the database AND Redis are both reachable, else 503.

    Distinct from ``/health`` (static liveness). This is an infra probe, not an SPA-facing route, so it
    is excluded from the OpenAPI schema (no generated-client surface; keeps backend/openapi.json stable).
    The synchronous Redis PING is run off the event loop via ``asyncio.to_thread``.
    """
    checks = {
        "database": await _check_database(),
        "redis": await asyncio.to_thread(_check_redis),
    }
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"code": "NOT_READY", "checks": checks})
    return {"status": "ready", "checks": checks}
