import asyncio
import inspect
import os
import subprocess
from pathlib import Path

import asyncpg
from pgvector.sqlalchemy import Vector
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from uuid6 import uuid7

import app.platform.db.models.transcript_chunk as transcript_chunk_model
from app.platform.db.models import AppUser, TranscriptChunk


BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "app_users",
    "course_modules",
    "course_memberships",
    "module_sections",
    "section_assets",
    "transcripts",
    "transcript_segments",
    "transcript_chunks",
    "ingestion_jobs",
    "maintenance_runs",
    "student_activity_events",
    "quiz_definitions",
    "quiz_attempts",
    "quiz_questions",
    "answer_options",
    "student_answers",
    "mistake_records",
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
    "ck_section_assets_asset_kind",
    "ck_section_assets_file_size",
    "ck_transcripts_lifecycle_state",
    "ck_transcripts_supersession_reason",
    "ck_transcripts_superseded_has_ts",
    "ck_transcripts_active_no_ts",
    "ck_transcripts_checksum_lower_hex",
    "ck_transcripts_file_size",
    "ck_transcripts_manual_upload_has_uploader",
    "ck_transcripts_source_type",
    "ck_transcripts_status",
    "ck_transcript_segments_sequence_number",
    "ck_transcript_segments_timestamp_pair",
    "ck_transcript_segments_start_ms",
    "ck_transcript_segments_end_ms",
    "ck_transcript_segments_text_not_blank",
    "ck_ingestion_jobs_job_type",
    "ck_ingestion_jobs_status",
    "ck_ingestion_jobs_attempts",
    "ck_transcript_chunks_token_count",
    "ck_transcript_chunks_text_not_blank",
    "ck_transcript_chunks_chunk_index",
    "ck_transcript_chunks_sequence_range",
    "ck_transcript_chunks_embedding_provenance",
    "ck_student_activity_events_event_type",
    "ck_quiz_definitions_quiz_mode",
    "ck_quiz_attempts_status",
    "ck_quiz_attempts_failure_category",
    "ck_quiz_questions_question_type",
    "ck_quiz_questions_source_type",
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
    "ix_transcripts_status_created_at",
    "ix_ingestion_jobs_transcript_job_type",
    "uq_active_transcript_per_section",
    "uq_pending_transcript_per_section",
    "uq_ingestion_jobs_idempotency_key",
    "uq_transcript_segments_transcript_sequence",
    "uq_transcript_chunks_transcript_chunk_index",
    "uq_transcripts_storage_key",
    "ingestion_jobs_one_active_embed_per_transcript",
    "uq_student_activity_events_type_source",
    "ix_student_activity_events_student_type",
    "uq_quiz_definitions_post_class_section",
    "uq_quiz_attempts_one_active",
    "uq_quiz_attempts_student_def_number",
    "ix_quiz_attempts_student_definition",
    "ix_quiz_questions_attempt_order",
    "ix_answer_options_question_order",
    "uq_student_answers_attempt_question",
    "uq_mistake_records_attempt_question",
    "ix_mistake_records_student_module",
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


async def _fetch_columns(table_name: str) -> dict[str, str]:
    engine = create_async_engine(_test_database_url())
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT column_name, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    """
                ),
                {"table_name": table_name},
            )
            return dict(result.all())
    finally:
        await engine.dispose()


async def _fetch_column_nullability(table_name: str) -> dict[str, str]:
    engine = create_async_engine(_test_database_url())
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT column_name, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    """
                ),
                {"table_name": table_name},
            )
            return dict(result.all())
    finally:
        await engine.dispose()


async def _fetch_one(query: str, params: dict | None = None):
    engine = create_async_engine(_test_database_url())
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(query), params or {})
            return result.one()
    finally:
        await engine.dispose()


