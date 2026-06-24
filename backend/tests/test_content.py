from __future__ import annotations

import hashlib
import inspect
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from httpx import AsyncClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.api.routers import content as content_router
from app.domains.content import service as content_service
from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    IngestionJob,
    ModuleSection,
    SectionAsset,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)
from app.platform.storage import get_storage_provider
from app.platform.storage.base import (
    StorageProviderError,
    StorageUnavailableError,
    StoredObject,
)
from app.platform.storage.keys import generate_section_asset_storage_key
from app.domains.content.validators import (
    InvalidPdfError,
    InvalidSectionAssetError,
    NOTEBOOK_MIME_TYPE,
    UploadTooLargeError,
    sanitize_filename,
    spool_and_validate_pdf,
    spool_and_validate_section_asset,
)
from app.main import app


PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
NOTEBOOK_BYTES = (
    b'{"cells":[],"metadata":{"language_info":{"name":"python"}},'
    b'"nbformat":4,"nbformat_minor":5}\n'
)


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.signed_url_calls: list[tuple[str, int]] = []
        self.fail_put: Exception | None = None
        self.fail_get: Exception | None = None
        self.fail_delete = False
        # Stage 4.6c: per-key created_at for storage reconciliation (grace-window) tests.
        self.object_created_at: dict[str, datetime] = {}

    async def put_object(
        self,
        *,
        key: str,
        content,
        content_type: str,
        content_length: int,
        metadata: dict[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredObject:
        if self.fail_put is not None:
            raise self.fail_put
        content.seek(0)
        data = content.read()
        if not overwrite and key in self.objects:
            raise StorageProviderError("duplicate key")
        self.objects[key] = data
        self.put_calls.append(key)
        return StoredObject(key=key, size=content_length, content_type=content_type)

    async def get_object(self, *, key: str) -> bytes:
        if self.fail_get is not None:
            raise self.fail_get
        return self.objects[key]

    async def delete_object(self, *, key: str) -> None:
        self.delete_calls.append(key)
        if self.fail_delete:
            raise StorageProviderError("delete failed")
        self.objects.pop(key, None)

    async def list_objects(self, *, prefix: str, max_objects: int):
        from app.platform.storage.base import ListedObject

        results: list[ListedObject] = []
        for key in sorted(self.objects):
            if not key.startswith(prefix):
                continue
            if len(results) >= max_objects:
                break
            results.append(
                ListedObject(
                    key=key,
                    created_at=self.object_created_at.get(key, datetime.now(UTC)),
                    size=len(self.objects[key]),
                )
            )
        return results

    async def create_signed_read_url(
        self,
        *,
        key: str,
        expires_in_seconds: int,
    ) -> str:
        self.signed_url_calls.append((key, expires_in_seconds))
        return f"https://storage.example/{key}?ttl={expires_in_seconds}"


async def _create_user(
    session: AsyncSession,
    *,
    email: str,
    role: str = "student",
    auth_provider_id: str | None = None,
    is_active: bool = True,
) -> AppUser:
    user = AppUser(
        auth_provider_id=auth_provider_id or f"provider-{uuid4()}",
        email=email,
        full_name="Test User",
        role=role,
        is_active=is_active,
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
    starts_on: date | None = None,
    ends_on: date | None = None,
    week_start_day: str | None = None,
    session_pattern: list[dict[str, str]] | None = None,
    quiz_day: str | None = None,
) -> CourseModule:
    module = CourseModule(
        title=title,
        owner_id=owner_id,
        timezone="UTC",
        starts_on=starts_on,
        ends_on=ends_on,
        week_start_day=week_start_day,
        session_pattern=session_pattern,
        quiz_day=quiz_day,
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
    week_number: int | None = None,
    session_date: date | None = None,
    due_at: datetime | None = None,
    publish_status: str = "draft",
    lecturer_notes: str | None = None,
    status: str = "active",
) -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title=title,
        type=section_type,
        order_index=order_index,
        week_number=week_number,
        session_date=session_date,
        due_at=due_at,
        publish_status=publish_status,
        lecturer_notes=lecturer_notes,
        status=status,
    )
    session.add(section)
    await session.flush()
    return section


async def _create_asset(
    session: AsyncSession,
    *,
    section_id: UUID,
    uploaded_by_user_id: UUID,
    file_name: str = "slides.pdf",
    processing_status: str = "completed",
    asset_kind: str = "processable",
    mime_type: str = "application/pdf",
    data: bytes = PDF_BYTES,
    storage_key: str | None = None,
) -> SectionAsset:
    asset = SectionAsset(
        module_section_id=section_id,
        storage_key=storage_key
        or f"modules/test/{uuid4()}{'.ipynb' if file_name.endswith('.ipynb') else '.pdf'}",
        file_name=file_name,
        mime_type=mime_type,
        file_size=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        asset_kind=asset_kind,
        processing_status=processing_status,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    session.add(asset)
    await session.flush()
    return asset


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    token = jwt_factory(sub=user.auth_provider_id)
    return {"Authorization": f"Bearer {token}"}


def _pdf_file(name: str = "slides.pdf", data: bytes = PDF_BYTES):
    return {"file": (name, data, "application/pdf")}


def _ipynb_file(
    name: str = "lab.ipynb",
    data: bytes = NOTEBOOK_BYTES,
    content_type: str = NOTEBOOK_MIME_TYPE,
):
    return {"file": (name, data, content_type)}


@pytest.fixture
def fake_storage() -> FakeStorageProvider:
    provider = FakeStorageProvider()
    app.dependency_overrides[get_storage_provider] = lambda: provider
    return provider


@pytest.mark.anyio
async def test_pdf_validator_accepts_valid_pdf_and_hashes_spooled_bytes() -> None:
    upload = UploadFile(filename="../slides.pdf", file=BytesIO(PDF_BYTES))

    validated = await spool_and_validate_pdf(upload, max_bytes=1024)

    assert validated.file_name == "slides.pdf"
    assert validated.mime_type == "application/pdf"
    assert validated.file_size == len(PDF_BYTES)
    assert validated.checksum_sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    validated.content.seek(0)
    assert validated.content.read() == PDF_BYTES
    validated.content.close()


@pytest.mark.anyio
async def test_pdf_validator_rejects_non_pdf_and_oversize() -> None:
    with pytest.raises(InvalidPdfError):
        await spool_and_validate_pdf(
            UploadFile(filename="fake.pdf", file=BytesIO(b"not a pdf")),
            max_bytes=1024,
        )

    with pytest.raises(UploadTooLargeError):
        await spool_and_validate_pdf(
            UploadFile(filename="large.pdf", file=BytesIO(PDF_BYTES)),
            max_bytes=4,
        )


@pytest.mark.anyio
async def test_section_asset_validator_classifies_pdf_and_notebook() -> None:
    pdf = await spool_and_validate_section_asset(
        UploadFile(
            filename="slides.pdf",
            file=BytesIO(PDF_BYTES),
            headers=Headers({"content-type": "application/pdf"}),
        ),
        max_bytes=1024,
    )
    notebook = await spool_and_validate_section_asset(
        UploadFile(
            filename="lab.ipynb",
            file=BytesIO(NOTEBOOK_BYTES),
            headers=Headers({"content-type": NOTEBOOK_MIME_TYPE}),
        ),
        max_bytes=1024,
    )

    assert pdf.asset_kind == "processable"
    assert pdf.storage_extension == ".pdf"
    assert notebook.asset_kind == "attachment"
    assert notebook.storage_extension == ".ipynb"
    assert notebook.mime_type == NOTEBOOK_MIME_TYPE
    pdf.content.close()
    notebook.content.close()

    with pytest.raises(InvalidSectionAssetError):
        await spool_and_validate_section_asset(
            UploadFile(
                filename="lab.ipynb",
                file=BytesIO(NOTEBOOK_BYTES),
                headers=Headers({"content-type": "text/plain"}),
            ),
            max_bytes=1024,
        )
    with pytest.raises(InvalidSectionAssetError):
        await spool_and_validate_section_asset(
            UploadFile(
                filename="lab.ipynb",
                file=BytesIO(b"not-json"),
                headers=Headers({"content-type": NOTEBOOK_MIME_TYPE}),
            ),
            max_bytes=1024,
        )


def test_filename_sanitizer_and_storage_key_shape() -> None:
    module_id = uuid4()
    section_id = uuid4()
    asset_id = uuid4()

    assert sanitize_filename("../../bad\x00name.pdf") == "badname.pdf"
    key = generate_section_asset_storage_key(
        module_id=module_id,
        section_id=section_id,
        asset_id=asset_id,
    )

    assert key.startswith(f"modules/{module_id}/sections/{section_id}/assets/{asset_id}/")
    assert key.endswith(".pdf")
    assert "badname" not in key


@pytest.mark.anyio
async def test_list_upload_and_replace_asset_happy_path(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(db_session, email="content-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    headers = _headers(lecturer, jwt_factory)

    empty_response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/assets",
        headers=headers,
    )
    upload_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/assets",
        files=_pdf_file("lecture-1.pdf"),
        headers=headers,
    )
    second_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/assets",
        files=_pdf_file("lecture-1-extra.pdf"),
        headers=headers,
    )

    assert empty_response.status_code == 200
    assert empty_response.json() == {"assets": []}
    assert upload_response.status_code == 201
    assert upload_response.json()["assetKind"] == "processable"
    assert second_response.status_code == 201
    assert len(fake_storage.objects) == 2
    assert "storageKey" not in upload_response.json()

    first_asset_id = upload_response.json()["id"]
    replace_response = await auth_client.put(
        f"/modules/{module.id}/sections/{section.id}/assets/{first_asset_id}",
        files=_pdf_file("replacement.pdf", b"%PDF-1.7\nreplacement\n"),
        headers=headers,
    )
    list_response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/assets",
        headers=headers,
    )

    assert replace_response.status_code == 200
    assert replace_response.json()["id"] == first_asset_id
    assert replace_response.json()["fileName"] == "replacement.pdf"
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]
    assert list_response.status_code == 200
    assert [asset["id"] for asset in list_response.json()["assets"]] == [
        first_asset_id,
        second_response.json()["id"],
    ]


