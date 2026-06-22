from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.analytics.recommendation_ai import generate_recommendation_copy_async
from app.domains.analytics.service import get_or_create_agent_run, run_agent_run
from app.domains.progress.seed import seed_progress_dataset
from app.platform.db.models import Recommendation
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider

pytestmark = pytest.mark.anyio


async def _seed_recommendation(db_session) -> Recommendation:
    summary = await seed_progress_dataset(db_session, prefix="stage11-rec-ai", reset=True, cohort_size=6)
    run, _ = await get_or_create_agent_run(
        db_session,
        trigger_type="manual_admin",
        scope_type="module",
        scope_id=summary.module_two_id,
        scheduled_for=datetime.now(UTC) + timedelta(seconds=1),
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    await db_session.commit()
    await run_agent_run(db_session, run_id=run.id)
    row = (
        await db_session.scalars(
            select(Recommendation).where(
                Recommendation.module_id == summary.module_two_id,
                Recommendation.status == "active",
            )
        )
    ).first()
    assert row is not None
    return row


async def _run_generation(
    recommendation_id,
    database_url: str,
    *,
    provider: DeterministicTestProvider | None = None,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    gateway = LLMGateway(provider=provider, session_factory=factory) if provider else None
    try:
        await generate_recommendation_copy_async(
            recommendation_id,
            gateway=gateway,
            session_factory=factory,
        )
    finally:
        await engine.dispose()


async def test_recommendation_ai_persists_valid_copy_and_provenance(
    db_session,
    migrated_test_database,
):
    row = await _seed_recommendation(db_session)
    row_id = row.id

    await _run_generation(
        row_id,
        migrated_test_database,
        provider=DeterministicTestProvider(),
    )

    db_session.expire_all()
    refreshed = await db_session.get(Recommendation, row_id)
    assert refreshed is not None
    assert refreshed.ai_status == "succeeded"
    assert refreshed.lecturer_ai_text
    assert refreshed.student_ai_text
    assert refreshed.lecturer_ai_text == refreshed.deterministic_payload["lecturerTemplate"]
    assert refreshed.student_ai_text == refreshed.deterministic_payload["studentTemplate"]
    assert refreshed.ai_model_id
    assert refreshed.ai_prompt_version == "v1"
    assert refreshed.ai_input_hash == refreshed.input_hash
    assert refreshed.ai_generated_at is not None


async def test_recommendation_ai_invalid_output_falls_back_to_template(
    db_session,
    migrated_test_database,
):
    row = await _seed_recommendation(db_session)
    row_id = row.id

    await _run_generation(
        row_id,
        migrated_test_database,
        provider=DeterministicTestProvider(fault="invalid_output"),
    )

    db_session.expire_all()
    refreshed = await db_session.get(Recommendation, row_id)
    assert refreshed is not None
    assert refreshed.ai_status == "template_fallback"
    assert refreshed.lecturer_ai_text is None
    assert refreshed.student_ai_text is None
