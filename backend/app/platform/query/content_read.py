from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import CourseMembership, CourseModule, ModuleSection, SectionAsset


@dataclass(frozen=True)
class SectionAccessRow:
    section_id: UUID
    module_id: UUID


@dataclass(frozen=True)
class SectionAssetReadRow:
    id: UUID
    module_section_id: UUID
    file_name: str
    mime_type: str
    file_size: int
    checksum_sha256: str
    asset_kind: str
    processing_status: str
    uploaded_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SectionDetailReadRow:
    id: UUID
    course_module_id: UUID
    title: str
    type: str
    order_index: int
    publish_status: str
    lecturer_notes: str | None
    status: str
    updated_at: datetime


@dataclass(frozen=True)
class SectionListItemReadRow:
    id: UUID
    title: str
    type: str
    order_index: int
    has_assets: bool
    has_notes: bool


@dataclass(frozen=True)
class StudentAssetMetaReadRow:
    id: UUID
    file_name: str
    mime_type: str
    file_size: int
    asset_kind: str


@dataclass(frozen=True)
class StudentSectionDetailReadRow:
    id: UUID
    title: str
    type: str
    order_index: int
    lecturer_notes: str | None
    assets: list[StudentAssetMetaReadRow]


@dataclass(frozen=True)
class AssetDownloadRefRow:
    asset_id: UUID
    section_id: UUID
    course_module_id: UUID
    section_publish_status: str
    section_status: str
    asset_processing_status: str
    asset_kind: str
    storage_key: str
    file_name: str
    mime_type: str


