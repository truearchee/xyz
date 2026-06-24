from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from httpx import AsyncClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.domains.admin import service as admin_service
from app.platform.db.models import AppUser, CourseMembership, CourseModule, ModuleSection


# Stage 5.5a reference schedule (test oracle): 11 May–26 Jun 2026, Mon/Tue/Wed=lecture, Thu=lab,
# Fri=quiz day (generates nothing) → 7 weeks, 21 lectures, 7 labs, 28 total, 0 Friday sections.
def _schedule_payload(
    *,
    course_start_date: str = "2026-05-11",
    course_end_date: str = "2026-06-26",
    week_start_day: str = "monday",
    session_pattern: list[dict[str, str]] | None = None,
    quiz_day: str | None = "friday",
) -> dict:
    if session_pattern is None:
        session_pattern = [
            {"weekday": "monday", "sectionType": "lecture"},
            {"weekday": "tuesday", "sectionType": "lecture"},
            {"weekday": "wednesday", "sectionType": "lecture"},
            {"weekday": "thursday", "sectionType": "lab"},
        ]
    payload: dict = {
        "courseStartDate": course_start_date,
        "courseEndDate": course_end_date,
        "weekStartDay": week_start_day,
        "sessionPattern": session_pattern,
    }
    if quiz_day is not None:
        payload["quizDay"] = quiz_day
    return payload


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


async def _create_section(
    session: AsyncSession,
    *,
    module_id,
    title: str,
    section_type: str,
    order_index: int,
    week_number: int | None = None,
    session_date: date | None = None,
    status: str = "active",
) -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title=title,
        type=section_type,
        order_index=order_index,
        week_number=week_number,
        session_date=session_date,
        publish_status="draft",
        status=status,
    )
    session.add(section)
    await session.flush()
    return section


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


async def _auth_headers(
    session: AsyncSession,
    jwt_factory,
    *,
    role: str = "admin",
    email: str | None = None,
) -> tuple[dict[str, str], AppUser]:
    user = await _create_user(
        session,
        email=email or f"{role}-{uuid4()}@example.com",
        role=role,
        auth_provider_id=f"{role}-provider-{uuid4()}",
    )
    token = jwt_factory(sub=user.auth_provider_id)
    return {"Authorization": f"Bearer {token}"}, user


def _admin_routes() -> list[tuple[str, str, dict | None]]:
    user_id = str(uuid4())
    module_id = str(uuid4())
    return [
        (
            "POST",
            "/admin/users",
            {
                "email": "new-user@example.com",
                "fullName": "New User",
                "role": "student",
                "password": "password123",
            },
        ),
        ("GET", "/admin/users?limit=1&offset=0", None),
        ("GET", f"/admin/users/{user_id}", None),
        ("POST", f"/admin/users/{user_id}/deactivate", None),
        (
            "POST",
            f"/admin/users/{user_id}/reset-password",
            {"newPassword": "newpassword123"},
        ),
        (
            "POST",
            "/admin/modules",
            {
                "title": "Intro",
                "ownerId": str(uuid4()),
                "timezone": "UTC",
                "schedule": _schedule_payload(),
            },
        ),
        ("GET", "/admin/modules?limit=1&offset=0", None),
        ("POST", "/admin/modules/preview-sections", _schedule_payload()),
        ("GET", f"/admin/modules/{module_id}/sections/by-week?includeUnstamped=true", None),
        (
            "POST",
            f"/admin/modules/{module_id}/members",
            {"userId": str(uuid4()), "role": "student"},
        ),
        ("GET", f"/admin/modules/{module_id}/members", None),
        ("DELETE", f"/admin/modules/{module_id}/members/{user_id}", None),
    ]


class MockSupabaseAdmin:
    def __init__(self) -> None:
        self.next_user_id: str | None = None
        self._counter = 0
        self.create_user = AsyncMock(side_effect=self._create_user)
        self.update_user_by_id = AsyncMock(return_value=SimpleNamespace(user=None))
        self.delete_user = AsyncMock(return_value=None)

    async def _create_user(self, payload: dict) -> SimpleNamespace:
        self._counter += 1
        user_id = self.next_user_id or f"supabase-user-{self._counter}"
        self.next_user_id = None
        return SimpleNamespace(user=SimpleNamespace(id=user_id))