async def _seed_assistant_0040_delete_reopen_shape() -> dict[str, object]:
    """Seed the exact 8.4 lifecycle shape that 0039 cannot represent.

    0040 allows a soft-deleted lecture_default tombstone plus a fresh active row for the same
    (student, section). Downgrade must reconcile that before restoring the old 0039 unique index.
    """
    student_id = uuid7()
    lecturer_id = uuid7()
    module_id = uuid7()
    section_id = uuid7()
    deleted_conversation_id = uuid7()
    active_conversation_id = uuid7()
    deleted_message_id = uuid7()

    engine = create_async_engine(_test_database_url())
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO app_users (id, auth_provider_id, email, full_name, role)
                    VALUES
                      (:student_id, :student_auth, :student_email, 'Stage 8.4 Student', 'student'),
                      (:lecturer_id, :lecturer_auth, :lecturer_email, 'Stage 8.4 Lecturer', 'lecturer')
                    """
                ),
                {
                    "student_id": student_id,
                    "student_auth": f"auth-{student_id}",
                    "student_email": f"stage84-{student_id}@example.test",
                    "lecturer_id": lecturer_id,
                    "lecturer_auth": f"auth-{lecturer_id}",
                    "lecturer_email": f"stage84-{lecturer_id}@example.test",
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO course_modules (id, title, owner_id, timezone, is_active)
                    VALUES (:module_id, 'Stage 8.4 Downgrade Module', :lecturer_id, 'UTC', true)
                    """
                ),
                {"module_id": module_id, "lecturer_id": lecturer_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO module_sections (
                        id, course_module_id, title, type, order_index, publish_status, status
                    )
                    VALUES (
                        :section_id, :module_id, 'Stage 8.4 Downgrade Lecture',
                        'lecture', 0, 'published', 'active'
                    )
                    """
                ),
                {"section_id": section_id, "module_id": module_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO assistant_conversations (
                        id, student_id, conversation_kind, attached_section_id, title,
                        title_source, deleted_at, last_activity_at
                    )
                    VALUES
                      (
                        :deleted_conversation_id, :student_id, 'lecture_default', :section_id,
                        'Deleted tombstone', 'auto', now() - interval '5 minutes', now() - interval '10 minutes'
                      ),
                      (
                        :active_conversation_id, :student_id, 'lecture_default', :section_id,
                        'Fresh active', 'auto', NULL, now()
                      )
                    """
                ),
                {
                    "deleted_conversation_id": deleted_conversation_id,
                    "active_conversation_id": active_conversation_id,
                    "student_id": student_id,
                    "section_id": section_id,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO assistant_messages (
                        id, conversation_id, role, status, content, retryable, client_idempotency_key
                    )
                    VALUES (
                        :deleted_message_id, :deleted_conversation_id, 'user', 'completed',
                        'message on the tombstone', false, 'deleted-key'
                    )
                    """
                ),
                {
                    "deleted_message_id": deleted_message_id,
                    "deleted_conversation_id": deleted_conversation_id,
                },
            )
    finally:
        await engine.dispose()

    return {
        "student_id": student_id,
        "section_id": section_id,
        "deleted_conversation_id": deleted_conversation_id,
        "active_conversation_id": active_conversation_id,
        "deleted_message_id": deleted_message_id,
    }


async def _insert_transcript_fixture(connection) -> dict[str, object]:
    app_user_id = uuid7()
    module_id = uuid7()
    section_id = uuid7()
    transcript_id = uuid7()
    segment_id = uuid7()

    await connection.execute(
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
                :app_user_id,
                :auth_provider_id,
                :email,
                'Schema Test User',
                'lecturer'
            )
            """
        ),
        {
            "app_user_id": app_user_id,
            "auth_provider_id": f"schema-auth-{app_user_id}",
            "email": f"schema-{app_user_id}@example.com",
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO course_modules (id, title, owner_id)
            VALUES (:module_id, 'Schema Test Module', :app_user_id)
            """
        ),
        {"module_id": module_id, "app_user_id": app_user_id},
    )
    await connection.execute(
        text(
            """
            INSERT INTO module_sections (
                id,
                course_module_id,
                title,
                type,
                order_index
            )
            VALUES (
                :section_id,
                :module_id,
                'Schema Test Section',
                'lecture',
                0
            )
            """
        ),
        {"section_id": section_id, "module_id": module_id},
    )
    await connection.execute(
        text(
            """
            INSERT INTO transcripts (
                id,
                module_section_id,
                original_file_name,
                storage_key,
                mime_type,
                file_size,
                checksum,
                uploaded_by_user_id
            )
            VALUES (
                :transcript_id,
                :section_id,
                'schema.vtt',
                :storage_key,
                'text/vtt',
                10,
                repeat('0', 64),
                :app_user_id
            )
            """
        ),
        {
            "transcript_id": transcript_id,
            "section_id": section_id,
            "storage_key": f"modules/schema/transcripts/{transcript_id}/schema.vtt",
            "app_user_id": app_user_id,
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO transcript_segments (
                id,
                transcript_id,
                sequence_number,
                start_ms,
                end_ms,
                text
            )
            VALUES (
                :segment_id,
                :transcript_id,
                0,
                0,
                1000,
                'schema segment'
            )
            """
        ),
        {"segment_id": segment_id, "transcript_id": transcript_id},
    )
    return {
        "segment_id": segment_id,
        "transcript_id": transcript_id,
    }


