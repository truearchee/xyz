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
from app.platform.llm.limiter import BackoffPolicy
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


async def _make_summary_jobs(db_session: AsyncSession, factory, *, enable_detailed: bool = False):
    transcript, _ = await _create_parsed_transcript(db_session, texts=TEXTS)
    async with factory() as session:
        async with session.begin():
            jobs = await insert_summary_jobs(
                session, transcript=transcript, enable_detailed=enable_detailed
            )
    return transcript, dict(jobs)


# --- job creation -----------------------------------------------------------

@pytest.mark.anyio
async def test_insert_summary_jobs_creates_two_queued_jobs_idempotently(db_session: AsyncSession):
    factory = _session_factory(db_session)
    # The two-job creation mechanism is exercised with detailed enabled (the 4.5c regime); 4.5b
    # default-off behavior is covered by test_detailed_enqueue_gated_off below (§5).
    transcript, jobs = await _make_summary_jobs(db_session, factory, enable_detailed=True)
    assert set(jobs) == {"generate_brief_summary", "generate_detailed_summary"}

    # Idempotent: a second call returns the same job ids and does not duplicate.
    async with factory() as session:
        async with session.begin():
            again = dict(
                await insert_summary_jobs(session, transcript=transcript, enable_detailed=True)
            )
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
    transcript, jobs = await _make_summary_jobs(db_session, factory, enable_detailed=True)
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


# --- 4.5c: detailed activated by default + routing split made live -------------------------

@pytest.mark.anyio
async def test_detailed_enabled_by_default_creates_both_jobs(db_session: AsyncSession):
    # 4.5c default ENABLE_DETAILED_SUMMARY=true: insert_summary_jobs (no override) creates BOTH.
    factory = _session_factory(db_session)
    transcript, _ = await _create_parsed_transcript(db_session, texts=TEXTS)
    async with factory() as session:
        async with session.begin():
            jobs = dict(await insert_summary_jobs(session, transcript=transcript))
    assert set(jobs) == {"generate_brief_summary", "generate_detailed_summary"}


@pytest.mark.anyio
async def test_both_summaries_complete_with_separate_route_budgets(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory, enable_detailed=True)

    # One shared limiter across both jobs proves each acquires its OWN backend budget (rule 15).
    limiter = _FakeLimiter()

    def gateway():
        return LLMGateway(
            provider=DeterministicTestProvider(), limiter=limiter, session_factory=factory
        )

    await generate_brief_summary_async(
        jobs["generate_brief_summary"], gateway=gateway(), session_factory=factory
    )
    await generate_detailed_summary_async(
        jobs["generate_detailed_summary"], gateway=gateway(), session_factory=factory
    )

    # Routing split exercised end-to-end: brief→cerebras budget, detailed→nvidia budget.
    assert {backend for backend, _tokens, _priority in limiter.acquired} == {"cerebras", "nvidia"}

    async with factory() as session:
        for job_type in ("generate_brief_summary", "generate_detailed_summary"):
            job = (
                await session.execute(
                    select(IngestionJob).where(
                        IngestionJob.transcript_id == transcript.id,
                        IngestionJob.job_type == job_type,
                    )
                )
            ).scalar_one()
            assert job.status == "completed"

        summaries = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id
                )
            )
        ).scalars().all()
        by_type = {s.summary_type: s for s in summaries}
        assert set(by_type) == {"brief", "detailed_study"}
        assert by_type["brief"].backend_used == "cerebras"
        assert by_type["detailed_study"].backend_used == "nvidia"  # detailed on the Nvidia route
        assert "overview" in by_type["detailed_study"].content_json


# --- 4.5b: detailed gated off (§5) + terminal provider categories (§8) ----------------------

async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.anyio
async def test_detailed_enqueue_gated_off_creates_no_detailed_row_or_log(db_session: AsyncSession):
    factory = _session_factory(db_session)
    # Default (ENABLE_DETAILED_SUMMARY off): only the brief job is created — gated at CREATION (§5).
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    assert set(jobs) == {"generate_brief_summary"}

    async with factory() as session:
        detailed_rows = (
            await session.execute(
                select(IngestionJob).where(
                    IngestionJob.transcript_id == transcript.id,
                    IngestionJob.job_type == "generate_detailed_summary",
                )
            )
        ).scalars().all()
    assert detailed_rows == []  # no detailed IngestionJob row for the 4.6 sweeper to misread

    await generate_brief_summary_async(
        jobs["generate_brief_summary"], gateway=_gateway(factory), session_factory=factory
    )

    async with factory() as session:
        brief_job = await session.get(IngestionJob, jobs["generate_brief_summary"])
        assert brief_job.status == "completed"
        detailed_logs = (
            await session.execute(
                select(AIRequestLog).where(AIRequestLog.feature == "summary_detailed")
            )
        ).scalars().all()
    assert detailed_logs == []  # Think-v0 is never called; no detailed AIRequestLog


@pytest.mark.anyio
async def test_provider_config_error_is_terminal_category_no_retry(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    brief_id = jobs["generate_brief_summary"]

    # Terminal 4xx: the handler swallows it (NO RQ retry) and records the precise category (§8).
    await generate_brief_summary_async(
        brief_id, gateway=_gateway(factory, fault="provider_config"), session_factory=factory
    )

    async with factory() as session:
        job = await session.get(IngestionJob, brief_id)
        assert job.status == "failed"
        assert job.failure_category == "provider_config_error"
        summaries = (
            await session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript.id
                )
            )
        ).scalars().all()
        assert summaries == []


@pytest.mark.anyio
async def test_rate_limited_exhaustion_is_terminal_not_retried(db_session: AsyncSession):
    factory = _session_factory(db_session)
    transcript, jobs = await _make_summary_jobs(db_session, factory)
    brief_id = jobs["generate_brief_summary"]

    # Fast backoff + no-op sleep so exhaustion is deterministic and instant.
    gateway = LLMGateway(
        provider=DeterministicTestProvider(fault="rate_limited"),
        limiter=_FakeLimiter(),
        backoff=BackoffPolicy(max_backoffs=1, base_delay_ms=1, max_delay_ms=1, max_elapsed_ms=10_000),
        sleep=_no_sleep,
        session_factory=factory,
    )
    # rate_limited is NOT in RQ_RETRY_STATUSES (rule 15) → the handler returns without raising.
    await generate_brief_summary_async(brief_id, gateway=gateway, session_factory=factory)

    async with factory() as session:
        job = await session.get(IngestionJob, brief_id)
        assert job.status == "failed"
        assert job.failure_category == "rate_limited"


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


def test_overall_state_summarizing_when_brief_done_and_detailed_deferred(monkeypatch):
    # When detailed is explicitly suppressed (ENABLE_DETAILED_SUMMARY=false — the 4.5b regime, still a
    # supported cost-control config in 4.5c) there is no detailed job, and brief-complete rests at
    # 'summarizing' (not 'embedded', not 'summarized'). 4.5c default is true (both run → 'summarized').
    monkeypatch.setenv("ENABLE_DETAILED_SUMMARY", "false")
    state = _overall_state(
        transcript=SimpleNamespace(status="completed"),
        steps=_embedded_steps(summary_brief="completed", summary_detailed="not_started"),
        segment_count=3,
        chunk_count=1,
        embedded_chunk_count=1,
    )
    assert state == "summarizing"


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
    failed = _failed_step(jobs=jobs)  # F-4.6d-3: derived from step states, no transcript breadcrumb
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