@pytest.mark.anyio
async def test_lab_notebook_attachment_upload_sets_due_at_and_creates_no_pipeline_rows(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="lab-attachment-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    lab = await _create_section(
        db_session,
        module_id=module.id,
        title="Lab 1",
        section_type="lab",
    )
    due_at = datetime(2026, 5, 21, 18, 30, tzinfo=UTC)

    response = await auth_client.post(
        f"/modules/{module.id}/sections/{lab.id}/assets",
        data={"dueAt": due_at.isoformat().replace("+00:00", "Z")},
        files=_ipynb_file("exercise.ipynb"),
        headers=_headers(lecturer, jwt_factory),
    )
    await db_session.refresh(lab)
    asset = (
        await db_session.execute(
            select(SectionAsset).where(SectionAsset.module_section_id == lab.id)
        )
    ).scalar_one()

    transcript_count = await db_session.scalar(
        select(func.count()).select_from(Transcript).where(Transcript.module_section_id == lab.id)
    )
    ingestion_job_count = await db_session.scalar(
        select(func.count())
        .select_from(IngestionJob)
        .join(Transcript, IngestionJob.transcript_id == Transcript.id)
        .where(Transcript.module_section_id == lab.id)
    )
    segment_count = await db_session.scalar(
        select(func.count())
        .select_from(TranscriptSegment)
        .join(Transcript, TranscriptSegment.transcript_id == Transcript.id)
        .where(Transcript.module_section_id == lab.id)
    )
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(TranscriptChunk)
        .join(Transcript, TranscriptChunk.transcript_id == Transcript.id)
        .where(Transcript.module_section_id == lab.id)
    )
    summary_count = await db_session.scalar(
        select(func.count())
        .select_from(GeneratedLectureSummary)
        .join(Transcript, GeneratedLectureSummary.transcript_id == Transcript.id)
        .where(Transcript.module_section_id == lab.id)
    )

    assert response.status_code == 201
    assert response.json()["assetKind"] == "attachment"
    assert response.json()["processingStatus"] == "completed"
    assert response.json()["mimeType"] == NOTEBOOK_MIME_TYPE
    assert asset.asset_kind == "attachment"
    assert asset.processing_status == "completed"
    assert asset.storage_key.endswith(".ipynb")
    assert lab.due_at == due_at
    assert fake_storage.objects[asset.storage_key] == NOTEBOOK_BYTES
    assert {
        "transcripts": transcript_count,
        "ingestion_jobs": ingestion_job_count,
        "transcript_segments": segment_count,
        "transcript_chunks": chunk_count,
        "generated_lecture_summaries": summary_count,
    } == {
        "transcripts": 0,
        "ingestion_jobs": 0,
        "transcript_segments": 0,
        "transcript_chunks": 0,
        "generated_lecture_summaries": 0,
    }