async def _insert_section_asset_before_asset_kind():
    engine = create_async_engine(_test_database_url())
    asset_id = uuid7()
    app_user_id = uuid7()
    module_id = uuid7()
    section_id = uuid7()
    try:
        async with engine.begin() as connection:
            await connection.execute(
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
                        :app_user_id,
                        :auth_provider_id,
                        :email,
                        'Asset Kind Backfill User',
                        'lecturer'
                    )
                    """
                ),
                {
                    "app_user_id": app_user_id,
                    "auth_provider_id": f"asset-kind-auth-{app_user_id}",
                    "email": f"asset-kind-{app_user_id}@example.com",
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO course_modules (id, title, owner_id)
                    VALUES (:module_id, 'Asset Kind Backfill Module', :app_user_id)
                    """
                ),
                {"module_id": module_id, "app_user_id": app_user_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO module_sections (
                        id,
                        course_module_id,
                        title,
                        type,
                        order_index
                    )
                    VALUES (
                        :section_id,
                        :module_id,
                        'Asset Kind Backfill Section',
                        'lecture',
                        0
                    )
                    """
                ),
                {"section_id": section_id, "module_id": module_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO section_assets (
                        id,
                        module_section_id,
                        storage_key,
                        file_name,
                        mime_type,
                        file_size,
                        checksum_sha256,
                        processing_status,
                        uploaded_by_user_id
                    )
                    VALUES (
                        :asset_id,
                        :section_id,
                        :storage_key,
                        'legacy.pdf',
                        'application/pdf',
                        10,
                        repeat('0', 64),
                        'completed',
                        :app_user_id
                    )
                    """
                ),
                {
                    "asset_id": asset_id,
                    "section_id": section_id,
                    "storage_key": f"modules/schema/assets/{asset_id}.pdf",
                    "app_user_id": app_user_id,
                },
            )
    finally:
        await engine.dispose()
    return asset_id


