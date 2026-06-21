"""Stage 10c — GET /student/gamification HTTP surface: student-only (403 otherwise), response shape,
no-store, and an end-to-end award through the real auth path (no student_id param to spoof)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    ModuleSection,
    StudentActivityEvent,
)
from app.platform.events import COMPLETED_QUIZ

pytestmark = pytest.mark.anyio

_SHAPE_KEYS = (
    "currentStreak",
    "longestStreak",
    "todayIsScheduled",
    "todaySatisfied",
    "nextScheduledDay",
    "streakStatus",
    "earnedBadges",
    "lockedBadges",
    "progressItems",
    "newBadgeIds",
    "lastSeenAt",
)


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


async def _make_user(db, *, role: str) -> AppUser:
    user = AppUser(
        auth_provider_id=f"{role}-{uuid4().hex[:8]}",
        email=f"{role}-{uuid4().hex[:8]}@example.test",
        full_name="User",
        role=role,
        is_active=True,
        timezone="UTC",
    )
    db.add(user)
    await db.commit()
    return user


async def test_lecturer_forbidden(auth_client, db_session, jwt_factory, mock_jwks_client):
    lecturer = await _make_user(db_session, role="lecturer")
    response = await auth_client.get("/student/gamification", headers=_headers(lecturer, jwt_factory))
    assert response.status_code == 403


async def test_admin_forbidden(auth_client, db_session, jwt_factory, mock_jwks_client):
    admin = await _make_user(db_session, role="admin")
    response = await auth_client.get("/student/gamification", headers=_headers(admin, jwt_factory))
    assert response.status_code == 403


async def test_student_ok_shape_and_no_store(auth_client, db_session, jwt_factory, mock_jwks_client):
    student = await _make_user(db_session, role="student")
    response = await auth_client.get("/student/gamification", headers=_headers(student, jwt_factory))
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "private, no-store"
    body = response.json()
    for key in _SHAPE_KEYS:
        assert key in body, f"missing {key}"
    assert isinstance(body["earnedBadges"], list)
    assert isinstance(body["lockedBadges"], list)


async def test_student_response_includes_next_scheduled_day(
    auth_client, db_session, jwt_factory, mock_jwks_client
):
    student = await _make_user(db_session, role="student")
    owner = await _make_user(db_session, role="lecturer")
    today = datetime.now(UTC).date()
    next_day = today + timedelta(days=2)
    module = CourseModule(
        title="M", description="d", owner_id=owner.id, timezone="UTC", is_active=True
    )
    db_session.add(module)
    await db_session.flush()
    db_session.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    db_session.add(
        ModuleSection(
            course_module_id=module.id,
            title="Future",
            type="lecture",
            order_index=1,
            week_number=1,
            session_date=next_day,
            publish_status="draft",
            status="active",
        )
    )
    await db_session.commit()

    response = await auth_client.get("/student/gamification", headers=_headers(student, jwt_factory))
    assert response.status_code == 200
    assert response.json()["nextScheduledDay"] == next_day.isoformat()


async def test_student_award_through_event_path(auth_client, db_session, jwt_factory, mock_jwks_client):
    student = await _make_user(db_session, role="student")
    owner = await _make_user(db_session, role="lecturer")
    today = datetime.now(UTC).date()
    module = CourseModule(
        title="M", description="d", owner_id=owner.id, timezone="UTC", is_active=True
    )
    db_session.add(module)
    await db_session.flush()
    db_session.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    db_session.add(
        ModuleSection(
            course_module_id=module.id,
            title="S",
            type="lecture",
            order_index=1,
            week_number=1,
            session_date=today,
            publish_status="published",
            status="active",
        )
    )
    db_session.add(
        StudentActivityEvent(
            student_id=student.id,
            module_id=module.id,
            event_type=COMPLETED_QUIZ,
            source_id=uuid4(),
            occurred_at=datetime.now(UTC),
            metadata_json={"quizMode": "post_class", "quizDefinitionId": str(uuid4())},
        )
    )
    await db_session.commit()

    response = await auth_client.get("/student/gamification", headers=_headers(student, jwt_factory))
    assert response.status_code == 200
    body = response.json()
    assert body["currentStreak"] == 1
    assert body["streakStatus"] == "active"
    earned = {badge["badgeKey"] for badge in body["earnedBadges"]}
    assert "first_quiz" in earned
    assert "first_quiz" in body["newBadgeIds"]