@pytest.mark.anyio
async def test_attachment_upload_is_lab_only_and_validated_by_extension_and_content_type(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="attachment-validation-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    lecture = await _create_section(db_session, module_id=module.id)
    lab = await _create_section(
        db_session,
        module_id=module.id,
        title="Lab",
        section_type="lab",
        order_index=1,
    )
    headers = _headers(lecturer, jwt_factory)

    lecture_attachment_response = await auth_client.post(
        f"/modules/{module.id}/sections/{lecture.id}/assets",
        files=_ipynb_file("lecture.ipynb"),
        headers=headers,
    )
    wrong_mime_response = await auth_client.post(
        f"/modules/{module.id}/sections/{lab.id}/assets",
        files=_ipynb_file("lab.ipynb", content_type="text/plain"),
        headers=headers,
    )
    due_at_on_lecture_response = await auth_client.post(
        f"/modules/{module.id}/sections/{lecture.id}/assets",
        data={"dueAt": "2026-05-21T18:30:00Z"},
        files=_pdf_file("lecture.pdf"),
        headers=headers,
    )

    assert lecture_attachment_response.status_code == 422
    assert lecture_attachment_response.json()["detail"] == "SECTION_DUE_AT_LAB_ONLY"
    assert wrong_mime_response.status_code == 422
    assert due_at_on_lecture_response.status_code == 422
    assert due_at_on_lecture_response.json()["detail"] == "SECTION_DUE_AT_LAB_ONLY"
    assert fake_storage.objects == {}


@pytest.mark.anyio
async def test_upload_negative_authorization_and_validation_cases(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lecturer = await _create_user(db_session, email="auth-lecturer@example.com", role="lecturer")
    unassigned_lecturer = await _create_user(
        db_session,
        email="auth-unassigned@example.com",
        role="lecturer",
    )
    student = await _create_user(db_session, email="auth-student@example.com")
    admin = await _create_user(db_session, email="auth-admin@example.com", role="admin")
    module = await _create_module(db_session, owner_id=lecturer.id)
    other_module = await _create_module(db_session, owner_id=lecturer.id, title="Other")
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
    other_section = await _create_section(
        db_session,
        module_id=other_module.id,
        order_index=0,
    )

    cases = [
        (student, section.id, PDF_BYTES, 403),
        (admin, section.id, PDF_BYTES, 403),
        (unassigned_lecturer, section.id, PDF_BYTES, 403),
        (lecturer, other_section.id, PDF_BYTES, 404),
        (lecturer, section.id, b"not a pdf", 422),
    ]
    for user, section_id, payload, expected_status in cases:
        response = await auth_client.post(
            f"/modules/{module.id}/sections/{section_id}/assets",
            files=_pdf_file(data=payload),
            headers=_headers(user, jwt_factory),
        )
        assert response.status_code == expected_status

    monkeypatch.setenv("MAX_SECTION_ASSET_UPLOAD_BYTES", "4")
    oversize_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/assets",
        files=_pdf_file(data=PDF_BYTES),
        headers=_headers(lecturer, jwt_factory),
    )
    assert oversize_response.status_code == 413
    assert fake_storage.objects == {}


@pytest.mark.anyio
async def test_unauthorized_upload_rejects_before_multipart_form_parse(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lecturer = await _create_user(db_session, email="parse-lecturer@example.com", role="lecturer")
    student = await _create_user(db_session, email="parse-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    section = await _create_section(db_session, module_id=module.id)

    async def fail_if_called(_request):
        raise AssertionError("multipart form was parsed before authorization")

    monkeypatch.setattr(content_router, "_extract_multipart_asset_upload", fail_if_called)

    response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/assets",
        files=_pdf_file(),
        headers=_headers(student, jwt_factory),
    )

    assert response.status_code == 403
    assert fake_storage.put_calls == []


@pytest.mark.anyio
async def test_upload_db_failure_cleans_new_object_and_persists_no_row(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lecturer = await _create_user(db_session, email="upload-db-fail@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)

    async def fail_commit() -> None:
        raise SQLAlchemyError("forced commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/assets",
        files=_pdf_file(),
        headers=_headers(lecturer, jwt_factory),
    )
    rows = await db_session.execute(select(SectionAsset))

    assert response.status_code == 500
    assert fake_storage.put_calls
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]
    assert fake_storage.objects == {}
    assert rows.scalars().all() == []


@pytest.mark.anyio
async def test_unexpected_storage_error_returns_502_and_persists_no_row(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(db_session, email="storage-error@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    fake_storage.fail_put = StorageProviderError("broken")

    response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/assets",
        files=_pdf_file(),
        headers=_headers(lecturer, jwt_factory),
    )
    rows = await db_session.execute(select(SectionAsset))

    assert response.status_code == 502
    assert rows.scalars().all() == []


@pytest.mark.anyio
async def test_replace_asset_from_another_section_returns_404_and_cleans_new_object(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(db_session, email="replace-cross@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id, order_index=0)
    other_section = await _create_section(db_session, module_id=module.id, order_index=1)
    asset = SectionAsset(
        module_section_id=other_section.id,
        storage_key="modules/old.pdf",
        file_name="old.pdf",
        mime_type="application/pdf",
        file_size=len(PDF_BYTES),
        checksum_sha256="0" * 64,
        processing_status="completed",
        uploaded_by_user_id=lecturer.id,
    )
    db_session.add(asset)
    await db_session.flush()

    response = await auth_client.put(
        f"/modules/{module.id}/sections/{section.id}/assets/{asset.id}",
        files=_pdf_file(),
        headers=_headers(lecturer, jwt_factory),
    )

    assert response.status_code == 404
    assert fake_storage.put_calls
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]


@pytest.mark.anyio
async def test_replace_db_failure_keeps_old_row_and_cleans_new_object(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lecturer = await _create_user(db_session, email="replace-db-fail@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    asset = SectionAsset(
        module_section_id=section.id,
        storage_key="modules/old-replace-db-fail.pdf",
        file_name="old.pdf",
        mime_type="application/pdf",
        file_size=len(PDF_BYTES),
        checksum_sha256=hashlib.sha256(PDF_BYTES).hexdigest(),
        processing_status="completed",
        uploaded_by_user_id=lecturer.id,
    )
    db_session.add(asset)
    await db_session.flush()
    asset_id = asset.id
    old_storage_key = asset.storage_key
    await db_session.commit()
    fake_storage.objects[old_storage_key] = PDF_BYTES

    async def fail_commit() -> None:
        raise SQLAlchemyError("forced replace commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    response = await auth_client.put(
        f"/modules/{module.id}/sections/{section.id}/assets/{asset_id}",
        files=_pdf_file("new.pdf", b"%PDF-1.7\nnew\n"),
        headers=_headers(lecturer, jwt_factory),
    )
    result = await db_session.execute(select(SectionAsset).where(SectionAsset.id == asset_id))
    persisted_asset = result.scalar_one()

    assert response.status_code == 500
    assert fake_storage.put_calls
    assert fake_storage.delete_calls == [fake_storage.put_calls[0]]
    assert persisted_asset.storage_key == old_storage_key
    assert fake_storage.objects == {old_storage_key: PDF_BYTES}


@pytest.mark.anyio
async def test_storage_outage_returns_503_and_persists_no_row(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(db_session, email="outage@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    fake_storage.fail_put = StorageUnavailableError("down")

    response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/assets",
        files=_pdf_file(),
        headers=_headers(lecturer, jwt_factory),
    )
    result = await db_session.execute(select(SectionAsset))

    assert response.status_code == 503
    assert result.scalars().all() == []


@pytest.mark.anyio
async def test_replace_cleanup_failure_still_succeeds(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(db_session, email="cleanup@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    asset = SectionAsset(
        module_section_id=section.id,
        storage_key="modules/old-cleanup.pdf",
        file_name="old.pdf",
        mime_type="application/pdf",
        file_size=len(PDF_BYTES),
        checksum_sha256="0" * 64,
        processing_status="completed",
        uploaded_by_user_id=lecturer.id,
    )
    db_session.add(asset)
    await db_session.flush()
    fake_storage.objects[asset.storage_key] = PDF_BYTES
    fake_storage.fail_delete = True

    response = await auth_client.put(
        f"/modules/{module.id}/sections/{section.id}/assets/{asset.id}",
        files=_pdf_file("new.pdf"),
        headers=_headers(lecturer, jwt_factory),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(asset.id)
    assert response.json()["fileName"] == "new.pdf"
    assert fake_storage.delete_calls == ["modules/old-cleanup.pdf"]


def test_replace_asset_query_uses_row_lock_for_concurrent_replaces() -> None:
    source = inspect.getsource(content_service.replace_section_asset)

    assert ".with_for_update()" in source


def test_publish_transition_matrix_and_internal_draft_rejection() -> None:
    assert content_service.resolve_publish_status_transition("draft", "published") == "published"
    assert (
        content_service.resolve_publish_status_transition("published", "published")
        == "published"
    )
    assert (
        content_service.resolve_publish_status_transition("unpublished", "published")
        == "published"
    )
    assert (
        content_service.resolve_publish_status_transition("published", "unpublished")
        == "unpublished"
    )
    assert (
        content_service.resolve_publish_status_transition("unpublished", "unpublished")
        == "unpublished"
    )

    with pytest.raises(HTTPException) as draft_unpublish:
        content_service.resolve_publish_status_transition("draft", "unpublished")
    assert draft_unpublish.value.status_code == 422
    assert draft_unpublish.value.detail == "SECTION_TRANSITION_INVALID"

    with pytest.raises(HTTPException) as internal_draft:
        content_service.resolve_publish_status_transition("published", "draft")
    assert internal_draft.value.status_code == 422
    assert internal_draft.value.detail == "SECTION_TRANSITION_INVALID"


@pytest.mark.anyio
async def test_publish_unpublish_and_notes_round_trip(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="publish-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(db_session, module_id=module.id)
    headers = _headers(lecturer, jwt_factory)

    publish_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/publish",
        headers=headers,
    )
    unpublish_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/unpublish",
        headers=headers,
    )
    republish_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/publish",
        headers=headers,
    )
    notes_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{section.id}/notes",
        json={"lecturerNotes": " \r\nLine one\rLine two\n "},
        headers=headers,
    )
    whitespace_clear_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{section.id}/notes",
        json={"lecturerNotes": "   \n\t  "},
        headers=headers,
    )
    null_clear_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{section.id}/notes",
        json={"lecturerNotes": None},
        headers=headers,
    )
    persisted = await db_session.get(ModuleSection, section.id)

    assert publish_response.status_code == 200
    assert publish_response.json()["publishStatus"] == "published"
    assert publish_response.json()["courseModuleId"] == str(module.id)
    assert unpublish_response.status_code == 200
    assert unpublish_response.json()["publishStatus"] == "unpublished"
    assert republish_response.status_code == 200
    assert republish_response.json()["publishStatus"] == "published"
    assert notes_response.status_code == 200
    assert notes_response.json()["lecturerNotes"] == "Line one\nLine two"
    assert whitespace_clear_response.status_code == 200
    assert whitespace_clear_response.json()["lecturerNotes"] is None
    assert null_clear_response.status_code == 200
    assert null_clear_response.json()["lecturerNotes"] is None
    assert persisted is not None
    assert persisted.lecturer_notes is None


@pytest.mark.anyio
async def test_metadata_patch_whitelist_d13_due_at_and_admin_access(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="metadata-lecturer@example.com", role="lecturer")
    admin = await _create_user(db_session, email="metadata-admin@example.com", role="admin")
    module = await _create_module(
        db_session,
        owner_id=lecturer.id,
        starts_on=date(2026, 5, 11),
        ends_on=date(2026, 6, 26),
        week_start_day="monday",
        session_pattern=[
            {"weekday": "monday", "sectionType": "lecture"},
            {"weekday": "thursday", "sectionType": "lab"},
        ],
        quiz_day="friday",
    )
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    lecture = await _create_section(
        db_session,
        module_id=module.id,
        week_number=1,
        session_date=date(2026, 5, 11),
    )
    lab = await _create_section(
        db_session,
        module_id=module.id,
        title="Lab 1",
        section_type="lab",
        order_index=1,
        week_number=1,
        session_date=date(2026, 5, 14),
    )
    lecturer_headers = _headers(lecturer, jwt_factory)
    admin_headers = _headers(admin, jwt_factory)

    recompute_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{lecture.id}/metadata",
        json={"sessionDate": "2026-05-20"},
        headers=lecturer_headers,
    )
    explicit_override_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{lecture.id}/metadata",
        json={"sessionDate": "2026-05-25", "weekNumber": 9},
        headers=lecturer_headers,
    )
    week_only_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{lecture.id}/metadata",
        json={"weekNumber": 3},
        headers=admin_headers,
    )
    due_at = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    due_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{lab.id}/metadata",
        json={"dueAt": due_at.isoformat().replace("+00:00", "Z")},
        headers=lecturer_headers,
    )
    extra_field_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{lecture.id}/metadata",
        json={"title": "Not allowed"},
        headers=lecturer_headers,
    )
    lecture_due_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{lecture.id}/metadata",
        json={"dueAt": due_at.isoformat().replace("+00:00", "Z")},
        headers=lecturer_headers,
    )
    persisted_lecture = await db_session.get(ModuleSection, lecture.id)
    persisted_lab = await db_session.get(ModuleSection, lab.id)

    assert recompute_response.status_code == 200
    assert recompute_response.json()["sessionDate"] == "2026-05-20"
    assert recompute_response.json()["weekNumber"] == 2
    assert explicit_override_response.status_code == 200
    assert explicit_override_response.json()["sessionDate"] == "2026-05-25"
    assert explicit_override_response.json()["weekNumber"] == 9
    assert week_only_response.status_code == 200
    assert week_only_response.json()["sessionDate"] == "2026-05-25"
    assert week_only_response.json()["weekNumber"] == 3
    assert due_response.status_code == 200
    assert due_response.json()["dueAt"] is not None
    assert extra_field_response.status_code == 422
    assert lecture_due_response.status_code == 422
    assert lecture_due_response.json()["detail"] == "SECTION_DUE_AT_LAB_ONLY"
    assert persisted_lecture is not None
    assert persisted_lecture.session_date == date(2026, 5, 25)
    assert persisted_lecture.week_number == 3
    assert persisted_lab is not None
    assert persisted_lab.due_at == due_at


