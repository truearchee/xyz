from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext, MembershipRole, ModuleMembership
from app.platform.auth.jwt import credentials_exception, decode_and_verify_jwt
from app.platform.db.models import AppUser, CourseMembership, CourseModule
from app.platform.db.session import get_db_session


def _parse_authorization_header(authorization: str | None) -> str:
    if authorization is None:
        raise credentials_exception("Authorization header required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
        raise credentials_exception()

    return parts[1]


def _membership_role(value: str) -> MembershipRole:
    if value == "student" or value == "lecturer":
        return value
    raise RuntimeError(f"Unexpected course membership role: {value}")


async def get_current_user(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> CurrentUserContext:
    token = _parse_authorization_header(authorization)
    claims = decode_and_verify_jwt(token)
    auth_provider_id = claims["sub"]

    user = await db_session.scalar(
        select(AppUser).where(AppUser.auth_provider_id == auth_provider_id)
    )
    if user is None:
        raise credentials_exception()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    result = await db_session.execute(
        select(
            CourseMembership.module_id,
            CourseMembership.role,
            CourseModule.owner_id,
        )
        .join(CourseModule, CourseMembership.module_id == CourseModule.id)
        .where(
            CourseMembership.user_id == user.id,
            CourseMembership.status == "active",
        )
    )

    module_memberships = tuple(
        ModuleMembership(
            module_id=row.module_id,
            role=_membership_role(row.role),
            is_owner=row.owner_id == user.id,
            can_publish=row.role == "lecturer",
        )
        for row in result.all()
    )

    return CurrentUserContext(
        user_id=user.id,
        auth_provider_id=user.auth_provider_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        timezone=user.timezone,
        module_memberships=module_memberships,
    )
