from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.content.validators import (
    InvalidPdfError,
    SectionNotesTooLongError,
    UploadTooLargeError,
    normalize_section_notes,
    spool_and_validate_pdf,
)
from app.domains.admin.section_generation import DEFAULT_WEEK_START_DAY, week_number_for
from app.domains.content.schemas import AssetDownloadUrl, SectionMetadataPatchRequest
from app.platform.auth.context import CurrentUserContext, ModuleAccessContext
from app.platform.config import settings
from app.platform.db.models import CourseMembership, CourseModule, ModuleSection, SectionAsset
from app.platform.query.content_read import (
    SectionAssetReadRow,
    SectionDetailReadRow,
    SectionListItemReadRow,
    StudentSectionDetailReadRow,
    get_asset_download_ref,
    get_lecturer_section_detail_row,
    get_published_section_for_student,
    get_section_access_row,
    lecturer_has_active_module_membership,
    list_lecturer_section_rows,
    list_published_sections_for_student,
    list_section_asset_rows,
)
from app.platform.storage.base import (
    StorageProvider,
    StorageProviderError,
    StorageUnavailableError,
)
from app.platform.storage.keys import generate_section_asset_storage_key


logger = logging.getLogger(__name__)

CONTENT_FORBIDDEN = "CONTENT_FORBIDDEN"
SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
SECTION_ARCHIVED = "SECTION_ARCHIVED"
SECTION_TRANSITION_INVALID = "SECTION_TRANSITION_INVALID"
SECTION_NOTES_TOO_LONG = "SECTION_NOTES_TOO_LONG"
SECTION_METADATA_TYPE_INVALID = "SECTION_METADATA_TYPE_INVALID"
SECTION_DUE_AT_LAB_ONLY = "SECTION_DUE_AT_LAB_ONLY"
MODULE_SCHEDULE_REQUIRED = "MODULE_SCHEDULE_REQUIRED"


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _coded_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=code)


def _section_detail_from_model(section: ModuleSection) -> SectionDetailReadRow:
    return SectionDetailReadRow(
        id=section.id,
        course_module_id=section.course_module_id,
        title=section.title,
        type=section.type,
        order_index=section.order_index,
        publish_status=section.publish_status,
        lecturer_notes=section.lecturer_notes,
        status=section.status,
        updated_at=section.updated_at,
    )


async def _get_assigned_lecturer_section(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
    for_update: bool = False,
) -> ModuleSection:
    if current_user.role != "lecturer":
        raise _coded_error(status.HTTP_403_FORBIDDEN, CONTENT_FORBIDDEN)

    query = (
        select(ModuleSection)
        .join(CourseModule, ModuleSection.course_module_id == CourseModule.id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            ModuleSection.id == section_id,
            ModuleSection.course_module_id == module_id,
            CourseMembership.user_id == current_user.user_id,
            CourseMembership.role == "lecturer",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
    )
    if for_update:
        query = query.with_for_update(of=ModuleSection)

    section = await db.scalar(query)
    if section is None:
        raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)

    if section.status == "archived":
        raise _coded_error(status.HTTP_409_CONFLICT, SECTION_ARCHIVED)

    return section


async def _get_metadata_edit_section(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> tuple[ModuleSection, CourseModule]:
    query = (
        select(ModuleSection, CourseModule)
        .join(CourseModule, ModuleSection.course_module_id == CourseModule.id)
        .where(
            ModuleSection.id == section_id,
            ModuleSection.course_module_id == module_id,
            CourseModule.is_active.is_(True),
        )
        .with_for_update(of=ModuleSection)
    )

    if current_user.role == "lecturer":
        query = query.join(CourseMembership, CourseMembership.module_id == CourseModule.id).where(
            CourseMembership.user_id == current_user.user_id,
            CourseMembership.role == "lecturer",
            CourseMembership.status == "active",
        )
    elif current_user.role != "admin":
        raise _coded_error(status.HTTP_403_FORBIDDEN, CONTENT_FORBIDDEN)

    row = (await db.execute(query)).one_or_none()
    if row is None:
        raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)

    section, module = row
    if section.status == "archived":
        raise _coded_error(status.HTTP_409_CONFLICT, SECTION_ARCHIVED)
    if section.type not in {"lecture", "lab"}:
        raise _coded_error(422, SECTION_METADATA_TYPE_INVALID)
    return section, module