@pytest.mark.anyio
async def test_metadata_patch_authz_cross_module_and_type_boundaries(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="metadata-auth-lecturer@example.com", role="lecturer")
    other_lecturer = await _create_user(
        db_session,
        email="metadata-auth-other@example.com",
        role="lecturer",
    )
    student = await _create_user(db_session, email="metadata-auth-student@example.com")
    module = await _create_module(
        db_session,
        owner_id=lecturer.id,
        starts_on=date(2026, 5, 11),
        week_start_day="monday",
    )
    other_module = await _create_module(
        db_session,
        owner_id=other_lecturer.id,
        title="Other metadata module",
        starts_on=date(2026, 5, 11),
        week_start_day="monday",
    )
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(
        db_session,
        user_id=other_lecturer.id,
        module_id=other_module.id,
        role="lecturer",
    )
    section = await _create_section(
        db_session,
        module_id=module.id,
        week_number=1,
        session_date=date(2026, 5, 11),
    )
    other_section = await _create_section(
        db_session,
        module_id=other_module.id,
        week_number=1,
        session_date=date(2026, 5, 11),
    )
    assignment = await _create_section(
        db_session,
        module_id=module.id,
        title="Assignment",
        section_type="assignment",
        order_index=1,
    )

    student_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{section.id}/metadata",
        json={"weekNumber": 2},
        headers=_headers(student, jwt_factory),
    )
    unassigned_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{section.id}/metadata",
        json={"weekNumber": 2},
        headers=_headers(other_lecturer, jwt_factory),
    )
    cross_module_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{other_section.id}/metadata",
        json={"weekNumber": 2},
        headers=_headers(lecturer, jwt_factory),
    )
    assignment_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{assignment.id}/metadata",
        json={"weekNumber": 2},
        headers=_headers(lecturer, jwt_factory),
    )

    assert student_response.status_code == 403
    assert student_response.json()["detail"] == "CONTENT_FORBIDDEN"
    assert unassigned_response.status_code == 404
    assert unassigned_response.json()["detail"] == "SECTION_NOT_FOUND"
    assert cross_module_response.status_code == 404
    assert cross_module_response.json()["detail"] == "SECTION_NOT_FOUND"
    assert assignment_response.status_code == 422
    assert assignment_response.json()["detail"] == "SECTION_METADATA_TYPE_INVALID"


