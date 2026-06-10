"""AIRequestLog open/close helpers — gateway-attempt semantics (Patch A, spec §6.6).

``open_request_log`` writes a ``running`` row (committed independently of the caller's transaction
so it survives a later rollback) BEFORE the ContextBuilder routing check, recording prompt identity
and the conservative token estimate. ``close_request_log`` transitions the row to a terminal status
and fills provider fields when transport occurred. Hashes only — never raw transcript/prompt text.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.db.models import AIRequestLog
from app.platform.db.session import async_session
from app.platform.llm.models.prompt import Backend, RenderedPrompt, SummaryFeature, Usage


def _now() -> datetime:
    return datetime.now(UTC)


def _factory(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> async_sessionmaker[AsyncSession]:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return factory


async def open_request_log(
    *,
    ingestion_job_id: UUID,
    feature: SummaryFeature,
    rendered: RenderedPrompt,
    input_content_hash: str,
    estimated_prompt_tokens: int,
    attempt_number: int = 1,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> UUID:
    factory = _factory(session_factory)
    log = AIRequestLog(
        ingestion_job_id=ingestion_job_id,
        attempt_number=attempt_number,
        feature=feature,
        model_id=rendered.model_id,
        prompt_version=rendered.prompt_key.version,
        prompt_content_hash=rendered.prompt_content_hash,
        rendered_prompt_hash=rendered.rendered_prompt_hash,
        input_content_hash=input_content_hash,
        estimated_prompt_tokens=estimated_prompt_tokens,
        status="running",
    )
    async with factory() as session:
        async with session.begin():
            session.add(log)
        return log.id


async def close_request_log(
    *,
    log_id: UUID,
    status: str,
    backend_used: Backend | None = None,
    model_id: str | None = None,
    reasoning_level: str | None = None,
    usage: Usage | None = None,
    provider_request_id: str | None = None,
    latency_ms: int | None = None,
    error_class: str | None = None,
    error_code: str | None = None,
    debug_text: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = _factory(session_factory)
    async with factory() as session:
        async with session.begin():
            log = await session.get(AIRequestLog, log_id)
            if log is None:  # pragma: no cover - defensive
                return
            log.status = status
            if backend_used is not None:
                log.backend_used = backend_used
            if model_id is not None:
                log.model_id = model_id
            if reasoning_level is not None:
                log.reasoning_level = reasoning_level
            if usage is not None:
                log.prompt_tokens = usage["prompt_tokens"]
                log.completion_tokens = usage["completion_tokens"]
                log.total_tokens = usage["total_tokens"]
            if provider_request_id is not None:
                log.provider_request_id = provider_request_id
            if latency_ms is not None:
                log.latency_ms = latency_ms
                # request_completed_at is set only when transport actually completed.
                log.request_completed_at = _now()
            if error_class is not None:
                log.error_class = error_class
            if error_code is not None:
                log.error_code = error_code
            if debug_text is not None:
                log.debug_text_truncated = debug_text