def resolve_publish_status_transition(current_status: str, target_status: str) -> str:
    if target_status == "draft":
        raise _coded_error(
            422,
            SECTION_TRANSITION_INVALID,
        )

    if target_status == "published":
        if current_status in {"draft", "published", "unpublished"}:
            return "published"

    if target_status == "unpublished":
        if current_status == "draft":
            raise _coded_error(
                422,
                SECTION_TRANSITION_INVALID,
            )
        if current_status in {"published", "unpublished"}:
            return "unpublished"

    raise _coded_error(
        422,
        SECTION_TRANSITION_INVALID,
    )


async def authorize_lecturer_section(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> None:
    if current_user.role != "lecturer":
        raise _coded_error(status.HTTP_403_FORBIDDEN, CONTENT_FORBIDDEN)

    has_membership = await lecturer_has_active_module_membership(
        db,
        user_id=current_user.user_id,
        module_id=module_id,
    )
    if not has_membership:
        raise _http_error(status.HTTP_403_FORBIDDEN, "Lecturer is not assigned to module")

    section = await get_section_access_row(db, module_id=module_id, section_id=section_id)
    if section is None:
        raise _http_error(status.HTTP_404_NOT_FOUND, "Section not found")


async def list_module_sections(
    db: AsyncSession,
    *,
    module_access: ModuleAccessContext,
) -> list[SectionListItemReadRow]:
    if module_access.global_role == "student":
        return await list_published_sections_for_student(
            db,
            module_id=module_access.module_id,
        )
    if module_access.global_role == "lecturer":
        return await list_lecturer_section_rows(db, module_id=module_access.module_id)
    raise _coded_error(status.HTTP_403_FORBIDDEN, CONTENT_FORBIDDEN)


async def get_module_section_detail(
    db: AsyncSession,
    *,
    module_access: ModuleAccessContext,
    section_id: UUID,
) -> SectionDetailReadRow | StudentSectionDetailReadRow:
    if module_access.global_role == "student":
        section = await get_published_section_for_student(
            db,
            module_id=module_access.module_id,
            section_id=section_id,
        )
        if section is None:
            raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)
        return section

    if module_access.global_role == "lecturer":
        section = await get_lecturer_section_detail_row(
            db,
            module_id=module_access.module_id,
            section_id=section_id,
        )
        if section is None:
            raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)
        if section.status == "archived":
            raise _coded_error(status.HTTP_409_CONFLICT, SECTION_ARCHIVED)
        return section

    raise _coded_error(status.HTTP_403_FORBIDDEN, CONTENT_FORBIDDEN)


async def create_asset_download_url(
    db: AsyncSession,
    *,
    module_access: ModuleAccessContext,
    storage_provider: StorageProvider,
    section_id: UUID,
    asset_id: UUID,
) -> AssetDownloadUrl:
    download_ref = await get_asset_download_ref(
        db,
        module_id=module_access.module_id,
        section_id=section_id,
        asset_id=asset_id,
    )
    if download_ref is None:
        raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)

    if module_access.global_role == "student":
        if download_ref.section_publish_status == "unpublished":
            raise _coded_error(status.HTTP_403_FORBIDDEN, CONTENT_FORBIDDEN)
        if (
            download_ref.section_publish_status != "published"
            or download_ref.section_status != "active"
            or download_ref.asset_processing_status != "completed"
        ):
            raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)
    elif module_access.global_role == "lecturer":
        if download_ref.section_status == "archived":
            raise _coded_error(status.HTTP_409_CONFLICT, SECTION_ARCHIVED)
    else:
        raise _coded_error(status.HTTP_403_FORBIDDEN, CONTENT_FORBIDDEN)

    ttl_seconds = settings.SIGNED_READ_URL_TTL_SECONDS
    try:
        url = await storage_provider.create_signed_read_url(
            key=download_ref.storage_key,
            expires_in_seconds=ttl_seconds,
        )
    except StorageProviderError as exc:
        raise _storage_http_error(exc) from exc

    return AssetDownloadUrl(
        url=url,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )


def _storage_http_error(exc: StorageProviderError) -> HTTPException:
    if isinstance(exc, StorageUnavailableError):
        return _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Storage provider unavailable",
        )
    return _http_error(status.HTTP_502_BAD_GATEWAY, "Storage provider failed")


async def _validated_upload(upload: UploadFile):
    try:
        return await spool_and_validate_pdf(
            upload,
            max_bytes=settings.MAX_SECTION_ASSET_UPLOAD_BYTES,
        )
    except UploadTooLargeError as exc:
        raise _http_error(413, str(exc)) from exc
    except InvalidPdfError as exc:
        raise _http_error(422, str(exc)) from exc


async def _best_effort_delete(
    storage_provider: StorageProvider,
    *,
    key: str,
    message: str,
) -> None:
    try:
        await storage_provider.delete_object(key=key)
    except Exception:
        logger.warning(message, extra={"storage_key": key})


async def list_section_assets(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> list[SectionAssetReadRow]:
    await authorize_lecturer_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    return await list_section_asset_rows(db, section_id=section_id)


async def upload_section_asset(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    storage_provider: StorageProvider,
    module_id: UUID,
    section_id: UUID,
    upload: UploadFile,
    authorize: bool = True,
) -> SectionAsset:
    if authorize:
        await authorize_lecturer_section(
            db,
            current_user=current_user,
            module_id=module_id,
            section_id=section_id,
        )
    validated = await _validated_upload(upload)
    asset_id = uuid7()
    storage_key = generate_section_asset_storage_key(
        module_id=module_id,
        section_id=section_id,
        asset_id=asset_id,
    )

    try:
        await storage_provider.put_object(
            key=storage_key,
            content=validated.content,
            content_type=validated.mime_type,
            content_length=validated.file_size,
            metadata={"asset_id": str(asset_id), "section_id": str(section_id)},
            overwrite=False,
        )
    except StorageProviderError as exc:
        validated.content.close()
        raise _storage_http_error(exc) from exc

    asset = SectionAsset(
        id=asset_id,
        module_section_id=section_id,
        storage_key=storage_key,
        file_name=validated.file_name,
        mime_type=validated.mime_type,
        file_size=validated.file_size,
        checksum_sha256=validated.checksum_sha256,
        processing_status="completed",
        uploaded_by_user_id=current_user.user_id,
    )
    db.add(asset)

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        await _best_effort_delete(
            storage_provider,
            key=storage_key,
            message="Failed to clean up section asset object after DB failure",
        )
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not persist asset metadata",
        ) from exc
    finally:
        validated.content.close()

    await db.refresh(asset)
    return asset


async def replace_section_asset(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    storage_provider: StorageProvider,
    module_id: UUID,
    section_id: UUID,
    asset_id: UUID,
    upload: UploadFile,
    authorize: bool = True,
) -> SectionAsset:
    if authorize:
        await authorize_lecturer_section(
            db,
            current_user=current_user,
            module_id=module_id,
            section_id=section_id,
        )
    validated = await _validated_upload(upload)
    new_storage_key = generate_section_asset_storage_key(
        module_id=module_id,
        section_id=section_id,
        asset_id=asset_id,
    )

    try:
        await storage_provider.put_object(
            key=new_storage_key,
            content=validated.content,
            content_type=validated.mime_type,
            content_length=validated.file_size,
            metadata={"asset_id": str(asset_id), "section_id": str(section_id)},
            overwrite=False,
        )
    except StorageProviderError as exc:
        validated.content.close()
        raise _storage_http_error(exc) from exc

    try:
        result = await db.execute(
            select(SectionAsset)
            .where(
                SectionAsset.id == asset_id,
                SectionAsset.module_section_id == section_id,
            )
            .with_for_update()
        )
        asset = result.scalar_one_or_none()
        if asset is None:
            await db.rollback()
            await _best_effort_delete(
                storage_provider,
                key=new_storage_key,
                message="Failed to clean up replacement object after missing asset",
            )
            raise _http_error(status.HTTP_404_NOT_FOUND, "Asset not found")

        old_storage_key = asset.storage_key
        asset.storage_key = new_storage_key
        asset.file_name = validated.file_name
        asset.mime_type = validated.mime_type
        asset.file_size = validated.file_size
        asset.checksum_sha256 = validated.checksum_sha256
        asset.processing_status = "completed"
        asset.uploaded_by_user_id = current_user.user_id
        asset.updated_at = datetime.now(UTC)
        await db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        await db.rollback()
        await _best_effort_delete(
            storage_provider,
            key=new_storage_key,
            message="Failed to clean up replacement object after DB failure",
        )
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not replace asset metadata",
        ) from exc
    finally:
        validated.content.close()

    await db.refresh(asset)
    try:
        await storage_provider.delete_object(key=old_storage_key)
    except Exception:
        logger.warning(
            "Failed to delete replaced section asset object",
            extra={"storage_key": old_storage_key, "asset_id": str(asset_id)},
        )

    return asset