@pytest.mark.anyio
async def test_assigned_lecturer_sections_by_week_uses_resolver_modes(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="by-week-lecturer@example.com", role="lecturer")
    student = await _create_user(db_session, email="by-week-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    week_one_lecture = await _create_section(
        db_session,
        module_id=module.id,
        title="Lecture week one",
        section_type="lecture",
        order_index=1,
        week_number=1,
        session_date=date(2026, 5, 11),
    )
    week_one_lab = await _create_section(
        db_session,
        module_id=module.id,
        title="Lab week one",
        section_type="lab",
        order_index=2,
        week_number=1,
        session_date=date(2026, 5, 14),
    )
    week_two = await _create_section(
        db_session,
        module_id=module.id,
        title="Lecture week two",
        section_type="lecture",
        order_index=3,
        week_number=2,
        session_date=date(2026, 5, 18),
    )
    unstamped = await _create_section(
        db_session,
        module_id=module.id,
        title="Needs curation",
        section_type="lab",
        order_index=4,
    )
    assignment = await _create_section(
        db_session,
        module_id=module.id,
        title="Legacy assignment",
        section_type="assignment",
        order_index=5,
        week_number=1,
        session_date=date(2026, 5, 15),
    )

    lecturer_headers = _headers(lecturer, jwt_factory)
    week_one_response = await auth_client.get(
        f"/modules/{module.id}/sections/by-week?coveredWeeks=1",
        headers=lecturer_headers,
    )
    curation_response = await auth_client.get(
        f"/modules/{module.id}/sections/by-week?includeUnstamped=true",
        headers=lecturer_headers,
    )
    student_response = await auth_client.get(
        f"/modules/{module.id}/sections/by-week?includeUnstamped=true",
        headers=_headers(student, jwt_factory),
    )

    assert week_one_response.status_code == 200
    assert [row["id"] for row in week_one_response.json()] == [
        str(week_one_lecture.id),
        str(week_one_lab.id),
    ]
    assert curation_response.status_code == 200
    assert [row["id"] for row in curation_response.json()] == [
        str(week_one_lecture.id),
        str(week_one_lab.id),
        str(week_two.id),
        str(unstamped.id),
    ]
    assert str(assignment.id) not in curation_response.text
    assert student_response.status_code == 403
    assert student_response.json()["detail"] == "CONTENT_FORBIDDEN"


@pytest.mark.anyio
async def test_student_reads_only_published_sections_and_completed_assets(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="student-read-lecturer@example.com", role="lecturer")
    student = await _create_user(db_session, email="student-read-student@example.com")
    admin = await _create_user(db_session, email="student-read-admin@example.com", role="admin")
    module = await _create_module(db_session, owner_id=lecturer.id)
    other_module = await _create_module(db_session, owner_id=lecturer.id, title="Hidden Module")
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")

    later_published = await _create_section(
        db_session,
        module_id=module.id,
        title="Later",
        order_index=2,
        publish_status="published",
        lecturer_notes="   ",
    )
    visible = await _create_section(
        db_session,
        module_id=module.id,
        title="Visible",
        order_index=1,
        publish_status="published",
        due_at=datetime(2026, 5, 14, 17, 0, tzinfo=UTC),
        lecturer_notes="Read this first",
    )
    draft = await _create_section(
        db_session,
        module_id=module.id,
        title="Draft",
        order_index=3,
        publish_status="draft",
    )
    unpublished = await _create_section(
        db_session,
        module_id=module.id,
        title="Unpublished",
        order_index=4,
        publish_status="unpublished",
    )
    archived = await _create_section(
        db_session,
        module_id=module.id,
        title="Archived",
        order_index=5,
        publish_status="published",
        status="archived",
    )
    other_section = await _create_section(
        db_session,
        module_id=other_module.id,
        title="Other",
        publish_status="published",
    )
    completed_asset = await _create_asset(
        db_session,
        section_id=visible.id,
        uploaded_by_user_id=lecturer.id,
        file_name="visible.pdf",
    )
    earlier_asset = await _create_asset(
        db_session,
        section_id=visible.id,
        uploaded_by_user_id=lecturer.id,
        file_name="earlier.pdf",
    )
    later_asset = await _create_asset(
        db_session,
        section_id=visible.id,
        uploaded_by_user_id=lecturer.id,
        file_name="later.pdf",
    )
    earlier_asset.created_at = datetime.now(UTC) - timedelta(minutes=2)
    completed_asset.created_at = datetime.now(UTC) - timedelta(minutes=1)
    later_asset.created_at = datetime.now(UTC)
    processing_asset = await _create_asset(
        db_session,
        section_id=visible.id,
        uploaded_by_user_id=lecturer.id,
        file_name="processing.pdf",
        processing_status="processing",
    )
    await _create_asset(
        db_session,
        section_id=draft.id,
        uploaded_by_user_id=lecturer.id,
        file_name="draft.pdf",
    )
    await _create_asset(
        db_session,
        section_id=later_published.id,
        uploaded_by_user_id=lecturer.id,
        file_name="not-ready.pdf",
        processing_status="uploaded",
    )

    student_headers = _headers(student, jwt_factory)
    list_response = await auth_client.get(
        f"/modules/{module.id}/sections",
        headers=student_headers,
    )
    detail_response = await auth_client.get(
        f"/modules/{module.id}/sections/{visible.id}",
        headers=student_headers,
    )

    assert list_response.status_code == 200
    assert list_response.json() == [
        {
            "id": str(visible.id),
            "title": "Visible",
            "type": "lecture",
            "orderIndex": 1,
            "hasAssets": True,
            "hasNotes": True,
        },
        {
            "id": str(later_published.id),
            "title": "Later",
            "type": "lecture",
            "orderIndex": 2,
            "hasAssets": False,
            "hasNotes": False,
        },
    ]
    assert detail_response.status_code == 200
    assert detail_response.json() == {
        "id": str(visible.id),
        "title": "Visible",
        "type": "lecture",
        "orderIndex": 1,
        "dueAt": "2026-05-14T17:00:00Z",
        "lecturerNotes": "Read this first",
        "assets": [
            {
                "id": str(earlier_asset.id),
                "fileName": "earlier.pdf",
                "mimeType": "application/pdf",
                "fileSize": len(PDF_BYTES),
                "assetKind": "processable",
            },
            {
                "id": str(completed_asset.id),
                "fileName": "visible.pdf",
                "mimeType": "application/pdf",
                "fileSize": len(PDF_BYTES),
                "assetKind": "processable",
            },
            {
                "id": str(later_asset.id),
                "fileName": "later.pdf",
                "mimeType": "application/pdf",
                "fileSize": len(PDF_BYTES),
                "assetKind": "processable",
            }
        ],
    }
    response_text = detail_response.text
    assert "storageKey" not in response_text
    assert "processingStatus" not in response_text
    assert "publishStatus" not in response_text
    assert str(processing_asset.id) not in response_text

    for section in (draft, unpublished, archived):
        hidden_response = await auth_client.get(
            f"/modules/{module.id}/sections/{section.id}",
            headers=student_headers,
        )
        assert hidden_response.status_code == 404
        assert hidden_response.json()["detail"] == "SECTION_NOT_FOUND"

    unassigned_response = await auth_client.get(
        f"/modules/{other_module.id}/sections/{other_section.id}",
        headers=student_headers,
    )
    admin_response = await auth_client.get(
        f"/modules/{module.id}/sections",
        headers=_headers(admin, jwt_factory),
    )

    assert unassigned_response.status_code == 404
    assert admin_response.status_code == 404


