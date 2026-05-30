from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext, ModuleAccessContext
from app.platform.auth.dependencies import get_current_user
from app.platform.auth.guards import require_module_access
from app.platform.db.session import get_db_session
from app.platform.query.modules import get_module_detail_row, list_active_modules_for_user


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class ModuleSummary(CamelModel):
    id: UUID
    title: str
    is_active: bool
    global_role: str


class ModuleDetail(CamelModel):
    id: UUID
    title: str
    is_active: bool
    global_role: str
    can_publish: bool
    created_at: datetime


router = APIRouter(tags=["modules"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[CurrentUserContext, Depends(get_current_user)]
ModuleAccess = Annotated[ModuleAccessContext, Depends(require_module_access)]


@router.get("/modules", response_model=list[ModuleSummary])
async def list_modules(
    db: DbSession,
    current_user: CurrentUser,
) -> list[ModuleSummary]:
    modules = await list_active_modules_for_user(db, current_user.user_id)
    return [
        ModuleSummary(
            id=module.module_id,
            title=module.title,
            is_active=module.is_active,
            global_role=current_user.role,
        )
        for module in modules
    ]


@router.get("/modules/{module_id}", response_model=ModuleDetail)
async def get_module(
    module_id: UUID,
    db: DbSession,
    module_access: ModuleAccess,
) -> ModuleDetail:
    module = await get_module_detail_row(db, module_id)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    return ModuleDetail(
        id=module.module_id,
        title=module.title,
        is_active=module_access.is_active,
        global_role=module_access.global_role,
        can_publish=module_access.can_publish,
        created_at=module.created_at,
    )
