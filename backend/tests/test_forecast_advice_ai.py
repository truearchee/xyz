"""Stage 11.6 grade-forecast advice — DB-backed tests.

AI job (succeeded + template fallback), read-model equality (single forecast path / no drift), endpoint
authz (403 non-student, 404 not-enrolled), two-student isolation, and single-enqueue under repeat reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.analytics import forecast_advice
from app.domains.analytics.forecast_advice_ai import generate_forecast_advice_async
from app.domains.analytics.service import _forecast_result
from app.domains.progress.forecast import ForecastResult
from app.domains.progress.seed import seed_progress_dataset
from app.domains.progress.service import _build_module_detail
from app.platform.db.models import AppUser, StudentForecastAdvice
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider

pytestmark = pytest.mark.anyio


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


def _impossible_forecast() -> ForecastResult:
    return ForecastResult(
        state="impossible",
        target_letter_grade="A",
        target_points=Decimal("90"),
        earned_so_far=Decimal("33"),
        remaining_weight=Decimal("0.2"),
        min_reachable=Decimal("33"),
        max_reachable=Decimal("53"),
        current_letter_grade="F",
        best_reachable_letter_grade="D",
        required_remaining_average=Decimal("285"),  # > 100, never cited
    )


async def _insert_row(
    db_session: AsyncSession,
    *,
    student_id,
    module_id,
    forecast: ForecastResult,
    module_title: str = "Forecast Module",
) -> StudentForecastAdvice:
    payload = forecast_advice.build_deterministic_payload(forecast, module_title=module_title)
    row = StudentForecastAdvice(
        student_id=student_id,
        module_id=module_id,
        algorithm_version=forecast_advice.ALGORITHM_VERSION,
        input_hash=forecast_advice.forecast_advice_input_hash(payload),
        source_cutoff_at=datetime.now(UTC),
        forecast_state=forecast.state,
        deterministic_payload=payload,
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def _run_job(advice_id, database_url: str, *, provider: DeterministicTestProvider | None = None) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    gateway = LLMGateway(provider=provider, session_factory=factory) if provider else None
    try:
        await generate_forecast_advice_async(advice_id, gateway=gateway, session_factory=factory)
    finally:
        await engine.dispose()


async def test_advice_ai_persists_valid_text_and_provenance(db_session, migrated_test_database):
    summary = await seed_progress_dataset(db_session, prefix="stage11-adv-ai", reset=True, cohort_size=6)
    student_id = summary.student_ids_by_key["d"]
    row = await _insert_row(
        db_session, student_id=student_id, module_id=summary.module_two_id, forecast=_impossible_forecast()
    )
    row_id = row.id
    template = row.deterministic_payload["templateAdvice"]

    await _run_job(row_id, migrated_test_database, provider=DeterministicTestProvider())

    db_session.expire_all()
    refreshed = await db_session.get(StudentForecastAdvice, row_id)
    assert refreshed is not None
    assert refreshed.ai_status == "succeeded"
    # The deterministic provider echoes the validator-safe template, proving the full AI render path
    # (gateway → schema validate → numeric/contradiction/safety validators → persist) end to end.
    assert refreshed.ai_text == template
    assert refreshed.ai_model_id
    assert refreshed.ai_prompt_version == "v1"
    assert refreshed.ai_input_hash == refreshed.input_hash
    assert refreshed.ai_generated_at is not None


async def test_advice_ai_invalid_output_falls_back_to_template(db_session, migrated_test_database):
    summary = await seed_progress_dataset(db_session, prefix="stage11-adv-fault", reset=True, cohort_size=6)
    student_id = summary.student_ids_by_key["d"]
    row = await _insert_row(
        db_session, student_id=student_id, module_id=summary.module_two_id, forecast=_impossible_forecast()
    )
    row_id = row.id

    await _run_job(row_id, migrated_test_database, provider=DeterministicTestProvider(fault="invalid_output"))

    db_session.expire_all()
    refreshed = await db_session.get(StudentForecastAdvice, row_id)
    assert refreshed is not None
    assert refreshed.ai_status == "template_fallback"
    assert refreshed.ai_text is None
    # Hash recorded so a subsequent view does not re-attempt this exact forecast (rule-15).
    assert refreshed.ai_input_hash == refreshed.input_hash


async def test_forecast_read_models_agree_no_drift(db_session, migrated_test_database):
    summary = await seed_progress_dataset(db_session, prefix="stage11-adv-eq", reset=True, cohort_size=6)
    for key in ("c", "d"):
        student_id = summary.student_ids_by_key[key]
        analytics_forecast = await _forecast_result(
            db_session, student_id=student_id, module_id=summary.module_two_id
        )
        detail = await _build_module_detail(
            db_session, student_id=student_id, module_id=summary.module_two_id
        )
        assert analytics_forecast is not None
        assert detail.forecast is not None
        assert analytics_forecast.state == detail.forecast.state
        assert analytics_forecast.required_remaining_average == detail.forecast.required_remaining_average
        assert analytics_forecast.target_letter_grade == detail.forecast.target_letter_grade
        assert analytics_forecast.best_reachable_letter_grade == detail.forecast.best_reachable_letter_grade
        assert analytics_forecast.earned_so_far == detail.forecast.earned_so_far


async def test_forecast_advice_requires_student_role(auth_client, db_session, jwt_factory, mock_jwks_client):
    summary = await seed_progress_dataset(db_session, prefix="stage11-adv-403", reset=True, cohort_size=6)
    lecturer = await db_session.scalar(
        select(AppUser).where(AppUser.email == "stage11-adv-403-lecturer@example.test")
    )
    resp = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/forecast-advice",
        headers=_headers(lecturer, jwt_factory),
    )
    assert resp.status_code == 403


async def test_forecast_advice_not_enrolled_is_404(auth_client, db_session, jwt_factory, mock_jwks_client):
    summary = await seed_progress_dataset(db_session, prefix="stage11-adv-404", reset=True, cohort_size=6)
    outsider = AppUser(
        auth_provider_id="stage11-adv-404-outsider",
        email="stage11-adv-404-outsider@example.test",
        full_name="Outsider Student",
        role="student",
        is_active=True,
        timezone="UTC",
    )
    db_session.add(outsider)
    await db_session.commit()
    resp = await auth_client.get(
        f"/student/modules/{summary.module_two_id}/forecast-advice",
        headers=_headers(outsider, jwt_factory),
    )
    assert resp.status_code == 404


async def test_forecast_advice_two_students_isolated(
    auth_client, db_session, jwt_factory, mock_jwks_client, monkeypatch
):
    enqueued: list[object] = []
    monkeypatch.setattr(
        "app.domains.analytics.service.enqueue_generate_forecast_advice",
        lambda advice_id: enqueued.append(advice_id),
    )
    summary = await seed_progress_dataset(db_session, prefix="stage11-adv-iso", reset=True, cohort_size=6)
    student_c = await db_session.scalar(
        select(AppUser).where(AppUser.email == summary.student_emails_by_key["c"])
    )
    student_d = await db_session.scalar(
        select(AppUser).where(AppUser.email == summary.student_emails_by_key["d"])
    )
    url = f"/student/modules/{summary.module_two_id}/forecast-advice"

    resp_c = await auth_client.get(url, headers=_headers(student_c, jwt_factory))
    resp_d = await auth_client.get(url, headers=_headers(student_d, jwt_factory))
    assert resp_c.status_code == 200, resp_c.text
    assert resp_d.status_code == 200, resp_d.text
    body_c, body_d = resp_c.json(), resp_d.json()
    # Each student sees only their own forecast — no bleed.
    assert body_c["forecastState"] == "requires_high_score"
    assert body_d["forecastState"] == "impossible"
    assert body_c["text"] != body_d["text"]
    assert body_d["moduleId"] == str(summary.module_two_id)


async def test_forecast_advice_enqueues_once_for_repeated_reads(
    auth_client, db_session, jwt_factory, mock_jwks_client, monkeypatch
):
    enqueued: list[object] = []
    monkeypatch.setattr(
        "app.domains.analytics.service.enqueue_generate_forecast_advice",
        lambda advice_id: enqueued.append(advice_id),
    )
    summary = await seed_progress_dataset(db_session, prefix="stage11-adv-once", reset=True, cohort_size=6)
    student_d = await db_session.scalar(
        select(AppUser).where(AppUser.email == summary.student_emails_by_key["d"])
    )
    headers = _headers(student_d, jwt_factory)
    url = f"/student/modules/{summary.module_two_id}/forecast-advice"

    r1 = await auth_client.get(url, headers=headers)
    r2 = await auth_client.get(url, headers=headers)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    # Template renders immediately; the second read sees ai_status=queued and does not re-enqueue.
    assert r1.json()["source"] == "template"
    assert len(enqueued) == 1
