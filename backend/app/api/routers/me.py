import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.models import CourseMembership, CourseModule
from app.platform.db.session import get_db_session


logger = logging.getLogger(__name__)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class ActiveModuleMembership(CamelModel):
    module_id: UUID
    role: Literal["lecturer", "student"]


class CurrentUserResponse(CamelModel):
    user_id: UUID
    email: str
    full_name: str
    role: Literal["admin", "lecturer", "student"]
    timezone: str
    active_module_memberships: list[ActiveModuleMembership]


router = APIRouter(tags=["me"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    db: DbSession,
    current_user: CurrentUser,
) -> CurrentUserResponse:
    result = await db.execute(
        select(
            CourseMembership.module_id,
            CourseMembership.role,
        )
        .join(CourseModule, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == current_user.user_id,
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
        .order_by(CourseModule.created_at, CourseModule.id)
    )
    memberships = [
        ActiveModuleMembership(module_id=row.module_id, role=row.role)
        for row in result.all()
    ]

    if current_user.role == "admin":
        if memberships:
            logger.warning(
                "Ignoring active module memberships for admin user",
                extra={"user_id": str(current_user.user_id)},
            )
        memberships = []

    return CurrentUserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        timezone=current_user.timezone,
        active_module_memberships=memberships,
    )
