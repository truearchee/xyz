from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import UploadFile
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import transcripts as transcript_router
from app.domains.transcripts import service as transcript_service
from app.domains.transcripts.validators import (
    InvalidTranscriptError,
    TranscriptUploadTooLargeError,
    sanitize_storage_filename,
    spool_and_validate_transcript,
)
from app.platform.db.models import (
    AIRequestLog,
    AppUser,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    IngestionJob,
    ModuleSection,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)
from app.platform.storage import get_storage_provider
from app.platform.storage.base import (
    StorageUnavailableError,
)
from app.main import app
from tests.test_content import FakeStorageProvider


VTT_BYTES = b"\xef\xbb\xbf\n WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n"
TXT_BYTES = "Transcript line\n".encode()


async def _create_user(
    session: AsyncSession,
    *,
    email: str,
    role: str = "student",
    auth_provider_id: str | None = None,
) -> AppUser:
    user = AppUser(
        auth_provider_id=auth_provider_id or f"provider-{uuid4()}",
        email=email,
        full_name="Test User",
        role=role,
        timezone="UTC",
    )
    session.add(user)
    await session.flush()
    return user


async def _create_module(
    session: AsyncSession,
    *,
    owner_id: UUID,
    title: str = "Module",
) -> CourseModule:
    module = CourseModule(
        title=title,
        owner_id=owner_id,
        timezone="UTC",
        is_active=True,
    )
    session.add(module)
    await session.flush()
    return module


async def _create_membership(
    session: AsyncSession,
    *,
    user_id: UUID,
    module_id: UUID,
    role: str,
) -> CourseMembership:
    membership = CourseMembership(
        user_id=user_id,
        module_id=module_id,
        role=role,
        status="active",
    )
    session.add(membership)
    await session.flush()
    return membership


async def _create_section(
    session: AsyncSession,
    *,
    module_id: UUID,
    title: str = "Lecture 1",
    section_type: str = "lecture",
    order_index: int = 0,
    publish_status: str = "draft",
) -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title=title,
        type=section_type,
        order_index=order_index,
        publish_status=publish_status,
        status="active",
    )
    session.add(section)
    await session.flush()
    return section


async def _create_transcript(
    session: AsyncSession,
    *,
    section_id: UUID,
    uploaded_by_user_id: UUID,
    lifecycle_state: str = "active",
    status: str = "uploaded",
    storage_key: str | None = None,
) -> Transcript:
    transcript = Transcript(
        module_section_id=section_id,
        source_type="manual_upload",
        original_file_name="existing.vtt",
        storage_key=storage_key or f"modules/test/transcripts/{uuid4()}/existing.vtt",
        mime_type="text/vtt",
        file_size=len(VTT_BYTES),
        checksum=hashlib.sha256(VTT_BYTES).hexdigest(),
        status=status,
        uploaded_by_user_id=uploaded_by_user_id,
        lifecycle_state=lifecycle_state,
        superseded_at=(
            datetime.now(UTC) if lifecycle_state == "superseded" else None
        ),
    )
    session.add(transcript)
    await session.flush()
    return transcript


async def _create_ingestion_job(
    session: AsyncSession,
    *,
    transcript_id: UUID,
    job_type: str,
    status: str,
    error_message: str | None = None,
    result_metadata: dict | None = None,
) -> IngestionJob:
    job = IngestionJob(
        transcript_id=transcript_id,
        job_type=job_type,
        status=status,
        idempotency_key=f"{transcript_id}:{job_type}:{uuid4()}",
        processor_version=f"{job_type}:test",
        result_metadata=result_metadata,
        error_message=error_message,
        attempts=1,
    )
    session.add(job)
    await session.flush()
    return job


async def _create_transcript_segment(
    session: AsyncSession,
    *,
    transcript_id: UUID,
    sequence_number: int = 0,
    text: str = "Hello world",
) -> TranscriptSegment:
    segment = TranscriptSegment(
        transcript_id=transcript_id,
        sequence_number=sequence_number,
        start_ms=sequence_number * 1000,
        end_ms=(sequence_number + 1) * 1000,
        text=text,
    )
    session.add(segment)
    await session.flush()
    return segment


async def _create_transcript_chunk(
    session: AsyncSession,
    *,
    transcript_id: UUID,
    segment_id: UUID,
    chunk_index: int = 0,
    text: str = "Hello world",
) -> TranscriptChunk:
    chunk = TranscriptChunk(
        transcript_id=transcript_id,
        chunk_index=chunk_index,
        start_segment_id=segment_id,
        end_segment_id=segment_id,
        start_sequence_number=chunk_index,
        end_sequence_number=chunk_index,
        start_time=chunk_index * 1000,
        end_time=(chunk_index + 1) * 1000,
        text=text,
        token_count=len(text.split()),
        token_count_method="words",
        normalization_version="norm-v1-structural",
        chunking_version="chunk-v1-no-overlap-180w",
    )
    session.add(chunk)
    await session.flush()
    return chunk


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    token = jwt_factory(sub=user.auth_provider_id)
    return {"Authorization": f"Bearer {token}"}


def _transcript_file(
    name: str = "lecture.vtt",
    data: bytes = VTT_BYTES,
    content_type: str = "application/octet-stream",
):
    return {"file": (name, data, content_type)}


@pytest.fixture
def fake_storage() -> FakeStorageProvider:
    provider = FakeStorageProvider()
    app.dependency_overrides[get_storage_provider] = lambda: provider
    return provider


