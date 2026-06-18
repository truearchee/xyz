import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.models import AppUser, CourseMembership, CourseModule
from app.platform.db.session import get_db_session


logger = logging.getLogger(__name__)

# The five supported glossary languages (Stage 7). Mirrors ck_app_users_preferred_language.
PreferredLanguage = Literal["en", "ar", "zh", "es", "fr"]


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
    preferred_language: PreferredLanguage
    active_module_memberships: list[ActiveModuleMembership]


class UpdatePreferencesRequest(CamelModel):
    preferred_language: PreferredLanguage


router = APIRouter(tags=["me"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]


async def _active_memberships(
    db: AsyncSession, current_user: CurrentUserContext
) -> list[ActiveModuleMembership]:
    result = await db.execute(
        select(CourseMembership.module_id, CourseMembership.role)
        .join(CourseModule, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == current_user.user_id,
            CourseMembership.status == "active",
            CourseModule.is_active.is_(True),
        )
        .order_by(CourseModule.created_at, CourseModule.id)
    )
    memberships = [
        ActiveModuleMembership(module_id=row.module_id, role=row.role) for row in result.all()
    ]
    if current_user.role == "admin":
        if memberships:
            logger.warning(
                "Ignoring active module memberships for admin user",
                extra={"user_id": str(current_user.user_id)},
            )
        memberships = []
    return memberships


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(db: DbSession, current_user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        timezone=current_user.timezone,
        preferred_language=current_user.preferred_language,
        active_module_memberships=await _active_memberships(db, current_user),
    )


@router.patch("/me/preferences", response_model=CurrentUserResponse)
async def update_me_preferences(
    payload: UpdatePreferencesRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> CurrentUserResponse:
    """Update the caller's own preferences (Stage 7: glossary definition language). Self-scoped — a
    user can only change their own row. New saves use the new language; existing entries keep theirs."""
    user = await db.get(AppUser, current_user.user_id)
    if user is None:  # pragma: no cover - get_current_user guarantees the row
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")
    user.preferred_language = payload.preferred_language
    await db.commit()
    return CurrentUserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        timezone=current_user.timezone,
        preferred_language=payload.preferred_language,
        active_module_memberships=await _active_memberships(db, current_user),
    )