@pytest.fixture
def mock_supabase_admin(monkeypatch: pytest.MonkeyPatch) -> MockSupabaseAdmin:
    admin = MockSupabaseAdmin()
    client = SimpleNamespace(auth=SimpleNamespace(admin=admin))

    async def get_client():
        return client

    monkeypatch.setattr(admin_service, "get_supabase_admin_client", get_client)
    return admin


@pytest.mark.anyio
async def test_no_token_on_any_admin_endpoint_returns_401(auth_client: AsyncClient) -> None:
    for method, path, body in _admin_routes():
        response = await auth_client.request(method, path, json=body)

        assert response.status_code == 401


@pytest.mark.anyio
async def test_student_token_on_admin_endpoints_returns_403(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="student")

    for method, path, body in _admin_routes():
        response = await auth_client.request(method, path, headers=headers, json=body)

        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"


@pytest.mark.anyio
async def test_lecturer_token_on_admin_endpoints_returns_403(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="lecturer")

    for method, path, body in _admin_routes():
        response = await auth_client.request(method, path, headers=headers, json=body)

        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"


@pytest.mark.anyio
async def test_admin_creates_student(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    mock_supabase_admin: MockSupabaseAdmin,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")

    response = await auth_client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "created-student@example.com",
            "fullName": "Created Student",
            "role": "student",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "created-student@example.com"
    assert data["fullName"] == "Created Student"
    assert data["role"] == "student"
    assert data["isActive"] is True
    assert "password" not in data
    assert "authProviderId" not in data
    user = await db_session.scalar(
        select(AppUser).where(AppUser.email == "created-student@example.com")
    )
    assert user is not None
    assert user.auth_provider_id == "supabase-user-1"
    mock_supabase_admin.create_user.assert_awaited_once()
    assert mock_supabase_admin.create_user.await_args.args[0]["email_confirm"] is True


@pytest.mark.anyio
async def test_admin_create_role_admin_returns_business_400(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    mock_supabase_admin: MockSupabaseAdmin,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")

    response = await auth_client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "new-admin@example.com",
            "fullName": "New Admin",
            "role": "admin",
            "password": "password123",
        },
    )

    assert response.status_code == 400
    mock_supabase_admin.create_user.assert_not_awaited()


