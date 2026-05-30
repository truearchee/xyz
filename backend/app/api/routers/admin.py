from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.admin import service
from app.domains.admin.schemas import (
    AssignMemberRequest,
    CreateModuleRequest,
    CreateUserRequest,
    MembershipResponse,
    ModuleResponse,
    ResetPasswordRequest,
    StatusResponse,
    UserResponse,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.auth.guards import require_role
from app.platform.db.session import get_db_session


router = APIRouter(prefix="/admin", tags=["admin"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AdminUser = Annotated[CurrentUserContext, Depends(require_role("admin"))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: CreateUserRequest,
    db: DbSession,
    current_user: AdminUser,
):
    user = await service.create_user(db, payload)
    await db.commit()
    return user


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: DbSession,
    current_user: AdminUser,
    limit: Limit = 50,
    offset: Offset = 0,
):
    return await service.list_users(db, limit=limit, offset=offset)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: DbSession,
    current_user: AdminUser,
):
    return await service.get_user(db, user_id)


@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: UUID,
    db: DbSession,
    current_user: AdminUser,
):
    user = await service.deactivate_user(db, user_id, current_user)
    await db.commit()
    return user


@router.post("/users/{user_id}/reset-password", response_model=StatusResponse)
async def reset_password(
    user_id: UUID,
    payload: ResetPasswordRequest,
    db: DbSession,
    current_user: AdminUser,
):
    await service.reset_password(db, user_id, payload.new_password)
    await db.commit()
    return StatusResponse(status="ok")


@router.post(
    "/modules",
    response_model=ModuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_module(
    payload: CreateModuleRequest,
    db: DbSession,
    current_user: AdminUser,
):
    module = await service.create_module(db, payload, current_user)
    await db.commit()
    return module


@router.get("/modules", response_model=list[ModuleResponse])
async def list_modules(
    db: DbSession,
    current_user: AdminUser,
    limit: Limit = 50,
    offset: Offset = 0,
):
    return await service.list_modules(db, limit=limit, offset=offset)


@router.post(
    "/modules/{module_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_to_module(
    module_id: UUID,
    payload: AssignMemberRequest,
    db: DbSession,
    current_user: AdminUser,
):
    membership = await service.assign_to_module(db, module_id, payload, current_user)
    await db.commit()
    return membership


@router.delete("/modules/{module_id}/members/{user_id}", response_model=StatusResponse)
async def remove_from_module(
    module_id: UUID,
    user_id: UUID,
    db: DbSession,
    current_user: AdminUser,
):
    await service.remove_from_module(db, user_id, module_id, current_user)
    await db.commit()
    return StatusResponse(status="ok")
