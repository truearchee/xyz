from __future__ import annotations

from fastapi import HTTPException
import pytest
from redis.exceptions import ConnectionError

from app.platform.rate_limit import enforce_fixed_window_rate_limit

pytestmark = pytest.mark.anyio


class FakeRedis:
    def __init__(self) -> None:
        self.count = 0
        self.expirations: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        self.count += 1
        return self.count

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations.append((key, seconds))


async def test_fixed_window_rate_limit_blocks_after_limit():
    client = FakeRedis()

    await enforce_fixed_window_rate_limit(key="manual:admin-1", limit=1, window_seconds=60, client=client)
    with pytest.raises(HTTPException) as excinfo:
        await enforce_fixed_window_rate_limit(key="manual:admin-1", limit=1, window_seconds=60, client=client)

    assert excinfo.value.status_code == 429
    assert client.expirations == [("manual:admin-1", 60)]


async def test_fixed_window_rate_limit_fails_open_on_redis_error():
    class BrokenRedis:
        async def incr(self, _key: str) -> int:
            raise ConnectionError("redis unavailable")

    await enforce_fixed_window_rate_limit(
        key="manual:admin-1",
        limit=1,
        window_seconds=60,
        client=BrokenRedis(),
    )
