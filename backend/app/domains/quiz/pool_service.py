"""Section question pool service (Stage 6a, Layer 1 — capacity ADR).

``ensure_section_pool`` is the get-or-create entry: it reuses a fresh ``ready`` pool, supersedes a stale one
(content-hash mismatch → atomic-swap), attaches to an in-flight ``generating`` pool (the herd lock — the
one-active-generating partial-unique means EXACTLY ONE generation runs no matter how many students arrive
at once), surfaces a terminal ``failed`` pool (explicit retry only — never an auto-retry storm), or creates
a ``generating`` pool and enqueues generation AFTER commit (a rollback can never leave a phantom job).

``generate_section_pool_async`` is the RQ job: ONE gateway call (rule 15) from the section's DETAILED
SUMMARY through the 4.5 chain → validate (``GeneratedQuizPool``) → persist ``pool_questions`` → flip
``ready`` → FAN-IN (re-enqueue assembly for every attempt waiting on this section — the scheduler-free
two-level-waiting driver; the worker has no RQ scheduler, reserved for 11.1). A transient/invalid failure
marks the pool ``failed`` and re-raises for a bounded RQ retry (rule 15); the claim re-activates a
retryable ``failed`` pool back to ``generating`` so the retry actually regenerates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.quiz.summary_text import summary_content_hash, summary_to_text
from app.platform.db.models import (
    GeneratedLectureSummary,
    ModuleSection,
    PoolQuestion,
    QuizAttempt,
    QuizDefinition,
    SectionQuestionPool,
)
from app.platform.db.session import async_session
from app.platform.llm.context import model_for_backend
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.prompt import PromptKey
from app.platform.llm.models.quiz import GeneratedQuizPool
from app.platform.query.quiz_availability_read import resolve_quiz_source_summary
from app.workers.queues import (
    enqueue_generate_section_pool,
    enqueue_try_assemble_attempt,
)

logger = logging.getLogger(__name__)

QUIZ_POOL_PROMPT_KEY = PromptKey("quiz_pool_generation", "v1")
QUIZ_POOL_FEATURE = "quiz_pool"
# Gateway statuses warranting an RQ retry (rule 15: transient + bounded invalid_output only).
RQ_RETRY_STATUSES = {"provider_transient", "invalid_output"}
_RQ_RETRYABLE_CATEGORIES = {"provider_error", "invalid_output"}

POOL_READY = "ready"
POOL_GENERATING = "generating"
POOL_FAILED = "failed"
POOL_SUPERSEDED = "superseded"
# ensure_section_pool result statuses (POOL_* plus this "no usable detailed summary yet" signal).
POOL_SUMMARY_NOT_READY = "summary_not_ready"

__all__ = [
    "EnsurePoolResult",
    "ensure_section_pool",
    "retry_section_pool",
    "generate_section_pool_async",
    "mark_pool_failed",
    "QUIZ_POOL_PROMPT_KEY",
    "QUIZ_POOL_FEATURE",
]


def _now() -> datetime:
    return datetime.now(UTC)


def _pool_model() -> str:
    """The reasoning route's resolved model id (what AIRequestLog.model_id records). Pool generation always
    uses the nvidia/reasoning route — the prompt declares it and that route has no fallback."""
    return model_for_backend("nvidia")


def _pool_prompt_version() -> str:
    return QUIZ_POOL_PROMPT_KEY.version


@dataclass(frozen=True)
class EnsurePoolResult:
    status: str  # ready | generating | failed | summary_not_ready
    pool_id: UUID | None


@dataclass(frozen=True)
class _PoolGenContext:
    pool_id: UUID
    section_id: UUID
    section_type: str
    summary_text: str
    input_hash: str
    ai_request_log_id: UUID | None = None


async def _pool_by_status(
    session: AsyncSession,
    *,
    section_id: UUID,
    model: str,
    prompt_version: str,
    status: str,
    for_update: bool = False,
) -> SectionQuestionPool | None:
    stmt = (
        select(SectionQuestionPool)
        .where(
            SectionQuestionPool.module_section_id == section_id,
            SectionQuestionPool.model == model,
            SectionQuestionPool.prompt_version == prompt_version,
            SectionQuestionPool.status == status,
        )
        .order_by(SectionQuestionPool.created_at.desc())
        .limit(1)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


# ── ensure (get-or-create + staleness + herd lock + enqueue-after-commit) ─────────────────────────
async def ensure_section_pool(
    factory: async_sessionmaker[AsyncSession] | None,
    *,
    section_id: UUID,
) -> EnsurePoolResult:
    f = factory or async_session
    if f is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    model = _pool_model()
    prompt_version = _pool_prompt_version()

    # Phase A: resolve the active detailed summary + supersede a stale ready pool (frees the ready slot).
    async with f() as session:
        async with session.begin():
            section = await session.get(ModuleSection, section_id)
            if section is None:
                return EnsurePoolResult(POOL_SUMMARY_NOT_READY, None)
            summary = await resolve_quiz_source_summary(
                session, section_id=section_id, section_type=section.type
            )
            if summary is None:
                return EnsurePoolResult(POOL_SUMMARY_NOT_READY, None)
            current_hash = summary_content_hash(summary.content_json)
            summary_id = summary.id

            ready = await _pool_by_status(
                session, section_id=section_id, model=model, prompt_version=prompt_version, status=POOL_READY
            )
            if ready is not None:
                if ready.source_summary_content_hash == current_hash:
                    return EnsurePoolResult(POOL_READY, ready.id)
                # Stale → supersede (guarded: only if still ready). The 4.6 atomic-swap applied to pools.
                await session.execute(
                    update(SectionQuestionPool)
                    .where(
                        SectionQuestionPool.id == ready.id,
                        SectionQuestionPool.status == POOL_READY,
                    )
                    .values(status=POOL_SUPERSEDED, updated_at=_now())
                )

    # Phase B: attach to generating / surface failed / create + enqueue after commit.
    new_pool_id: UUID | None = None
    async with f() as session:
        async with session.begin():
            generating = await _pool_by_status(
                session,
                section_id=section_id,
                model=model,
                prompt_version=prompt_version,
                status=POOL_GENERATING,
            )
            if generating is not None:
                return EnsurePoolResult(POOL_GENERATING, generating.id)
            ready = await _pool_by_status(
                session, section_id=section_id, model=model, prompt_version=prompt_version, status=POOL_READY
            )
            if ready is not None and ready.source_summary_content_hash == current_hash:
                return EnsurePoolResult(POOL_READY, ready.id)
            failed = await _pool_by_status(
                session, section_id=section_id, model=model, prompt_version=prompt_version, status=POOL_FAILED
            )
            if failed is not None:
                return EnsurePoolResult(POOL_FAILED, failed.id)

            pool = SectionQuestionPool(
                module_section_id=section_id,
                model=model,
                prompt_version=prompt_version,
                source_summary_id=summary_id,
                source_summary_content_hash=current_hash,
                status=POOL_GENERATING,
            )
            session.add(pool)
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                # Lost the herd race: exactly one generating pool may exist for the key. Attach to it.
                generating = await _pool_by_status(
                    session,
                    section_id=section_id,
                    model=model,
                    prompt_version=prompt_version,
                    status=POOL_GENERATING,
                )
                if generating is not None:
                    return EnsurePoolResult(POOL_GENERATING, generating.id)
                raise  # pragma: no cover - the unique violation implies a generating row exists
            new_pool_id = pool.id

    try:
        enqueue_generate_section_pool(new_pool_id)
    except Exception:
        logger.exception("pool generation enqueue failed; compensating to failed")
        await mark_pool_failed(
            f,
            pool_id=new_pool_id,
            failure_category="provider_error",
            message="failed to enqueue generation job",
        )
        return EnsurePoolResult(POOL_FAILED, new_pool_id)
    return EnsurePoolResult(POOL_GENERATING, new_pool_id)


async def retry_section_pool(
    factory: async_sessionmaker[AsyncSession] | None, *, pool_id: UUID
) -> EnsurePoolResult:
    """The explicit retry affordance: re-enqueue a terminally-failed pool under the same herd lock.
    Re-activates ``failed → generating`` (idempotent; stands down if another generation already won the
    slot) and enqueues after commit. A no-op for a pool that is not failed."""
    f = factory or async_session
    re_enqueue = False
    async with f() as session:
        async with session.begin():
            pool = (
                await session.execute(
                    select(SectionQuestionPool)
                    .where(SectionQuestionPool.id == pool_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if pool is None:
                return EnsurePoolResult(POOL_FAILED, pool_id)
            if pool.status in (POOL_GENERATING, POOL_READY):
                return EnsurePoolResult(pool.status, pool.id)  # already (re)generating / ready
            if pool.status != POOL_FAILED:
                return EnsurePoolResult(pool.status, pool.id)
            pool.status = POOL_GENERATING
            pool.failure_category = None
            pool.failure_message_sanitized = None
            pool.updated_at = _now()
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                # Another generation already holds the one-active-generating slot — stand down.
                return EnsurePoolResult(POOL_GENERATING, pool_id)
            re_enqueue = True
    if re_enqueue:
        enqueue_generate_section_pool(pool_id)
    return EnsurePoolResult(POOL_GENERATING, pool_id)


# ── generation job (claim → gateway → persist → ready → fan-in) ───────────────────────────────────
async def generate_section_pool_async(
    pool_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim_pool_generation(factory, pool_id=pool_id)
    if context is None:
        return  # fenced: not generating, or questions already persisted (idempotent re-run)

    try:
        result = await active_gateway.complete(
            prompt_key=QUIZ_POOL_PROMPT_KEY,
            output_schema=GeneratedQuizPool,
            context_refs=ContextRefs(
                ingestion_job_id=None,  # pool generation has no IngestionJob (0020)
                transcript_text=context.summary_text,
                input_content_hash=context.input_hash,
                section_type=context.section_type,
            ),
            priority="background",
            feature=QUIZ_POOL_FEATURE,
            attempt_number=1,
        )
    except GatewayError as exc:
        category = "invalid_output" if exc.status == "invalid_output" else "provider_error"
        await mark_pool_failed(
            factory, pool_id=pool_id, failure_category=category, message=_sanitize_error(exc)
        )
        if exc.status in RQ_RETRY_STATUSES:
            raise  # bounded RQ retry
        return
    except Exception:  # pragma: no cover - defensive
        await mark_pool_failed(
            factory, pool_id=pool_id, failure_category="provider_error", message="pool generation failed"
        )
        raise

    section_id = await _persist_pool_success(factory, pool_id=pool_id, result=result)
    if section_id is not None:
        # FAN-IN (scheduler-free two-level waiting): re-trigger assembly for every attempt waiting on
        # this section. The LAST in-scope pool to become ready is the one that lets the attempt assemble.
        await enqueue_assembly_for_waiting_attempts(factory, section_id=section_id)


async def _claim_pool_generation(
    factory: async_sessionmaker[AsyncSession], *, pool_id: UUID
) -> _PoolGenContext | None:
    async with factory() as session:
        async with session.begin():
            pool = (
                await session.execute(
                    select(SectionQuestionPool)
                    .where(SectionQuestionPool.id == pool_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if pool is None:
                return None
            if pool.status == POOL_FAILED and pool.failure_category in _RQ_RETRYABLE_CATEGORIES:
                # RQ retry of a transiently-failed pool: re-activate failed → generating (re-acquiring the
                # herd slot). If another generation already holds the slot, stand down.
                pool.status = POOL_GENERATING
                pool.failure_category = None
                pool.failure_message_sanitized = None
                pool.updated_at = _now()
                try:
                    async with session.begin_nested():
                        await session.flush()
                except IntegrityError:
                    return None
            elif pool.status != POOL_GENERATING:
                return None
            # Fence: generate only if no pool questions exist yet (idempotent re-run guard).
            has_questions = (
                await session.execute(
                    select(PoolQuestion.id)
                    .where(PoolQuestion.section_question_pool_id == pool_id)
                    .limit(1)
                )
            ).first()
            if has_questions is not None:
                return None

            section = await session.get(ModuleSection, pool.module_section_id)
            if section is None:  # pragma: no cover - FK guarantees this
                return None
            summary = (
                await session.get(GeneratedLectureSummary, pool.source_summary_id)
                if pool.source_summary_id is not None
                else None
            )
            if summary is None:
                return None
            return _PoolGenContext(
                pool_id=pool.id,
                section_id=section.id,
                section_type=section.type,
                summary_text=summary_to_text(summary.content_json),
                input_hash=summary_content_hash(summary.content_json),
            )


async def _persist_pool_success(
    factory: async_sessionmaker[AsyncSession], *, pool_id: UUID, result: dict
) -> UUID | None:
    parsed: GeneratedQuizPool = result["parsed"]
    async with factory() as session:
        async with session.begin():
            pool = (
                await session.execute(
                    select(SectionQuestionPool)
                    .where(SectionQuestionPool.id == pool_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if pool is None or pool.status != POOL_GENERATING:
                return None  # fenced (raced to terminal / superseded)
            has_questions = (
                await session.execute(
                    select(PoolQuestion.id)
                    .where(PoolQuestion.section_question_pool_id == pool_id)
                    .limit(1)
                )
            ).first()
            if has_questions is not None:
                return None  # idempotent: a concurrent run already persisted
            for question in parsed.questions:
                session.add(
                    PoolQuestion(
                        section_question_pool_id=pool.id,
                        question_text=question.question_text,
                        explanation=question.explanation,
                        options=[
                            {"text": opt.text, "isCorrect": opt.is_correct}
                            for opt in question.options
                        ],
                    )
                )
            pool.status = POOL_READY
            pool.ai_request_log_id = result.get("ai_request_log_id")
            pool.updated_at = _now()
            return pool.module_section_id


async def mark_pool_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    pool_id: UUID,
    failure_category: str,
    message: str,
) -> None:
    async with factory() as session:
        async with session.begin():
            pool = (
                await session.execute(
                    select(SectionQuestionPool)
                    .where(SectionQuestionPool.id == pool_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if pool is None or pool.status != POOL_GENERATING:
                return  # never overwrite a terminal/ready/superseded pool
            now = _now()
            pool.status = POOL_FAILED
            pool.failure_category = failure_category
            pool.failure_message_sanitized = message
            pool.updated_at = now
    logger.warning(
        "Section pool generation failed",
        extra={"section_question_pool_id": str(pool_id), "failure_category": failure_category},
    )


async def enqueue_assembly_for_waiting_attempts(
    factory: async_sessionmaker[AsyncSession], *, section_id: UUID
) -> None:
    """Fan-in: enqueue an (idempotent) assembly job for every ``generating`` attempt whose scope includes
    this section. Drives the scheduler-free two-level wait — no pool→attempt registry is kept; the waiting
    set is derived from the QuizDefinition scope (``source_scope.sectionIds``)."""
    async with factory() as session:
        rows = (
            await session.execute(
                select(QuizAttempt.id)
                .join(QuizDefinition, QuizDefinition.id == QuizAttempt.quiz_definition_id)
                .where(
                    QuizAttempt.status == "generating",
                    text("quiz_definitions.source_scope->'sectionIds' @> :needle"),
                )
                .params(needle=f'["{section_id}"]')
            )
        ).all()
    for (attempt_id,) in rows:
        try:
            enqueue_try_assemble_attempt(attempt_id)
        except Exception:  # pragma: no cover - one bad enqueue must not block the rest
            logger.exception("assembly fan-in enqueue failed for attempt %s", attempt_id)


def _sanitize_error(exc: GatewayError) -> str:
    code = f" ({exc.error_code})" if exc.error_code else ""
    return f"{exc.status}{code}"
