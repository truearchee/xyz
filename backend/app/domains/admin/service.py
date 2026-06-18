from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.admin.schemas import (
    AssignMemberRequest,
    CreateModuleRequest,
    CreateUserRequest,
    ModuleMemberResponse,
    ModuleScheduleInput,
    ModuleSchedulePreviewResponse,
    ModuleSectionPreview,
)
from app.domains.admin.section_generation import generate_initial_sections, generate_sections
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import AppUser, CourseMembership, CourseModule
from app.platform.supabase_client import get_supabase_admin_client


logger = logging.getLogger(__name__)


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _supabase_error(exc: Exception) -> HTTPException:
    message = str(exc) or "Supabase Admin API error"
    status_code = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    code = str(getattr(exc, "code", "")).lower()
    lower_message = message.lower()

    if status_code == status.HTTP_409_CONFLICT:
        return _http_error(status.HTTP_409_CONFLICT, message)
    if "duplicate" in lower_message or "already" in lower_message or code == "conflict":
        return _http_error(status.HTTP_409_CONFLICT, message)
    return _http_error(status.HTTP_400_BAD_REQUEST, message)


def _extract_supabase_user_id(response: Any) -> str:
    candidate = getattr(response, "user", None) or getattr(response, "data", None)
    if isinstance(candidate, dict):
        value = candidate.get("id")
    else:
        value = getattr(candidate, "id", None)

    if not value:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "Supabase user id missing from create_user response",
        )
    return str(value)


async def _flush_new_user(db: AsyncSession) -> None:
    await db.flush()


async def _delete_supabase_user(supabase_user_id: str) -> None:
    supabase = await get_supabase_admin_client()
    try:
        await supabase.auth.admin.delete_user(supabase_user_id)
    except Exception:
        logger.exception(
            "Failed to roll back Supabase user after local user insert failure",
            extra={"supabase_user_id": supabase_user_id},
        )
    else:
        logger.info(
            "Rolled back Supabase user after local user insert failure",
            extra={"supabase_user_id": supabase_user_id},
        )


async def create_user(db: AsyncSession, payload: CreateUserRequest) -> AppUser:
    if payload.role == "admin":
        raise _http_error(status.HTTP_400_BAD_REQUEST, "Admin users cannot be created")

    existing_user = await db.scalar(
        select(AppUser).where(AppUser.email == str(payload.email))
    )
    if existing_user is not None:
        raise _http_error(status.HTTP_409_CONFLICT, "Email already exists")

    supabase = await get_supabase_admin_client()
    try:
        response = await supabase.auth.admin.create_user(
            {
                "email": str(payload.email),
                "password": payload.password,
                "email_confirm": True,
            }
        )
    except Exception as exc:
        raise _supabase_error(exc) from exc

    supabase_user_id = _extract_supabase_user_id(response)
    user = AppUser(
        auth_provider_id=supabase_user_id,
        email=str(payload.email),
        full_name=payload.full_name,
        role=payload.role,
        timezone=payload.timezone,
        is_active=True,
    )
    db.add(user)

    try:
        await _flush_new_user(db)
    except IntegrityError as exc:
        await db.rollback()
        await _delete_supabase_user(supabase_user_id)
        if "uq_app_users_email" in str(exc):
            raise _http_error(status.HTTP_409_CONFLICT, "Email already exists") from exc
        raise _http_error(status.HTTP_400_BAD_REQUEST, "Could not create user") from exc
    except Exception:
        await db.rollback()
        await _delete_supabase_user(supabase_user_id)
        raise

    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, user_id: UUID) -> AppUser:
    user = await db.get(AppUser, user_id)
    if user is None:
        raise _http_error(status.HTTP_404_NOT_FOUND, "User not found")
    return user


async def deactivate_user(
    db: AsyncSession,
    user_id: UUID,
    current_user: CurrentUserContext,
) -> AppUser:
    if user_id == current_user.user_id:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "Admins cannot deactivate themselves",
        )

    user = await get_user(db, user_id)
    user.is_active = False
    user.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(user)
    return user


async def reset_password(
    db: AsyncSession,
    user_id: UUID,
    new_password: str,
) -> None:
    user = await get_user(db, user_id)
    supabase = await get_supabase_admin_client()
    try:
        await supabase.auth.admin.update_user_by_id(
            user.auth_provider_id,
            {"password": new_password},
        )
    except Exception as exc:
        raise _supabase_error(exc) from exc


