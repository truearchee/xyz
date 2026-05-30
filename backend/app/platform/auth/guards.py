from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user


def require_role(*roles: str) -> Callable[..., CurrentUserContext]:
    allowed_roles = set(roles)

    async def dependency(
        current_user: Annotated[CurrentUserContext, Depends(get_current_user)],
    ) -> CurrentUserContext:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency
