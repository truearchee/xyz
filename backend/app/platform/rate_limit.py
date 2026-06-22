from __future__ import annotations

from inspect import isawaitable
import logging
from typing import Any

from fastapi import HTTPException, status
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.platform.config import settings

logger = logging.getLogger(__name__)


async def enforce_fixed_window_rate_limit(
    *,
    key: str,
    limit: int,
    window_seconds: int,
    client: Any | None = None,
) -> None:
    """Small Redis fixed-window limiter for non-LLM HTTP controls.

    This is deliberately separate from ``platform.llm.limiter`` because manual admin controls are
    request-count bounded only and must not consume AI capacity dimensions.
    """
    if limit <= 0:
        return

    owns_client = client is None
    redis_client = client or aioredis.from_url(settings.REDIS_URL)
    try:
        count = int(await redis_client.incr(key))
        if count == 1:
            await redis_client.expire(key, window_seconds)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
    except RedisError:
        logger.warning("Rate limiter unavailable for %s; allowing request", key, exc_info=True)
    finally:
        if owns_client:
            close = getattr(redis_client, "aclose", None) or getattr(redis_client, "close", None)
            if close is not None:
                result = close()
                if isawaitable(result):
                    await result