@pytest.fixture(autouse=True)
def fake_enqueue(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    enqueued: list[UUID] = []
    monkeypatch.setattr(
        transcript_service,
        "enqueue_parse_transcript",
        lambda transcript_id: enqueued.append(transcript_id),
    )
    return enqueued


@pytest.mark.anyio
async def test_transcript_validator_accepts_vtt_txt_and_hashes_raw_bytes() -> None:
    vtt_upload = UploadFile(filename="../../lecture.vtt", file=BytesIO(VTT_BYTES))
    txt_upload = UploadFile(filename="notes.txt", file=BytesIO(TXT_BYTES))

    vtt = await spool_and_validate_transcript(vtt_upload, max_bytes=1024)
    txt = await spool_and_validate_transcript(txt_upload, max_bytes=1024)

    assert vtt.original_file_name == "../../lecture.vtt"
    assert vtt.safe_file_name == "lecture.vtt"
    assert vtt.effective_mime_type == "text/vtt"
    assert vtt.size_bytes == len(VTT_BYTES)
    assert vtt.sha256 == hashlib.sha256(VTT_BYTES).hexdigest()
    vtt.content.seek(0)
    assert vtt.content.read() == VTT_BYTES
    vtt.content.close()

    assert txt.original_file_name == "notes.txt"
    assert txt.safe_file_name == "notes.txt"
    assert txt.effective_mime_type == "text/plain"
    txt.content.close()


@pytest.mark.anyio
async def test_transcript_validator_rejects_invalid_content_and_oversize() -> None:
    invalid_cases = [
        UploadFile(filename="bad.vtt", file=BytesIO(b"NOTE\nnot vtt")),
        UploadFile(filename="empty.txt", file=BytesIO(b"   ")),
        UploadFile(filename="bad.txt", file=BytesIO(b"\xff\xfe")),
        UploadFile(filename="slides.pdf", file=BytesIO(VTT_BYTES)),
        UploadFile(filename="captions.srt", file=BytesIO(VTT_BYTES)),
        UploadFile(filename="zero.txt", file=BytesIO(b"")),
    ]
    for upload in invalid_cases:
        with pytest.raises(InvalidTranscriptError):
            await spool_and_validate_transcript(upload, max_bytes=1024)

    with pytest.raises(TranscriptUploadTooLargeError):
        await spool_and_validate_transcript(
            UploadFile(filename="large.vtt", file=BytesIO(VTT_BYTES)),
            max_bytes=4,
        )


def test_transcript_filename_sanitizer_preserves_extension_and_fallback() -> None:
    long_name = f"{'a' * 250}.vtt"

    assert sanitize_storage_filename("../../lecture.vtt", extension="vtt") == "lecture.vtt"
    assert sanitize_storage_filename("lecture\n3.vtt", extension="vtt") == "lecture3.vtt"
    assert sanitize_storage_filename("\n.vtt", extension="vtt") == "transcript.vtt"
    assert sanitize_storage_filename(long_name, extension="vtt").endswith(".vtt")
    assert len(sanitize_storage_filename(long_name, extension="vtt")) == 200


@pytest.mark.anyio
async def test_assigned_lecturer_uploads_vtt_and_txt_to_lecture_and_lab(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    fake_enqueue: list[UUID],
) -> None:
    lecturer = await _create_user(db_session, email="transcript-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    lecture = await _create_section(db_session, module_id=module.id, section_type="lecture")
    lab = await _create_section(
        db_session,
        module_id=module.id,
        section_type="lab",
        order_index=1,
    )
    headers = _headers(lecturer, jwt_factory)

    lecture_response = await auth_client.post(
        f"/modules/{module.id}/sections/{lecture.id}/transcript",
        files=_transcript_file("lecture.vtt", VTT_BYTES, "text/plain"),
        headers=headers,
    )
    lab_response = await auth_client.post(
        f"/modules/{module.id}/sections/{lab.id}/transcript",
        files=_transcript_file("lab.txt", TXT_BYTES, "application/octet-stream"),
        headers=headers,
    )
    rows = (
        await db_session.execute(select(Transcript).order_by(Transcript.created_at.asc()))
    ).scalars().all()

    assert lecture_response.status_code == 201
    assert lecture_response.json()["status"] == "queued"
    assert lecture_response.json()["mimeType"] == "text/vtt"
    assert lecture_response.json()["originalFileName"] == "lecture.vtt"
    assert lecture_response.json()["lifecycleState"] == "active"
    assert not {"storageKey", "checksum", "isActive", "supersededAt"} & set(
        lecture_response.json()
    )
    assert lab_response.status_code == 201
    assert lab_response.json()["status"] == "queued"
    assert lab_response.json()["mimeType"] == "text/plain"
    assert len(rows) == 2
    assert fake_enqueue == [rows[0].id, rows[1].id]
    assert rows[0].checksum == hashlib.sha256(VTT_BYTES).hexdigest()
    assert rows[0].storage_key in fake_storage.objects
    assert fake_storage.objects[rows[0].storage_key] == VTT_BYTES
    assert rows[1].storage_key in fake_storage.objects
    assert fake_storage.objects[rows[1].storage_key] == TXT_BYTES


@pytest.mark.anyio
async def test_transcript_upload_rejects_unsupported_sections_and_roles_before_parse(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lecturer = await _create_user(db_session, email="transcript-auth-lecturer@example.com", role="lecturer")
    unassigned = await _create_user(db_session, email="transcript-unassigned@example.com", role="lecturer")
    student = await _create_user(db_session, email="transcript-student@example.com")
    admin = await _create_user(db_session, email="transcript-admin@example.com", role="admin")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    assignment = await _create_section(
        db_session,
        module_id=module.id,
        section_type="assignment",
    )
    supplementary = await _create_section(
        db_session,
        module_id=module.id,
        section_type="supplementary",
        order_index=1,
    )
    lecture = await _create_section(
        db_session,
        module_id=module.id,
        section_type="lecture",
        order_index=2,
    )

    async def fail_if_called(_request):
        raise AssertionError("multipart form was parsed before authorization")

    monkeypatch.setattr(transcript_router, "_extract_transcript_multipart_file", fail_if_called)

    role_cases = [
        (student, 403),
        (admin, 403),
        (unassigned, 404),
    ]
    for user, expected_status in role_cases:
        response = await auth_client.post(
            f"/modules/{module.id}/sections/{lecture.id}/transcript",
            files=_transcript_file(data=VTT_BYTES * 1000),
            headers=_headers(user, jwt_factory),
        )
        assert response.status_code == expected_status

    for section in [assignment, supplementary]:
        response = await auth_client.post(
            f"/modules/{module.id}/sections/{section.id}/transcript",
            files=_transcript_file(),
            headers=_headers(lecturer, jwt_factory),
        )
        assert response.status_code == 422

    rows = (await db_session.execute(select(Transcript))).scalars().all()
    assert rows == []
    assert fake_storage.put_calls == []


@pytest.mark.anyio
async def test_transcript_upload_multipart_shape_and_size_errors(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lecturer = await _create_user(db_session, email="multipart-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    headers = _headers(lecturer, jwt_factory)
    url = f"/modules/{module.id}/sections/{section.id}/transcript"

    no_file = await auth_client.post(url, data={"note": "ignored"}, headers=headers)
    multiple_files = await auth_client.post(
        url,
        files=[
            ("file", ("one.vtt", VTT_BYTES, "text/vtt")),
            ("file", ("two.vtt", VTT_BYTES, "text/vtt")),
        ],
        headers=headers,
    )
    unexpected_file = await auth_client.post(
        url,
        files={"other": ("one.vtt", VTT_BYTES, "text/vtt")},
        headers=headers,
    )

    monkeypatch.setenv("MAX_TRANSCRIPT_UPLOAD_BYTES", "4")
    oversize = await auth_client.post(
        url,
        files=_transcript_file(),
        headers=headers,
    )

    assert no_file.status_code == 422
    assert multiple_files.status_code == 422
    assert unexpected_file.status_code == 422
    assert oversize.status_code == 413
    assert fake_storage.put_calls == []


@pytest.mark.anyio
async def test_second_upload_creates_pending_replacement(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    # Stage 4.6a (ADR-46-A): a second upload to a section with an active transcript no longer 409s —
    # it becomes a `pending` replacement processing alongside the still-active old one.
    lecturer = await _create_user(db_session, email="duplicate-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    existing = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
    )
    module_id = module.id
    section_id = section.id
    existing_id = existing.id
    await db_session.commit()

    response = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript",
        files=_transcript_file(),
        headers=_headers(lecturer, jwt_factory),
    )

    assert response.status_code == 201
    assert fake_storage.put_calls  # the replacement object IS stored
    new_id = UUID(response.json()["id"])
    assert new_id != existing_id

    db_session.expire_all()
    rows = (
        await db_session.execute(
            select(Transcript).where(Transcript.module_section_id == section_id)
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    assert by_id[existing_id].lifecycle_state == "active"
    assert by_id[new_id].lifecycle_state == "pending"
    assert by_id[new_id].replacement_of_transcript_id == existing_id


async def _raise_active_conflict(_db, **_kwargs):
    # Simulate a lost section-lock race: the one-active partial-unique index rejects the insert.
    raise IntegrityError(
        'INSERT INTO transcripts ... "uq_active_transcript_per_section"',
        {},
        Exception("duplicate key value violates unique constraint"),
    )


@pytest.mark.anyio
async def test_integrity_conflict_cleans_loser_object_and_keeps_one_active_row(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The section lock normally serializes uploads, but the integrity-conflict cleanup path remains a
    # defensive backstop: on a unique-index violation the just-stored object must be deleted and 409
    # returned, leaving the prior active row untouched.
    lecturer = await _create_user(db_session, email="race-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    existing = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
    )
    module_id = module.id
    section_id = section.id
    existing_id = existing.id
    await db_session.commit()

    monkeypatch.setattr(
        transcript_service, "_create_transcript_under_section_lock", _raise_active_conflict
    )

    response = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript",
        files=_transcript_file(),
        headers=_headers(lecturer, jwt_factory),
    )
    rows = (
        await db_session.execute(
            select(Transcript).where(
                Transcript.module_section_id == section_id,
                Transcript.lifecycle_state == "active",
            )
        )
    ).scalars().all()

    assert response.status_code == 409
    assert fake_storage.put_calls
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]
    assert fake_storage.objects == {}
    assert [row.id for row in rows] == [existing_id]


@pytest.mark.anyio
async def test_integrity_conflict_cleanup_failure_logs_and_keeps_one_active_row(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    lecturer = await _create_user(db_session, email="race-cleanup-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    existing = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
    )
    module_id = module.id
    section_id = section.id
    existing_id = existing.id
    await db_session.commit()

    monkeypatch.setattr(
        transcript_service, "_create_transcript_under_section_lock", _raise_active_conflict
    )
    fake_storage.fail_delete = True
    caplog.set_level("WARNING", logger=transcript_service.__name__)

    response = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript",
        files=_transcript_file(),
        headers=_headers(lecturer, jwt_factory),
    )
    rows = (
        await db_session.execute(
            select(Transcript).where(
                Transcript.module_section_id == section_id,
                Transcript.lifecycle_state == "active",
            )
        )
    ).scalars().all()

    assert response.status_code == 409
    assert fake_storage.put_calls
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]
    assert fake_storage.objects == {fake_storage.put_calls[0]: VTT_BYTES}
    assert [row.id for row in rows] == [existing_id]
    assert "Failed to clean up transcript object after integrity failure" in caplog.text


@pytest.mark.anyio
async def test_storage_and_db_failures_do_not_leave_bad_rows_or_objects(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
    fake_enqueue: list[UUID],
) -> None:
    lecturer = await _create_user(db_session, email="failure-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    storage_fail_section = await _create_section(db_session, module_id=module.id)
    db_fail_section = await _create_section(
        db_session,
        module_id=module.id,
        order_index=1,
    )
    headers = _headers(lecturer, jwt_factory)

    fake_storage.fail_put = StorageUnavailableError("down")
    storage_response = await auth_client.post(
        f"/modules/{module.id}/sections/{storage_fail_section.id}/transcript",
        files=_transcript_file(),
        headers=headers,
    )
    fake_storage.fail_put = None

    async def fail_commit() -> None:
        raise SQLAlchemyError("forced commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    db_response = await auth_client.post(
        f"/modules/{module.id}/sections/{db_fail_section.id}/transcript",
        files=_transcript_file(),
        headers=headers,
    )
    rows = (await db_session.execute(select(Transcript))).scalars().all()

    assert storage_response.status_code == 503
    assert db_response.status_code == 500
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]
    assert fake_storage.objects == {}
    assert rows == []
    assert fake_enqueue == []


@pytest.mark.anyio
async def test_db_failure_cleanup_failure_logs_orphan_and_returns_500(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    lecturer = await _create_user(db_session, email="db-cleanup-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    headers = _headers(lecturer, jwt_factory)
    fake_storage.fail_delete = True
    caplog.set_level("WARNING", logger=transcript_service.__name__)

    async def fail_commit() -> None:
        raise SQLAlchemyError("forced commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/transcript",
        files=_transcript_file(),
        headers=headers,
    )
    rows = (await db_session.execute(select(Transcript))).scalars().all()

    assert response.status_code == 500
    assert fake_storage.put_calls
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]
    assert fake_storage.objects == {fake_storage.put_calls[0]: VTT_BYTES}
    assert rows == []
    assert "Failed to clean up transcript object after DB failure" in caplog.text


@pytest.mark.anyio
async def test_get_active_transcript_is_lecturer_only(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="get-lecturer@example.com", role="lecturer")
    student = await _create_user(db_session, email="get-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    section = await _create_section(db_session, module_id=module.id)
    empty_section = await _create_section(db_session, module_id=module.id, order_index=1)
    transcript = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
    )

    active_response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript",
        headers=_headers(lecturer, jwt_factory),
    )
    none_response = await auth_client.get(
        f"/modules/{module.id}/sections/{empty_section.id}/transcript",
        headers=_headers(lecturer, jwt_factory),
    )
    student_response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript",
        headers=_headers(student, jwt_factory),
    )

    assert active_response.status_code == 200
    assert active_response.json()["id"] == str(transcript.id)
    assert active_response.json()["lifecycleState"] == "active"
    assert not {"storageKey", "checksum", "isActive", "supersededAt"} & set(
        active_response.json()
    )
    assert none_response.status_code == 404
    assert student_response.status_code == 403


@pytest.mark.anyio
async def test_transcript_processing_status_projects_chunked_state(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="projection-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        status="completed",
    )
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="parse",
        status="completed",
    )
    segment = await _create_transcript_segment(db_session, transcript_id=transcript.id)
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="chunk",
        status="completed",
        result_metadata={"chunk_count": 1},
    )
    await _create_transcript_chunk(
        db_session,
        transcript_id=transcript.id,
        segment_id=segment.id,
    )

    response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript-processing-status",
        headers=_headers(lecturer, jwt_factory),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["activeTranscriptId"] == str(transcript.id)
    assert body["transcriptStatus"] == "completed"
    assert body["overallState"] == "chunked"
    assert body["currentPhase"] is None
    assert body["failedStep"] is None
    assert body["safeFailureMessage"] is None
    assert body["steps"]["upload"]["status"] == "completed"
    assert body["steps"]["parse"]["status"] == "completed"
    assert body["steps"]["chunk"]["status"] == "completed"
    assert body["steps"]["embed"]["status"] == "not_started"
    assert body["segmentCount"] == 1
    assert body["chunkCount"] == 1
    assert body["embeddedChunkCount"] == 0
    assert not {"storageKey", "checksum", "text", "chunks", "segments"} & set(body)


@pytest.mark.anyio
async def test_transcript_processing_status_projects_embedded_state(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="projection-embedded-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        status="completed",
    )
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="parse",
        status="completed",
    )
    segment = await _create_transcript_segment(db_session, transcript_id=transcript.id)
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="chunk",
        status="completed",
        result_metadata={"chunk_count": 1},
    )
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="embed",
        status="completed",
        result_metadata={"chunk_count": 1, "embedded_chunk_count": 1},
    )
    chunk = await _create_transcript_chunk(
        db_session,
        transcript_id=transcript.id,
        segment_id=segment.id,
    )
    chunk.embedding = [0.0] * 383 + [1.0]
    chunk.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
    chunk.embedding_model_revision = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    chunk.embedding_dimension = 384
    chunk.embedding_normalization = "l2"
    chunk.embedding_version = "embedding-v1"
    chunk.embedding_input_hash = "a" * 64
    await db_session.flush()

    response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript-processing-status",
        headers=_headers(lecturer, jwt_factory),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["overallState"] == "embedded"
    assert body["currentPhase"] is None
    assert body["failedStep"] is None
    assert body["safeFailureMessage"] is None
    assert body["steps"]["embed"]["status"] == "completed"
    assert body["chunkCount"] == 1
    assert body["embeddedChunkCount"] == 1
    assert not {"storageKey", "checksum", "text", "chunks", "segments", "embedding"} & set(body)


