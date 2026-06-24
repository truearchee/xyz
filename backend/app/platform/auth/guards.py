from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext, ModuleAccessContext
from app.platform.auth.dependencies import get_current_user
from app.platform.db.session import get_db_session
from app.platform.query.modules import get_active_module_access


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


async def require_module_access(
    module_id: UUID,
    current_user: Annotated[CurrentUserContext, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ModuleAccessContext:
    access = await get_active_module_access(db, current_user.user_id, module_id)
    if access is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Publish capability is membership-derived (Stage 12a): it mirrors the content-service
    # enforcement gate (`_get_assigned_lecturer_section`), which requires BOTH the global
    # lecturer role AND an active `lecturer` membership in this module. Deriving it from the
    # global role alone (the prior behaviour) over-reported `canPublish` for a lecturer who
    # holds only a non-lecturer membership here. `get_active_module_access` already filters to
    # an active membership, so we only need the membership role.
    can_publish = (
        current_user.role == "lecturer" and access.membership_role == "lecturer"
    )
    return ModuleAccessContext(
        module_id=access.module_id,
        is_active=access.is_active,
        global_role=current_user.role,
        can_publish=can_publish,
        membership_id=access.membership_id,
    )
