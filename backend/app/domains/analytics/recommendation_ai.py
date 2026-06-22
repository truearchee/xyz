from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.analytics import recommendations
from app.platform.db.models import AIRequestLog, Recommendation
from app.platform.db.session import async_session
from app.platform.llm.errors import GatewayError, InvalidOutput
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.prompt import PromptKey
from app.platform.llm.models.recommendation import RecommendationCopy

RQ_RETRY_STATUSES = {"provider_transient", "rate_limited"}


def generate_recommendation_copy(recommendation_id: str) -> None:
    asyncio.run(generate_recommendation_copy_async(UUID(recommendation_id)))


async def generate_recommendation_copy_async(
    recommendation_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim(factory, recommendation_id=recommendation_id)
    if context is None:
        return
    recommendation_id, prompt_blob, input_hash = context
    last_error: GatewayError | None = None
    for attempt in (1, 2):
        try:
            result = await active_gateway.complete(
                prompt_key=PromptKey(
                    recommendations.RECOMMENDATION_COPY_PROMPT_NAME,
                    recommendations.RECOMMENDATION_COPY_PROMPT_VERSION,
                ),
                output_schema=RecommendationCopy,
                context_refs=ContextRefs(
                    ingestion_job_id=None,
                    transcript_text=prompt_blob,
                    input_content_hash=input_hash,
                    section_type="recommendation",
                ),
                priority="background",
                feature=recommendations.RECOMMENDATION_COPY_FEATURE,
                attempt_number=attempt,
            )
            copy = result["parsed"]
            async with factory() as session:
                row = await session.get(Recommendation, recommendation_id)
                if row is None:
                    return
                recommendations.validate_recommendation_copy(
                    copy,
                    context=recommendations.validation_context(row.deterministic_payload),
                )
                log = await session.get(AIRequestLog, result["ai_request_log_id"])
                now = datetime.now(UTC)
                row.lecturer_ai_text = copy.lecturer_draft.strip()
                row.student_ai_text = copy.student_nudge.strip()
                row.ai_status = "succeeded"
                row.ai_failure_message_sanitized = None
                row.ai_request_log_id = result["ai_request_log_id"]
                row.ai_model_id = log.model_id if log is not None else result["model_id_echoed"]
                row.ai_prompt_version = recommendations.RECOMMENDATION_COPY_PROMPT_VERSION
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
                await _mark_failed(factory, recommendation_id=recommendation_id, exc=exc)
                raise
            break

    await _mark_template_fallback(factory, recommendation_id=recommendation_id, exc=last_error)


async def _claim(
    factory: async_sessionmaker[AsyncSession],
    *,
    recommendation_id: UUID,
) -> tuple[UUID, str, str] | None:
    async with factory() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(Recommendation)
                    .where(Recommendation.id == recommendation_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None or row.status != "active":
                return None
            if (
                row.ai_status == "succeeded"
                and row.ai_input_hash == row.input_hash
                and row.ai_prompt_version == recommendations.RECOMMENDATION_COPY_PROMPT_VERSION
            ):
                return None
            prompt_blob = recommendations.ai_prompt_blob(row)
            row.ai_status = "queued"
            row.updated_at = datetime.now(UTC)
            return row.id, prompt_blob, row.input_hash


async def _mark_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    recommendation_id: UUID,
    exc: Exception,
) -> None:
    async with factory() as session:
        async with session.begin():
            row = await session.get(Recommendation, recommendation_id)
            if row is None:
                return
            row.ai_status = "failed"
            row.ai_failure_message_sanitized = _sanitize(exc)
            row.updated_at = datetime.now(UTC)


async def _mark_template_fallback(
    factory: async_sessionmaker[AsyncSession],
    *,
    recommendation_id: UUID,
    exc: Exception | None,
) -> None:
    async with factory() as session:
        async with session.begin():
            row = await session.get(Recommendation, recommendation_id)
            if row is None:
                return
            row.lecturer_ai_text = None
            row.student_ai_text = None
            row.ai_status = "template_fallback"
            row.ai_failure_message_sanitized = _sanitize(exc) if exc is not None else None
            row.updated_at = datetime.now(UTC)


def _sanitize(exc: Exception) -> str:
    return (str(exc).strip() or exc.__class__.__name__)[:500]
