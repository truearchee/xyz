from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import CourseMembership, CourseModule


@dataclass(frozen=True)
class ModuleAccessRow:
    membership_id: UUID
    module_id: UUID
    is_active: bool
    membership_role: str


@dataclass(frozen=True)
class ModuleSummaryRow:
    module_id: UUID
    title: str
    is_active: bool


@dataclass(frozen=True)
class ModuleDetailRow:
    module_id: UUID
    title: str
    is_active: bool
    created_at: datetime


async def get_active_module_access(
    db: AsyncSession,
    user_id: UUID,
    module_id: UUID,
) -> ModuleAccessRow | None:
    result = await db.execute(
        select(
            CourseMembership.id.label("membership_id"),
            CourseMembership.module_id,
            CourseModule.is_active,
            CourseMembership.role.label("membership_role"),
        )
        .join(CourseModule, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == user_id,
            CourseMembership.module_id == module_id,
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
    )
    row = result.one_or_none()
    if row is None:
        return None

    return ModuleAccessRow(
        membership_id=row.membership_id,
        module_id=row.module_id,
        is_active=row.is_active,
        membership_role=row.membership_role,
    )


async def list_active_modules_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> list[ModuleSummaryRow]:
    result = await db.execute(
        select(
            CourseModule.id.label("module_id"),
            CourseModule.title,
            CourseModule.is_active,
        )
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == user_id,
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
        .order_by(CourseModule.created_at, CourseModule.id)
    )

    return [
        ModuleSummaryRow(
            module_id=row.module_id,
            title=row.title,
            is_active=row.is_active,
        )
        for row in result.all()
    ]


async def get_module_detail_row(
    db: AsyncSession,
    module_id: UUID,
) -> ModuleDetailRow | None:
    result = await db.execute(
        select(
            CourseModule.id.label("module_id"),
            CourseModule.title,
            CourseModule.is_active,
            CourseModule.created_at,
        ).where(CourseModule.id == module_id)
    )
    row = result.one_or_none()
    if row is None:
        return None

    return ModuleDetailRow(
        module_id=row.module_id,
        title=row.title,
        is_active=row.is_active,
        created_at=row.created_at,
    )
