"""LLMGateway — the single orchestration point (adr-028, spec §4).

Owns every cross-cutting concern: render → open log → context fit (routing check) → limiter
acquire → provider transport → output validation → close log. The provider is transport-only and
is behaviorally interchangeable (real vs deterministic) behind this chain. The log row is opened
BEFORE the routing check so ``invalid_input`` is loggable (Patch A). ``stream()`` exists from day
one but raises ``NotImplementedError`` until Stage 8.3 so no caller can bypass the gateway.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Iterator, TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.llm.context import ContextBuilder, estimate_tokens
from app.platform.llm.errors import GatewayError, GatewayFailed, InvalidInput
from app.platform.llm.logging import close_request_log, open_request_log
from app.platform.llm.models.prompt import (
    Backend,
    Priority,
    PromptKey,
    SummaryFeature,
    Usage,
)
from app.platform.llm.models.summary import BriefSummary, DetailedSummary
from app.platform.llm.provider import LLMProvider, get_provider
from app.platform.llm.registry import PromptRegistry, get_prompt_registry
from app.platform.llm.limiter import RedisRateLimiter, get_rate_limiter
from app.platform.llm.validation import OutputValidator


@dataclass(frozen=True)
class ContextRefs:
    ingestion_job_id: UUID
    transcript_text: str
    input_content_hash: str
    section_type: str


class CompletionResult(TypedDict):
    parsed: BriefSummary | DetailedSummary
    model_id_echoed: str
    usage: Usage
    backend_used: Backend
    reasoning_level: str | None
    ai_request_log_id: UUID


class LLMGateway:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        registry: PromptRegistry | None = None,
        limiter: RedisRateLimiter | None = None,
        context_builder: ContextBuilder | None = None,
        validator: OutputValidator | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._provider = provider or get_provider()
        self._registry = registry or get_prompt_registry()
        self._limiter = limiter or get_rate_limiter()
        self._context = context_builder or ContextBuilder()
        self._validator = validator or OutputValidator()
        self._session_factory = session_factory

    async def complete(
        self,
        *,
        prompt_key: PromptKey,
        output_schema: type[BriefSummary] | type[DetailedSummary],
        context_refs: ContextRefs,
        priority: Priority,
        feature: SummaryFeature,
        attempt_number: int = 1,
    ) -> CompletionResult:
        rendered = self._registry.render(
            prompt_key,
            transcript=context_refs.transcript_text,
            section_type=context_refs.section_type,
        )
        estimated = estimate_tokens(rendered.content)

        # Patch A: open BEFORE any check so invalid_input is loggable.
        log_id = await open_request_log(
            ingestion_job_id=context_refs.ingestion_job_id,
            feature=feature,
            rendered=rendered,
            input_content_hash=context_refs.input_content_hash,
            estimated_prompt_tokens=estimated,
            attempt_number=attempt_number,
            session_factory=self._session_factory,
        )

        fit = None
        raw = None
        latency_ms: int | None = None
        try:
            # Deterministic E2E fault: over-context detected before transport.
            if getattr(self._provider, "fault", None) == "invalid_input":
                raise InvalidInput(
                    "deterministic provider forced over-context", error_code="forced_over_context"
                )

            fit = self._context.fit(rendered, estimated_prompt_tokens=estimated)

            lease = await self._limiter.acquire(
                backend=fit.backend,
                estimated_tokens=fit.reserved_tokens,
                priority=priority,
            )
            started = time.monotonic()
            try:
                raw = await asyncio.to_thread(
                    self._provider.send, rendered=rendered, backend=fit.backend
                )
            finally:
                await lease.release()
            latency_ms = int((time.monotonic() - started) * 1000)

            parsed = self._validator.validate(
                raw_text=raw.text,
                output_schema=output_schema,
                section_type=context_refs.section_type,
            )

            await close_request_log(
                log_id=log_id,
                status="succeeded",
                backend_used=fit.backend,
                model_id=fit.model_id,
                reasoning_level=raw.reasoning_level,
                usage=raw.usage,
                provider_request_id=raw.provider_request_id,
                latency_ms=latency_ms,
                session_factory=self._session_factory,
            )
            return CompletionResult(
                parsed=parsed,
                model_id_echoed=raw.model_id_echoed,
                usage=raw.usage,
                backend_used=fit.backend,
                reasoning_level=raw.reasoning_level,
                ai_request_log_id=log_id,
            )
        except GatewayError as exc:
            await close_request_log(
                log_id=log_id,
                status=exc.status,
                backend_used=(fit.backend if fit is not None else None),
                model_id=(fit.model_id if fit is not None else None),
                usage=(raw.usage if raw is not None else None),
                provider_request_id=(raw.provider_request_id if raw is not None else None),
                latency_ms=latency_ms,
                error_class=exc.error_class,
                error_code=exc.error_code,
                session_factory=self._session_factory,
            )
            raise
        except Exception as exc:  # unexpected — generic failed (§6.6)
            await close_request_log(
                log_id=log_id,
                status="failed",
                backend_used=(fit.backend if fit is not None else None),
                error_class=type(exc).__name__,
                error_code="unexpected",
                session_factory=self._session_factory,
            )
            raise GatewayFailed("unexpected gateway failure") from exc

    def stream(
        self,
        *,
        prompt_key: PromptKey,
        output_schema: type,
        context_refs: ContextRefs,
        priority: Priority,
    ) -> Iterator[str]:
        raise NotImplementedError("LLM streaming transport lands in Stage 8.3")
