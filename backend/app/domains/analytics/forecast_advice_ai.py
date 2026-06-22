from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.analytics import forecast_advice
from app.platform.db.models import AIRequestLog, StudentForecastAdvice
from app.platform.db.session import async_session
from app.platform.llm.errors import GatewayError, InvalidOutput
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.forecast_advice import GradeForecastAdvice
from app.platform.llm.models.prompt import PromptKey

RQ_RETRY_STATUSES = {"provider_transient", "rate_limited"}


def generate_forecast_advice(advice_id: str) -> None:
    asyncio.run(generate_forecast_advice_async(UUID(advice_id)))


async def generate_forecast_advice_async(
    advice_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim(factory, advice_id=advice_id)
    if context is None:
        return
    advice_id, prompt_blob, input_hash = context
    last_error: GatewayError | None = None
    for attempt in (1, 2):
        try:
            result = await active_gateway.complete(
                prompt_key=PromptKey(
                    forecast_advice.ADVICE_PROMPT_NAME,
                    forecast_advice.ADVICE_PROMPT_VERSION,
                ),
                output_schema=GradeForecastAdvice,
                context_refs=ContextRefs(
                    ingestion_job_id=None,
                    transcript_text=prompt_blob,
                    input_content_hash=input_hash,
                    section_type=forecast_advice.ADVICE_SECTION_TYPE,
                ),
                priority="background",
                feature=forecast_advice.ADVICE_FEATURE,
                attempt_number=attempt,
            )
            advice = result["parsed"]
            async with factory() as session:
                row = await session.get(StudentForecastAdvice, advice_id)
                if row is None:
                    return
                forecast_advice.validate_forecast_advice(
                    advice,
                    context=forecast_advice.advice_validation_context(row.deterministic_payload),
                )
                log = await session.get(AIRequestLog, result["ai_request_log_id"])
                now = datetime.now(UTC)
                row.ai_text = advice.advice.strip()
                row.ai_status = "succeeded"
                row.ai_failure_message_sanitized = None
                row.ai_request_log_id = result["ai_request_log_id"]
                row.ai_model_id = log.model_id if log is not None else result["model_id_echoed"]
                row.ai_prompt_version = forecast_advice.ADVICE_PROMPT_VERSION
                row.ai_input_hash = input_hash
                row.ai_generated_at = now
                row.updated_at = now
                await session.commit()
            return
        except InvalidOutput as exc:
            last_error = exc
            continue
        except GatewayError as exc:
            last_error = exc
            if exc.status in RQ_RETRY_STATUSES:
                await _mark_failed(factory, advice_id=advice_id, input_hash=input_hash, exc=exc)
                raise
            break

    await _mark_template_fallback(
        factory, advice_id=advice_id, input_hash=input_hash, exc=last_error
    )


async def _claim(
    factory: async_sessionmaker[AsyncSession],
    *,
    advice_id: UUID,
) -> tuple[UUID, str, str] | None:
    async with factory() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(StudentForecastAdvice)
                    .where(StudentForecastAdvice.id == advice_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if (
                row.ai_status == "succeeded"
                and row.ai_input_hash == row.input_hash
                and row.ai_prompt_version == forecast_advice.ADVICE_PROMPT_VERSION
            ):
                return None
            prompt_blob = forecast_advice.advice_prompt_blob(row.deterministic_payload)
            row.ai_status = "queued"
            row.updated_at = datetime.now(UTC)
            return row.id, prompt_blob, row.input_hash


async def _mark_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    advice_id: UUID,
    input_hash: str,
    exc: Exception,
) -> None:
    async with factory() as session:
        async with session.begin():
            row = await session.get(StudentForecastAdvice, advice_id)
            if row is None:
                return
            row.ai_status = "failed"
            # Record the attempted hash so a view does not re-enqueue this exact forecast every time
            # (rule-15). A forecast change bumps input_hash and re-enables regeneration.
            row.ai_input_hash = input_hash
            row.ai_failure_message_sanitized = _sanitize(exc)
            row.updated_at = datetime.now(UTC)


async def _mark_template_fallback(
    factory: async_sessionmaker[AsyncSession],
    *,
    advice_id: UUID,
    input_hash: str,
    exc: Exception | None,
) -> None:
    async with factory() as session:
        async with session.begin():
            row = await session.get(StudentForecastAdvice, advice_id)
            if row is None:
                return
            row.ai_text = None
            row.ai_status = "template_fallback"
            row.ai_input_hash = input_hash
            row.ai_failure_message_sanitized = _sanitize(exc) if exc is not None else None
            row.updated_at = datetime.now(UTC)


def _sanitize(exc: Exception) -> str:
    return (str(exc).strip() or exc.__class__.__name__)[:500]