async def _assert_vector_round_trip_and_provenance_constraint() -> None:
    engine = create_async_engine(_test_database_url())
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        ids = await _insert_transcript_fixture(connection)
        vector = "[" + ",".join(["0.0"] * 383 + ["1.0"]) + "]"

        with pytest.raises(IntegrityError) as exc_info:
            await connection.execute(
                text(
                    """
                    INSERT INTO transcript_chunks (
                        id,
                        transcript_id,
                        chunk_index,
                        start_segment_id,
                        end_segment_id,
                        start_sequence_number,
                        end_sequence_number,
                        text,
                        token_count,
                        token_count_method,
                        normalization_version,
                        chunking_version,
                        embedding
                    )
                    VALUES (
                        :chunk_id,
                        :transcript_id,
                        0,
                        :segment_id,
                        :segment_id,
                        0,
                        0,
                        'schema chunk',
                        2,
                        'words',
                        'norm-v1-structural',
                        'chunk-v1-no-overlap-180w',
                        CAST(:embedding AS vector)
                    )
                    """
                ),
                {
                    "chunk_id": uuid7(),
                    "transcript_id": ids["transcript_id"],
                    "segment_id": ids["segment_id"],
                    "embedding": vector,
                },
            )
        assert "ck_transcript_chunks_embedding_provenance" in str(exc_info.value)

        await transaction.rollback()
        transaction = await connection.begin()
        ids = await _insert_transcript_fixture(connection)

        await connection.execute(
            text(
                """
                INSERT INTO transcript_chunks (
                    id,
                    transcript_id,
                    chunk_index,
                    start_segment_id,
                    end_segment_id,
                    start_sequence_number,
                    end_sequence_number,
                    text,
                    token_count,
                    token_count_method,
                    normalization_version,
                    chunking_version,
                    embedding,
                    embedding_model,
                    embedding_model_revision,
                    embedding_dimension,
                    embedding_normalization,
                    embedding_version,
                    embedding_input_hash
                )
                VALUES (
                    :chunk_id,
                    :transcript_id,
                    0,
                    :segment_id,
                    :segment_id,
                    0,
                    0,
                    'schema chunk',
                    2,
                    'words',
                    'norm-v1-structural',
                    'chunk-v1-no-overlap-180w',
                    CAST(:embedding AS vector),
                    'sentence-transformers/all-MiniLM-L6-v2',
                    '1110a243fdf4706b3f48f1d95db1a4f5529b4d41',
                    384,
                    'l2',
                    'embedding-v1',
                    repeat('a', 64)
                )
                """
            ),
            {
                    "chunk_id": uuid7(),
                    "transcript_id": ids["transcript_id"],
                    "segment_id": ids["segment_id"],
                    "embedding": vector,
            },
        )
        dims = (
            await connection.execute(
                text(
                    """
                    SELECT vector_dims(embedding)
                    FROM transcript_chunks
                    WHERE transcript_id = :transcript_id
                    """
                ),
                {"transcript_id": ids["transcript_id"]},
            )
        ).scalar_one()
        assert dims == 384
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


async def _insert_legacy_embedding_chunk_before_preflight() -> None:
    engine = create_async_engine(_test_database_url())
    try:
        async with engine.begin() as connection:
            ids = await _insert_transcript_fixture(connection)
            vector = "[" + ",".join(["0.0"] * 383 + ["1.0"]) + "]"
            await connection.execute(
                text(
                    """
                    INSERT INTO transcript_chunks (
                        id,
                        transcript_id,
                        chunk_index,
                        start_segment_id,
                        end_segment_id,
                        start_sequence_number,
                        end_sequence_number,
                        text,
                        token_count,
                        token_count_method,
                        normalization_version,
                        chunking_version,
                        embedding
                    )
                    VALUES (
                        :chunk_id,
                        :transcript_id,
                        0,
                        :segment_id,
                        :segment_id,
                        0,
                        0,
                        'legacy embedding chunk',
                        3,
                        'words',
                        'norm-v1-structural',
                        'chunk-v1-no-overlap-180w',
                        CAST(:embedding AS vector)
                    )
                    """
                ),
                {
                    "chunk_id": uuid7(),
                    "transcript_id": ids["transcript_id"],
                    "segment_id": ids["segment_id"],
                    "embedding": vector,
                },
            )
    finally:
        await engine.dispose()


