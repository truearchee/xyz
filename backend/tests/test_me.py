from datetime import UTC, datetime
from uuid import uuid4

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import AppUser, CourseMembership, CourseModule


async def _create_user(
    session: AsyncSession,
    *,
    email: str,
    role: str = "student",
    auth_provider_id: str | None = None,
    is_active: bool = True,
    full_name: str = "Test User",
    timezone: str = "UTC",
) -> AppUser:
    user = AppUser(
        auth_provider_id=auth_provider_id or f"provider-{uuid4()}",
        email=email,
        full_name=full_name,
        role=role,
        is_active=is_active,
        timezone=timezone,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_module(
    session: AsyncSession,
    *,
    owner_id,
    title: str = "Module",
    is_active: bool = True,
) -> CourseModule:
    module = CourseModule(
        title=title,
        description=None,
        owner_id=owner_id,
        timezone="UTC",
        starts_on=None,
        ends_on=None,
        is_active=is_active,
    )
    session.add(module)
    await session.flush()
    return module


async def _create_membership(
    session: AsyncSession,
    *,
    user_id,
    module_id,
    role: str,
    status: str = "active",
    archived_at: datetime | None = None,
) -> CourseMembership:
    membership = CourseMembership(
        user_id=user_id,
        module_id=module_id,
        role=role,
        status=status,
        archived_at=archived_at,
    )
    session.add(membership)
    await session.flush()
    return membership


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    token = jwt_factory(sub=user.auth_provider_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_me_returns_admin_without_module_memberships(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    admin = await _create_user(
        db_session,
        email="admin-me@example.com",
        role="admin",
        full_name="Admin User",
        timezone="Asia/Dubai",
    )
    owner = await _create_user(db_session, email="admin-owner@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=owner.id)
    await _create_membership(
        db_session,
        user_id=admin.id,
        module_id=module.id,
        role="lecturer",
    )

    response = await auth_client.get("/me", headers=_headers(admin, jwt_factory))

    assert response.status_code == 200
    assert response.json() == {
        "userId": str(admin.id),
        "email": "admin-me@example.com",
        "fullName": "Admin User",
        "role": "admin",
        "timezone": "Asia/Dubai",
        "preferredLanguage": "en",
        "activeModuleMemberships": [],
    }


@pytest.mark.anyio
async def test_me_returns_lecturer_active_membership(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="lecturer-me@example.com",
        role="lecturer",
        full_name="Lecturer User",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )

    response = await auth_client.get("/me", headers=_headers(lecturer, jwt_factory))

    assert response.status_code == 200
    assert response.json() == {
        "userId": str(lecturer.id),
        "email": "lecturer-me@example.com",
        "fullName": "Lecturer User",
        "role": "lecturer",
        "timezone": "UTC",
        "preferredLanguage": "en",
        "activeModuleMemberships": [
            {"moduleId": str(module.id), "role": "lecturer"},
        ],
    }


@pytest.mark.anyio
async def test_me_returns_student_active_membership(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    owner = await _create_user(db_session, email="student-owner@example.com", role="lecturer")
    student = await _create_user(
        db_session,
        email="student-me@example.com",
        role="student",
        full_name="Student User",
    )
    module = await _create_module(db_session, owner_id=owner.id)
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )

    response = await auth_client.get("/me", headers=_headers(student, jwt_factory))

    assert response.status_code == 200
    assert response.json() == {
        "userId": str(student.id),
        "email": "student-me@example.com",
        "fullName": "Student User",
        "role": "student",
        "timezone": "UTC",
        "preferredLanguage": "en",
        "activeModuleMemberships": [
            {"moduleId": str(module.id), "role": "student"},
        ],
    }


@pytest.mark.anyio
async def test_patch_me_preferences_updates_language(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    student = await _create_user(
        db_session, email="pref-student@example.com", role="student", full_name="Pref User"
    )
    headers = _headers(student, jwt_factory)

    before = await auth_client.get("/me", headers=headers)
    assert before.json()["preferredLanguage"] == "en"

    patched = await auth_client.patch(
        "/me/preferences", headers=headers, json={"preferredLanguage": "ar"}
    )
    assert patched.status_code == 200
    assert patched.json()["preferredLanguage"] == "ar"

    after = await auth_client.get("/me", headers=headers)
    assert after.json()["preferredLanguage"] == "ar"


@pytest.mark.anyio
async def test_me_excludes_archived_membership(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    owner = await _create_user(db_session, email="archived-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="archived-student@example.com")
    visible_module = await _create_module(db_session, owner_id=owner.id, title="Visible")
    archived_module = await _create_module(db_session, owner_id=owner.id, title="Archived")
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=visible_module.id,
        role="student",
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=archived_module.id,
        role="student",
        status="archived",
        archived_at=datetime.now(UTC),
    )

    response = await auth_client.get("/me", headers=_headers(student, jwt_factory))

    assert response.status_code == 200
    assert response.json()["activeModuleMemberships"] == [
        {"moduleId": str(visible_module.id), "role": "student"},
    ]


@pytest.mark.anyio
async def test_me_rejects_inactive_user_before_response(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    inactive = await _create_user(
        db_session,
        email="inactive-me@example.com",
        is_active=False,
    )

    response = await auth_client.get("/me", headers=_headers(inactive, jwt_factory))

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is inactive"
