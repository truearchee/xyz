from __future__ import annotations

import hashlib
import inspect
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import UploadFile
from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import content as content_router
from app.domains.content import service as content_service
from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    SectionAsset,
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
    UploadTooLargeError,
    sanitize_filename,
    spool_and_validate_pdf,
)
from app.main import app


PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.fail_put: Exception | None = None
        self.fail_delete = False

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

    async def delete_object(self, *, key: str) -> None:
        self.delete_calls.append(key)
        if self.fail_delete:
            raise StorageProviderError("delete failed")
        self.objects.pop(key, None)

    async def create_signed_read_url(
        self,
        *,
        key: str,
        expires_in_seconds: int,
    ) -> str:
        return f"https://storage.example/{key}?ttl={expires_in_seconds}"


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
) -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title=title,
        type=section_type,
        order_index=order_index,
        publish_status="draft",
        status="active",
    )
    session.add(section)
    await session.flush()
    return section


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    token = jwt_factory(sub=user.auth_provider_id)
    return {"Authorization": f"Bearer {token}"}


def _pdf_file(name: str = "slides.pdf", data: bytes = PDF_BYTES):
    return {"file": (name, data, "application/pdf")}


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

    monkeypatch.setattr(content_router, "_extract_multipart_file", fail_if_called)

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