@pytest.mark.anyio
async def test_transcript_processing_status_uses_existing_authz_convention(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="projection-auth-lecturer@example.com",
        role="lecturer",
    )
    unassigned = await _create_user(
        db_session,
        email="projection-auth-unassigned@example.com",
        role="lecturer",
    )
    student = await _create_user(db_session, email="projection-auth-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    section = await _create_section(db_session, module_id=module.id)
    empty_section = await _create_section(db_session, module_id=module.id, order_index=1)
    await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
    )
    projection_url = (
        f"/modules/{module.id}/sections/{section.id}/transcript-processing-status"
    )

    student_response = await auth_client.get(
        projection_url,
        headers=_headers(student, jwt_factory),
    )
    unassigned_response = await auth_client.get(
        projection_url,
        headers=_headers(unassigned, jwt_factory),
    )
    none_response = await auth_client.get(
        f"/modules/{module.id}/sections/{empty_section.id}/transcript-processing-status",
        headers=_headers(lecturer, jwt_factory),
    )

    assert student_response.status_code == 403
    assert student_response.json()["detail"] == "TRANSCRIPT_FORBIDDEN"
    assert unassigned_response.status_code == 404
    assert unassigned_response.json()["detail"] == "SECTION_NOT_FOUND"
    assert none_response.status_code == 404
    assert none_response.json()["detail"] == "TRANSCRIPT_NOT_FOUND"


