from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
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
    publish_status: str
    lecturer_notes: str | None
    updated_at: datetime


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
            processing_status=row.processing_status,
            uploaded_by_user_id=row.uploaded_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in result.all()
    ]


async def get_lecturer_section_detail_row(
    db: AsyncSession,
    *,
    user_id: UUID,
    module_id: UUID,
    section_id: UUID,
) -> SectionDetailReadRow | None:
    result = await db.execute(
        select(
            ModuleSection.id,
            ModuleSection.course_module_id,
            ModuleSection.title,
            ModuleSection.type,
            ModuleSection.publish_status,
            ModuleSection.lecturer_notes,
            ModuleSection.updated_at,
        )
        .join(CourseModule, ModuleSection.course_module_id == CourseModule.id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            ModuleSection.id == section_id,
            ModuleSection.course_module_id == module_id,
            CourseMembership.user_id == user_id,
            CourseMembership.role == "lecturer",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
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
        publish_status=row.publish_status,
        lecturer_notes=row.lecturer_notes,
        updated_at=row.updated_at,
    )
