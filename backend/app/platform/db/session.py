import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_async_engine(DATABASE_URL) if DATABASE_URL else None
async_session = (
    async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    if engine is not None
    else None
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    if async_session is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    async with async_session() as session:
        yield session
