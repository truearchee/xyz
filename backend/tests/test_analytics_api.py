from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
import pytest
from sqlalchemy import delete, select

from app.domains.analytics.service import run_agent_run
from app.domains.progress.seed import seed_progress_dataset
from app.platform.db.models import AppUser, Recommendation, StudentTargetGradeGoal

pytestmark = pytest.mark.anyio


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


async def _user_by_email(db_session, email: str) -> AppUser:
    user = await db_session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


async def _noop_rate_limit(**_kwargs) -> None:
    return None


async def test_manual_trigger_is_admin_only_and_idempotent(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
):
    summary = await seed_progress_dataset(db_session, prefix="stage11-api-trigger", reset=True, cohort_size=6)
    admin = AppUser(
        auth_provider_id="stage11-admin",
        email="stage11-admin@example.test",
        full_name="Stage 11 Admin",
        role="admin",
        is_active=True,
        timezone="UTC",
    )
    db_session.add(admin)
    await db_session.commit()
    lecturer = await _user_by_email(db_session, "stage11-api-trigger-lecturer@example.test")

    enqueued: list[str] = []
    live_jobs: set[str] = set()
    rate_limit_keys: list[str] = []

    async def fake_rate_limit(**kwargs) -> None:
        rate_limit_keys.append(kwargs["key"])

    monkeypatch.setattr("app.domains.analytics.service.enforce_fixed_window_rate_limit", fake_rate_limit)

    def fake_enqueue_if_needed(run_id):
        if str(run_id) in live_jobs:
            return f"agent-run-{run_id}", False
        live_jobs.add(str(run_id))
        enqueued.append(str(run_id))
        return f"agent-run-{run_id}", True

    monkeypatch.setattr("app.api.routers.analytics.enqueue_run_agent_if_needed", fake_enqueue_if_needed)
    scheduled_for = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    payload = {
        "triggerType": "manual_admin",
        "scopeType": "module",
        "scopeId": str(summary.module_two_id),
        "scheduledFor": scheduled_for,
    }

    forbidden = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(lecturer, jwt_factory),
        json=payload,
    )
    assert forbidden.status_code == 403
    assert rate_limit_keys == []

    first = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(admin, jwt_factory),
        json=payload,
    )
    assert first.status_code == 202, first.text
    second = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(admin, jwt_factory),
        json=payload,
    )
    assert second.status_code == 202, second.text
    assert first.json()["id"] == second.json()["id"]
    assert len(enqueued) == 1
    assert rate_limit_keys == [f"agent-run:manual-trigger:{admin.id}", f"agent-run:manual-trigger:{admin.id}"]


async def test_manual_trigger_reenqueues_same_run_after_enqueue_failure(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
):
    summary = await seed_progress_dataset(db_session, prefix="stage11-api-requeue", reset=True, cohort_size=6)
    admin = AppUser(
        auth_provider_id="stage11-requeue-admin",
        email="stage11-requeue-admin@example.test",
        full_name="Stage 11 Requeue Admin",
        role="admin",
        is_active=True,
        timezone="UTC",
    )
    db_session.add(admin)
    await db_session.commit()
    monkeypatch.setattr("app.domains.analytics.service.enforce_fixed_window_rate_limit", _noop_rate_limit)
    attempts: list[str] = []

    def flaky_enqueue(run_id):
        attempts.append(str(run_id))
        if len(attempts) == 1:
            raise RuntimeError("redis unavailable")
        return f"agent-run-{run_id}", True

    monkeypatch.setattr("app.api.routers.analytics.enqueue_run_agent_if_needed", flaky_enqueue)
    payload = {
        "triggerType": "manual_admin",
        "scopeType": "module",
        "scopeId": str(summary.module_two_id),
        "scheduledFor": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
    }

    with pytest.raises(RuntimeError, match="redis unavailable"):
        await auth_client.post(
            "/admin/analytics/agent-runs",
            headers=_headers(admin, jwt_factory),
            json=payload,
        )

    retry = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(admin, jwt_factory),
        json=payload,
    )

    assert retry.status_code == 202, retry.text
    assert attempts == [retry.json()["id"], retry.json()["id"]]


