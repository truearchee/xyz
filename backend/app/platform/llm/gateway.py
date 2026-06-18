"""LLMGateway — the single orchestration point (adr-028, spec §4).

Owns every cross-cutting concern: render → open log → context fit (routing check) → limiter
acquire → provider transport → output validation → close log. The provider is transport-only and
is behaviorally interchangeable (real vs deterministic) behind this chain. The log row is opened
BEFORE the routing check so ``invalid_input`` is loggable (Patch A). ``stream()`` exists from day
one but raises ``NotImplementedError`` until Stage 8.3 so no caller can bypass the gateway.

4.5b adds the in-call ``rate_limited`` backoff (rule 15 / §10): a single ``complete()`` may back off
on a full limiter slot or a provider HTTP 429 and retry the transport several times, but it remains
ONE AIRequestLog row — every transport POST and backoff is recorded IN that row (§9), never as new
rows. Gateway-level retries (RQ re-runs the job) are what open a new row, via ``attempt_number``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Iterator, TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.llm.context import ContextBuilder, FitResult, estimate_tokens
from app.platform.llm.errors import GatewayError, GatewayFailed, InvalidInput, RateLimited
from app.platform.llm.limiter import BackoffPolicy, RedisRateLimiter, get_rate_limiter
from app.platform.llm.logging import close_request_log, open_request_log
from app.platform.llm.models.prompt import (
    Backend,
    FEATURES_REQUIRING_INGESTION_JOB,
    GatewayFeature,
    Priority,
    PromptKey,
    Usage,
)
from app.platform.llm.models.assistant import AssistantAnswer, AssistantGroundedAnswer
from app.platform.llm.models.quiz import GeneratedQuizPool, PostClassQuiz
from app.platform.llm.models.summary import BriefSummary, DetailedSummary
from app.platform.llm.provider import LLMProvider, get_provider
from app.platform.llm.registry import PromptRegistry, get_prompt_registry
from app.platform.llm.validation import OutputValidator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextRefs:
    # Optional (0020): quiz/assistant calls have no IngestionJob. Summary features still require it,
    # enforced at the application layer in ``complete()`` (not by this type). ``transcript_text`` is
    # the source text rendered into the prompt's ``{{transcript}}`` placeholder — for quiz generation
    # that is the detailed-summary text, not a transcript.
    ingestion_job_id: UUID | None
    transcript_text: str
    input_content_hash: str
    section_type: str


class CompletionResult(TypedDict):
    parsed: (
        BriefSummary
        | DetailedSummary
        | PostClassQuiz
        | GeneratedQuizPool
        | AssistantAnswer
        | AssistantGroundedAnswer
    )
    model_id_echoed: str
    usage: Usage
    backend_used: Backend
    reasoning_level: str | None
    ai_request_log_id: UUID


def reconcile_token_estimate(
    *,
    content_chars: int,
    estimated_prompt_tokens: int,
    actual_prompt_tokens: int | None,
) -> dict | None:
    """Compare the D2 ``chars/3.5`` estimate to the provider's real ``prompt_tokens`` so the constant
    can be calibrated against live traffic (§3.8). Returns None when there is no real usage to
    reconcile against (a pre-transport failure). Pure → unit-tested directly."""
    if not actual_prompt_tokens:
        return None
    return {
        "estimatedPromptTokens": estimated_prompt_tokens,
        "actualPromptTokens": actual_prompt_tokens,
        "estimateRatio": round(estimated_prompt_tokens / actual_prompt_tokens, 4),
        "observedCharsPerToken": round(content_chars / actual_prompt_tokens, 4),
    }


class LLMGateway:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        registry: PromptRegistry | None = None,
        limiter: RedisRateLimiter | None = None,
        context_builder: ContextBuilder | None = None,
        validator: OutputValidator | None = None,
        backoff: BackoffPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._provider_was_injected = provider is not None
        self._provider = provider or get_provider()
        self._registry = registry or get_prompt_registry()
        self._limiter = limiter or get_rate_limiter()
        self._context = context_builder or ContextBuilder()
        self._validator = validator or OutputValidator()
        self._backoff = backoff or BackoffPolicy.from_settings()
        # Injectable so tests drive the backoff loop without real wall-clock sleeps.
        self._sleep = sleep or asyncio.sleep
        self._session_factory = session_factory

    def _backoff_seconds(self, backoff_count: int) -> float:
        """Equal-jitter delay (§10): half the capped exponential delay plus a random half. Jitter
        desynchronizes retries; it never affects tests, which inject a no-op ``sleep``."""
        capped_ms = self._backoff.delay_ms(backoff_count)
        return (capped_ms / 2 + random.random() * (capped_ms / 2)) / 1000

    async def complete(
        self,
        *,
        prompt_key: PromptKey,
        output_schema: type[BriefSummary]
        | type[DetailedSummary]
        | type[PostClassQuiz]
        | type[GeneratedQuizPool]
        | type[AssistantAnswer]
        | type[AssistantGroundedAnswer],
        context_refs: ContextRefs,
        priority: Priority,
        feature: GatewayFeature,
        attempt_number: int = 1,
    ) -> CompletionResult:
        # Application-layer contract (0020 / D-B): the ingestion_job_id column is nullable platform-wide,
        # but the summary features MUST still carry one. The optionality is a property of the new
        # (quiz/assistant) features, NOT a hole punched in the summary contract — enforced here, before
        # any log row is opened, so a summary caller passing None fails loud rather than logging a NULL.
        if feature in FEATURES_REQUIRING_INGESTION_JOB and context_refs.ingestion_job_id is None:
            raise ValueError(f"feature {feature!r} requires context_refs.ingestion_job_id")

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

        fit: FitResult | None = None
        raw = None
        latency_ms: int | None = None
        # In-row transport-retry accumulators (§9): all kept on the single gateway-attempt row.
        provider_attempts = 0
        backoff_count = 0
        last_status: int | None = None
        retry_events: list[dict] = []
        overall_start = time.monotonic()
        try:
            # Deterministic E2E fault: over-context detected before transport.
            if getattr(self._provider, "fault", None) == "invalid_input":
                raise InvalidInput(
                    "deterministic provider forced over-context", error_code="forced_over_context"
                )

            fit = self._context.fit(rendered, estimated_prompt_tokens=estimated)

            # One gateway attempt; the loop re-runs only on a bounded rate_limited backoff (§10).
            while True:
                lease, backoff_count = await self._acquire_with_backoff(
                    fit=fit,
                    priority=priority,
                    retry_events=retry_events,
                    overall_start=overall_start,
                    backoff_count=backoff_count,
                )
                provider_attempts += 1
                attempt_started = time.monotonic()
                try:
                    raw = await asyncio.to_thread(
                        self._provider.send, rendered=rendered, backend=fit.backend
                    )
                except RateLimited as exc:  # provider HTTP 429 (source 2 of §10)
                    await lease.release()
                    backoff_count += 1
                    last_status = exc.status_code or last_status
                    elapsed_ms = int((time.monotonic() - overall_start) * 1000)
                    retry_events.append(
                        {
                            "attempt": len(retry_events) + 1,
                            "statusCode": exc.status_code,
                            "errorClass": exc.error_class,
                            "latencyMs": int((time.monotonic() - attempt_started) * 1000),
                            "atOffsetMs": elapsed_ms,
                        }
                    )
                    if self._backoff.is_exhausted(
                        backoffs_done=backoff_count, elapsed_ms=elapsed_ms
                    ):
                        raise  # terminal rate_limited — recorded by the outer handler
                    await self._sleep(self._backoff_seconds(backoff_count))
                    continue
                except BaseException as exc:
                    await lease.release()
                    # Capture the HTTP status of a terminal provider error (400/401/403/5xx) so
                    # last_provider_status_code is recorded; status code only, never a body (§8).
                    status_code = getattr(exc, "status_code", None)
                    if status_code is not None:
                        last_status = status_code
                    raise
                else:
                    await lease.release()
                    latency_ms = int((time.monotonic() - attempt_started) * 1000)
                    last_status = (
                        raw.status_code if raw.status_code is not None else last_status
                    )
                    break

            parsed = self._validator.validate(
                raw_text=raw.text,
                output_schema=output_schema,
                section_type=context_refs.section_type,
            )

            reconciliation = reconcile_token_estimate(
                content_chars=len(rendered.content),
                estimated_prompt_tokens=estimated,
                actual_prompt_tokens=raw.usage["prompt_tokens"],
            )
            if reconciliation is not None:
                logger.info("llm token estimate reconciliation", extra=reconciliation)

            await close_request_log(
                log_id=log_id,
                status="succeeded",
                backend_used=fit.backend,
                model_id=fit.model_id,
                reasoning_level=raw.reasoning_level,
                usage=raw.usage,
                provider_request_id=raw.provider_request_id,
                latency_ms=latency_ms,
                provider_attempt_count=provider_attempts,
                rate_limit_backoff_count=backoff_count,
                last_provider_status_code=last_status,
                retry_events_json=(retry_events or None),
                backend_route_source="requested",
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
                provider_attempt_count=(provider_attempts or None),
                rate_limit_backoff_count=(backoff_count or None),
                last_provider_status_code=last_status,
                retry_events_json=(retry_events or None),
                backend_route_source=("requested" if fit is not None else None),
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
                provider_attempt_count=(provider_attempts or None),
                session_factory=self._session_factory,
            )
            raise GatewayFailed("unexpected gateway failure") from exc

    async def _acquire_with_backoff(
        self,
        *,
        fit: FitResult,
        priority: Priority,
        retry_events: list[dict],
        overall_start: float,
        backoff_count: int,
    ):
        """Acquire a limiter lease, backing off while OUR Redis budget has no free slot (source 1 of
        §10). A provider HTTP 429 (source 2) is handled at the transport call. Both share one budget
        (``BackoffPolicy``) so the two sources together cannot exceed the per-attempt cap. On
        exhaustion raises terminal ``RateLimited`` for the outer handler. Returns ``(lease,
        backoff_count)`` so the caller keeps an accurate in-row count across both sources."""
        if (
            not self._provider_was_injected
            and getattr(self._provider, "is_deterministic_test_provider", False)
        ):
            return _NoopLimiterLease(), backoff_count

        while True:
            try:
                lease = await self._limiter.acquire(
                    backend=fit.backend,
                    estimated_tokens=fit.reserved_tokens,
                    priority=priority,
                )
                return lease, backoff_count
            except RateLimited as exc:
                code = exc.error_code or ""
                if not code.startswith("limiter_"):
                    raise  # a non-capacity rate_limited classification — do not absorb it
                backoff_count += 1
                elapsed_ms = int((time.monotonic() - overall_start) * 1000)
                retry_events.append(
                    {
                        "attempt": len(retry_events) + 1,
                        "statusCode": None,  # our limiter, not a provider HTTP status
                        "errorClass": exc.error_class,
                        "latencyMs": 0,
                        "atOffsetMs": elapsed_ms,
                    }
                )
                if self._backoff.is_exhausted(
                    backoffs_done=backoff_count, elapsed_ms=elapsed_ms
                ):
                    raise
                await self._sleep(self._backoff_seconds(backoff_count))

    def stream(
        self,
        *,
        prompt_key: PromptKey,
        output_schema: type,
        context_refs: ContextRefs,
        priority: Priority,
    ) -> Iterator[str]:
        raise NotImplementedError("LLM streaming transport lands in Stage 8.3")


class _NoopLimiterLease:
    async def release(self) -> None:
        return None