@pytest.mark.anyio
async def test_generated_sections_use_existing_visibility_rules(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="generated-sections-lecturer@example.com",
        role="lecturer",
    )
    student = await _create_user(db_session, email="generated-sections-student@example.com")
    admin = await _create_user(
        db_session,
        email="generated-sections-admin@example.com",
        role="admin",
    )

    create_response = await auth_client.post(
        "/admin/modules",
        headers=_headers(admin, jwt_factory),
        json={
            "title": "Generated Visibility",
            "ownerId": str(lecturer.id),
            "schedule": {
                "courseStartDate": "2026-05-11",
                "courseEndDate": "2026-06-26",
                "weekStartDay": "monday",
                "sessionPattern": [
                    {"weekday": "monday", "sectionType": "lecture"},
                    {"weekday": "tuesday", "sectionType": "lecture"},
                    {"weekday": "wednesday", "sectionType": "lecture"},
                    {"weekday": "thursday", "sectionType": "lab"},
                ],
                "quizDay": "friday",
            },
        },
    )
    assert create_response.status_code == 201
    module_id = UUID(create_response.json()["id"])
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module_id,
        role="student",
    )

    section_result = await db_session.execute(
        select(
            ModuleSection.id,
            ModuleSection.title,
            ModuleSection.type,
            ModuleSection.publish_status,
        )
        .where(ModuleSection.course_module_id == module_id)
        .order_by(ModuleSection.order_index.asc())
    )
    sections = section_result.all()
    # Schedule-driven generation (Stage 5.5a): the reference schedule yields 28 draft lecture/lab
    # sections; visibility rules below operate on whatever was generated, not a fixed template.
    assert len(sections) == 28
    assert all(section.type in ("lecture", "lab") for section in sections)
    assert all(section.publish_status == "draft" for section in sections)

    lecturer_headers = _headers(lecturer, jwt_factory)
    student_headers = _headers(student, jwt_factory)
    lecturer_response = await auth_client.get(
        f"/modules/{module_id}/sections",
        headers=lecturer_headers,
    )
    draft_student_response = await auth_client.get(
        f"/modules/{module_id}/sections",
        headers=student_headers,
    )
    publish_response = await auth_client.post(
        f"/modules/{module_id}/sections/{sections[0].id}/publish",
        headers=lecturer_headers,
    )
    published_student_response = await auth_client.get(
        f"/modules/{module_id}/sections",
        headers=student_headers,
    )

    assert lecturer_response.status_code == 200
    assert [row["id"] for row in lecturer_response.json()] == [
        str(section.id) for section in sections
    ]
    assert draft_student_response.status_code == 200
    assert draft_student_response.json() == []
    assert publish_response.status_code == 200
    assert publish_response.json()["publishStatus"] == "published"
    assert published_student_response.status_code == 200
    # sections[0] is the order_index=1 row (earliest session); the student sees exactly it once
    # published, with its generated title/type — drafts stay hidden.
    assert published_student_response.json() == [
        {
            "id": str(sections[0].id),
            "title": sections[0].title,
            "type": sections[0].type,
            "orderIndex": 1,
            "hasAssets": False,
            "hasNotes": False,
        }
    ]


