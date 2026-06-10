"""Summary pipeline — job creation, handler success/failure contract, projection, migration 0008."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.transcripts.summary_service import (
    generate_brief_summary_async,
    generate_detailed_summary_async,
    insert_summary_jobs,
)
from app.platform.db.models import (
    AIRequestLog,
    GeneratedLectureSummary,
    IngestionJob,
)
from app.platform.llm.errors import ProviderTransient
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider
from app.platform.query.transcript_status import (
    TranscriptProcessingStepRead,
    _failed_step,
    _overall_state,
    _safe_failure_message,
)
from tests.test_llm_gateway import _FakeLimiter
from tests.test_transcript_worker import _create_parsed_transcript, _session_factory

TEXTS = ["Introduction to the topic.", "A key idea is explained here.", "A worked example follows."]


def _gateway(factory, *, fault: str | None = None) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(fault=fault),
        limiter=_FakeLimiter(),
        session_factory=factory,
    )


async def _make_summary_jobs(db_session: AsyncSession, factory):
    transcript, _ = await _create_parsed_transcript(db_session, texts=TEXTS)
    async with factory() as session:
        async with session.begin():
            jobs = await insert_summary_jobs(session, transcript=transcript)
    return transcript, dict(jobs)


# --- job creation -----------------------------------------------------------

@pytest.mark.anyio
async def test_insert_summary_jobs_creates_two_queued_jobs_idempotently(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    assert set(jobs) == {"generate_brief_summary", "generate_detailed_summary"}

    # Idempotent: a second call returns the same job ids and does not duplicate.
    async with factory() as session:
        async with session.begin():
            again = dict(await insert_summary_jobs(session, transcript=transcript))
    assert again == jobs

    async with factory() as session:
        count = (
            await session.execute(
                select(IngestionJob).where(
                    IngestionJob.transcript_id == transcript.id,
                    IngestionJob.job_type.in_(
                        ("generate_brief_summary", "generate_detailed_summary")
                    ),
                )
            )
        ).scalars().all()
    assert len(count) == 2


# --- handler success contract ----------------------------------------------

@pytest.mark.anyio
async def test_brief_handler_stores_artifact_with_full_provenance(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    brief_id = jobs["generate_brief_summary"]

    await generate_brief_summary_async(brief_id, gateway=_gateway(factory), session_factory=factory)

    async with factory() as session:
        job = await session.get(IngestionJob, brief_id)
        assert job.status == "completed"
        summary = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id,
                    GeneratedLectureSummary.summary_type == "brief",
                )
            )
        ).scalar_one()
        assert summary.ai_request_log_id is not None
        assert summary.backend_used == "cerebras"
        assert summary.source_transcript_checksum == transcript.checksum
        assert len(summary.prompt_content_hash) == 64
        assert len(summary.input_hash) == 64
        assert "text" in summary.content_json
        log = await session.get(AIRequestLog, summary.ai_request_log_id)
        assert log.status == "succeeded"
        # provenance on the artifact matches the log row exactly
        assert summary.prompt_content_hash == log.prompt_content_hash


@pytest.mark.anyio
async def test_detailed_handler_stores_structured_summary(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    detailed_id = jobs["generate_detailed_summary"]

    await generate_detailed_summary_async(
        detailed_id, gateway=_gateway(factory), session_factory=factory
    )

    async with factory() as session:
        job = await session.get(IngestionJob, detailed_id)
        assert job.status == "completed"
        summary = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id,
                    GeneratedLectureSummary.summary_type == "detailed_study",
                )
            )
        ).scalar_one()
        assert summary.backend_used == "nvidia"
        assert "overview" in summary.content_json
        assert "keyConcepts" in summary.content_json


@pytest.mark.anyio
async def test_brief_handler_is_idempotent_on_completed_job(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    brief_id = jobs["generate_brief_summary"]

    await generate_brief_summary_async(brief_id, gateway=_gateway(factory), session_factory=factory)
    # second run no-ops because the job is already completed
    await generate_brief_summary_async(brief_id, gateway=_gateway(factory), session_factory=factory)

    async with factory() as session:
        summaries = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id,
                    GeneratedLectureSummary.summary_type == "brief",
                )
            )
        ).scalars().all()
    assert len(summaries) == 1


# --- handler failure contract (§11) ----------------------------------------

@pytest.mark.anyio
async def test_invalid_input_is_non_retryable_and_writes_no_artifact(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    brief_id = jobs["generate_brief_summary"]

    # Non-retryable: the handler swallows it (no RQ retry) and records the category.
    await generate_brief_summary_async(
        brief_id, gateway=_gateway(factory, fault="invalid_input"), session_factory=factory
    )

    async with factory() as session:
        job = await session.get(IngestionJob, brief_id)
        assert job.status == "failed"
        assert job.failure_category == "invalid_input"
        summaries = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id
                )
            )
        ).scalars().all()
        assert summaries == []
        log = (
            await session.execute(
                select(AIRequestLog).where(AIRequestLog.ingestion_job_id == brief_id)
            )
        ).scalar_one()
        assert log.status == "invalid_input"


@pytest.mark.anyio
async def test_provider_transient_raises_for_rq_retry_and_marks_failed(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    brief_id = jobs["generate_brief_summary"]

    with pytest.raises(ProviderTransient):
        await generate_brief_summary_async(
            brief_id, gateway=_gateway(factory, fault="provider_transient"), session_factory=factory
        )

    async with factory() as session:
        job = await session.get(IngestionJob, brief_id)
        assert job.status == "failed"
        assert job.failure_category == "provider_transient"
        summaries = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id
                )
            )
        ).scalars().all()
        assert summaries == []


# --- projection (pure) ------------------------------------------------------

def _step(status: str) -> TranscriptProcessingStepRead:
    return TranscriptProcessingStepRead(status=status, started_at=None, completed_at=None)


def _steps(**overrides: str) -> dict[str, TranscriptProcessingStepRead]:
    base = {
        key: _step("not_started")
        for key in ("upload", "parse", "chunk", "embed", "summary_brief", "summary_detailed")
    }
    base["upload"] = _step("completed")
    for key, status in overrides.items():
        base[key] = _step(status)
    return base


def _embedded_steps(**overrides: str) -> dict[str, TranscriptProcessingStepRead]:
    return _steps(parse="completed", chunk="completed", embed="completed", **overrides)


def test_overall_state_summarized_when_both_summaries_complete():
    state = _overall_state(
        transcript=SimpleNamespace(status="completed"),
        steps=_embedded_steps(summary_brief="completed", summary_detailed="completed"),
        segment_count=3,
        chunk_count=1,
        embedded_chunk_count=1,
    )
    assert state == "summarized"


def test_overall_state_summarizing_while_a_summary_runs():
    state = _overall_state(
        transcript=SimpleNamespace(status="completed"),
        steps=_embedded_steps(summary_brief="completed", summary_detailed="running"),
        segment_count=3,
        chunk_count=1,
        embedded_chunk_count=1,
    )
    assert state == "summarizing"


def test_overall_state_embedded_when_no_summary_jobs_yet():
    state = _overall_state(
        transcript=SimpleNamespace(status="completed"),
        steps=_embedded_steps(),
        segment_count=3,
        chunk_count=1,
        embedded_chunk_count=1,
    )
    assert state == "embedded"


def test_overall_state_failed_is_representable_per_step():
    state = _overall_state(
        transcript=SimpleNamespace(status="completed"),
        steps=_embedded_steps(summary_brief="completed", summary_detailed="failed"),
        segment_count=3,
        chunk_count=1,
        embedded_chunk_count=1,
    )
    assert state == "failed"


def test_summary_failure_message_uses_category_copy():
    jobs = {"summary_detailed": SimpleNamespace(status="failed", failure_category="invalid_input")}
    failed = _failed_step(transcript=SimpleNamespace(status="completed"), jobs=jobs)
    assert failed == "summary_detailed"
    message = _safe_failure_message(failed_step=failed, jobs=jobs)
    assert "too long" in message


# --- migration 0008 ---------------------------------------------------------

@pytest.mark.anyio
async def test_migration_0008_objects_exist(db_session: AsyncSession):
    tables = (
        await db_session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' "
                "AND table_name IN ('ai_request_logs','generated_lecture_summaries')"
            )
        )
    ).scalars().all()
    assert set(tables) == {"ai_request_logs", "generated_lecture_summaries"}

    column = (
        await db_session.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='ingestion_jobs' AND column_name='failure_category'"
            )
        )
    ).scalar()
    assert column == 1

    index = (
        await db_session.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE indexname='ingestion_jobs_one_active_summary_per_transcript'"
            )
        )
    ).scalar()
    assert index == 1