@pytest.mark.anyio
async def test_transcript_processing_status_projects_safe_failure(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="projection-failure-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        status="failed",
    )
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="parse",
        status="failed",
        error_message="Transcript parse failed.",
    )

    response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript-processing-status",
        headers=_headers(lecturer, jwt_factory),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["overallState"] == "failed"
    assert body["failedStep"] == "parse"
    assert body["safeFailureMessage"] == "Transcript parsing failed."
    assert body["steps"]["parse"]["status"] == "failed"


@pytest.mark.anyio
async def test_transcript_processing_status_projects_safe_embed_failure(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="projection-embed-failure-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        status="failed",
    )
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="parse",
        status="completed",
    )
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="chunk",
        status="completed",
    )
    await _create_ingestion_job(
        db_session,
        transcript_id=transcript.id,
        job_type="embed",
        status="failed",
        error_message="raw stack trace with /opt/models and chunk text",
    )

    response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript-processing-status",
        headers=_headers(lecturer, jwt_factory),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["overallState"] == "failed"
    assert body["failedStep"] == "embed"
    assert body["safeFailureMessage"] == "Transcript embedding failed."
    assert body["steps"]["embed"]["status"] == "failed"
    assert "raw stack trace" not in str(body)
    assert "/opt/models" not in str(body)


