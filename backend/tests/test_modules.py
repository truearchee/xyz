from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.guards import require_module_access
from app.platform.db.models import AppUser, CourseMembership, CourseModule


async def _create_user(
    session: AsyncSession,
    *,
    email: str,
    role: str = "student",
    auth_provider_id: str | None = None,
    is_active: bool = True,
    full_name: str = "Test User",
) -> AppUser:
    user = AppUser(
        auth_provider_id=auth_provider_id or f"provider-{uuid4()}",
        email=email,
        full_name=full_name,
        role=role,
        is_active=is_active,
        timezone="UTC",
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


def _context(user: AppUser) -> CurrentUserContext:
    return CurrentUserContext(
        user_id=user.id,
        auth_provider_id=user.auth_provider_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        timezone=user.timezone,
    )


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    token = jwt_factory(sub=user.auth_provider_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_require_module_access_returns_context_for_active_access(
    db_session: AsyncSession,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="guard-owner@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=lecturer.id)
    membership = await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )

    access = await require_module_access(
        module_id=module.id,
        current_user=_context(lecturer),
        db=db_session,
    )

    assert access.module_id == module.id
    assert access.membership_id == membership.id
    assert access.is_active is True
    assert access.global_role == "lecturer"
    assert access.can_publish is True


@pytest.mark.anyio
async def test_require_module_access_hides_missing_archived_and_inactive_access(
    db_session: AsyncSession,
) -> None:
    owner = await _create_user(db_session, email="hidden-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="hidden-student@example.com")
    unassigned = await _create_module(db_session, owner_id=owner.id, title="Unassigned")
    archived_module = await _create_module(db_session, owner_id=owner.id, title="Archived Membership")
    inactive_module = await _create_module(
        db_session,
        owner_id=owner.id,
        title="Inactive",
        is_active=False,
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=archived_module.id,
        role="student",
        status="archived",
        archived_at=datetime.now(UTC),
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=inactive_module.id,
        role="student",
    )

    for module_id in (unassigned.id, archived_module.id, inactive_module.id):
        with pytest.raises(HTTPException) as exc_info:
            await require_module_access(
                module_id=module_id,
                current_user=_context(student),
                db=db_session,
            )
        assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_list_modules_returns_only_active_assigned_modules_for_participants(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    owner = await _create_user(db_session, email="list-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="list-student@example.com")
    lecturer = await _create_user(db_session, email="list-lecturer@example.com", role="lecturer")
    visible_student = await _create_module(db_session, owner_id=owner.id, title="Visible Student")
    visible_lecturer = await _create_module(db_session, owner_id=owner.id, title="Visible Lecturer")
    archived_membership = await _create_module(db_session, owner_id=owner.id, title="Archived Membership")
    inactive_module = await _create_module(
        db_session,
        owner_id=owner.id,
        title="Inactive Module",
        is_active=False,
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=visible_student.id,
        role="student",
    )
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=visible_lecturer.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=archived_membership.id,
        role="student",
        status="archived",
        archived_at=datetime.now(UTC),
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=inactive_module.id,
        role="student",
    )

    student_response = await auth_client.get(
        "/modules",
        headers=_headers(student, jwt_factory),
    )
    lecturer_response = await auth_client.get(
        "/modules",
        headers=_headers(lecturer, jwt_factory),
    )

    assert student_response.status_code == 200
    assert student_response.json() == [
        {
            "id": str(visible_student.id),
            "title": "Visible Student",
            "isActive": True,
            "globalRole": "student",
        }
    ]
    assert lecturer_response.status_code == 200
    assert lecturer_response.json() == [
        {
            "id": str(visible_lecturer.id),
            "title": "Visible Lecturer",
            "isActive": True,
            "globalRole": "lecturer",
        }
    ]


@pytest.mark.anyio
async def test_admin_list_is_empty_and_detail_is_hidden(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    admin = await _create_user(db_session, email="modules-admin@example.com", role="admin")
    owner = await _create_user(db_session, email="modules-admin-owner@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=owner.id, title="Admin Hidden")

    list_response = await auth_client.get("/modules", headers=_headers(admin, jwt_factory))
    detail_response = await auth_client.get(
        f"/modules/{module.id}",
        headers=_headers(admin, jwt_factory),
    )

    assert list_response.status_code == 200
    assert list_response.json() == []
    assert detail_response.status_code == 404


@pytest.mark.anyio
async def test_student_detail_and_can_publish_false(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    owner = await _create_user(db_session, email="detail-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="detail-student@example.com")
    assigned = await _create_module(db_session, owner_id=owner.id, title="Assigned")
    unassigned = await _create_module(db_session, owner_id=owner.id, title="Unassigned")
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=assigned.id,
        role="student",
    )

    assigned_response = await auth_client.get(
        f"/modules/{assigned.id}",
        headers=_headers(student, jwt_factory),
    )
    unassigned_response = await auth_client.get(
        f"/modules/{unassigned.id}",
        headers=_headers(student, jwt_factory),
    )

    assert assigned_response.status_code == 200
    data = assigned_response.json()
    assert data["id"] == str(assigned.id)
    assert data["title"] == "Assigned"
    assert data["isActive"] is True
    assert data["globalRole"] == "student"
    assert data["canPublish"] is False
    assert "createdAt" in data
    assert unassigned_response.status_code == 404


@pytest.mark.anyio
async def test_co_lecturer_detail_can_publish_true(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    owner = await _create_user(db_session, email="co-owner@example.com", role="lecturer")
    co_lecturer = await _create_user(
        db_session,
        email="co-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=owner.id, title="Shared")
    await _create_membership(
        db_session,
        user_id=owner.id,
        module_id=module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=co_lecturer.id,
        module_id=module.id,
        role="lecturer",
    )

    response = await auth_client.get(
        f"/modules/{module.id}",
        headers=_headers(co_lecturer, jwt_factory),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(module.id)
    assert data["globalRole"] == "lecturer"
    assert data["canPublish"] is True


@pytest.mark.anyio
async def test_lecturer_with_student_membership_can_publish_false(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    # Stage 12a display-alignment: a global-role lecturer who holds only a *student*
    # membership in this module cannot publish here — the content-service gate
    # (`_get_assigned_lecturer_section`) requires an active `lecturer` membership.
    # `canPublish` must mirror that; the prior global-role derivation wrongly reported `true`.
    owner = await _create_user(db_session, email="align-owner@example.com", role="lecturer")
    visiting_lecturer = await _create_user(
        db_session,
        email="align-visiting-lecturer@example.com",
        role="lecturer",
    )
    module = await _create_module(db_session, owner_id=owner.id, title="Visited")
    await _create_membership(
        db_session,
        user_id=visiting_lecturer.id,
        module_id=module.id,
        role="student",
    )

    response = await auth_client.get(
        f"/modules/{module.id}",
        headers=_headers(visiting_lecturer, jwt_factory),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["globalRole"] == "lecturer"
    assert data["canPublish"] is False


@pytest.mark.anyio
async def test_historical_reassignment_resolves_active_membership(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    owner = await _create_user(db_session, email="history-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="history-student@example.com")
    module = await _create_module(db_session, owner_id=owner.id, title="History")
    archived = await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
        status="archived",
        archived_at=datetime.now(UTC),
    )
    active = await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )

    access = await require_module_access(
        module_id=module.id,
        current_user=_context(student),
        db=db_session,
    )
    response = await auth_client.get(
        f"/modules/{module.id}",
        headers=_headers(student, jwt_factory),
    )

    assert archived.id != active.id
    assert access.membership_id == active.id
    assert response.status_code == 200
    assert response.json()["id"] == str(module.id)


@pytest.mark.anyio
async def test_revocation_without_token_refresh(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    admin = await _create_user(db_session, email="revoke-admin@example.com", role="admin")
    owner = await _create_user(db_session, email="revoke-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="revoke-student@example.com")
    module = await _create_module(db_session, owner_id=owner.id, title="Revoked")
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    student_headers = _headers(student, jwt_factory)

    before_detail = await auth_client.get(f"/modules/{module.id}", headers=student_headers)
    before_list = await auth_client.get("/modules", headers=student_headers)
    delete_response = await auth_client.delete(
        f"/admin/modules/{module.id}/members/{student.id}",
        headers=_headers(admin, jwt_factory),
    )
    after_detail = await auth_client.get(f"/modules/{module.id}", headers=student_headers)
    after_list = await auth_client.get("/modules", headers=student_headers)

    assert before_detail.status_code == 200
    assert before_list.status_code == 200
    assert [module["id"] for module in before_list.json()] == [str(module.id)]
    assert delete_response.status_code == 200
    assert after_detail.status_code == 404
    assert after_list.status_code == 200
    assert after_list.json() == []


@pytest.mark.anyio
async def test_inactive_module_is_absent_from_list_and_detail(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    owner = await _create_user(db_session, email="inactive-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="inactive-student@example.com")
    module = await _create_module(
        db_session,
        owner_id=owner.id,
        title="Inactive",
        is_active=False,
    )
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    headers = _headers(student, jwt_factory)

    list_response = await auth_client.get("/modules", headers=headers)
    detail_response = await auth_client.get(f"/modules/{module.id}", headers=headers)

    assert list_response.status_code == 200
    assert list_response.json() == []
    assert detail_response.status_code == 404


@pytest.mark.anyio
async def test_unauthenticated_module_routes_return_401(auth_client: AsyncClient) -> None:
    module_id = uuid4()

    list_response = await auth_client.get("/modules")
    detail_response = await auth_client.get(f"/modules/{module_id}")

    assert list_response.status_code == 401
    assert detail_response.status_code == 401


@pytest.mark.anyio
async def test_malformed_and_nonexistent_module_ids(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    student = await _create_user(db_session, email="missing-student@example.com")

    malformed = await auth_client.get(
        "/modules/not-a-uuid",
        headers=_headers(student, jwt_factory),
    )
    missing = await auth_client.get(
        f"/modules/{uuid4()}",
        headers=_headers(student, jwt_factory),
    )

    assert malformed.status_code == 422
    assert missing.status_code == 404
