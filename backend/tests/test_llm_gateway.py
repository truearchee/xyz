"""Gateway full-path + AIRequestLog gateway-attempt semantics (Patch A) against the deterministic
provider. The full chain (render → open log → fit → limiter → provider → validate → close) runs;
only the provider boundary is a test double."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import AIRequestLog, IngestionJob
from app.platform.llm.errors import InvalidInput, InvalidOutput, ProviderTransient
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.prompt import PromptKey
from app.platform.llm.models.summary import BriefSummary
from app.platform.llm.provider import DeterministicTestProvider
from tests.test_transcript_worker import _create_worker_transcript, _session_factory

pytestmark = pytest.mark.anyio

BRIEF_KEY = PromptKey("brief_summary", "v1")
TRANSCRIPT_TEXT = "This is the lecture content. " * 40


class _FakeLease:
    def __init__(self) -> None:
        self.released = False

    async def heartbeat(self) -> bool:
        return True

    async def release(self) -> None:
        self.released = True


class _FakeLimiter:
    def __init__(self) -> None:
        self.acquired: list[tuple] = []

    async def acquire(self, *, backend, estimated_tokens, priority):
        self.acquired.append((backend, estimated_tokens, priority))
        return _FakeLease()


async def _summary_job(session: AsyncSession, transcript_id: UUID) -> IngestionJob:
    job = IngestionJob(
        transcript_id=transcript_id,
        job_type="generate_brief_summary",
        status="queued",
        idempotency_key=f"{transcript_id}:generate_brief_summary:{uuid4().hex}",
        processor_version="brief_summary/v1",
    )
    session.add(job)
    await session.flush()
    return job


async def _logs(factory, ingestion_job_id: UUID) -> list[AIRequestLog]:
    async with factory() as session:
        return list(
            (
                await session.execute(
                    select(AIRequestLog)
                    .where(AIRequestLog.ingestion_job_id == ingestion_job_id)
                    .order_by(AIRequestLog.attempt_number)
                )
            ).scalars().all()
        )


async def _setup(db_session: AsyncSession):
    transcript = await _create_worker_transcript(
        db_session, raw=b"WEBVTT\n\n00:00.000 --> 00:01.000\nHi\n"
    )
    job = await _summary_job(db_session, transcript.id)
    await db_session.commit()
    return transcript, job


def _gateway(factory, *, fault: str | None = None) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(fault=fault),
        limiter=_FakeLimiter(),
        session_factory=factory,
    )


def _refs(job: IngestionJob) -> ContextRefs:
    return ContextRefs(
        ingestion_job_id=job.id,
        transcript_text=TRANSCRIPT_TEXT,
        input_content_hash="deadbeef",
        section_type="lecture",
    )


async def test_happy_path_writes_succeeded_log_and_validated_output(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)

    result = await _gateway(factory).complete(
        prompt_key=BRIEF_KEY,
        output_schema=BriefSummary,
        context_refs=_refs(job),
        priority="background",
        feature="summary_brief",
    )

    assert isinstance(result["parsed"], BriefSummary)
    assert result["backend_used"] == "cerebras"
    assert isinstance(result["ai_request_log_id"], UUID)

    logs = await _logs(factory, job.id)
    assert len(logs) == 1
    log = logs[0]
    assert log.status == "succeeded"
    assert log.backend_used == "cerebras"
    assert log.estimated_prompt_tokens is not None
    assert log.prompt_tokens is not None and log.total_tokens is not None
    assert log.provider_request_id is not None and log.provider_request_id.startswith("det-")
    assert log.request_completed_at is not None
    assert log.input_content_hash == "deadbeef"


async def test_invalid_input_logged_before_transport_without_provider_fields(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)

    with pytest.raises(InvalidInput):
        await _gateway(factory, fault="invalid_input").complete(
            prompt_key=BRIEF_KEY,
            output_schema=BriefSummary,
            context_refs=_refs(job),
            priority="background",
            feature="summary_brief",
        )

    logs = await _logs(factory, job.id)
    assert len(logs) == 1
    log = logs[0]
    assert log.status == "invalid_input"
    # Opened BEFORE the (skipped) transport: estimate recorded, no provider fields.
    assert log.estimated_prompt_tokens is not None
    assert log.provider_request_id is None
    assert log.backend_used is None
    assert log.request_completed_at is None
    assert log.prompt_tokens is None


async def test_invalid_output_logs_after_transport(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)

    with pytest.raises(InvalidOutput):
        await _gateway(factory, fault="invalid_output").complete(
            prompt_key=BRIEF_KEY,
            output_schema=BriefSummary,
            context_refs=_refs(job),
            priority="background",
            feature="summary_brief",
        )

    log = (await _logs(factory, job.id))[0]
    assert log.status == "invalid_output"
    assert log.backend_used == "cerebras"
    assert log.provider_request_id is not None  # transport happened, then validation failed
    assert log.prompt_tokens is not None


async def test_provider_transient_logs_without_provider_request_id(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)

    with pytest.raises(ProviderTransient):
        await _gateway(factory, fault="provider_transient").complete(
            prompt_key=BRIEF_KEY,
            output_schema=BriefSummary,
            context_refs=_refs(job),
            priority="background",
            feature="summary_brief",
        )

    log = (await _logs(factory, job.id))[0]
    assert log.status == "provider_transient"
    assert log.backend_used == "cerebras"  # fit succeeded, transport raised
    assert log.provider_request_id is None


async def test_each_attempt_opens_a_new_row(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)
    gateway = _gateway(factory)

    for attempt in (1, 2):
        await gateway.complete(
            prompt_key=BRIEF_KEY,
            output_schema=BriefSummary,
            context_refs=_refs(job),
            priority="background",
            feature="summary_brief",
            attempt_number=attempt,
        )

    logs = await _logs(factory, job.id)
    assert [log.attempt_number for log in logs] == [1, 2]
    assert all(log.status == "succeeded" for log in logs)
