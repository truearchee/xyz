"""Redis rate limiter (rule 15 / spec §6.5).

Budgets three dimensions per backend — requests/min, tokens/min, concurrency — with priority
headroom (background traffic may use at most ``100 - LLM_INTERACTIVE_HEADROOM_PERCENT`` % of each
dimension, reserving the rest for INTERACTIVE Stage-8 traffic). Concurrency slots are **TTL leases**:
each lease is a ZSET member scored by its expiry, so a crashed worker's slot is reclaimed on the
next prune rather than leaked forever. The acquire is a single atomic Lua script (prune → check all
three → reserve) keyed off the Redis server clock to avoid cross-worker skew.
"""

from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as aioredis
from uuid6 import uuid7

from app.platform.config import settings
from app.platform.llm.errors import RateLimited
from app.platform.llm.models.prompt import Backend, Priority

WINDOW_MS = 60_000

# Atomic acquire: prune expired entries, check rpm/tpm/concurrency, reserve all three.
# Returns {granted(0/1), blocked_dimension, observed_value}.
_ACQUIRE_LUA = """
local t = redis.call('TIME')
local now_ms = (tonumber(t[1]) * 1000) + math.floor(tonumber(t[2]) / 1000)
local window_ms = tonumber(ARGV[1])
local rpm_limit = tonumber(ARGV[2])
local tpm_limit = tonumber(ARGV[3])
local conc_limit = tonumber(ARGV[4])
local tokens = tonumber(ARGV[5])
local entry_id = ARGV[6]
local lease_ttl_ms = tonumber(ARGV[7])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now_ms - window_ms)
redis.call('ZREMRANGEBYSCORE', KEYS[2], 0, now_ms - window_ms)
redis.call('ZREMRANGEBYSCORE', KEYS[3], 0, now_ms)

local rpm = redis.call('ZCARD', KEYS[1])
if rpm + 1 > rpm_limit then return {0, 'rpm', rpm} end

local members = redis.call('ZRANGE', KEYS[2], 0, -1)
local used = 0
for i = 1, #members do
  local sep = string.find(members[i], ':', 1, true)
  if sep then used = used + tonumber(string.sub(members[i], sep + 1)) end
end
if used + tokens > tpm_limit then return {0, 'tpm', used} end

local conc = redis.call('ZCARD', KEYS[3])
if conc + 1 > conc_limit then return {0, 'concurrency', conc} end

redis.call('ZADD', KEYS[1], now_ms, entry_id)
redis.call('ZADD', KEYS[2], now_ms, entry_id .. ':' .. tokens)
redis.call('ZADD', KEYS[3], now_ms + lease_ttl_ms, entry_id)
redis.call('PEXPIRE', KEYS[1], window_ms)
redis.call('PEXPIRE', KEYS[2], window_ms)
redis.call('PEXPIRE', KEYS[3], lease_ttl_ms)
return {1, 'ok', 0}
"""

# Extend a still-live lease's expiry; no-op (returns 0) if it was already reclaimed.
_HEARTBEAT_LUA = """
local t = redis.call('TIME')
local now_ms = (tonumber(t[1]) * 1000) + math.floor(tonumber(t[2]) / 1000)
if redis.call('ZSCORE', KEYS[1], ARGV[2]) then
  redis.call('ZADD', KEYS[1], now_ms + tonumber(ARGV[1]), ARGV[2])
  redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]))
  return 1
end
return 0
"""


@dataclass(frozen=True)
class BackendLimits:
    rpm: int
    tpm: int
    concurrency: int


def limits_for(backend: Backend) -> BackendLimits:
    if backend == "cerebras":
        return BackendLimits(
            rpm=settings.LLM_CEREBRAS_RPM,
            tpm=settings.LLM_CEREBRAS_TPM,
            concurrency=settings.LLM_CEREBRAS_CONCURRENCY,
        )
    return BackendLimits(
        rpm=settings.LLM_NVIDIA_RPM,
        tpm=settings.LLM_NVIDIA_TPM,
        concurrency=settings.LLM_NVIDIA_CONCURRENCY,
    )


def effective_limit(limit: int, priority: Priority, headroom_percent: int) -> int:
    """Background priority is capped to leave headroom for interactive traffic."""
    if priority == "interactive":
        return limit
    return max(1, (limit * (100 - headroom_percent)) // 100)


class ConcurrencyLease:
    """A held concurrency slot. Heartbeat-extend for long calls; always release in ``finally``."""

    def __init__(
        self,
        client: aioredis.Redis,
        *,
        conc_key: str,
        entry_id: str,
        ttl_ms: int,
    ) -> None:
        self._client = client
        self._conc_key = conc_key
        self._entry_id = entry_id
        self._ttl_ms = ttl_ms
        self._released = False

    @property
    def entry_id(self) -> str:
        return self._entry_id

    async def heartbeat(self) -> bool:
        """Extend the lease TTL; returns False if the lease was already reclaimed."""
        result = await self._client.eval(
            _HEARTBEAT_LUA, 1, self._conc_key, str(self._ttl_ms), self._entry_id
        )
        return bool(int(result))

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._client.zrem(self._conc_key, self._entry_id)


class RedisRateLimiter:
    def __init__(
        self,
        client: aioredis.Redis | None = None,
        *,
        key_prefix: str = "llm:limiter",
        lease_ttl_ms: int | None = None,
        headroom_percent: int | None = None,
    ) -> None:
        self._client = client or aioredis.from_url(settings.REDIS_URL)
        self._prefix = key_prefix
        self._lease_ttl_ms = lease_ttl_ms or settings.LLM_LEASE_TTL_SECONDS * 1000
        self._headroom = (
            headroom_percent
            if headroom_percent is not None
            else settings.LLM_INTERACTIVE_HEADROOM_PERCENT
        )

    def _keys(self, backend: Backend) -> tuple[str, str, str]:
        return (
            f"{self._prefix}:rpm:{backend}",
            f"{self._prefix}:tpm:{backend}",
            f"{self._prefix}:conc:{backend}",
        )

    async def acquire(
        self,
        *,
        backend: Backend,
        estimated_tokens: int,
        priority: Priority,
    ) -> ConcurrencyLease:
        limits = limits_for(backend)
        rpm = effective_limit(limits.rpm, priority, self._headroom)
        tpm = effective_limit(limits.tpm, priority, self._headroom)
        concurrency = effective_limit(limits.concurrency, priority, self._headroom)
        rpm_key, tpm_key, conc_key = self._keys(backend)
        entry_id = str(uuid7())

        result = await self._client.eval(
            _ACQUIRE_LUA,
            3,
            rpm_key,
            tpm_key,
            conc_key,
            str(WINDOW_MS),
            str(rpm),
            str(tpm),
            str(concurrency),
            str(max(0, estimated_tokens)),
            entry_id,
            str(self._lease_ttl_ms),
        )
        granted = int(result[0])
        if not granted:
            dimension = result[1].decode() if isinstance(result[1], bytes) else result[1]
            raise RateLimited(
                f"{backend} limiter blocked on {dimension}",
                error_code=f"limiter_{dimension}",
            )
        return ConcurrencyLease(
            self._client,
            conc_key=conc_key,
            entry_id=entry_id,
            ttl_ms=self._lease_ttl_ms,
        )


_LIMITER: RedisRateLimiter | None = None


def get_rate_limiter() -> RedisRateLimiter:
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = RedisRateLimiter()
    return _LIMITER
