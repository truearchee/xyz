import asyncio
import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from uuid6 import uuid7

from app.platform.db.models import AppUser


BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "app_users",
    "course_modules",
    "course_memberships",
    "module_sections",
    "section_assets",
    "transcripts",
}
EXPECTED_ID_DEFAULTS = {table: None for table in EXPECTED_TABLES}
EXPECTED_CHECKS = {
    "ck_app_users_role",
    "ck_course_memberships_role",
    "ck_course_memberships_status",
    "ck_module_sections_type",
    "ck_module_sections_publish_status",
    "ck_module_sections_status",
    "ck_module_sections_order_index",
    "ck_module_sections_week_number",
    "ck_section_assets_processing_status",
    "ck_section_assets_file_size",
    "ck_transcripts_active_not_superseded",
    "ck_transcripts_checksum_lower_hex",
    "ck_transcripts_file_size",
    "ck_transcripts_manual_upload_has_uploader",
    "ck_transcripts_source_type",
    "ck_transcripts_status",
}
EXPECTED_INDEXES = {
    "ix_course_memberships_active_user_module",
    "ix_module_sections_module_week",
    "ix_module_sections_module_session_date",
    "ix_module_sections_due_at",
    "ix_module_sections_module_publish_status",
    "ix_section_assets_section",
    "ix_section_assets_uploader",
    "ix_transcripts_module_section_id",
    "uq_active_transcript_per_section",
    "uq_transcripts_storage_key",
}


def _test_database_url() -> str:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for destructive DB spine tests")
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


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    test_database_url = _test_database_url()
    asyncio.run(_ensure_test_database_exists(test_database_url))
    env = os.environ.copy()
    env["DATABASE_URL"] = test_database_url
    return subprocess.run(
        ["alembic", *args],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


async def _fetch_all(query: str) -> set[str]:
    engine = create_async_engine(_test_database_url())
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(query))
            return {row[0] for row in result}
    finally:
        await engine.dispose()


async def _fetch_id_defaults() -> dict[str, str | None]:
    engine = create_async_engine(_test_database_url())
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT table_name, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND column_name = 'id'
                      AND table_name = ANY(:table_names)
                    """
                ),
                {"table_names": list(EXPECTED_TABLES)},
            )
            return dict(result.all())
    finally:
        await engine.dispose()


async def _assert_app_user_constraint_and_uuid7_default() -> None:
    engine = create_async_engine(_test_database_url())
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            user = AppUser(
                auth_provider_id="auth-valid-constraint-test",
                email="valid-constraint-test@example.com",
                full_name="Valid Constraint Test",
                role="student",
            )
            session.add(user)
            await session.flush()
            assert user.id.version == 7

            with pytest.raises(IntegrityError) as exc_info:
                await session.execute(
                    text(
                        """
                        INSERT INTO app_users (
                            id,
                            auth_provider_id,
                            email,
                            full_name,
                            role
                        )
                        VALUES (
                            :id,
                            'auth-invalid-role-test',
                            'invalid-role-test@example.com',
                            'Invalid Role Test',
                            'superuser'
                        )
                        """
                    ),
                    {"id": uuid7()},
                )
                await session.flush()
            assert "ck_app_users_role" in str(exc_info.value)
            await session.rollback()
    finally:
        await engine.dispose()


def test_migration_round_trip() -> None:
    _assert_success(_run_alembic("upgrade", "head"))
    _assert_success(_run_alembic("downgrade", "base"))
    _assert_success(_run_alembic("upgrade", "head"))


def test_expected_tables_exist_after_upgrade_head() -> None:
    _assert_success(_run_alembic("upgrade", "head"))

    tables = asyncio.run(
        _fetch_all(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
    )
    checks = asyncio.run(
        _fetch_all(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND constraint_type = 'CHECK'
            """
        )
    )
    indexes = asyncio.run(
        _fetch_all(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            """
        )
    )
    id_defaults = asyncio.run(_fetch_id_defaults())

    assert EXPECTED_TABLES <= tables
    assert EXPECTED_CHECKS <= checks
    assert EXPECTED_INDEXES <= indexes
    assert id_defaults == EXPECTED_ID_DEFAULTS


def test_app_user_role_check_constraint_is_enforced() -> None:
    _assert_success(_run_alembic("upgrade", "head"))
    asyncio.run(_assert_app_user_constraint_and_uuid7_default())