async def test_manual_trigger_rate_limited_after_admin_auth(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
):
    admin = AppUser(
        auth_provider_id="stage11-rate-admin",
        email="stage11-rate-admin@example.test",
        full_name="Stage 11 Rate Admin",
        role="admin",
        is_active=True,
        timezone="UTC",
    )
    db_session.add(admin)
    await db_session.commit()

    async def deny_rate_limit(**_kwargs) -> None:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    monkeypatch.setattr("app.domains.analytics.service.enforce_fixed_window_rate_limit", deny_rate_limit)

    response = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(admin, jwt_factory),
        json={"triggerType": "manual_admin", "scopeType": "all"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"


async def test_roster_and_student_risk_surfaces_are_role_scoped(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
):
    summary = await seed_progress_dataset(db_session, prefix="stage11-api-risk", reset=True, cohort_size=6)
    lecturer = await _user_by_email(db_session, "stage11-api-risk-lecturer@example.test")
    student_d = await _user_by_email(db_session, summary.student_emails_by_key["d"])
    student_a = await _user_by_email(db_session, summary.student_emails_by_key["a"])

    roster = await auth_client.get(
        f"/lecturer/modules/{summary.module_two_id}/analytics/roster-risk",
        headers=_headers(lecturer, jwt_factory),
    )
    assert roster.status_code == 200, roster.text
    body = roster.json()
    assert body["needsSupportCount"] >= 1
    assert any(row["riskTier"] == "needs_support" for row in body["rows"])
    needs_support = next(row for row in body["rows"] if row["studentId"] == str(student_d.id))
    assert needs_support["riskLabel"] == "Needs support"
    assert needs_support["riskReasons"]
    for reason in needs_support["riskReasons"]:
        assert set(reason["metricKeys"]) == set(reason["supportingMetrics"])

    student = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/risk",
        headers=_headers(student_d, jwt_factory),
    )
    assert student.status_code == 200, student.text
    raw = student.text.lower()
    assert "other students" not in raw
    assert "behind the class" not in raw
    student_body = student.json()
    assert "riskTier" not in student_body
    assert student_body["riskReasons"]
    assert {"code", "studentText"} == set(student_body["riskReasons"][0])
    assert "lecturerText" not in raw
    assert "supportingMetrics" not in raw
    assert "severity" not in raw

    forbidden_roster = await auth_client.get(
        f"/lecturer/modules/{summary.module_two_id}/analytics/roster-risk",
        headers=_headers(student_d, jwt_factory),
    )
    assert forbidden_roster.status_code == 403
    missing_student_module = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/risk",
        headers=_headers(student_a, jwt_factory),
    )
    assert missing_student_module.status_code == 200


async def test_agent_run_can_be_polled_after_worker_execution(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
):
    summary = await seed_progress_dataset(db_session, prefix="stage11-api-poll", reset=True, cohort_size=6)
    admin = AppUser(
        auth_provider_id="stage11-poll-admin",
        email="stage11-poll-admin@example.test",
        full_name="Stage 11 Poll Admin",
        role="admin",
        is_active=True,
        timezone="UTC",
    )
    db_session.add(admin)
    await db_session.commit()
    monkeypatch.setattr("app.api.routers.analytics.enqueue_run_agent_if_needed", lambda run_id: None)
    monkeypatch.setattr("app.domains.analytics.service.enforce_fixed_window_rate_limit", _noop_rate_limit)
    scheduled_for = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()

    created = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(admin, jwt_factory),
        json={
            "triggerType": "manual_admin",
            "scopeType": "module",
            "scopeId": str(summary.module_two_id),
            "scheduledFor": scheduled_for,
        },
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]

    await run_agent_run(db_session, run_id=run_id)
    polled = await auth_client.get(
        f"/admin/analytics/agent-runs/{run_id}",
        headers=_headers(admin, jwt_factory),
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["status"] == "completed"
    assert polled.json()["snapshotCount"] == 6
    assert polled.json()["recommendationCount"] > 0


async def test_recommendation_endpoints_are_scoped_and_states_do_not_bleed(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
):
    summary = await seed_progress_dataset(db_session, prefix="stage11-api-rec", reset=True, cohort_size=6)
    lecturer = await _user_by_email(db_session, "stage11-api-rec-lecturer@example.test")
    student_d = await _user_by_email(db_session, summary.student_emails_by_key["d"])
    student_a = await _user_by_email(db_session, summary.student_emails_by_key["a"])
    admin = AppUser(
        auth_provider_id="stage11-api-rec-admin",
        email="stage11-api-rec-admin@example.test",
        full_name="Stage 11 Recommendation Admin",
        role="admin",
        is_active=True,
        timezone="UTC",
    )
    db_session.add(admin)
    await db_session.commit()
    monkeypatch.setattr("app.api.routers.analytics.enqueue_run_agent_if_needed", lambda run_id: None)
    monkeypatch.setattr("app.domains.analytics.service.enforce_fixed_window_rate_limit", _noop_rate_limit)
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.domains.analytics.service.enqueue_generate_recommendation_copy",
        lambda recommendation_id: enqueued.append(str(recommendation_id)) or f"recommendation-copy-{recommendation_id}",
    )

    created = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(admin, jwt_factory),
        json={
            "triggerType": "manual_admin",
            "scopeType": "module",
            "scopeId": str(summary.module_two_id),
            "scheduledFor": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        },
    )
    assert created.status_code == 202, created.text
    await run_agent_run(db_session, run_id=created.json()["id"])

    lecturer_detail = await auth_client.get(
        f"/lecturer/modules/{summary.module_two_id}/analytics/students/{student_d.id}/recommendations",
        headers=_headers(lecturer, jwt_factory),
    )
    assert lecturer_detail.status_code == 200, lecturer_detail.text
    detail = lecturer_detail.json()
    assert detail["recommendations"]
    recommendation_id = detail["recommendations"][0]["id"]
    assert detail["recommendations"][0]["lecturerDraftSource"] == "template"
    assert detail["recommendations"][0]["studentNudgeText"]
    assert detail["recommendations"][0]["aiStatus"] == "queued"
    assert enqueued == [recommendation_id]
    assert "send" not in lecturer_detail.text.lower()

    forbidden_detail = await auth_client.get(
        f"/lecturer/modules/{summary.module_two_id}/analytics/students/{student_d.id}/recommendations",
        headers=_headers(student_d, jwt_factory),
    )
    assert forbidden_detail.status_code == 403

    student_nudge = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/recommendations",
        headers=_headers(student_d, jwt_factory),
    )
    assert student_nudge.status_code == 200, student_nudge.text
    nudge_body = student_nudge.json()
    assert len(nudge_body["recommendations"]) == 1
    assert "riskTier" not in student_nudge.text
    assert "other students" not in student_nudge.text.lower()

    lecturer_dismiss = await auth_client.post(
        f"/lecturer/recommendations/{recommendation_id}/dismiss",
        headers=_headers(lecturer, jwt_factory),
    )
    assert lecturer_dismiss.status_code == 200, lecturer_dismiss.text
    assert lecturer_dismiss.json()["lecturerState"] == "dismissed"

    still_student_visible = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/recommendations",
        headers=_headers(student_d, jwt_factory),
    )
    assert still_student_visible.status_code == 200, still_student_visible.text
    assert still_student_visible.json()["recommendations"]

    student_dismiss = await auth_client.post(
        f"/student/recommendations/{recommendation_id}/dismiss",
        headers=_headers(student_d, jwt_factory),
    )
    assert student_dismiss.status_code == 200, student_dismiss.text
    assert student_dismiss.json()["studentState"] == "dismissed"

    not_other_student = await auth_client.post(
        f"/student/recommendations/{recommendation_id}/dismiss",
        headers=_headers(student_a, jwt_factory),
    )
    assert not_other_student.status_code == 404


