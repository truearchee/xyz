from __future__ import annotations

import argparse
import asyncio
import json
import os

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domains.progress.seed import seed_progress_dataset


EXPECTED_ALEMBIC_VERSION = "0057"
_LOCAL_DATABASE_HOSTS = {"", "localhost", "127.0.0.1", "::1", "db", "postgres"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Stage 9 progress demo data.")
    parser.add_argument("--reset-stage9-demo", action="store_true", help="Replace existing Stage 9 demo data.")
    parser.add_argument("--allow-remote-db", action="store_true", help="Allow non-local DB host.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if not args.reset_stage9_demo:
        raise SystemExit("Refusing to seed without --reset-stage9-demo")
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    if environment in {"production", "staging"}:
        raise SystemExit("Refusing to seed Stage 9 demo data in production/staging")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    url = make_url(database_url)
    if not args.allow_remote_db and (url.host or "").lower() not in _LOCAL_DATABASE_HOSTS:
        raise SystemExit(f"Refusing non-local database host {(url.host or '').lower()!r}")

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            versions = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalars().all()
            if versions != [EXPECTED_ALEMBIC_VERSION]:
                raise SystemExit(f"Expected Alembic {EXPECTED_ALEMBIC_VERSION}, found {versions}")
            summary = await seed_progress_dataset(
                session,
                prefix="stage9-demo",
                reset=True,
                cohort_size=24,
                source="seed",
            )
            print(
                json.dumps(
                    {
                        "moduleOneId": str(summary.module_one_id),
                        "moduleTwoId": str(summary.module_two_id),
                        "studentEmailsByKey": summary.student_emails_by_key,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
