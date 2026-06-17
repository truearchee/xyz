"""Pooled-attempt assembly (Stage 6a, Layer 2).

A pooled quiz (recap / exam_prep / mistakes-bank's source quizzes / — after the 6d retrofit — post_class)
does NOT own questions: the QuizDefinition stores SCOPE, and each ATTEMPT is assembled by SAMPLING the
in-scope section pools and SNAPSHOTTING the chosen questions into per-attempt QuizQuestion / AnswerOption
rows. Snapshot-at-assembly is the 4.6 atomic-swap applied to quizzes: once snapshotted, pool invalidation
or regeneration NEVER mutates an in-progress / completed attempt, and scores stay reproducible.

Two-level waiting, scheduler-free (the worker has no RQ scheduler — reserved for 11.1): ``start`` ensures a
pool per in-scope section (herd-locked) and creates a ``generating`` attempt; ``try_assemble`` runs as an
idempotent fenced job that assembles when ALL in-scope pools are ready, no-ops while any is still
generating (a later pool-completion fan-in re-triggers it), or fails the attempt NAMING the section when a
pool terminally failed. Sampling is seedable so the browser gate is deterministic (mirrors the existing
fault-injection env hooks); production derives the seed from the attempt id.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.quiz import config
from app.domains.quiz.pool_service import (
    POOL_FAILED,
    POOL_GENERATING,
    POOL_READY,
    ensure_section_pool,
    _pool_model,
    _pool_prompt_version,
)
from app.domains.quiz.sampling import (
    PoolQuestionRef,
    SectionSamplePlan,
    sample_across_sections,
    seed_for_attempt,
)
from app.platform.db.models import (
    AnswerOption,
    PoolQuestion,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    SectionQuestionPool,
)
from app.platform.db.session import async_session
from app.workers.queues import enqueue_try_assemble_attempt

logger = logging.getLogger(__name__)

# Snapshot-shuffle decorrelation per question (deterministic from the attempt seed; value irrelevant).
_QUESTION_SHUFFLE_MIX = 40503


class PooledQuizUnavailableError(RuntimeError):
    """An in-scope section has no usable detailed summary to build/resolve a pool from (→ unavailable)."""


@dataclass(frozen=True)
class PooledStartResult:
    attempt_id: UUID
    status: str
    created: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _scope_section_ids(definition: QuizDefinition) -> list[UUID]:
    """The in-scope section ids a pooled attempt samples from (QuizDefinition scope). Falls back to the
    single ``module_section_id`` for a definition that does not carry a multi-section ``sectionIds`` list."""
    scope = definition.source_scope or {}
    ids = scope.get("sectionIds")
    if ids:
        return [UUID(str(s)) for s in ids]
    if definition.module_section_id is not None:
        return [definition.module_section_id]
    return []


def _per_section_count(definition: QuizDefinition) -> int:
    if definition.quiz_mode == "post_class":
        return config.POST_CLASS_QUIZ_LENGTH
    return config.RECAP_EXAM_QUESTIONS_PER_SECTION


# ── start (ensure pools + create generating attempt + enqueue assembly after commit) ──────────────
async def start_pooled_attempt(
    factory: async_sessionmaker[AsyncSession] | None,
    *,
    student_id: UUID,
    quiz_definition_id: UUID,
    enqueue: bool = True,
) -> PooledStartResult:
    f = factory or async_session
    if f is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    # Resolve scope + resume a non-terminal attempt.
    async with f() as session:
        definition = await session.get(QuizDefinition, quiz_definition_id)
        if definition is None:
            raise PooledQuizUnavailableError(str(quiz_definition_id))
        section_ids = _scope_section_ids(definition)
        existing = await _non_terminal_attempt(
            session, student_id=student_id, definition_id=quiz_definition_id
        )
        if existing is not None:
            return PooledStartResult(existing.id, existing.status, created=False)

    if not section_ids:
        raise PooledQuizUnavailableError(str(quiz_definition_id))

    # Ensure every in-scope section has a pool (herd-locked; idempotent). A section with no ready detailed
    # summary cannot be pooled — the (6b) eligibility filter excludes those before we get here.
    for section_id in section_ids:
        result = await ensure_section_pool(f, section_id=section_id)
        if result.status == "summary_not_ready":
            raise PooledQuizUnavailableError(str(section_id))

    # Create the generating attempt + enqueue assembly AFTER commit (compensate on enqueue failure).
    async with f() as session:
        async with session.begin():
            next_number = await _next_attempt_number(
                session, student_id=student_id, definition_id=quiz_definition_id
            )
            now = _now()
            attempt = QuizAttempt(
                quiz_definition_id=quiz_definition_id,
                student_id=student_id,
                attempt_number=next_number,
                status="generating",
                started_at=now,
                generation_started_at=now,
            )
            session.add(attempt)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                attempt = None
            else:
                attempt_id = attempt.id

    if attempt is None:
        # Concurrent start race: re-read the now-existing non-terminal attempt.
        async with f() as session:
            existing = await _non_terminal_attempt(
                session, student_id=student_id, definition_id=quiz_definition_id
            )
            if existing is not None:
                return PooledStartResult(existing.id, existing.status, created=False)
        raise PooledQuizUnavailableError(str(quiz_definition_id))

    if enqueue:
        try:
            enqueue_try_assemble_attempt(attempt_id)
        except Exception:
            logger.exception("assembly enqueue failed; compensating to failed")
            await _mark_attempt_failed(
                f,
                attempt_id=attempt_id,
                failure_category="enqueue_failed",
                message="failed to enqueue assembly job",
            )
            return PooledStartResult(attempt_id, "failed", created=True)
    return PooledStartResult(attempt_id, "generating", created=True)


# ── assembly job (claim → check pools → sample + snapshot + flip | wait | fail naming section) ─────
async def try_assemble_attempt_async(
    attempt_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    seed_override: int | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    model = _pool_model()
    prompt_version = _pool_prompt_version()

    async with factory() as session:
        async with session.begin():
            attempt = (
                await session.execute(
                    select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is None or attempt.status != "generating":
                return  # fenced: idempotent (already assembled / failed / not a pooled-generating attempt)
            # Belt-and-suspenders fence: never re-snapshot an attempt that already has questions.
            has_questions = (
                await session.execute(
                    select(QuizQuestion.id)
                    .where(QuizQuestion.quiz_attempt_id == attempt_id)
                    .limit(1)
                )
            ).first()
            if has_questions is not None:
                return

            definition = await session.get(QuizDefinition, attempt.quiz_definition_id)
            if definition is None:  # pragma: no cover - FK guarantees this
                return
            section_ids = _scope_section_ids(definition)

            ready_pools: list[SectionQuestionPool] = []
            failed_section: UUID | None = None
            still_generating = False
            for section_id in section_ids:
                pool = await _latest_pool(
                    session, section_id=section_id, model=model, prompt_version=prompt_version
                )
                if pool is not None and pool.status == POOL_READY:
                    ready_pools.append(pool)
                elif pool is not None and pool.status == POOL_GENERATING:
                    still_generating = True
                elif pool is None or pool.status == POOL_FAILED:
                    failed_section = section_id
                    break

            if failed_section is not None:
                # Name the terminally-failed section — the quiz must never hang forever in "preparing".
                now = _now()
                attempt.status = "failed"
                attempt.failure_category = "provider_error"
                attempt.failure_message_sanitized = (
                    f"question generation failed for one section ({failed_section})"
                )
                attempt.generation_completed_at = now
                attempt.updated_at = now
                return
            if still_generating or len(ready_pools) != len(section_ids):
                return  # not all pools ready → wait (a later pool-completion fan-in re-triggers)

            await _assemble(
                session,
                attempt=attempt,
                definition=definition,
                ready_pools=ready_pools,
                seed_override=seed_override,
            )


async def _assemble(
    session: AsyncSession,
    *,
    attempt: QuizAttempt,
    definition: QuizDefinition,
    ready_pools: list[SectionQuestionPool],
    seed_override: int | None,
) -> None:
    per_section = _per_section_count(definition)
    plans: list[SectionSamplePlan] = []
    for pool in ready_pools:
        refs = await _load_pool_refs(
            session, pool=pool, student_id=attempt.student_id
        )
        plans.append(
            SectionSamplePlan(section_id=pool.module_section_id, pool_questions=refs, count=per_section)
        )

    seed = seed_for_attempt(attempt.id, override=seed_override)
    chosen = sample_across_sections(plans, seed=seed)
    pool_by_section = {p.module_section_id: p for p in ready_pools}
    section_by_pool_question = await _section_for_pool_questions(
        session, [c.id for c in chosen]
    )

    display_order = 0
    for ref in chosen:
        section_id = section_by_pool_question.get(ref.id)
        pool = pool_by_section.get(section_id) if section_id is not None else None
        question = QuizQuestion(
            quiz_attempt_id=attempt.id,
            question_text=ref.question_text,
            display_order=display_order,
            question_type="multiple_choice",
            explanation=ref.explanation,
            source_type="new_generated",
            source_pool_question_id=ref.id,
            source_module_id=definition.module_id,
            source_section_id=section_id,
            source_summary_id=(pool.source_summary_id if pool is not None else None),
            model_name=(pool.model if pool is not None else None),
            prompt_version=(pool.prompt_version if pool is not None else None),
        )
        session.add(question)
        await session.flush()
        # Snapshot-shuffle the options (seeded → reproducible); correctness rides on is_correct, not slot.
        rng = random.Random(seed ^ (display_order * _QUESTION_SHUFFLE_MIX))
        orders = list(range(len(ref.options)))
        rng.shuffle(orders)
        for option, order in zip(ref.options, orders):
            session.add(
                AnswerOption(
                    quiz_question_id=question.id,
                    text=str(option.get("text", "")),
                    display_order=order,
                    is_correct=bool(option.get("isCorrect", False)),
                )
            )
        display_order += 1

    now = _now()
    first_pool = ready_pools[0]
    attempt.status = "in_progress"
    attempt.total_questions = display_order
    attempt.new_question_count = display_order
    attempt.mistake_review_question_count = 0
    attempt.model_name = first_pool.model
    attempt.prompt_version = first_pool.prompt_version
    attempt.backend_used = "nvidia"
    attempt.generation_completed_at = now
    attempt.updated_at = now


# ── reads ─────────────────────────────────────────────────────────────────────────────────────────
async def _latest_pool(
    session: AsyncSession, *, section_id: UUID, model: str, prompt_version: str
) -> SectionQuestionPool | None:
    """The decisive pool for a section: the live ready pool if any, else the most recent
    generating/failed (so the caller can distinguish "wait" from "fail"). Superseded pools are ignored."""
    return (
        await session.execute(
            select(SectionQuestionPool)
            .where(
                SectionQuestionPool.module_section_id == section_id,
                SectionQuestionPool.model == model,
                SectionQuestionPool.prompt_version == prompt_version,
                SectionQuestionPool.status.in_((POOL_READY, POOL_GENERATING, POOL_FAILED)),
            )
            .order_by(
                # ready first, then most recent.
                (SectionQuestionPool.status == POOL_READY).desc(),
                SectionQuestionPool.created_at.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def _load_pool_refs(
    session: AsyncSession, *, pool: SectionQuestionPool, student_id: UUID
) -> list[PoolQuestionRef]:
    """Load a pool's questions + THIS student's exposure (recency) for recency-biased sampling."""
    questions = (
        await session.execute(
            select(PoolQuestion).where(PoolQuestion.section_question_pool_id == pool.id)
        )
    ).scalars().all()
    if not questions:
        return []
    ids = [q.id for q in questions]
    exposure_rows = (
        await session.execute(
            select(
                QuizQuestion.source_pool_question_id,
                func.max(QuizQuestion.created_at),
            )
            .join(QuizAttempt, QuizAttempt.id == QuizQuestion.quiz_attempt_id)
            .where(
                QuizAttempt.student_id == student_id,
                QuizQuestion.source_pool_question_id.in_(ids),
            )
            .group_by(QuizQuestion.source_pool_question_id)
        )
    ).all()
    last_seen = {row[0]: row[1] for row in exposure_rows}
    return [
        PoolQuestionRef(
            id=q.id,
            question_text=q.question_text,
            explanation=q.explanation,
            options=list(q.options or []),
            last_seen=last_seen.get(q.id),
        )
        for q in questions
    ]


async def _section_for_pool_questions(
    session: AsyncSession, pool_question_ids: list[UUID]
) -> dict[UUID, UUID]:
    if not pool_question_ids:
        return {}
    rows = (
        await session.execute(
            select(PoolQuestion.id, SectionQuestionPool.module_section_id)
            .join(SectionQuestionPool, SectionQuestionPool.id == PoolQuestion.section_question_pool_id)
            .where(PoolQuestion.id.in_(pool_question_ids))
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def _non_terminal_attempt(
    session: AsyncSession, *, student_id: UUID, definition_id: UUID
) -> QuizAttempt | None:
    return (
        await session.execute(
            select(QuizAttempt).where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.quiz_definition_id == definition_id,
                QuizAttempt.status.in_(("generating", "in_progress")),
            )
        )
    ).scalar_one_or_none()


async def _next_attempt_number(
    session: AsyncSession, *, student_id: UUID, definition_id: UUID
) -> int:
    current_max = (
        await session.execute(
            select(func.max(QuizAttempt.attempt_number)).where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.quiz_definition_id == definition_id,
            )
        )
    ).scalar()
    return (current_max or 0) + 1


async def _mark_attempt_failed(
    factory: async_sessionmaker[AsyncSession],
    *,
    attempt_id: UUID,
    failure_category: str,
    message: str,
) -> None:
    async with factory() as session:
        async with session.begin():
            attempt = (
                await session.execute(
                    select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is None or attempt.status != "generating":
                return
            now = _now()
            attempt.status = "failed"
            attempt.failure_category = failure_category
            attempt.failure_message_sanitized = message
            attempt.generation_completed_at = now
            attempt.updated_at = now
