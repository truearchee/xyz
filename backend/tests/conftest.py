import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.platform.auth import jwt as auth_jwt
from app.platform.db.session import get_db_session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_JWKS_URL = "https://test.supabase.co/auth/v1/.well-known/jwks.json"
TEST_JWT_AUDIENCE = "authenticated"
TEST_JWT_ISSUER = "https://test.supabase.co/auth/v1"
TRUNCATE_TABLES = """
TRUNCATE TABLE
    section_assets,
    module_sections,
    course_memberships,
    course_modules,
    app_users
RESTART IDENTITY CASCADE
"""


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def _test_database_url() -> str:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for DB-touching auth tests")
    return test_database_url


def _asyncpg_dsn(database_url: str, database: str | None = None) -> str:
    url = make_url(database_url)
    if database is not None:
        url = url.set(database=database)
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _ensure_test_database_exists(database_url: str) -> None:
    url = make_url(database_url)
    database_name = url.database
    if not database_name:
        raise AssertionError("TEST_DATABASE_URL must include a database name")

    connection = await asyncpg.connect(_asyncpg_dsn(database_url, database="postgres"))
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            database_name,
        )
        if not exists:
            await connection.execute(f"CREATE DATABASE {_quote_identifier(database_name)}")
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def migrated_test_database() -> str:
    test_database_url = _test_database_url()
    asyncio.run(_ensure_test_database_exists(test_database_url))
    from tests.test_db_spine import _assert_success, _run_alembic

    _assert_success(_run_alembic("upgrade", "head"))
    return test_database_url


@pytest.fixture
async def db_session(migrated_test_database: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_test_database)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(TRUNCATE_TABLES))

        async with session_factory() as session:
            yield session
            await session.rollback()

        async with engine.begin() as connection:
            await connection.execute(text(TRUNCATE_TABLES))
    finally:
        await engine.dispose()


@pytest.fixture
async def auth_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def jwks_private_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def wrong_jwks_private_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", TEST_JWT_AUDIENCE)
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", TEST_JWT_ISSUER)


@pytest.fixture
def mock_jwks_client(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings: None,
    jwks_private_key,
) -> None:
    public_key = jwks_private_key.public_key()

    class MockJwksClient:
        def get_signing_key_from_jwt(self, token: str):
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(auth_jwt, "get_jwks_client", lambda: MockJwksClient())


@pytest.fixture
def jwt_factory(
    auth_settings: None,
    jwks_private_key,
) -> Callable[..., str]:
    def make_token(
        *,
        sub: str | None = None,
        role: str = "authenticated",
        audience: str = TEST_JWT_AUDIENCE,
        issuer: str = TEST_JWT_ISSUER,
        expires_delta: timedelta = timedelta(hours=1),
        private_key=None,
    ) -> str:
        now = datetime.now(UTC)
        signing_key = private_key if private_key is not None else jwks_private_key
        return jwt.encode(
            {
                "sub": sub or str(uuid4()),
                "aud": audience,
                "iss": issuer,
                "iat": now,
                "exp": now + expires_delta,
                "role": role,
            },
            signing_key,
            algorithm="ES256",
            headers={"kid": "test-key"},
        )

    return make_token