async def create_module(
    db: AsyncSession,
    payload: CreateModuleRequest,
    current_user: CurrentUserContext,
) -> CourseModule:
    owner = await db.get(AppUser, payload.owner_id)
    if owner is None or owner.role != "lecturer":
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "Module owner must be a lecturer",
        )

    schedule = payload.schedule
    module = CourseModule(
        title=payload.title,
        description=payload.description,
        owner_id=payload.owner_id,
        timezone=payload.timezone,
        starts_on=schedule.course_start_date,
        ends_on=schedule.course_end_date,
        week_start_day=schedule.week_start_day,
        session_pattern=[
            {"weekday": entry.weekday, "sectionType": entry.section_type}
            for entry in schedule.session_pattern
        ],
        quiz_day=schedule.quiz_day,
        is_active=True,
    )
    db.add(module)
    await db.flush()
    generate_initial_sections(db, module=module)

    active_membership = await db.scalar(
        select(CourseMembership).where(
            CourseMembership.user_id == payload.owner_id,
            CourseMembership.module_id == module.id,
            CourseMembership.status == "active",
        )
    )
    if active_membership is None:
        db.add(
            CourseMembership(
                user_id=payload.owner_id,
                module_id=module.id,
                role="lecturer",
                status="active",
            )
        )

    await db.flush()
    await db.refresh(module)
    return module


def preview_module_schedule(schedule: ModuleScheduleInput) -> ModuleSchedulePreviewResponse:
    drafts = generate_sections(
        start=schedule.course_start_date,
        end=schedule.course_end_date,
        week_start_day=schedule.week_start_day,
        session_pattern=[
            {"weekday": entry.weekday, "sectionType": entry.section_type}
            for entry in schedule.session_pattern
        ],
    )
    weeks = {draft.week_number for draft in drafts}
    return ModuleSchedulePreviewResponse(
        total_sections=len(drafts),
        week_count=len(weeks),
        lecture_count=sum(1 for draft in drafts if draft.type == "lecture"),
        lab_count=sum(1 for draft in drafts if draft.type == "lab"),
        friday_section_count=sum(1 for draft in drafts if draft.session_date.weekday() == 4),
        sections=[
            ModuleSectionPreview(
                title=draft.title,
                type=draft.type,
                order_index=draft.order_index,
                week_number=draft.week_number,
                session_date=draft.session_date,
            )
            for draft in drafts
        ],
    )


async def get_module(db: AsyncSession, module_id: UUID) -> CourseModule:
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise _http_error(status.HTTP_404_NOT_FOUND, "Module not found")
    return module


async def assign_to_module(
    db: AsyncSession,
    module_id: UUID,
    payload: AssignMemberRequest,
    current_user: CurrentUserContext,
) -> CourseMembership:
    user = await db.get(AppUser, payload.user_id)
    module = await db.get(CourseModule, module_id)
    if user is None or module is None:
        raise _http_error(status.HTTP_404_NOT_FOUND, "User or module not found")

    if user.role == "admin":
        raise _http_error(status.HTTP_400_BAD_REQUEST, "Admin users cannot be members")
    if payload.role != user.role:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "Membership role must match user's global role",
        )

    active_membership = await db.scalar(
        select(CourseMembership).where(
            CourseMembership.user_id == payload.user_id,
            CourseMembership.module_id == module_id,
            CourseMembership.status == "active",
        )
    )
    if active_membership is not None:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "User already has an active membership",
        )

    membership = CourseMembership(
        user_id=payload.user_id,
        module_id=module_id,
        role=payload.role,
        status="active",
    )
    db.add(membership)
    await db.flush()
    await db.refresh(membership)
    return membership


async def remove_from_module(
    db: AsyncSession,
    user_id: UUID,
    module_id: UUID,
    current_user: CurrentUserContext,
) -> None:
    membership = await db.scalar(
        select(CourseMembership).where(
            CourseMembership.user_id == user_id,
            CourseMembership.module_id == module_id,
            CourseMembership.status == "active",
        )
    )
    if membership is None:
        raise _http_error(status.HTTP_404_NOT_FOUND, "Active membership not found")

    now = datetime.now(UTC)
    membership.status = "archived"
    membership.archived_at = now
    membership.updated_at = now
    await db.flush()


async def list_module_members(
    db: AsyncSession,
    module_id: UUID,
) -> list[ModuleMemberResponse]:
    await get_module(db, module_id)

    result = await db.execute(
        select(CourseMembership, AppUser)
        .join(AppUser, CourseMembership.user_id == AppUser.id)
        .where(
            CourseMembership.module_id == module_id,
            CourseMembership.status == "active",
            AppUser.role.in_(("lecturer", "student")),
        )
        .order_by(CourseMembership.role.asc(), AppUser.email.asc())
    )

    return [
        ModuleMemberResponse(
            membership_id=membership.id,
            user_id=user.id,
            module_id=membership.module_id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            membership_status=membership.status,
            user_is_active=user.is_active,
            created_at=membership.created_at,
        )
        for membership, user in result.all()
    ]


async def list_users(
    db: AsyncSession,
    limit: int,
    offset: int,
) -> list[AppUser]:
    result = await db.scalars(
        select(AppUser).order_by(AppUser.created_at, AppUser.id).limit(limit).offset(offset)
    )
    return list(result.all())


async def list_modules(
    db: AsyncSession,
    limit: int,
    offset: int,
) -> list[CourseModule]:
    result = await db.scalars(
        select(CourseModule)
        # Newest-first so a just-created module appears at the top of page 1.
        # With ascending order, new modules fell off page 1 once enough modules
        # accumulated (default limit=50), so admins stopped seeing them.
        .order_by(CourseModule.created_at.desc(), CourseModule.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all())
