"""Stage 4.8b (MF4) — assert all three RQ worker groups are registered (the first-ready-boot floor).

`/health/ready` proves only the API; this proves the workers actually booted + joined the RQ worker
registry. Exits non-zero if ingestion / embedding / ai lacks a live worker. Run locally with REDIS_URL
reachable, or on a machine:  fly ssh console -a <backend-app> -C 'python scripts/check_workers.py'
(A functional pipeline round-trip stays 4.8d; "booted + registered" is the floor.)
"""

from __future__ import annotations

import os
import sys

from redis import Redis
from rq import Worker

REQUIRED_QUEUES = {"ingestion", "embedding", "ai"}


def main() -> int:
    connection = Redis.from_url(os.environ["REDIS_URL"])
    listened: set[str] = set()
    for worker in Worker.all(connection=connection):
        listened.update(worker.queue_names())
    print(f"registered worker queues: {sorted(listened)}")
    missing = REQUIRED_QUEUES - listened
    if missing:
        print(f"MISSING worker queues (no registered worker): {sorted(missing)}", file=sys.stderr)
        return 1
    print("OK — all three worker groups registered (ingestion / embedding / ai)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
