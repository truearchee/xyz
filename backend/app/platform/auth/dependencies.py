from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.jwt import credentials_exception, decode_and_verify_jwt
from app.platform.db.models import AppUser
from app.platform.db.session import get_db_session


def _parse_authorization_header(authorization: str | None) -> str:
    if authorization is None:
        raise credentials_exception("Authorization header required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
        raise credentials_exception()

    return parts[1]


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

    return CurrentUserContext(
        user_id=user.id,
        auth_provider_id=user.auth_provider_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        timezone=user.timezone,
    )