@pytest.mark.anyio
async def test_partial_unique_index_rejects_second_active_transcript(
    db_session: AsyncSession,
) -> None:
    lecturer = await _create_user(db_session, email="db-index-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    section = await _create_section(db_session, module_id=module.id)
    await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        storage_key="modules/test/first.vtt",
    )

    with pytest.raises(IntegrityError) as exc_info:
        await _create_transcript(
            db_session,
            section_id=section.id,
            uploaded_by_user_id=lecturer.id,
            storage_key="modules/test/second.vtt",
        )
        await db_session.flush()

    assert "uq_active_transcript_per_section" in str(exc_info.value)


# --- Stage 4.5d: lecturer summary read endpoint -------------------------------------------------

_BRIEF_CONTENT = {"text": "A concise paragraph summarizing the lecture for a student."}
_DETAILED_CONTENT = {
    "overview": "An overview of the session.",
    "keyConcepts": ["First concept", "Second concept"],
    "importantDefinitions": [{"term": "Term", "definition": "Its definition."}],
    "mainExplanations": ["A full-sentence explanation."],
    "examples": ["A worked example."],
    "examRelevantPoints": ["A point likely to be assessed."],
    "labNotes": ["A procedure note."],
}


async def _create_generated_summary(
    session: AsyncSession,
    *,
    transcript: Transcript,
    section_id: UUID,
    summary_type: str,
    backend_used: str,
    content_json: dict,
) -> GeneratedLectureSummary:
    feature = "summary_brief" if summary_type == "brief" else "summary_detailed"
    job = await _create_ingestion_job(
        session,
        transcript_id=transcript.id,
        job_type=("generate_brief_summary" if summary_type == "brief" else "generate_detailed_summary"),
        status="completed",
    )
    log = AIRequestLog(
        ingestion_job_id=job.id,
        feature=feature,
        model_id="MBZUAI-IFM/K2-Think-v2",
        prompt_version="v1",
        prompt_content_hash="h" * 64,
        rendered_prompt_hash="r" * 64,
        input_content_hash="i" * 64,
        backend_used=backend_used,
        backend_route_source="requested",
        status="succeeded",
    )
    session.add(log)
    await session.flush()
    summary = GeneratedLectureSummary(
        transcript_id=transcript.id,
        module_section_id=section_id,
        summary_type=summary_type,
        content_json=content_json,
        content_schema_version=("brief-v1" if summary_type == "brief" else "detailed-v1"),
        model_id="MBZUAI-IFM/K2-Think-v2",
        prompt_version="v1",
        prompt_content_hash="h" * 64,
        backend_used=backend_used,
        source_transcript_checksum=transcript.checksum,
        input_hash="i" * 64,
        ai_request_log_id=log.id,
    )
    session.add(summary)
    await session.flush()
    return summary


