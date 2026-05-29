from typing import Annotated

from fastapi import APIRouter, Depends

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.dependencies import get_current_user

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "xyz-lms-backend"}


@router.get("/health/authed")
async def authed_health(
    current_user: Annotated[CurrentUserContext, Depends(get_current_user)],
) -> dict[str, str]:
    return {
        "status": "ok",
        "user_id": str(current_user.user_id),
        "role": current_user.role,
        "email": current_user.email,
    }