async def test_recommendation_visibility_revalidates_current_risk_on_read(
    auth_client,
    db_session,
    jwt_factory,
    mock_jwks_client,
    monkeypatch: pytest.MonkeyPatch,
):
    summary = await seed_progress_dataset(db_session, prefix="stage11-api-rec-live", reset=True, cohort_size=6)
    student_d = await _user_by_email(db_session, summary.student_emails_by_key["d"])
    admin = AppUser(
        auth_provider_id="stage11-api-rec-live-admin",
        email="stage11-api-rec-live-admin@example.test",
        full_name="Stage 11 Recommendation Live Admin",
        role="admin",
        is_active=True,
        timezone="UTC",
    )
    db_session.add(admin)
    await db_session.commit()
    monkeypatch.setattr("app.api.routers.analytics.enqueue_run_agent_if_needed", lambda run_id: None)
    monkeypatch.setattr("app.domains.analytics.service.enforce_fixed_window_rate_limit", _noop_rate_limit)

    created = await auth_client.post(
        "/admin/analytics/agent-runs",
        headers=_headers(admin, jwt_factory),
        json={
            "triggerType": "manual_admin",
            "scopeType": "module",
            "scopeId": str(summary.module_two_id),
            "scheduledFor": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        },
    )
    assert created.status_code == 202, created.text
    await run_agent_run(db_session, run_id=created.json()["id"])
    before = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/recommendations",
        headers=_headers(student_d, jwt_factory),
    )
    assert before.status_code == 200, before.text
    assert before.json()["recommendations"]

    await db_session.execute(
        delete(StudentTargetGradeGoal).where(
            StudentTargetGradeGoal.student_id == student_d.id,
            StudentTargetGradeGoal.module_id == summary.module_two_id,
        )
    )
    await db_session.commit()

    after = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/recommendations",
        headers=_headers(student_d, jwt_factory),
    )
    assert after.status_code == 200, after.text
    assert after.json()["recommendations"] == []
    persisted = await db_session.scalar(
        select(Recommendation).where(
            Recommendation.student_id == student_d.id,
            Recommendation.module_id == summary.module_two_id,
        )
    )
    assert persisted is not None
    assert persisted.status == "active"
