"""Assistant answer generation (Stage 8.1) — the interactive gateway turn.

Mirrors the quiz generation pipeline (claim → gateway → atomic persist → mark-failed), but at
INTERACTIVE priority (rule 15, first consumer of the reserved headroom) and over the conversation's
bounded recent history (decision 1) — no lecture grounding yet (8.2 adds it). ONE gateway call per
turn (rule 15) through the full 4.5 chain (PromptRegistry → limiter → AIRequestLog → OutputValidator →
provenance). The pending assistant message is claimed FOR UPDATE and fenced so a duplicate/lost RQ run
is idempotent; a transiently-failed message is re-activated on a bounded RQ retry (transient /
invalid_output only), exactly like the 4.5 summary claim.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.db.models import (
    AIRequestLog,
    AssistantConversation,
    AssistantMessage,
    ModuleSection,
)
from app.platform.db.session import async_session
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.assistant import AssistantAnswer
from app.platform.llm.models.prompt import PromptKey

logger = logging.getLogger(__name__)

ASSISTANT_PROMPT_KEY = PromptKey("assistant", "v1")
ASSISTANT_FEATURE = "assistant"
# Bounded history sent to the model (decision 1) — older turns stay stored + visible, drop from the prompt.
HISTORY_MAX_MESSAGES = 20
# Gateway statuses that warrant an RQ retry (rule 15: transient + bounded invalid_output only). A
# terminal rate_limited / config / auth is NOT RQ-retried (the student may retry manually).
RQ_RETRY_STATUSES = {"provider_transient", "invalid_output"}
_RETRYABLE_STATUSES = {"provider_transient", "invalid_output", "rate_limited"}
_FRIENDLY_FAILURE = {
    "rate_limited": "The assistant is busy right now. Please try again in a moment.",
    "provider_transient": "The assistant had a temporary problem. Please try again.",
    "invalid_output": "The assistant couldn't produce a good answer. Please try again.",
    "invalid_input": "This conversation is too long for the assistant.",
    "provider_config_error": "The assistant is unavailable right now.",
    "provider_auth_error": "The assistant is unavailable right now.",
    "failed": "The assistant failed to answer. Please try again.",
}


class AssistantGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class _TurnContext:
    message_id: UUID
    section_type: str
    history_text: str
    input_hash: str


def _now() -> datetime:
    return datetime.now(UTC)


def _format_history(messages: list[AssistantMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        speaker = "Student" if m.role == "user" else "Assistant"
        text = (m.content or "").strip()
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n\n".join(lines)


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def generate_assistant_answer_async(
    message_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim_message(factory, message_id=message_id)
    if context is None:
        return  # fenced: not a pending assistant message (already answered, or non-retryable failure)

    try:
        result = await active_gateway.complete(
            prompt_key=ASSISTANT_PROMPT_KEY,
            output_schema=AssistantAnswer,
            context_refs=ContextRefs(
                ingestion_job_id=None,  # assistant has no IngestionJob (0020)
                transcript_text=context.history_text,
                input_content_hash=context.input_hash,
                section_type=context.section_type,
            ),
            priority="interactive",
            feature=ASSISTANT_FEATURE,
            attempt_number=1,
        )
    except GatewayError as exc:
        await _mark_message_failed(
            factory,
            message_id=message_id,
            failure_category=exc.status,
            message=_FRIENDLY_FAILURE.get(exc.status, _FRIENDLY_FAILURE["failed"]),
            retryable=exc.status in _RETRYABLE_STATUSES,
        )
        if exc.status in RQ_RETRY_STATUSES:
            raise  # bounded RQ retry
        return
    except Exception as exc:  # pragma: no cover - defensive
        await _mark_message_failed(
            factory,
            message_id=message_id,
            failure_category="failed",
            message=_FRIENDLY_FAILURE["failed"],
            retryable=True,
        )
        raise AssistantGenerationError(str(exc)) from None

    await _persist_answer(factory, message_id=message_id, result=result)


async def _claim_message(
    factory: async_sessionmaker[AsyncSession], *, message_id: UUID
) -> _TurnContext | None:
    async with factory() as session:
        async with session.begin():
            msg = (
                await session.execute(
                    select(AssistantMessage)
                    .where(AssistantMessage.id == message_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if msg is None or msg.role != "assistant":
                return None
            if msg.status == "failed" and msg.retryable:
                # RQ retry of a transiently-failed turn: re-activate to pending (mirrors the 4.5 claim).
                msg.status = "pending"
                msg.failure_category = None
                msg.failure_message_sanitized = None
                msg.updated_at = _now()
            elif msg.status != "pending":
                return None
            if msg.content is not None:  # belt-and-suspenders: already answered
                return None

            conv = await session.get(AssistantConversation, msg.conversation_id)
            section_type = "lecture"
            if conv is not None and conv.attached_section_id is not None:
                section = await session.get(ModuleSection, conv.attached_section_id)
                if section is not None:
                    section_type = section.type

            prior = (
                (
                    await session.execute(
                        select(AssistantMessage)
                        .where(
                            AssistantMessage.conversation_id == msg.conversation_id,
                            AssistantMessage.id != msg.id,
                            AssistantMessage.created_at <= msg.created_at,
                            AssistantMessage.content.is_not(None),
                        )
                        .order_by(
                            AssistantMessage.created_at.desc(), AssistantMessage.id.desc()
                        )
                        .limit(HISTORY_MAX_MESSAGES)
                    )
                )
                .scalars()
                .all()
            )
            history = list(reversed(prior))  # back to chronological order
            history_text = _format_history(history)
            return _TurnContext(
                message_id=msg.id,
                section_type=section_type,
                history_text=history_text,
                input_hash=_input_hash(history_text),
            )


async def _persist_answer(
    factory: async_sessionmaker[AsyncSession], *, message_id: UUID, result: dict
) -> None:
    parsed: AssistantAnswer = result["parsed"]
    async with factory() as session:
        async with session.begin():
            msg = (
                await session.execute(
                    select(AssistantMessage)
                    .where(AssistantMessage.id == message_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            # Fence: idempotent — a concurrent/duplicate run that already completed this message no-ops.
            if msg is None or msg.status != "pending":
                return
            log = await session.get(AIRequestLog, result["ai_request_log_id"])
            now = _now()
            msg.content = parsed.answer
            msg.status = "completed"
            msg.grounding_status = None  # 8.2 populates this from retrieval
            msg.model_id = log.model_id if log is not None else result["model_id_echoed"]
            msg.prompt_version = log.prompt_version if log is not None else ASSISTANT_PROMPT_KEY.version
            msg.backend_used = log.backend_used if log is not None else result["backend_used"]
            msg.input_content_hash = log.input_content_hash if log is not None else None
            msg.ai_request_log_id = result["ai_request_log_id"]
            msg.generated_at = now
            msg.failure_category = None
            msg.failure_message_sanitized = None
            msg.retryable = False
            msg.updated_at = now


async def _mark_message_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    message_id: UUID,
    failure_category: str,
    message: str,
    retryable: bool,
) -> None:
    async with factory() as session:
        async with session.begin():
            msg = (
                await session.execute(
                    select(AssistantMessage)
                    .where(AssistantMessage.id == message_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if msg is None or msg.status != "pending":
                return  # never overwrite a terminal/completed message
            now = _now()
            msg.status = "failed"
            msg.failure_category = failure_category
            msg.failure_message_sanitized = message
            msg.retryable = retryable
            msg.updated_at = now
    logger.warning(
        "Assistant answer generation failed",
        extra={"assistant_message_id": str(message_id), "failure_category": failure_category},
    )
