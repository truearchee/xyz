from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import CourseMembership, CourseModule, ModuleSection


@dataclass(frozen=True)
class AuthorizedSectionContext:
    section_id: UUID
    module_id: UUID
    section_type: str
    publish_status: str
    section_status: str


async def get_authorized_lecturer_section_context(
    db: AsyncSession,
    *,
    user_id: UUID,
    module_id: UUID,
    section_id: UUID,
) -> AuthorizedSectionContext | None:
    result = await db.execute(
        select(
            ModuleSection.id.label("section_id"),
            ModuleSection.course_module_id.label("module_id"),
            ModuleSection.type.label("section_type"),
            ModuleSection.publish_status,
            ModuleSection.status.label("section_status"),
        )
        .join(CourseModule, ModuleSection.course_module_id == CourseModule.id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            ModuleSection.id == section_id,
            ModuleSection.course_module_id == module_id,
            ModuleSection.status == "active",
            CourseMembership.user_id == user_id,
            CourseMembership.role == "lecturer",
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    return AuthorizedSectionContext(
        section_id=row.section_id,
        module_id=row.module_id,
        section_type=row.section_type,
        publish_status=row.publish_status,
        section_status=row.section_status,
    )