async def _assert_active_embed_partial_unique_index() -> None:
    engine = create_async_engine(_test_database_url())
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        ids = await _insert_transcript_fixture(connection)
        await connection.execute(
            text(
                """
                INSERT INTO ingestion_jobs (
                    id,
                    transcript_id,
                    job_type,
                    status,
                    idempotency_key
                )
                VALUES (
                    :id,
                    :transcript_id,
                    :job_type,
                    :status,
                    :idempotency_key
                )
                """
            ),
            {
                "id": uuid7(),
                "transcript_id": ids["transcript_id"],
                "job_type": "embed",
                "status": "queued",
                "idempotency_key": f"{ids['transcript_id']}:embed:queued",
            },
        )
        for job_type in ("parse", "chunk"):
            await connection.execute(
                text(
                    """
                    INSERT INTO ingestion_jobs (
                        id,
                        transcript_id,
                        job_type,
                        status,
                        idempotency_key
                    )
                    VALUES (
                        :id,
                        :transcript_id,
                        :job_type,
                        'queued',
                        :idempotency_key
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "transcript_id": ids["transcript_id"],
                    "job_type": job_type,
                    "idempotency_key": f"{ids['transcript_id']}:{job_type}:queued",
                },
            )

        with pytest.raises(IntegrityError) as exc_info:
            await connection.execute(
                text(
                    """
                    INSERT INTO ingestion_jobs (
                        id,
                        transcript_id,
                        job_type,
                        status,
                        idempotency_key
                    )
                    VALUES (
                        :id,
                        :transcript_id,
                        'embed',
                        'running',
                        :idempotency_key
                    )
                    """
                ),
                {
                    "id": uuid7(),
                    "transcript_id": ids["transcript_id"],
                    "idempotency_key": f"{ids['transcript_id']}:embed:running",
                },
            )
        assert "ingestion_jobs_one_active_embed_per_transcript" in str(exc_info.value)
    finally:
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
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


def test_assistant_0040_downgrade_reconciles_delete_reopen_tombstone() -> None:
    try:
        _assert_success(_run_alembic("downgrade", "base"))
        _assert_success(_run_alembic("upgrade", "head"))
        ids = asyncio.run(_seed_assistant_0040_delete_reopen_shape())

        # This used to fail while recreating the 0039 unique index because both rows shared the same
        # (student_id, attached_section_id, lecture_default) identity. The downgrade must remove the
        # soft-deleted tombstone before restoring the old predicate.
        _assert_success(_run_alembic("downgrade", "0039"))

        remaining = asyncio.run(
            _fetch_one(
                """
                SELECT
                  count(*)::int AS conversation_count,
                  string_agg(id::text, ',') AS remaining_conversation_id
                FROM assistant_conversations
                WHERE student_id = :student_id
                  AND attached_section_id = :section_id
                  AND conversation_kind = 'lecture_default'
                """,
                {"student_id": ids["student_id"], "section_id": ids["section_id"]},
            )
        )
        assert remaining.conversation_count == 1
        assert remaining.remaining_conversation_id == str(ids["active_conversation_id"])

        tombstone_messages = asyncio.run(
            _fetch_one(
                """
                SELECT count(*)::int AS message_count
                FROM assistant_messages
                WHERE conversation_id = :deleted_conversation_id
                """,
                {"deleted_conversation_id": ids["deleted_conversation_id"]},
            )
        )
        assert tombstone_messages.message_count == 0

        _assert_success(_run_alembic("upgrade", "head"))
    finally:
        _assert_success(_run_alembic("downgrade", "base"))
        _assert_success(_run_alembic("upgrade", "head"))


def test_section_asset_kind_migration_backfills_existing_rows() -> None:
    try:
        _assert_success(_run_alembic("downgrade", "base"))
        _assert_success(_run_alembic("upgrade", "0020"))
        asset_id = asyncio.run(_insert_section_asset_before_asset_kind())

        _assert_success(_run_alembic("upgrade", "head"))

        asset_kind = asyncio.run(
            _fetch_one(
                """
                SELECT asset_kind
                FROM section_assets
                WHERE id = :asset_id
                """,
                {"asset_id": asset_id},
            )
        )
        assert asset_kind.asset_kind == "processable"
    finally:
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
    chunk_columns = asyncio.run(_fetch_columns("transcript_chunks"))
    job_columns = asyncio.run(_fetch_columns("ingestion_jobs"))
    asset_columns = asyncio.run(_fetch_columns("section_assets"))
    asset_nullability = asyncio.run(_fetch_column_nullability("section_assets"))

    assert EXPECTED_TABLES <= tables
    assert EXPECTED_CHECKS <= checks
    assert EXPECTED_INDEXES <= indexes
    assert id_defaults == EXPECTED_ID_DEFAULTS
    assert chunk_columns["embedding"] == "vector"
    assert chunk_columns["updated_at"] == "timestamptz"
    assert job_columns["result_metadata"] == "jsonb"
    assert asset_columns["asset_kind"] == "text"
    assert asset_nullability["asset_kind"] == "NO"
    assert "ix_transcript_chunks_transcript_id" not in indexes


def test_app_user_role_check_constraint_is_enforced() -> None:
    _assert_success(_run_alembic("upgrade", "head"))
    asyncio.run(_assert_app_user_constraint_and_uuid7_default())


def test_embedding_schema_preflight_contract() -> None:
    _assert_success(_run_alembic("upgrade", "head"))

    extension = asyncio.run(
        _fetch_one(
            """
            SELECT extname, extversion
            FROM pg_extension
            WHERE extname = 'vector'
            """
        )
    )
    embedding_column = asyncio.run(
        _fetch_one(
            """
            SELECT atttypid::regtype::text AS type_name, atttypmod
            FROM pg_attribute
            WHERE attrelid = 'transcript_chunks'::regclass
              AND attname = 'embedding'
              AND NOT attisdropped
            """
        )
    )
    chunk_columns = asyncio.run(_fetch_columns("transcript_chunks"))
    chunk_nullability = asyncio.run(_fetch_column_nullability("transcript_chunks"))

    assert extension.extname == "vector"
    assert embedding_column.type_name == "vector"
    assert embedding_column.atttypmod == 384
    assert chunk_columns["embedding"] == "vector"
    assert chunk_columns["embedding_model"] == "text"
    assert chunk_columns["embedding_model_revision"] == "text"
    assert chunk_columns["embedding_dimension"] == "int4"
    assert chunk_columns["embedding_normalization"] == "text"
    assert chunk_columns["embedding_version"] == "text"
    assert chunk_columns["embedding_input_hash"] == "text"
    assert chunk_columns["chunking_version"] == "text"
    assert chunk_nullability["chunking_version"] == "NO"


def test_non_null_legacy_embedding_blocks_schema_preflight() -> None:
    try:
        _assert_success(_run_alembic("downgrade", "base"))
        _assert_success(_run_alembic("upgrade", "0006"))
        asyncio.run(_insert_legacy_embedding_chunk_before_preflight())

        result = _run_alembic("upgrade", "head")

        assert result.returncode != 0
        assert (
            "Refusing 4.4 provenance migration with pre-existing non-null embeddings"
            in result.stdout + result.stderr
        )
    finally:
        _assert_success(_run_alembic("downgrade", "base"))
        _assert_success(_run_alembic("upgrade", "head"))


def test_embedding_vector_round_trip_and_provenance_constraint() -> None:
    _assert_success(_run_alembic("upgrade", "head"))
    asyncio.run(_assert_vector_round_trip_and_provenance_constraint())


def test_active_embed_job_partial_unique_index_is_scoped() -> None:
    _assert_success(_run_alembic("upgrade", "head"))
    asyncio.run(_assert_active_embed_partial_unique_index())


def test_transcript_chunk_orm_uses_pgvector_type() -> None:
    source = inspect.getsource(transcript_chunk_model)

    assert "UserDefinedType" not in source
    assert isinstance(TranscriptChunk.__table__.c.embedding.type, Vector)
    assert TranscriptChunk.__table__.c.embedding.type.dim == 384
