from dataclasses import FrozenInstanceError, is_dataclass
from datetime import timedelta

from fastapi import HTTPException
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.context import CurrentUserContext, ModuleMembership
from app.platform.auth.dependencies import get_current_user
from app.platform.auth.jwt import decode_and_verify_jwt
from app.platform.db.models import AppUser, CourseMembership, CourseModule


async def _create_user(
    session: AsyncSession,
    *,
    auth_provider_id: str,
    email: str,
    role: str = "student",
    is_active: bool = True,
    full_name: str = "Test User",
) -> AppUser:
    user = AppUser(
        auth_provider_id=auth_provider_id,
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
    title: str,
) -> CourseModule:
    module = CourseModule(
        title=title,
        description=None,
        owner_id=owner_id,
        timezone="UTC",
        starts_on=None,
        ends_on=None,
        is_active=True,
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
) -> CourseMembership:
    membership = CourseMembership(
        user_id=user_id,
        module_id=module_id,
        role=role,
        status=status,
    )
    session.add(membership)
    await session.flush()
    return membership


def _assert_credential_error(exc: HTTPException) -> None:
    assert exc.status_code == 401
    assert exc.detail == "Invalid authentication credentials"
    assert exc.headers == {"WWW-Authenticate": "Bearer"}


def test_valid_jwt_decodes_correctly(jwt_factory, mock_jwks_client) -> None:
    token = jwt_factory(sub="supabase-user-1")

    claims = decode_and_verify_jwt(token)

    assert claims["sub"] == "supabase-user-1"
    assert "exp" in claims


def test_expired_jwt_raises_401(jwt_factory, mock_jwks_client) -> None:
    token = jwt_factory(expires_delta=timedelta(minutes=-1))

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_jwt(token)

    _assert_credential_error(exc_info.value)


def test_invalid_signature_raises_401(
    jwt_factory,
    mock_jwks_client,
    wrong_jwks_private_key,
) -> None:
    token = jwt_factory(private_key=wrong_jwks_private_key)

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_jwt(token)

    _assert_credential_error(exc_info.value)


def test_wrong_audience_raises_401(jwt_factory, mock_jwks_client) -> None:
    token = jwt_factory(audience="wrong")

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_jwt(token)

    _assert_credential_error(exc_info.value)


def test_wrong_issuer_raises_401(jwt_factory, mock_jwks_client) -> None:
    token = jwt_factory(issuer="https://evil.example.com")

    with pytest.raises(HTTPException) as exc_info:
        decode_and_verify_jwt(token)

    _assert_credential_error(exc_info.value)


@pytest.mark.anyio
async def test_missing_authorization_header_returns_401(auth_client) -> None:
    response = await auth_client.get("/health/authed")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authorization header required"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_malformed_authorization_header_returns_401(auth_client) -> None:
    for value in ("Basic xxx", "Bearer", "Bearer ", "Bearer a b c"):
        response = await auth_client.get(
            "/health/authed",
            headers={"Authorization": value},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid authentication credentials"}
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_valid_token_for_active_user_returns_200(
    auth_client,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    user = await _create_user(
        db_session,
        auth_provider_id="active-provider-id",
        email="active@example.com",
        role="lecturer",
    )
    token = jwt_factory(sub=user.auth_provider_id)

    response = await auth_client.get(
        "/health/authed",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "user_id": str(user.id),
        "role": "lecturer",
        "email": "active@example.com",
    }


@pytest.mark.anyio
async def test_valid_token_for_inactive_user_returns_403(
    auth_client,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    user = await _create_user(
        db_session,
        auth_provider_id="inactive-provider-id",
        email="inactive@example.com",
        is_active=False,
    )
    token = jwt_factory(sub=user.auth_provider_id)

    response = await auth_client.get(
        "/health/authed",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Account is inactive"}


@pytest.mark.anyio
async def test_valid_token_for_unknown_user_returns_401(
    auth_client,
    jwt_factory,
    mock_jwks_client,
) -> None:
    token = jwt_factory(sub="unknown-provider-id")

    response = await auth_client.get(
        "/health/authed",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_jwt_role_is_ignored_and_app_role_wins(
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    user = await _create_user(
        db_session,
        auth_provider_id="role-provider-id",
        email="role@example.com",
        role="student",
    )
    token = jwt_factory(sub=user.auth_provider_id, role="admin")

    context = await get_current_user(
        db_session=db_session,
        authorization=f"Bearer {token}",
    )

    assert context.role == "student"


@pytest.mark.anyio
async def test_current_user_context_includes_active_memberships_only(
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    user = await _create_user(
        db_session,
        auth_provider_id="membership-provider-id",
        email="membership@example.com",
    )
    owner = await _create_user(
        db_session,
        auth_provider_id="membership-owner-provider-id",
        email="membership-owner@example.com",
        role="lecturer",
    )
    active_a = await _create_module(db_session, owner_id=owner.id, title="Active A")
    active_b = await _create_module(db_session, owner_id=owner.id, title="Active B")
    archived = await _create_module(db_session, owner_id=owner.id, title="Archived")
    await _create_membership(
        db_session,
        user_id=user.id,
        module_id=active_a.id,
        role="student",
    )
    await _create_membership(
        db_session,
        user_id=user.id,
        module_id=active_b.id,
        role="student",
    )
    await _create_membership(
        db_session,
        user_id=user.id,
        module_id=archived.id,
        role="student",
        status="archived",
    )
    token = jwt_factory(sub=user.auth_provider_id)

    context = await get_current_user(
        db_session=db_session,
        authorization=f"Bearer {token}",
    )

    assert {membership.module_id for membership in context.module_memberships} == {
        active_a.id,
        active_b.id,
    }


@pytest.mark.anyio
async def test_membership_owner_publish_flags_and_context_are_frozen(
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    lecturer = await _create_user(
        db_session,
        auth_provider_id="lecturer-provider-id",
        email="lecturer@example.com",
        role="lecturer",
    )
    other_owner = await _create_user(
        db_session,
        auth_provider_id="other-owner-provider-id",
        email="other-owner@example.com",
        role="lecturer",
    )
    student = await _create_user(
        db_session,
        auth_provider_id="student-provider-id",
        email="student@example.com",
        role="student",
    )
    owned_module = await _create_module(db_session, owner_id=lecturer.id, title="Owned")
    other_module = await _create_module(
        db_session,
        owner_id=other_owner.id,
        title="Not Owned",
    )
    student_module = await _create_module(
        db_session,
        owner_id=other_owner.id,
        title="Student",
    )
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=owned_module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=other_module.id,
        role="lecturer",
    )
    await _create_membership(
        db_session,
        user_id=lecturer.id,
        module_id=student_module.id,
        role="student",
    )
    token = jwt_factory(sub=lecturer.auth_provider_id)

    context = await get_current_user(
        db_session=db_session,
        authorization=f"Bearer {token}",
    )
    memberships = {
        membership.module_id: membership for membership in context.module_memberships
    }

    assert memberships[owned_module.id].is_owner is True
    assert memberships[owned_module.id].can_publish is True
    assert memberships[other_module.id].is_owner is False
    assert memberships[other_module.id].can_publish is True
    assert memberships[student_module.id].is_owner is False
    assert memberships[student_module.id].can_publish is False
    assert is_dataclass(CurrentUserContext)
    assert is_dataclass(ModuleMembership)
    with pytest.raises(FrozenInstanceError):
        context.role = "admin"
    with pytest.raises(FrozenInstanceError):
        memberships[owned_module.id].can_publish = False