@pytest.mark.anyio
async def test_admin_deactivates_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    user = await _create_user(db_session, email="deactivate-me@example.com")

    response = await auth_client.post(
        f"/admin/users/{user.id}/deactivate",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["isActive"] is False
    await db_session.refresh(user)
    assert user.is_active is False


@pytest.mark.anyio
async def test_admin_deactivate_self_returns_400(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, admin = await _auth_headers(db_session, jwt_factory, role="admin")

    response = await auth_client.post(
        f"/admin/users/{admin.id}/deactivate",
        headers=headers,
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_create_module_with_lecturer_owner(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(
        db_session,
        email="module-owner@example.com",
        role="lecturer",
    )

    response = await auth_client.post(
        "/admin/modules",
        headers=headers,
        json={
            "title": "Physics",
            "ownerId": str(lecturer.id),
            "timezone": "UTC",
            "schedule": _schedule_payload(),
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Physics"
    assert data["ownerId"] == str(lecturer.id)
    assert data["isActive"] is True
    assert data["weekStartDay"] == "monday"
    assert data["quizDay"] == "friday"
    assert data["sessionPattern"] == _schedule_payload()["sessionPattern"]


@pytest.mark.anyio
async def test_create_module_generates_schedule_sections(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    # End-to-end through the API: the reference schedule must yield the 28-section oracle with
    # correct week_number/session_date — no fixed 4-section template, no Friday section.
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(
        db_session,
        email="module-sections-owner@example.com",
        role="lecturer",
    )

    response = await auth_client.post(
        "/admin/modules",
        headers=headers,
        json={
            "title": "Generated Sections",
            "ownerId": str(lecturer.id),
            "schedule": _schedule_payload(),
        },
    )

    assert response.status_code == 201
    module_id = response.json()["id"]
    result = await db_session.execute(
        select(ModuleSection)
        .where(ModuleSection.course_module_id == UUID(module_id))
        .order_by(ModuleSection.order_index.asc())
    )
    sections = result.scalars().all()

    assert len(sections) == 28
    assert sum(1 for section in sections if section.type == "lecture") == 21
    assert sum(1 for section in sections if section.type == "lab") == 7
    assert all(section.type in ("lecture", "lab") for section in sections)
    assert max(section.week_number for section in sections) == 7
    # No Friday (weekday 4) section exists — the quiz day generates nothing.
    assert all(section.session_date.weekday() != 4 for section in sections)
    assert all(section.session_date is not None for section in sections)
    assert [section.order_index for section in sections] == list(range(1, 29))
    assert all(section.publish_status == "draft" for section in sections)
    assert all(section.lecturer_notes is None for section in sections)
    assert all(section.status == "active" for section in sections)


@pytest.mark.anyio
async def test_admin_preview_sections_uses_reference_generator(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")

    response = await auth_client.post(
        "/admin/modules/preview-sections",
        headers=headers,
        json=_schedule_payload(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["totalSections"] == 28
    assert data["weekCount"] == 7
    assert data["lectureCount"] == 21
    assert data["labCount"] == 7
    assert data["fridaySectionCount"] == 0
    assert len(data["sections"]) == 28
    assert data["sections"][0] == {
        "title": "Lecture — Week 1 (Mon 11 May)",
        "type": "lecture",
        "orderIndex": 1,
        "weekNumber": 1,
        "sessionDate": "2026-05-11",
    }
    assert data["sections"][-1] == {
        "title": "Lab — Week 7 (Thu 25 Jun)",
        "type": "lab",
        "orderIndex": 28,
        "weekNumber": 7,
        "sessionDate": "2026-06-25",
    }


@pytest.mark.anyio
async def test_admin_sections_by_week_uses_resolver_modes(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="admin-by-week-owner@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    week_one = await _create_section(
        db_session,
        module_id=module.id,
        title="Lecture week one",
        section_type="lecture",
        order_index=1,
        week_number=1,
        session_date=date(2026, 5, 11),
    )
    week_two = await _create_section(
        db_session,
        module_id=module.id,
        title="Lab week two",
        section_type="lab",
        order_index=2,
        week_number=2,
        session_date=date(2026, 5, 21),
    )
    unstamped = await _create_section(
        db_session,
        module_id=module.id,
        title="Needs curation",
        section_type="lecture",
        order_index=3,
    )
    assignment = await _create_section(
        db_session,
        module_id=module.id,
        title="Legacy assignment",
        section_type="assignment",
        order_index=4,
        week_number=1,
        session_date=date(2026, 5, 12),
    )

    week_response = await auth_client.get(
        f"/admin/modules/{module.id}/sections/by-week?coveredWeeks=1",
        headers=headers,
    )
    curation_response = await auth_client.get(
        f"/admin/modules/{module.id}/sections/by-week?includeUnstamped=true",
        headers=headers,
    )

    assert week_response.status_code == 200
    assert [row["id"] for row in week_response.json()] == [str(week_one.id)]
    assert curation_response.status_code == 200
    assert [row["id"] for row in curation_response.json()] == [
        str(week_one.id),
        str(week_two.id),
        str(unstamped.id),
    ]
    assert str(assignment.id) not in curation_response.text


@pytest.mark.anyio
async def test_create_module_without_schedule_returns_422(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    # No silent fallback: a creation request without a schedule is rejected (the fixed 4-section
    # template path is gone).
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(
        db_session,
        email="no-schedule-owner@example.com",
        role="lecturer",
    )

    response = await auth_client.post(
        "/admin/modules",
        headers=headers,
        json={"title": "No Schedule", "ownerId": str(lecturer.id)},
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_module_generation_failure_is_atomic(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    migrated_test_database: str,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # D14: generation runs inside the creation transaction. If it fails mid-way, NOTHING commits —
    # no partial module, no orphan sections. Verified from a SEPARATE connection (committed state only).
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="atomic-owner@example.com", role="lecturer")

    def _boom(*args, **kwargs):
        raise RuntimeError("forced generation failure")

    monkeypatch.setattr(admin_service, "generate_initial_sections", _boom)

    with pytest.raises(RuntimeError):
        await auth_client.post(
            "/admin/modules",
            headers=headers,
            json={"title": "Atomic Fail", "ownerId": str(lecturer.id), "schedule": _schedule_payload()},
        )

    engine = create_async_engine(migrated_test_database)
    try:
        async with engine.connect() as conn:
            modules = await conn.scalar(
                text("SELECT count(*) FROM course_modules WHERE title = 'Atomic Fail'")
            )
            orphan_sections = await conn.scalar(
                text(
                    "SELECT count(*) FROM module_sections s "
                    "JOIN course_modules m ON m.id = s.course_module_id "
                    "WHERE m.title = 'Atomic Fail'"
                )
            )
    finally:
        await engine.dispose()

    assert modules == 0
    assert orphan_sections == 0


@pytest.mark.anyio
async def test_repeated_create_module_does_not_accumulate_sections(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    # No double-generation: each creation generates exactly once. Two creations yield two independent
    # 28-section modules — never one module with doubled sections.
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="repeat-owner@example.com", role="lecturer")

    for index in range(2):
        response = await auth_client.post(
            "/admin/modules",
            headers=headers,
            json={
                "title": f"Repeat {index}",
                "ownerId": str(lecturer.id),
                "schedule": _schedule_payload(),
            },
        )
        assert response.status_code == 201
        module_id = UUID(response.json()["id"])
        section_count = await db_session.scalar(
            select(func.count())
            .select_from(ModuleSection)
            .where(ModuleSection.course_module_id == module_id)
        )
        assert section_count == 28


@pytest.mark.anyio
async def test_create_module_with_student_owner_returns_400(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    student = await _create_user(db_session, email="student-owner@example.com")

    response = await auth_client.post(
        "/admin/modules",
        headers=headers,
        json={
            "title": "Biology",
            "ownerId": str(student.id),
            "schedule": _schedule_payload(),
        },
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_create_module_creates_owner_membership(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(
        db_session,
        email="owner-membership@example.com",
        role="lecturer",
    )

    response = await auth_client.post(
        "/admin/modules",
        headers=headers,
        json={
            "title": "Chemistry",
            "ownerId": str(lecturer.id),
            "schedule": _schedule_payload(),
        },
    )

    assert response.status_code == 201
    module_id = response.json()["id"]
    membership = await db_session.scalar(
        select(CourseMembership).where(
            CourseMembership.user_id == lecturer.id,
            CourseMembership.module_id == module_id,
            CourseMembership.status == "active",
        )
    )
    assert membership is not None
    assert membership.role == "lecturer"


@pytest.mark.anyio
async def test_assign_student_to_module(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="assign-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="assign-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)

    response = await auth_client.post(
        f"/admin/modules/{module.id}/members",
        headers=headers,
        json={"userId": str(student.id), "role": "student"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["userId"] == str(student.id)
    assert data["moduleId"] == str(module.id)
    assert data["status"] == "active"


@pytest.mark.anyio
async def test_admin_lists_active_module_members_with_user_fields(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    owner = await _create_user(
        db_session,
        email="projection-owner@example.com",
        role="lecturer",
        full_name="Projection Owner",
    )
    student = await _create_user(
        db_session,
        email="projection-student@example.com",
        role="student",
        full_name="Projection Student",
    )
    module = await _create_module(db_session, owner_id=owner.id)
    membership = await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )

    response = await auth_client.get(
        f"/admin/modules/{module.id}/members",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "membershipId": str(membership.id),
            "userId": str(student.id),
            "moduleId": str(module.id),
            "email": "projection-student@example.com",
            "fullName": "Projection Student",
            "role": "student",
            "membershipStatus": "active",
            "userIsActive": True,
            "createdAt": membership.created_at.isoformat().replace("+00:00", "Z"),
        }
    ]


@pytest.mark.anyio
async def test_admin_list_module_members_unknown_module_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")

    response = await auth_client.get(
        f"/admin/modules/{uuid4()}/members",
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_admin_list_module_members_filters_archived_and_admin_members(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    owner = await _create_user(db_session, email="filter-owner@example.com", role="lecturer")
    active_student = await _create_user(db_session, email="filter-active@example.com")
    archived_student = await _create_user(db_session, email="filter-archived@example.com")
    admin_user = await _create_user(db_session, email="filter-admin@example.com", role="admin")
    module = await _create_module(db_session, owner_id=owner.id)
    await _create_membership(
        db_session,
        user_id=active_student.id,
        module_id=module.id,
        role="student",
    )
    await _create_membership(
        db_session,
        user_id=archived_student.id,
        module_id=module.id,
        role="student",
        status="archived",
    )
    await _create_membership(
        db_session,
        user_id=admin_user.id,
        module_id=module.id,
        role="lecturer",
    )

    response = await auth_client.get(
        f"/admin/modules/{module.id}/members",
        headers=headers,
    )

    assert response.status_code == 200
    emails = [member["email"] for member in response.json()]
    assert emails == ["filter-active@example.com"]


@pytest.mark.anyio
async def test_admin_list_module_members_includes_inactive_active_member(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    owner = await _create_user(db_session, email="inactive-owner@example.com", role="lecturer")
    inactive_student = await _create_user(
        db_session,
        email="inactive-active-member@example.com",
        is_active=False,
    )
    module = await _create_module(db_session, owner_id=owner.id)
    await _create_membership(
        db_session,
        user_id=inactive_student.id,
        module_id=module.id,
        role="student",
    )

    response = await auth_client.get(
        f"/admin/modules/{module.id}/members",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["email"] == "inactive-active-member@example.com"
    assert response.json()[0]["userIsActive"] is False


@pytest.mark.anyio
async def test_admin_list_module_members_sorts_by_role_then_email(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    owner = await _create_user(db_session, email="sort-owner@example.com", role="lecturer")
    student_b = await _create_user(db_session, email="z-student@example.com")
    lecturer_b = await _create_user(db_session, email="b-lecturer@example.com", role="lecturer")
    student_a = await _create_user(db_session, email="a-student@example.com")
    lecturer_a = await _create_user(db_session, email="a-lecturer@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=owner.id)
    for user, role in (
        (student_b, "student"),
        (lecturer_b, "lecturer"),
        (student_a, "student"),
        (lecturer_a, "lecturer"),
    ):
        await _create_membership(
            db_session,
            user_id=user.id,
            module_id=module.id,
            role=role,
        )

    response = await auth_client.get(
        f"/admin/modules/{module.id}/members",
        headers=headers,
    )

    assert response.status_code == 200
    assert [(member["role"], member["email"]) for member in response.json()] == [
        ("lecturer", "a-lecturer@example.com"),
        ("lecturer", "b-lecturer@example.com"),
        ("student", "a-student@example.com"),
        ("student", "z-student@example.com"),
    ]


@pytest.mark.anyio
async def test_duplicate_active_assignment_returns_409(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="dup-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="dup-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )

    response = await auth_client.post(
        f"/admin/modules/{module.id}/members",
        headers=headers,
        json={"userId": str(student.id), "role": "student"},
    )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_assign_admin_user_to_module_returns_400(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="admin-target-owner@example.com", role="lecturer")
    admin_user = await _create_user(db_session, email="admin-target@example.com", role="admin")
    module = await _create_module(db_session, owner_id=lecturer.id)

    response = await auth_client.post(
        f"/admin/modules/{module.id}/members",
        headers=headers,
        json={"userId": str(admin_user.id), "role": "lecturer"},
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_assign_student_as_lecturer_returns_400(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="student-mismatch-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="student-mismatch@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)

    response = await auth_client.post(
        f"/admin/modules/{module.id}/members",
        headers=headers,
        json={"userId": str(student.id), "role": "lecturer"},
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_assign_lecturer_as_student_returns_400(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    owner = await _create_user(db_session, email="lecturer-mismatch-owner@example.com", role="lecturer")
    lecturer = await _create_user(db_session, email="lecturer-mismatch@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=owner.id)

    response = await auth_client.post(
        f"/admin/modules/{module.id}/members",
        headers=headers,
        json={"userId": str(lecturer.id), "role": "student"},
    )

    assert response.status_code == 400


@pytest.mark.anyio
async def test_remove_member_archives_membership(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="remove-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="remove-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    membership = await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )

    response = await auth_client.delete(
        f"/admin/modules/{module.id}/members/{student.id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    await db_session.refresh(membership)
    assert membership.status == "archived"
    assert membership.archived_at is not None


@pytest.mark.anyio
async def test_reassign_after_removal_creates_new_active_membership(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="reassign-owner@example.com", role="lecturer")
    student = await _create_user(db_session, email="reassign-student@example.com")
    module = await _create_module(db_session, owner_id=lecturer.id)
    archived = await _create_membership(
        db_session,
        user_id=student.id,
        module_id=module.id,
        role="student",
    )
    await auth_client.delete(
        f"/admin/modules/{module.id}/members/{student.id}",
        headers=headers,
    )

    response = await auth_client.post(
        f"/admin/modules/{module.id}/members",
        headers=headers,
        json={"userId": str(student.id), "role": "student"},
    )

    assert response.status_code == 201
    await db_session.refresh(archived)
    assert archived.status == "archived"
    memberships = (
        await db_session.scalars(
            select(CourseMembership).where(
                CourseMembership.user_id == student.id,
                CourseMembership.module_id == module.id,
            )
        )
    ).all()
    assert len(memberships) == 2
    assert sum(1 for membership in memberships if membership.status == "active") == 1


@pytest.mark.anyio
async def test_create_user_existing_email_returns_409_without_supabase_call(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    mock_supabase_admin: MockSupabaseAdmin,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    await _create_user(db_session, email="existing@example.com")

    response = await auth_client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "existing@example.com",
            "fullName": "Existing",
            "role": "student",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    mock_supabase_admin.create_user.assert_not_awaited()


@pytest.mark.anyio
async def test_create_user_rolls_back_supabase_user_on_insert_failure(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    mock_supabase_admin: MockSupabaseAdmin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    mock_supabase_admin.next_user_id = "rollback-provider-id"

    async def fail_flush(session: AsyncSession) -> None:
        raise IntegrityError("insert app_users", {}, Exception("uq_app_users_email"))

    monkeypatch.setattr(admin_service, "_flush_new_user", fail_flush)

    response = await auth_client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "rollback@example.com",
            "fullName": "Rollback User",
            "role": "student",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    mock_supabase_admin.delete_user.assert_awaited_once_with("rollback-provider-id")


@pytest.mark.anyio
async def test_list_users_is_paginated_and_camel_case(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    for index in range(3):
        await _create_user(
            db_session,
            email=f"list-user-{index}@example.com",
            full_name=f"List User {index}",
        )

    response = await auth_client.get(
        "/admin/users?limit=2&offset=1",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert "fullName" in data[0]
    assert "isActive" in data[0]
    assert "full_name" not in data[0]


@pytest.mark.anyio
async def test_get_user_existing_returns_200(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    user = await _create_user(
        db_session,
        email="get-existing@example.com",
        full_name="Get Existing",
    )

    response = await auth_client.get(f"/admin/users/{user.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["fullName"] == "Get Existing"


@pytest.mark.anyio
async def test_get_user_missing_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")

    response = await auth_client.get(f"/admin/users/{uuid4()}", headers=headers)

    assert response.status_code == 404


@pytest.mark.anyio
async def test_reset_password_invokes_supabase_admin(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    mock_supabase_admin: MockSupabaseAdmin,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    user = await _create_user(
        db_session,
        email="reset@example.com",
        auth_provider_id="reset-provider-id",
    )

    response = await auth_client.post(
        f"/admin/users/{user.id}/reset-password",
        headers=headers,
        json={"newPassword": "newpassword123"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_supabase_admin.update_user_by_id.assert_awaited_once_with(
        "reset-provider-id",
        {"password": "newpassword123"},
    )


@pytest.mark.anyio
async def test_reset_password_missing_user_returns_404(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
    mock_supabase_admin: MockSupabaseAdmin,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")

    response = await auth_client.post(
        f"/admin/users/{uuid4()}/reset-password",
        headers=headers,
        json={"newPassword": "newpassword123"},
    )

    assert response.status_code == 404
    mock_supabase_admin.update_user_by_id.assert_not_awaited()


@pytest.mark.anyio
async def test_list_modules_is_paginated_and_camel_case(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    jwt_factory,
    mock_jwks_client,
) -> None:
    headers, _ = await _auth_headers(db_session, jwt_factory, role="admin")
    lecturer = await _create_user(db_session, email="list-mod-owner@example.com", role="lecturer")
    for index in range(3):
        await _create_module(db_session, owner_id=lecturer.id, title=f"Module {index}")

    response = await auth_client.get(
        "/admin/modules?limit=2&offset=1",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert "ownerId" in data[0]
    assert "isActive" in data[0]
    assert "owner_id" not in data[0]
