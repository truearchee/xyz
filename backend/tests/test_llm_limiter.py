"""RedisRateLimiter tests — three-dimension budgeting + TTL-lease reclaim (rule 15 / §6.5).

The redis-dependent tests use the real Redis in the stack with an isolated key prefix; they skip
(with the exact reason) when Redis is unreachable, e.g. a host run outside docker compose.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.platform.config import settings
from app.platform.llm.errors import RateLimited
from app.platform.llm.limiter import RedisRateLimiter, effective_limit

pytestmark = pytest.mark.anyio


def test_effective_limit_headroom_is_pure():
    assert effective_limit(10, "interactive", 20) == 10
    assert effective_limit(10, "background", 20) == 8
    assert effective_limit(1, "background", 20) == 1  # never below 1


@pytest.fixture
async def redis_client():
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.REDIS_URL)
    try:
        await client.ping()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"redis unavailable at {settings.REDIS_URL}: {exc}")
    yield client
    await client.aclose()


def _limiter(redis_client, *, lease_ttl_ms: int = 60_000) -> RedisRateLimiter:
    return RedisRateLimiter(
        redis_client,
        key_prefix=f"test:{uuid4().hex}",
        lease_ttl_ms=lease_ttl_ms,
        headroom_percent=0,
    )


async def test_acquire_and_release_round_trip(redis_client):
    limiter = _limiter(redis_client)
    lease = await limiter.acquire(backend="cerebras", estimated_tokens=10, priority="interactive")
    assert await lease.heartbeat() is True
    await lease.release()
    # released slot is reusable immediately
    again = await limiter.acquire(backend="cerebras", estimated_tokens=10, priority="interactive")
    await again.release()


async def test_concurrency_limit_blocks_then_frees(redis_client, monkeypatch):
    monkeypatch.setenv("LLM_NVIDIA_CONCURRENCY", "2")
    monkeypatch.setenv("LLM_NVIDIA_RPM", "100")
    monkeypatch.setenv("LLM_NVIDIA_TPM", "1000000")
    limiter = _limiter(redis_client)

    a = await limiter.acquire(backend="nvidia", estimated_tokens=1, priority="interactive")
    b = await limiter.acquire(backend="nvidia", estimated_tokens=1, priority="interactive")
    with pytest.raises(RateLimited) as excinfo:
        await limiter.acquire(backend="nvidia", estimated_tokens=1, priority="interactive")
    assert excinfo.value.error_code == "limiter_concurrency"

    await a.release()
    c = await limiter.acquire(backend="nvidia", estimated_tokens=1, priority="interactive")
    await b.release()
    await c.release()


async def test_ttl_lease_is_reclaimed_after_simulated_worker_death(redis_client, monkeypatch):
    monkeypatch.setenv("LLM_NVIDIA_CONCURRENCY", "1")
    monkeypatch.setenv("LLM_NVIDIA_RPM", "100")
    monkeypatch.setenv("LLM_NVIDIA_TPM", "1000000")
    limiter = _limiter(redis_client, lease_ttl_ms=80)

    # Acquire and NEVER release — simulates a crashed worker holding the only slot.
    await limiter.acquire(backend="nvidia", estimated_tokens=1, priority="interactive")
    with pytest.raises(RateLimited):
        await limiter.acquire(backend="nvidia", estimated_tokens=1, priority="interactive")

    # After the lease TTL elapses the slot is reclaimable.
    await asyncio.sleep(0.2)
    reclaimed = await limiter.acquire(backend="nvidia", estimated_tokens=1, priority="interactive")
    await reclaimed.release()


async def test_tpm_binds_before_rpm(redis_client, monkeypatch):
    monkeypatch.setenv("LLM_NVIDIA_RPM", "100")
    monkeypatch.setenv("LLM_NVIDIA_TPM", "100")
    monkeypatch.setenv("LLM_NVIDIA_CONCURRENCY", "100")
    limiter = _limiter(redis_client)

    with pytest.raises(RateLimited) as excinfo:
        await limiter.acquire(backend="nvidia", estimated_tokens=200, priority="interactive")
    assert excinfo.value.error_code == "limiter_tpm"