@pytest.mark.anyio
async def test_signed_download_url_is_role_aware_and_revalidated_live(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIGNED_READ_URL_TTL_SECONDS", "300")
    lecturer = await _create_user(db_session, email="download-lecturer@example.com", role="lecturer")
    student = await _create_user(db_session, email="download-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _create_section(
        db_session,
        module_id=module.id,
        publish_status="published",
    )
    draft_section = await _create_section(
        db_session,
        module_id=module.id,
        order_index=1,
        publish_status="draft",
    )
    archived_section = await _create_section(
        db_session,
        module_id=module.id,
        order_index=2,
        publish_status="published",
        status="archived",
    )
    asset = await _create_asset(db_session, section_id=section.id, uploaded_by_user_id=lecturer.id)
    draft_asset = await _create_asset(
        db_session,
        section_id=draft_section.id,
        uploaded_by_user_id=lecturer.id,
    )
    archived_asset = await _create_asset(
        db_session,
        section_id=archived_section.id,
        uploaded_by_user_id=lecturer.id,
    )
    processing_asset = await _create_asset(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        processing_status="processing",
    )

    student_headers = _headers(student, jwt_factory)
    lecturer_headers = _headers(lecturer, jwt_factory)
    student_response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/assets/{asset.id}/download-url",
        headers=student_headers,
    )
    draft_response = await auth_client.get(
        f"/modules/{module.id}/sections/{draft_section.id}/assets/{draft_asset.id}/download-url",
        headers=student_headers,
    )
    processing_response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/assets/{processing_asset.id}/download-url",
        headers=student_headers,
    )
    lecturer_response = await auth_client.get(
        f"/modules/{module.id}/sections/{draft_section.id}/assets/{draft_asset.id}/download-url",
        headers=lecturer_headers,
    )
    archived_lecturer_response = await auth_client.get(
        f"/modules/{module.id}/sections/{archived_section.id}/assets/{archived_asset.id}/download-url",
        headers=lecturer_headers,
    )

    assert student_response.status_code == 200
    assert student_response.headers["cache-control"] == "no-store"
    assert student_response.json()["url"] == f"https://storage.example/{asset.storage_key}?ttl=300"
    assert student_response.json()["expiresAt"].endswith("Z")
    assert fake_storage.signed_url_calls[0] == (asset.storage_key, 300)
    assert "storageKey" not in student_response.text
    assert draft_response.status_code == 404
    assert processing_response.status_code == 404
    assert lecturer_response.status_code == 200
    assert archived_lecturer_response.status_code == 409
    assert archived_lecturer_response.json()["detail"] == "SECTION_ARCHIVED"

    unpublish_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/unpublish",
        headers=lecturer_headers,
    )
    revalidated_response = await auth_client.get(
        f"/modules/{module.id}/sections/{section.id}/assets/{asset.id}/download-url",
        headers=student_headers,
    )

    assert unpublish_response.status_code == 200
    assert revalidated_response.status_code == 403
    assert revalidated_response.json()["detail"] == "CONTENT_FORBIDDEN"


@pytest.mark.anyio
async def test_attachment_download_streams_through_backend_with_download_headers(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="attachment-download-lecturer@example.com",
        role="lecturer",
    )
    student = await _create_user(db_session, email="attachment-download-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    lab = await _create_section(
        db_session,
        module_id=module.id,
        title="Published lab",
        section_type="lab",
        publish_status="published",
    )
    attachment = await _create_asset(
        db_session,
        section_id=lab.id,
        uploaded_by_user_id=lecturer.id,
        file_name="week 1 lab.ipynb",
        asset_kind="attachment",
        mime_type=NOTEBOOK_MIME_TYPE,
        data=NOTEBOOK_BYTES,
    )
    pdf = await _create_asset(
        db_session,
        section_id=lab.id,
        uploaded_by_user_id=lecturer.id,
        file_name="lab.pdf",
    )
    fake_storage.objects[attachment.storage_key] = NOTEBOOK_BYTES

    student_headers = _headers(student, jwt_factory)
    download_response = await auth_client.get(
        f"/modules/{module.id}/sections/{lab.id}/assets/{attachment.id}/download",
        headers=student_headers,
    )
    signed_url_response = await auth_client.get(
        f"/modules/{module.id}/sections/{lab.id}/assets/{attachment.id}/download-url",
        headers=student_headers,
    )
    pdf_stream_response = await auth_client.get(
        f"/modules/{module.id}/sections/{lab.id}/assets/{pdf.id}/download",
        headers=student_headers,
    )

    assert download_response.status_code == 200
    assert download_response.content == NOTEBOOK_BYTES
    assert download_response.headers["x-content-type-options"] == "nosniff"
    assert download_response.headers["cache-control"] == "no-store"
    assert download_response.headers["content-type"].startswith(NOTEBOOK_MIME_TYPE)
    assert "attachment" in download_response.headers["content-disposition"]
    assert "filename*=UTF-8''week%201%20lab.ipynb" in download_response.headers[
        "content-disposition"
    ]
    assert signed_url_response.status_code == 404
    assert signed_url_response.json()["detail"] == "SECTION_NOT_FOUND"
    assert fake_storage.signed_url_calls == []
    assert pdf_stream_response.status_code == 404
    assert pdf_stream_response.json()["detail"] == "SECTION_NOT_FOUND"


@pytest.mark.anyio
async def test_lecturer_sections_include_all_active_publish_states_and_student_writes_stay_forbidden(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    fake_storage: FakeStorageProvider,
) -> None:
    lecturer = await _create_user(db_session, email="role-list-lecturer@example.com", role="lecturer")
    student = await _create_user(db_session, email="role-list-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    published = await _create_section(
        db_session,
        module_id=module.id,
        title="Published",
        order_index=0,
        publish_status="published",
    )
    draft = await _create_section(
        db_session,
        module_id=module.id,
        title="Draft",
        order_index=1,
        publish_status="draft",
    )
    unpublished = await _create_section(
        db_session,
        module_id=module.id,
        title="Unpublished",
        order_index=2,
        publish_status="unpublished",
    )
    asset = await _create_asset(db_session, section_id=published.id, uploaded_by_user_id=lecturer.id)

    lecturer_response = await auth_client.get(
        f"/modules/{module.id}/sections",
        headers=_headers(lecturer, jwt_factory),
    )
    student_headers = _headers(student, jwt_factory)
    write_responses = [
        await auth_client.post(
            f"/modules/{module.id}/sections/{published.id}/assets",
            files=_pdf_file(),
            headers=student_headers,
        ),
        await auth_client.put(
            f"/modules/{module.id}/sections/{published.id}/assets/{asset.id}",
            files=_pdf_file("replace.pdf"),
            headers=student_headers,
        ),
        await auth_client.post(
            f"/modules/{module.id}/sections/{published.id}/publish",
            headers=student_headers,
        ),
        await auth_client.post(
            f"/modules/{module.id}/sections/{published.id}/unpublish",
            headers=student_headers,
        ),
        await auth_client.patch(
            f"/modules/{module.id}/sections/{published.id}/notes",
            json={"lecturerNotes": "nope"},
            headers=student_headers,
        ),
    ]

    assert lecturer_response.status_code == 200
    assert [row["id"] for row in lecturer_response.json()] == [
        str(published.id),
        str(draft.id),
        str(unpublished.id),
    ]
    assert all("publishStatus" not in row for row in lecturer_response.json())
    for response in write_responses:
        assert response.status_code == 403
        assert response.json()["detail"] == "CONTENT_FORBIDDEN"
    assert fake_storage.put_calls == []