@pytest.mark.anyio
async def test_transcript_summaries_returns_brief_and_detailed_for_assigned_lecturer(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="sum-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session, section_id=section.id, uploaded_by_user_id=lecturer.id, status="completed"
    )
    await _create_generated_summary(
        db_session, transcript=transcript, section_id=section.id,
        summary_type="brief", backend_used="cerebras", content_json=_BRIEF_CONTENT,
    )
    await _create_generated_summary(
        db_session, transcript=transcript, section_id=section.id,
        summary_type="detailed_study", backend_used="nvidia", content_json=_DETAILED_CONTENT,
    )

    response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript-summaries",
        headers=_headers(lecturer, jwt_factory),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["brief"]["text"] == _BRIEF_CONTENT["text"]
    assert body["detailed"]["overview"] == _DETAILED_CONTENT["overview"]
    assert body["detailed"]["keyConcepts"] == _DETAILED_CONTENT["keyConcepts"]
    assert body["detailed"]["importantDefinitions"][0]["term"] == "Term"
    assert body["detailed"]["labNotes"] == ["A procedure note."]
    # The combined shape carries the projection status (the doneness authority).
    assert body["status"]["activeTranscriptId"] == str(transcript.id)
    assert body["status"]["steps"]["summaryBrief"]["status"] == "completed"
    assert body["status"]["steps"]["summaryDetailed"]["status"] == "completed"
    # No raw provenance / storage internals leak in the read surface.
    assert "storageKey" not in body and "inputHash" not in body


