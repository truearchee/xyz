from __future__ import annotations

import asyncio
import logging

from app.platform.db.session import async_session, engine
from app.platform.scheduler.service import run_scheduler_forever


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if async_session is None or engine is None:
        raise SystemExit("DATABASE_URL environment variable is required")
    asyncio.run(run_scheduler_forever(session_factory=async_session, engine=engine))


if __name__ == "__main__":
    main()