@pytest.mark.anyio
async def test_publish_notes_authz_archived_mismatch_and_validation_timing(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(db_session, email="matrix-lecturer@example.com", role="lecturer")
    other_lecturer = await _create_user(
        db_session,
        email="matrix-other-lecturer@example.com",
        role="lecturer",
    )
    inactive_lecturer = await _create_user(
        db_session,
        email="matrix-inactive@example.com",
        role="lecturer",
        is_active=False,
    )
    student = await _create_user(db_session, email="matrix-student@example.com")
    admin = await _create_user(db_session, email="matrix-admin@example.com", role="admin")
    module = await _create_module(db_session, owner_id=lecturer.id)
    other_module = await _create_module(db_session, owner_id=other_lecturer.id, title="Other")
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=other_lecturer.id,
        module_id=other_module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    section = await _create_section(db_session, module_id=module.id)
    other_section = await _create_section(db_session, module_id=other_module.id)
    archived_section = await _create_section(
        db_session,
        module_id=module.id,
        order_index=1,
        status="archived",
    )
    long_notes = "x" * 5001

    for user in (student, admin):
        publish_response = await auth_client.post(
            f"/modules/{module.id}/sections/{section.id}/publish",
            headers=_headers(user, jwt_factory),
        )
        notes_response = await auth_client.patch(
            f"/modules/{module.id}/sections/{section.id}/notes",
            json={"lecturerNotes": long_notes},
            headers=_headers(user, jwt_factory),
        )
        assert publish_response.status_code == 403
        assert publish_response.json()["detail"] == "CONTENT_FORBIDDEN"
        assert notes_response.status_code == 403
        assert notes_response.json()["detail"] == "CONTENT_FORBIDDEN"

    inactive_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/publish",
        headers=_headers(inactive_lecturer, jwt_factory),
    )
    inaccessible_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{section.id}/notes",
        json={"lecturerNotes": long_notes},
        headers=_headers(other_lecturer, jwt_factory),
    )
    mismatch_response = await auth_client.post(
        f"/modules/{module.id}/sections/{other_section.id}/publish",
        headers=_headers(lecturer, jwt_factory),
    )
    archived_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{archived_section.id}/notes",
        json={"lecturerNotes": "archived"},
        headers=_headers(lecturer, jwt_factory),
    )
    invalid_transition_response = await auth_client.post(
        f"/modules/{module.id}/sections/{section.id}/unpublish",
        headers=_headers(lecturer, jwt_factory),
    )
    over_cap_response = await auth_client.patch(
        f"/modules/{module.id}/sections/{section.id}/notes",
        json={"lecturerNotes": long_notes},
        headers=_headers(lecturer, jwt_factory),
    )

    assert inactive_response.status_code == 403
    assert inaccessible_response.status_code == 404
    assert inaccessible_response.json()["detail"] == "SECTION_NOT_FOUND"
    assert mismatch_response.status_code == 404
    assert mismatch_response.json()["detail"] == "SECTION_NOT_FOUND"
    assert archived_response.status_code == 409
    assert archived_response.json()["detail"] == "SECTION_ARCHIVED"
    assert invalid_transition_response.status_code == 422
    assert invalid_transition_response.json()["detail"] == "SECTION_TRANSITION_INVALID"
    assert over_cap_response.status_code == 422
    assert over_cap_response.json()["detail"] == "SECTION_NOTES_TOO_LONG"


@pytest.mark.anyio
async def test_unpublish_authz_membership_boundary(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    # Stage 12a regression lock: the unpublish mutation is membership-gated exactly like publish
    # (publish/notes were already covered; unpublish was only exercised for transition validity).
    # A student or admin is role-forbidden (403 CONTENT_FORBIDDEN); a lecturer with no active
    # membership in the module gets the information-hiding 404 (never 403, never 401 — rule 5).
    lecturer = await _create_user(db_session, email="unpub-lecturer@example.com", role="lecturer")
    unassigned_lecturer = await _create_user(
        db_session, email="unpub-unassigned@example.com", role="lecturer"
    )
    student = await _create_user(db_session, email="unpub-student@example.com")
    admin = await _create_user(db_session, email="unpub-admin@example.com", role="admin")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _create_section(db_session, module_id=module.id, publish_status="published")
    path = f"/modules/{module.id}/sections/{section.id}/unpublish"

    for user in (student, admin):
        response = await auth_client.post(path, headers=_headers(user, jwt_factory))
        assert response.status_code == 403  # role-forbidden, not 401 (session kept)
        assert response.json()["detail"] == "CONTENT_FORBIDDEN"

    unassigned_response = await auth_client.post(
        path, headers=_headers(unassigned_lecturer, jwt_factory)
    )
    assert unassigned_response.status_code == 404  # info-hiding, not 403 and not 401
    assert unassigned_response.json()["detail"] == "SECTION_NOT_FOUND"


@pytest.mark.anyio
async def test_authz_denial_carries_error_envelope_and_request_id(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    # Stage 12a: real domain authz denials flow through the global error envelope — the response
    # carries error.{code,message,request_id} AND the X-Request-ID header, the legacy `detail` is
    # preserved (additive), and the status is never 401 for an authenticated-but-unauthorized caller.
    lecturer = await _create_user(db_session, email="env-lecturer@example.com", role="lecturer")
    unassigned_lecturer = await _create_user(
        db_session, email="env-unassigned@example.com", role="lecturer"
    )
    student = await _create_user(db_session, email="env-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    section = await _create_section(db_session, module_id=module.id)
    path = f"/modules/{module.id}/sections/{section.id}/publish"

    # 403 role-forbidden (student): coded envelope + additive detail + X-Request-ID.
    forbidden = await auth_client.post(path, headers=_headers(student, jwt_factory))
    assert forbidden.status_code == 403
    body = forbidden.json()
    assert body["error"]["code"] == "CONTENT_FORBIDDEN"
    assert body["error"]["message"] == "CONTENT_FORBIDDEN"
    assert body["error"]["request_id"]
    assert body["detail"] == "CONTENT_FORBIDDEN"  # additive: legacy field preserved
    assert forbidden.headers["X-Request-ID"] == body["error"]["request_id"]

    # 404 information-hiding (unassigned lecturer): same envelope shape, never 401.
    not_found = await auth_client.post(path, headers=_headers(unassigned_lecturer, jwt_factory))
    assert not_found.status_code == 404
    nf_body = not_found.json()
    assert nf_body["error"]["code"] == "SECTION_NOT_FOUND"
    assert nf_body["error"]["request_id"]
    assert not_found.headers["X-Request-ID"] == nf_body["error"]["request_id"]


@pytest.mark.anyio
async def test_publish_and_notes_no_ops_do_not_commit_or_bump_updated_at(
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lecturer = await _create_user(db_session, email="noop-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(
        db_session,
        module_id=module.id,
        publish_status="published",
        lecturer_notes="Already normalized",
    )
    await db_session.commit()
    original_updated_at = section.updated_at
    current_user = content_service.CurrentUserContext(
        user_id=lecturer.id,
        auth_provider_id=lecturer.auth_provider_id,
        email=lecturer.email,
        full_name=lecturer.full_name,
        role=lecturer.role,
        is_active=lecturer.is_active,
        timezone=lecturer.timezone,
    )

    async def fail_commit() -> None:
        raise AssertionError("no-op should return before commit")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    publish_result = await content_service.publish_section(
        db_session,
        current_user=current_user,
        module_id=module.id,
        section_id=section.id,
    )
    notes_result = await content_service.update_section_notes(
        db_session,
        current_user=current_user,
        module_id=module.id,
        section_id=section.id,
        lecturer_notes="Already normalized",
    )

    assert publish_result.updated_at == original_updated_at
    assert notes_result.updated_at == original_updated_at