async def lecturer_has_active_module_membership(
    db: AsyncSession,
    *,
    user_id: UUID,
    module_id: UUID,
) -> bool:
    result = await db.execute(
        select(CourseMembership.id)
        .join(CourseModule, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == user_id,
            CourseMembership.module_id == module_id,
            CourseMembership.role == "lecturer",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
    )
    return result.first() is not None


async def get_section_access_row(
    db: AsyncSession,
    *,
    module_id: UUID,
    section_id: UUID,
) -> SectionAccessRow | None:
    result = await db.execute(
        select(
            ModuleSection.id.label("section_id"),
            ModuleSection.course_module_id.label("module_id"),
        ).where(
            ModuleSection.id == section_id,
            ModuleSection.course_module_id == module_id,
            ModuleSection.status == "active",
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    return SectionAccessRow(section_id=row.section_id, module_id=row.module_id)


async def list_section_asset_rows(
    db: AsyncSession,
    *,
    section_id: UUID,
) -> list[SectionAssetReadRow]:
    result = await db.execute(
        select(
            SectionAsset.id,
            SectionAsset.module_section_id,
            SectionAsset.file_name,
            SectionAsset.mime_type,
            SectionAsset.file_size,
            SectionAsset.checksum_sha256,
            SectionAsset.asset_kind,
            SectionAsset.processing_status,
            SectionAsset.uploaded_by_user_id,
            SectionAsset.created_at,
            SectionAsset.updated_at,
        )
        .where(SectionAsset.module_section_id == section_id)
        .order_by(SectionAsset.created_at.asc(), SectionAsset.id.asc())
    )
    return [
        SectionAssetReadRow(
            id=row.id,
            module_section_id=row.module_section_id,
            file_name=row.file_name,
            mime_type=row.mime_type,
            file_size=row.file_size,
            checksum_sha256=row.checksum_sha256,
            asset_kind=row.asset_kind,
            processing_status=row.processing_status,
            uploaded_by_user_id=row.uploaded_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in result.all()
    ]


async def list_lecturer_section_rows(
    db: AsyncSession,
    *,
    module_id: UUID,
) -> list[SectionListItemReadRow]:
    has_assets = exists(
        select(1).where(SectionAsset.module_section_id == ModuleSection.id)
    )
    result = await db.execute(
        select(
            ModuleSection.id,
            ModuleSection.title,
            ModuleSection.type,
            ModuleSection.order_index,
            has_assets.label("has_assets"),
            (func.length(func.trim(func.coalesce(ModuleSection.lecturer_notes, ""))) > 0).label(
                "has_notes"
            ),
        )
        .where(
            ModuleSection.course_module_id == module_id,
            ModuleSection.status == "active",
        )
        .order_by(ModuleSection.order_index.asc(), ModuleSection.id.asc())
    )
    return [
        SectionListItemReadRow(
            id=row.id,
            title=row.title,
            type=row.type,
            order_index=row.order_index,
            has_assets=row.has_assets,
            has_notes=row.has_notes,
        )
        for row in result.all()
    ]


async def list_published_sections_for_student(
    db: AsyncSession,
    *,
    module_id: UUID,
) -> list[SectionListItemReadRow]:
    has_completed_assets = exists(
        select(1).where(
            SectionAsset.module_section_id == ModuleSection.id,
            SectionAsset.processing_status == "completed",
        )
    )
    result = await db.execute(
        select(
            ModuleSection.id,
            ModuleSection.title,
            ModuleSection.type,
            ModuleSection.order_index,
            has_completed_assets.label("has_assets"),
            (func.length(func.trim(func.coalesce(ModuleSection.lecturer_notes, ""))) > 0).label(
                "has_notes"
            ),
        )
        .where(
            ModuleSection.course_module_id == module_id,
            ModuleSection.publish_status == "published",
            ModuleSection.status == "active",
        )
        .order_by(ModuleSection.order_index.asc(), ModuleSection.id.asc())
    )
    return [
        SectionListItemReadRow(
            id=row.id,
            title=row.title,
            type=row.type,
            order_index=row.order_index,
            has_assets=row.has_assets,
            has_notes=row.has_notes,
        )
        for row in result.all()
    ]


async def get_lecturer_section_detail_row(
    db: AsyncSession,
    *,
    module_id: UUID,
    section_id: UUID,
) -> SectionDetailReadRow | None:
    result = await db.execute(
        select(
            ModuleSection.id,
            ModuleSection.course_module_id,
            ModuleSection.title,
            ModuleSection.type,
            ModuleSection.order_index,
            ModuleSection.publish_status,
            ModuleSection.lecturer_notes,
            ModuleSection.status,
            ModuleSection.updated_at,
        )
        .where(
            ModuleSection.id == section_id,
            ModuleSection.course_module_id == module_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    return SectionDetailReadRow(
        id=row.id,
        course_module_id=row.course_module_id,
        title=row.title,
        type=row.type,
        order_index=row.order_index,
        publish_status=row.publish_status,
        lecturer_notes=row.lecturer_notes,
        status=row.status,
        updated_at=row.updated_at,
    )


async def get_published_section_for_student(
    db: AsyncSession,
    *,
    module_id: UUID,
    section_id: UUID,
) -> StudentSectionDetailReadRow | None:
    section_result = await db.execute(
        select(
            ModuleSection.id,
            ModuleSection.title,
            ModuleSection.type,
            ModuleSection.order_index,
            ModuleSection.lecturer_notes,
        ).where(
            ModuleSection.id == section_id,
            ModuleSection.course_module_id == module_id,
            ModuleSection.publish_status == "published",
            ModuleSection.status == "active",
        )
    )
    section = section_result.one_or_none()
    if section is None:
        return None

    asset_result = await db.execute(
        select(
            SectionAsset.id,
            SectionAsset.file_name,
            SectionAsset.mime_type,
            SectionAsset.file_size,
            SectionAsset.asset_kind,
        )
        .where(
            SectionAsset.module_section_id == section_id,
            SectionAsset.processing_status == "completed",
        )
        .order_by(SectionAsset.created_at.asc(), SectionAsset.id.asc())
    )
    return StudentSectionDetailReadRow(
        id=section.id,
        title=section.title,
        type=section.type,
        order_index=section.order_index,
        lecturer_notes=section.lecturer_notes,
        assets=[
            StudentAssetMetaReadRow(
                id=row.id,
                file_name=row.file_name,
                mime_type=row.mime_type,
                file_size=row.file_size,
                asset_kind=row.asset_kind,
            )
            for row in asset_result.all()
        ],
    )


async def get_asset_download_ref(
    db: AsyncSession,
    *,
    module_id: UUID,
    section_id: UUID,
    asset_id: UUID,
) -> AssetDownloadRefRow | None:
    result = await db.execute(
        select(
            SectionAsset.id.label("asset_id"),
            SectionAsset.module_section_id.label("section_id"),
            ModuleSection.course_module_id,
            ModuleSection.publish_status.label("section_publish_status"),
            ModuleSection.status.label("section_status"),
            SectionAsset.processing_status.label("asset_processing_status"),
            SectionAsset.asset_kind,
            SectionAsset.storage_key,
            SectionAsset.file_name,
            SectionAsset.mime_type,
        )
        .join(ModuleSection, SectionAsset.module_section_id == ModuleSection.id)
        .where(
            SectionAsset.id == asset_id,
            SectionAsset.module_section_id == section_id,
            ModuleSection.course_module_id == module_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    return AssetDownloadRefRow(
        asset_id=row.asset_id,
        section_id=row.section_id,
        course_module_id=row.course_module_id,
        section_publish_status=row.section_publish_status,
        section_status=row.section_status,
        asset_processing_status=row.asset_processing_status,
        asset_kind=row.asset_kind,
        storage_key=row.storage_key,
        file_name=row.file_name,
        mime_type=row.mime_type,
    )
