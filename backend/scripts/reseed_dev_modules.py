#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json

from app.domains.admin.dev_reseed import (
    assert_reseed_preconditions,
    assert_reseed_shape,
    reseed_dev_modules,
)
from app.platform.config import settings
from app.platform.db.session import DATABASE_URL, async_session
from app.platform.storage import get_storage_provider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace legacy dev modules with schedule-driven data.")
    parser.add_argument(
        "--confirm-dev-reseed",
        action="store_true",
        help="Required destructive confirmation for local dev reseed.",
    )
    parser.add_argument(
        "--allow-remote-db",
        action="store_true",
        help="Allow a non-local database host. Use only for a dedicated throwaway dev DB.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if async_session is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    async with async_session() as db:
        await assert_reseed_preconditions(
            db,
            confirmed=args.confirm_dev_reseed,
            database_url=DATABASE_URL,
            environment=settings.ENVIRONMENT,
            allow_remote_db=args.allow_remote_db,
        )
        storage_provider = await get_storage_provider()
        summary = await reseed_dev_modules(db, storage_provider=storage_provider)
        shape = await assert_reseed_shape(db, summary=summary)

    print(json.dumps({"summary": summary.to_jsonable(), "shape": shape}, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
