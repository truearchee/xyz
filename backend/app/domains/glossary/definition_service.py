"""Async glossary definition generation (Stage 7a).

Mirrors the quiz/summary async pattern, but keyed on the SHARED ``glossary_definition_cache`` row
(cross-student collapse) instead of a per-student job entity. The save winner inserts a ``pending``
cache row and enqueues ONE job per cache key; this job:
  claim (FOR UPDATE) → if already 'generated' fan out + return → else (re)generate via the gateway
  (ONE call, rule 15) → write the definition + provenance onto the cache row → FAN OUT to every pending
  active entry that shares the cache key (this is how two racing students get one model call).

Failure mirrors ``_mark_summary_failed``: the cache row + its pending entries go to 'failed'; a
RETRYABLE gateway status re-raises for a bounded RQ retry, on which ``_claim`` resets 'failed' → 'pending'
and regenerates. A TERMINAL failure does not re-raise, so the row stays 'failed' (a clean terminal
state, never a perpetual spinner).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.glossary.translation_service import (
    GatewayTranslationService,
    TranslationResult,
    TranslationService,
)
from app.platform.db.models import (
    AIRequestLog,
    CourseModule,
    GlossaryDefinitionCache,
    GlossaryEntry,
)
from app.platform.db.session import async_session
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)

# RQ retries are reserved for transient + bounded invalid_output (rule 15).
RQ_RETRY_STATUSES = {"provider_transient", "invalid_output"}

__all__ = ["generate_glossary_definition_async"]


class GlossaryDefinitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class _DefinitionContext:
    cache_row_id: UUID
    cache_key: str
    prompt_version: str
    term: str
    subject_label: str
    entry_type: str
    language: str
    context_text: str


def _now() -> datetime:
    return datetime.now(UTC)


async def generate_glossary_definition_async(
    cache_row_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    translation_service: TranslationService | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)
    service = translation_service or GatewayTranslationService(active_gateway)

    context = await _claim(factory, cache_row_id=cache_row_id)
    if context is None:
        return  # not found, or already generated (fanned out by _claim)

    try:
        result = await service.translate(
            term=context.term,
            subject_label=context.subject_label,
            entry_type=context.entry_type,
            language=context.language,
            context_text=context.context_text,
            cache_key=context.cache_key,
        )
    except GatewayError as exc:
        await _mark_failed(factory, cache_row_id=cache_row_id)
        if exc.status in RQ_RETRY_STATUSES:
            raise  # bounded RQ retry; _claim resets 'failed' → 'pending' on the re-run
        return
    except Exception as exc:  # pragma: no cover - defensive
        await _mark_failed(factory, cache_row_id=cache_row_id)
        raise GlossaryDefinitionError(str(exc)) from None

    await _persist_success(factory, cache_row_id=cache_row_id, result=result)


async def _claim(
    factory: async_sessionmaker[AsyncSession], *, cache_row_id: UUID
) -> _DefinitionContext | None:
    async with factory() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(GlossaryDefinitionCache)
                    .where(GlossaryDefinitionCache.id == cache_row_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if row.status == "generated":
                # Idempotent re-run: make sure any still-pending entries pick up the cached definition.
                await _fan_out_generated(session, row)
                return None

            now = _now()
            row.status = "pending"
            row.updated_at = now
            # On an RQ retry of a terminal-then-reenqueued failure, return its entries to 'generating'.
            await session.execute(
                update(GlossaryEntry)
                .where(
                    GlossaryEntry.cache_key == row.cache_key,
                    GlossaryEntry.status == "active",
                    GlossaryEntry.definition_status == "failed",
                )
                .values(definition_status="pending", updated_at=now)
            )
            module = await session.get(CourseModule, row.subject_id)
            return _DefinitionContext(
                cache_row_id=row.id,
                cache_key=row.cache_key,
                prompt_version=row.prompt_version,
                term=row.term,
                subject_label=module.title if module is not None else "",
                entry_type=row.entry_type,
                language=row.language,
                context_text=row.context_text or "",
            )


async def _persist_success(
    factory: async_sessionmaker[AsyncSession],
    *,
    cache_row_id: UUID,
    result: TranslationResult,
) -> None:
    async with factory() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(GlossaryDefinitionCache)
                    .where(GlossaryDefinitionCache.id == cache_row_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None or row.status == "generated":
                return
            log = await session.get(AIRequestLog, result.ai_request_log_id)
            if log is None:  # pragma: no cover - defensive
                raise GlossaryDefinitionError("AIRequestLog row missing for generated definition")

            now = _now()
            row.status = "generated"
            row.short_definition = result.short_definition
            row.model_id = log.model_id
            row.prompt_content_hash = log.prompt_content_hash
            row.backend_used = log.backend_used
            row.source_content_hash = result.source_content_hash
            row.ai_request_log_id = log.id
            row.generated_at = now
            row.updated_at = now
            await _fan_out_generated(session, row)


async def _fan_out_generated(session: AsyncSession, row: GlossaryDefinitionCache) -> None:
    """Copy the cache row's definition + provenance onto every pending/failed active entry that shares
    the cache key — the cross-student collapse fan-out (and the v1-only assumption: cache_key alone is
    sufficient while only prompt v1 exists)."""
    await session.execute(
        update(GlossaryEntry)
        .where(
            GlossaryEntry.cache_key == row.cache_key,
            GlossaryEntry.status == "active",
            GlossaryEntry.definition_status.in_(("pending", "failed")),
        )
        .values(
            short_definition=row.short_definition,
            definition_status="generated",
            model_id=row.model_id,
            prompt_version=row.prompt_version,
            prompt_content_hash=row.prompt_content_hash,
            backend_used=row.backend_used,
            source_content_hash=row.source_content_hash,
            ai_request_log_id=row.ai_request_log_id,
            definition_generated_at=row.generated_at,
            updated_at=_now(),
        )
    )


async def _mark_failed(
    factory: async_sessionmaker[AsyncSession], *, cache_row_id: UUID
) -> None:
    async with factory() as session:
        async with session.begin():
            row = (
                await session.execute(
                    select(GlossaryDefinitionCache)
                    .where(GlossaryDefinitionCache.id == cache_row_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None or row.status == "generated":
                return
            now = _now()
            row.status = "failed"
            row.updated_at = now
            await session.execute(
                update(GlossaryEntry)
                .where(
                    GlossaryEntry.cache_key == row.cache_key,
                    GlossaryEntry.status == "active",
                    GlossaryEntry.definition_status == "pending",
                )
                .values(definition_status="failed", updated_at=now)
            )
    logger.warning("Glossary definition generation failed", extra={"cacheRowId": str(cache_row_id)})