async def set_section_publish_status(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
    target_status: str,
) -> SectionDetailReadRow:
    section = await _get_assigned_lecturer_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
        for_update=True,
    )
    next_status = resolve_publish_status_transition(
        section.publish_status,
        target_status,
    )
    if next_status == section.publish_status:
        return _section_detail_from_model(section)

    section.publish_status = next_status
    section.updated_at = datetime.now(UTC)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not update section publish status",
        ) from exc

    await db.refresh(section)
    return _section_detail_from_model(section)


async def publish_section(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> SectionDetailReadRow:
    return await set_section_publish_status(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
        target_status="published",
    )


async def unpublish_section(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
) -> SectionDetailReadRow:
    return await set_section_publish_status(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
        target_status="unpublished",
    )


async def update_section_notes(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
    lecturer_notes: str | None,
) -> SectionDetailReadRow:
    section = await _get_assigned_lecturer_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
        for_update=True,
    )
    try:
        normalized_notes = normalize_section_notes(lecturer_notes)
    except SectionNotesTooLongError as exc:
        raise _coded_error(
            422,
            SECTION_NOTES_TOO_LONG,
        ) from exc

    if normalized_notes == section.lecturer_notes:
        return _section_detail_from_model(section)

    section.lecturer_notes = normalized_notes
    section.updated_at = datetime.now(UTC)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not update section notes",
        ) from exc

    await db.refresh(section)
    return _section_detail_from_model(section)


async def update_section_metadata(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    module_id: UUID,
    section_id: UUID,
    payload: SectionMetadataPatchRequest,
) -> ModuleSection:
    section, module = await _get_metadata_edit_section(
        db,
        current_user=current_user,
        module_id=module_id,
        section_id=section_id,
    )
    fields = payload.model_fields_set

    if "due_at" in fields and section.type != "lab":
        raise _coded_error(422, SECTION_DUE_AT_LAB_ONLY)

    next_session_date = section.session_date
    next_week_number = section.week_number
    next_due_at = section.due_at

    if "session_date" in fields:
        next_session_date = payload.session_date
    if "week_number" in fields:
        next_week_number = payload.week_number
    elif "session_date" in fields:
        if module.starts_on is None or next_session_date is None:
            raise _coded_error(422, MODULE_SCHEDULE_REQUIRED)
        next_week_number = week_number_for(
            next_session_date,
            start=module.starts_on,
            week_start_day=module.week_start_day or DEFAULT_WEEK_START_DAY,
        )
    if "due_at" in fields:
        next_due_at = payload.due_at

    if (
        next_session_date == section.session_date
        and next_week_number == section.week_number
        and next_due_at == section.due_at
    ):
        return section

    section.session_date = next_session_date
    section.week_number = next_week_number
    section.due_at = next_due_at
    section.updated_at = datetime.now(UTC)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Could not update section metadata",
        ) from exc

    await db.refresh(section)
    return section