@pytest.mark.anyio
async def test_transcript_summaries_are_null_before_generation(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="sum-pending@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session, section_id=section.id, uploaded_by_user_id=lecturer.id, status="completed"
    )

    response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/transcript-summaries",
        headers=_headers(lecturer, jwt_factory),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["brief"] is None
    assert body["detailed"] is None
    assert body["status"]["activeTranscriptId"] == str(transcript.id)


@pytest.mark.anyio
async def test_transcript_summaries_authz_matrix(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="sum-assigned@example.com", role="lecturer")
    unassigned = await _create_user(db_session, email="sum-unassigned@example.com", role="lecturer")
    student = await _create_user(db_session, email="sum-student@example.com", role="student")
    admin = await _create_user(db_session, email="sum-admin@example.com", role="admin")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    # unassigned lecturer + admin have NO membership in this module
    section = await _create_section(db_session, module_id=module.id)
    await _create_transcript(
        db_session, section_id=section.id, uploaded_by_user_id=lecturer.id, status="completed"
    )

    url = f"/modules/{module.id}/sections/{section.id}/transcript-summaries"
    cases = [
        (lecturer, 200, None),
        (unassigned, 404, "SECTION_NOT_FOUND"),   # cross-tenant → existence-leak prevention
        (student, 403, "TRANSCRIPT_FORBIDDEN"),    # role-forbidden, session kept
        (admin, 403, "TRANSCRIPT_FORBIDDEN"),
    ]
    for user, expected_status, expected_detail in cases:
        response = await auth_client.get(url, headers=_headers(user, jwt_factory))
        assert response.status_code == expected_status, (user.email, response.text)
        if expected_detail is not None:
            assert response.json()["detail"] == expected_detail
