"""Gateway full-path + AIRequestLog gateway-attempt semantics (Patch A) against the deterministic
provider. The full chain (render → open log → fit → limiter → provider → validate → close) runs;
only the provider boundary is a test double."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import json

from app.platform.db.models import AIRequestLog, IngestionJob
from app.platform.llm.errors import (
    InvalidInput,
    InvalidOutput,
    ProviderAuthError,
    ProviderConfigError,
    ProviderTransient,
    RateLimited,
)
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.limiter import BackoffPolicy
from app.platform.llm.models.prompt import PromptKey
from app.platform.llm.models.summary import BriefSummary
from app.platform.llm.provider import DeterministicTestProvider, RawCompletion
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


# --- 4.5b: in-row transport-retry provenance (§9) + rate_limited backoff (§10) ----------------

async def _no_sleep(_seconds: float) -> None:
    return None


def _fast_backoff(*, max_backoffs: int) -> BackoffPolicy:
    # tiny delays + huge elapsed cap → the loop terminates on the backoff COUNT, deterministically.
    return BackoffPolicy(
        max_backoffs=max_backoffs, base_delay_ms=1, max_delay_ms=1, max_elapsed_ms=10_000
    )


def _backoff_gateway(factory, provider, *, max_backoffs: int = 2) -> LLMGateway:
    return LLMGateway(
        provider=provider,
        limiter=_FakeLimiter(),
        backoff=_fast_backoff(max_backoffs=max_backoffs),
        sleep=_no_sleep,
        session_factory=factory,
    )


class _FlakyConcurrencyLimiter:
    """Denies with ``limiter_concurrency`` ``deny_times`` then grants — exercises the limiter-full
    backpressure source (source 1 of §10), distinct from a provider HTTP 429 (source 2)."""

    def __init__(self, *, deny_times: int) -> None:
        self._remaining = deny_times
        self.acquired: list[tuple] = []

    async def acquire(self, *, backend, estimated_tokens, priority):
        if self._remaining > 0:
            self._remaining -= 1
            raise RateLimited("limiter full", error_code="limiter_concurrency")
        self.acquired.append((backend, estimated_tokens, priority))
        return _FakeLease()


class _FlakyRateLimitProvider:
    """429s ``fail_times`` then returns a valid brief — proves backoff recovery within one row."""

    def __init__(self, *, fail_times: int) -> None:
        self._remaining = fail_times
        self.fault = None  # gateway introspects provider.fault for the invalid_input E2E hook

    def send(self, *, rendered, backend):
        if self._remaining > 0:
            self._remaining -= 1
            raise RateLimited("provider 429", error_code="provider_429", status_code=429)
        return RawCompletion(
            text=json.dumps({"text": "A valid brief summary paragraph for this lecture session."}),
            usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            model_id_echoed="MBZUAI-IFM/K2-Think-v2",
            provider_request_id="flaky-ok",
            status_code=200,
        )


async def test_happy_path_records_in_row_provenance(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)

    await _gateway(factory).complete(
        prompt_key=BRIEF_KEY,
        output_schema=BriefSummary,
        context_refs=_refs(job),
        priority="background",
        feature="summary_brief",
    )

    log = (await _logs(factory, job.id))[0]
    assert log.status == "succeeded"
    assert log.provider_attempt_count == 1
    assert log.rate_limit_backoff_count == 0
    assert log.retry_events_json is None  # no retries → no events
    assert log.backend_route_source == "requested"  # request-asserted, never provider-echoed (§6)


async def test_rate_limited_backoff_terminates_after_budget(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)
    gateway = _backoff_gateway(
        factory, DeterministicTestProvider(fault="rate_limited"), max_backoffs=2
    )

    with pytest.raises(RateLimited):
        await gateway.complete(
            prompt_key=BRIEF_KEY,
            output_schema=BriefSummary,
            context_refs=_refs(job),
            priority="background",
            feature="summary_brief",
        )

    log = (await _logs(factory, job.id))[0]
    assert log.status == "rate_limited"  # ONE row, terminal on exhaustion — not RQ-retried here
    assert log.provider_attempt_count == 3  # max_backoffs(2) + the final exhausting POST
    assert log.rate_limit_backoff_count == 3
    assert log.last_provider_status_code == 429
    assert log.retry_events_json is not None and len(log.retry_events_json) == 3
    assert log.retry_events_json[0]["statusCode"] == 429


async def test_rate_limited_backoff_recovers_and_succeeds_in_one_row(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)
    gateway = _backoff_gateway(factory, _FlakyRateLimitProvider(fail_times=2), max_backoffs=4)

    result = await gateway.complete(
        prompt_key=BRIEF_KEY,
        output_schema=BriefSummary,
        context_refs=_refs(job),
        priority="background",
        feature="summary_brief",
    )
    assert isinstance(result["parsed"], BriefSummary)

    logs = await _logs(factory, job.id)
    assert len(logs) == 1  # backoff retries live IN the row, not as new rows (§9)
    log = logs[0]
    assert log.status == "succeeded"
    assert log.provider_attempt_count == 3  # 2 × 429 + 1 success
    assert log.rate_limit_backoff_count == 2
    assert log.last_provider_status_code == 200
    assert len(log.retry_events_json) == 2


async def test_limiter_full_backs_off_then_acquires(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)
    gateway = LLMGateway(
        provider=DeterministicTestProvider(),
        limiter=_FlakyConcurrencyLimiter(deny_times=2),
        backoff=_fast_backoff(max_backoffs=4),
        sleep=_no_sleep,
        session_factory=factory,
    )

    result = await gateway.complete(
        prompt_key=BRIEF_KEY,
        output_schema=BriefSummary,
        context_refs=_refs(job),
        priority="background",
        feature="summary_brief",
    )
    assert isinstance(result["parsed"], BriefSummary)

    log = (await _logs(factory, job.id))[0]
    assert log.status == "succeeded"
    assert log.provider_attempt_count == 1  # only one transport POST, after capacity freed
    assert log.rate_limit_backoff_count == 2  # two limiter-full waits (source 1)
    assert log.retry_events_json is not None and len(log.retry_events_json) == 2
    assert log.retry_events_json[0]["statusCode"] is None  # limiter wait, not a provider HTTP status


async def test_provider_config_error_is_terminal_and_recorded(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)
    gateway = _backoff_gateway(factory, DeterministicTestProvider(fault="provider_config"))

    with pytest.raises(ProviderConfigError):
        await gateway.complete(
            prompt_key=BRIEF_KEY,
            output_schema=BriefSummary,
            context_refs=_refs(job),
            priority="background",
            feature="summary_brief",
        )

    log = (await _logs(factory, job.id))[0]
    assert log.status == "provider_config_error"  # terminal 4xx, never retried (§8)
    assert log.last_provider_status_code == 400
    assert log.provider_attempt_count == 1
    assert log.retry_events_json is None  # config error does not back off


async def test_provider_auth_error_is_terminal_and_recorded(db_session: AsyncSession):
    factory = _session_factory(db_session)
    _, job = await _setup(db_session)
    gateway = _backoff_gateway(factory, DeterministicTestProvider(fault="provider_auth"))

    with pytest.raises(ProviderAuthError):
        await gateway.complete(
            prompt_key=BRIEF_KEY,
            output_schema=BriefSummary,
            context_refs=_refs(job),
            priority="background",
            feature="summary_brief",
        )

    log = (await _logs(factory, job.id))[0]
    assert log.status == "provider_auth_error"
    assert log.last_provider_status_code == 403
    assert log.provider_attempt_count == 1
