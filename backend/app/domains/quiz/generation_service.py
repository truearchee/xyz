"""Post-class quiz generation pipeline (Stage 5b, locks 1/2/3/4/5/6).

Lazy, per-attempt generation: ``start_quiz_attempt`` get-or-creates the QuizDefinition, creates a
``generating`` QuizAttempt snapshotting the active detailed-summary provenance, COMMITS, then enqueues
``quiz-generate:{attemptId}`` AFTER commit (a rollback can never leave a phantom job; an enqueue
failure is compensated to ``failed/enqueue_failed``). The job (``generate_post_class_quiz_async``)
makes ONE gateway call (rule 15) through the 4.5 chain, validates, and in a SINGLE transaction persists
all questions+options (shuffled display order), stamps provenance, and flips ``generating →
in_progress``. Because that flip is atomic with the question writes, ``status == 'generating'`` PROVABLY
means "no questions persisted" — the fence and the reaper are unambiguous.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.db.models import (
    AIRequestLog,
    AnswerOption,
    GeneratedLectureSummary,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
)
from app.platform.db.session import async_session
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.prompt import PromptKey
from app.platform.llm.models.quiz import PostClassQuiz
from app.platform.query.quiz_availability_read import resolve_quiz_source_summary
from app.workers.queues import enqueue_generate_post_class_quiz

logger = logging.getLogger(__name__)

QUIZ_PROMPT_KEY = PromptKey("post_class_quiz_generation", "v1")
QUIZ_FEATURE = "post_class_quiz"
QUIZ_MODE_POST_CLASS = "post_class"
QUESTION_POLICY = {"count": 10, "optionsPerQuestion": 4}

# Gateway statuses that warrant an RQ retry (rule 15: transient + bounded invalid_output only).
RQ_RETRY_STATUSES = {"provider_transient", "invalid_output"}
# Quiz failure categories an RQ retry may re-activate (the transient ones). crashed (reaper) and
# enqueue_failed are terminal — Start Over makes a new attempt.
_RQ_RETRYABLE_CATEGORIES = {"provider_error", "invalid_output"}

__all__ = [
    "QuizUnavailableError",
    "SectionNotFoundError",
    "StartResult",
    "start_quiz_attempt",
    "generate_post_class_quiz_async",
]


class QuizUnavailableError(RuntimeError):
    """No active, READY detailed summary to build a quiz from (→ 409 quiz_unavailable)."""


class SectionNotFoundError(RuntimeError):
    """The section does not exist (→ 404; visibility/auth is enforced by the 5c endpoint)."""


class QuizGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class StartResult:
    attempt_id: UUID
    status: str
    created: bool  # True = a new generating attempt; False = resumed a non-terminal attempt


@dataclass(frozen=True)
class _GenContext:
    attempt_id: UUID
    module_id: UUID
    section_id: UUID
    section_type: str
    source_summary_id: UUID
    summary_text: str
    input_hash: str


def _now() -> datetime:
    return datetime.now(UTC)


def _summary_content_hash(content_json: dict) -> str:
    canonical = json.dumps(content_json, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _summary_to_text(content_json: dict) -> str:
    """Flatten a stored detailed-summary ``content_json`` to plain prompt input text. Kept in the quiz
    domain (no cross-domain import) — the deterministic adapter ignores it; the real provider reads it."""
    cj = content_json or {}
    parts: list[str] = []
    overview = str(cj.get("overview", "")).strip()
    if overview:
        parts.append(overview)
    for label, key in (
        ("Key concepts", "keyConcepts"),
        ("Main explanations", "mainExplanations"),
        ("Examples", "examples"),
        ("Exam-relevant points", "examRelevantPoints"),
        ("Lab notes", "labNotes"),
    ):
        items = cj.get(key) or []
        if items:
            parts.append(label + ": " + "; ".join(str(i) for i in items))
    definitions = cj.get("importantDefinitions") or []
    if definitions:
        rendered = "; ".join(
            f"{d.get('term', '')}: {d.get('definition', '')}".strip(": ")
            for d in definitions
            if isinstance(d, dict)
        )
        if rendered:
            parts.append("Important definitions: " + rendered)
    return "\n".join(parts).strip()


# ── Start (get-or-create definition + create/resume attempt + enqueue-after-commit) ──────────────
async def start_quiz_attempt(
    factory: async_sessionmaker[AsyncSession] | None,
    *,
    student_id: UUID,
    section_id: UUID,
    enqueue: bool = True,
) -> StartResult:
    """Resolve the detailed summary (none → QuizUnavailableError), get-or-create the post_class
    definition, resume a non-terminal attempt or create a new ``generating`` one (COMMIT), then enqueue
    AFTER commit (compensating to ``failed/enqueue_failed`` on enqueue error). Visibility/auth is the
    5c endpoint's job; this service is the generation entry."""
    f = factory or async_session
    if f is None:
        raise RuntimeError("DATABASE_URL environment variable is required")

    outcome = await _create_or_resume_attempt(f, student_id=student_id, section_id=section_id)
    if outcome.created and enqueue:
        try:
            job_id = enqueue_generate_post_class_quiz(outcome.attempt_id)
        except Exception:
            logger.exception("quiz generation enqueue failed; compensating to failed")
            await _mark_attempt_failed(
                f,
                attempt_id=outcome.attempt_id,
                failure_category="enqueue_failed",
                message="failed to enqueue generation job",
            )
            return StartResult(outcome.attempt_id, "failed", created=True)
        await _stamp_generation_job_id(f, attempt_id=outcome.attempt_id, job_id=job_id)
    return outcome


async def _create_or_resume_attempt(
    factory: async_sessionmaker[AsyncSession],
    *,
    student_id: UUID,
    section_id: UUID,
) -> StartResult:
    async with factory() as session:
        async with session.begin():
            section = await session.get(ModuleSection, section_id)
            if section is None:
                raise SectionNotFoundError(str(section_id))

            summary = await resolve_quiz_source_summary(
                session, section_id=section_id, section_type=section.type
            )
            if summary is None:
                raise QuizUnavailableError(str(section_id))

            definition = await _get_or_create_definition(session, section=section)

            existing = await _non_terminal_attempt(
                session, student_id=student_id, definition_id=definition.id
            )
            if existing is not None:
                return StartResult(existing.id, existing.status, created=False)

            next_number = await _next_attempt_number(
                session, student_id=student_id, definition_id=definition.id
            )
            now = _now()
            attempt = QuizAttempt(
                quiz_definition_id=definition.id,
                student_id=student_id,
                attempt_number=next_number,
                status="generating",
                source_summary_id=summary.id,
                source_summary_content_hash=_summary_content_hash(summary.content_json),
                source_transcript_checksum=summary.source_transcript_checksum,
                started_at=now,
                generation_started_at=now,
            )
            session.add(attempt)
            try:
                await session.flush()
            except IntegrityError:
                # Concurrent Start race: the one-active partial-unique index rejected our insert.
                # Roll back to the savepoint, re-read the winner, return it as a resume — a DB
                # rejection is NEVER surfaced as a user error (lock 3).
                await session.rollback()
            else:
                return StartResult(attempt.id, "generating", created=True)

    # The flush raced; re-read the now-existing non-terminal attempt in a fresh transaction.
    async with factory() as session:
        async with session.begin():
            definition = await _existing_definition(session, section_id=section_id)
            if definition is not None:
                existing = await _non_terminal_attempt(
                    session, student_id=student_id, definition_id=definition.id
                )
                if existing is not None:
                    return StartResult(existing.id, existing.status, created=False)
    raise QuizGenerationError("start race did not resolve to a non-terminal attempt")


async def _stamp_generation_job_id(
    factory: async_sessionmaker[AsyncSession], *, attempt_id: UUID, job_id: str
) -> None:
    async with factory() as session:
        async with session.begin():
            attempt = (
                await session.execute(
                    select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is not None and attempt.generation_job_id is None:
                attempt.generation_job_id = job_id
                attempt.updated_at = _now()


async def _existing_definition(
    session: AsyncSession, *, section_id: UUID
) -> QuizDefinition | None:
    return (
        await session.execute(
            select(QuizDefinition).where(
                QuizDefinition.module_section_id == section_id,
                QuizDefinition.quiz_mode == QUIZ_MODE_POST_CLASS,
            )
        )
    ).scalar_one_or_none()


async def _get_or_create_definition(
    session: AsyncSession, *, section: ModuleSection
) -> QuizDefinition:
    existing = await _existing_definition(session, section_id=section.id)
    if existing is not None:
        return existing
    definition = QuizDefinition(
        module_section_id=section.id,
        module_id=section.course_module_id,
        quiz_mode=QUIZ_MODE_POST_CLASS,
        question_policy=QUESTION_POLICY,
        source_scope={"sectionType": section.type, "moduleSectionId": str(section.id)},
    )
    session.add(definition)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        # A concurrent Start created the post_class definition first (partial-unique). Re-read it.
        existing = await _existing_definition(session, section_id=section.id)
        if existing is None:  # pragma: no cover - defensive
            raise
        return existing
    return definition


async def _non_terminal_attempt(
    session: AsyncSession, *, student_id: UUID, definition_id: UUID
) -> QuizAttempt | None:
    return (
        await session.execute(
            select(QuizAttempt)
            .where(
                QuizAttempt.student_id == student_id,
                QuizAttempt.quiz_definition_id == definition_id,
                QuizAttempt.status.in_(("generating", "in_progress")),
            )
            .with_for_update()
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


# ── Generation job (claim → gateway → atomic persist+flip → mark failed) ─────────────────────────
async def generate_post_class_quiz_async(
    attempt_id: UUID,
    *,
    gateway: LLMGateway | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    factory = session_factory or async_session
    if factory is None:
        raise RuntimeError("DATABASE_URL environment variable is required")
    active_gateway = gateway or LLMGateway(session_factory=factory)

    context = await _claim_generation(factory, attempt_id=attempt_id)
    if context is None:
        return  # fenced: not generating, or questions already persisted (idempotent re-run)

    try:
        result = await active_gateway.complete(
            prompt_key=QUIZ_PROMPT_KEY,
            output_schema=PostClassQuiz,
            context_refs=ContextRefs(
                ingestion_job_id=None,  # quiz has no IngestionJob (0020)
                transcript_text=context.summary_text,
                input_content_hash=context.input_hash,
                section_type=context.section_type,
            ),
            priority="background",
            feature=QUIZ_FEATURE,
            attempt_number=1,
        )
    except GatewayError as exc:
        category = "invalid_output" if exc.status == "invalid_output" else "provider_error"
        await _mark_attempt_failed(
            factory, attempt_id=attempt_id, failure_category=category, message=_sanitize_error(exc)
        )
        if exc.status in RQ_RETRY_STATUSES:
            raise  # bounded RQ retry
        return
    except Exception as exc:  # pragma: no cover - defensive
        await _mark_attempt_failed(
            factory,
            attempt_id=attempt_id,
            failure_category="provider_error",
            message="quiz generation failed",
        )
        raise QuizGenerationError(str(exc)) from None

    # Stamp the AIRequestLog id on the attempt BEFORE persisting questions. The common crash window is
    # between the AI call returning and the question write (a big DB write, a deploy, an OOM); stamping
    # here is what lets the reaper finalize the orphaned 'running' log on a lost job (lock 4). It only
    # sets a provenance pointer — the "generating ⟺ no questions" invariant is untouched.
    await _stamp_request_log(factory, attempt_id=attempt_id, log_id=result["ai_request_log_id"])
    await _persist_generation_success(factory, context=context, result=result)


async def _claim_generation(
    factory: async_sessionmaker[AsyncSession], *, attempt_id: UUID
) -> _GenContext | None:
    async with factory() as session:
        async with session.begin():
            attempt = (
                await session.execute(
                    select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is None:
                return None
            if attempt.status == "failed" and attempt.failure_category in _RQ_RETRYABLE_CATEGORIES:
                # An RQ retry of a transiently-failed generation: re-activate (mirrors the 4.5 summary
                # claim, which resets a failed job to running on retry). It stays ONE attempt; only its
                # bounded RQ retries re-run. A terminal crashed/enqueue_failed is NOT re-activated —
                # the student uses Start Over (lock 4: no in-place retry of a *failed* attempt).
                attempt.status = "generating"
                attempt.failure_category = None
                attempt.failure_message_sanitized = None
                attempt.updated_at = _now()
            elif attempt.status != "generating":
                return None
            # Fence (lock 5/6): generate only if still generating AND no questions exist. With the
            # atomic persist+flip, status != 'generating' alone is authoritative; no-questions is
            # belt-and-suspenders.
            has_questions = (
                await session.execute(
                    select(QuizQuestion.id)
                    .where(QuizQuestion.quiz_attempt_id == attempt_id)
                    .limit(1)
                )
            ).first()
            if has_questions is not None:
                return None
            if attempt.generation_started_at is None:
                attempt.generation_started_at = _now()

            definition = await session.get(QuizDefinition, attempt.quiz_definition_id)
            if definition is None:  # pragma: no cover - FK guarantees this
                raise QuizGenerationError("quiz definition missing")
            section = await session.get(ModuleSection, definition.module_section_id)
            if section is None:  # pragma: no cover - FK guarantees this
                raise QuizGenerationError("module section missing")
            summary = (
                await session.get(GeneratedLectureSummary, attempt.source_summary_id)
                if attempt.source_summary_id is not None
                else None
            )
            if summary is None:
                raise QuizGenerationError("source summary missing")
            text = _summary_to_text(summary.content_json)
            return _GenContext(
                attempt_id=attempt.id,
                module_id=definition.module_id,
                section_id=section.id,
                section_type=section.type,
                source_summary_id=summary.id,
                summary_text=text,
                input_hash=_summary_content_hash(summary.content_json),
            )


async def _stamp_request_log(
    factory: async_sessionmaker[AsyncSession], *, attempt_id: UUID, log_id: UUID
) -> None:
    async with factory() as session:
        async with session.begin():
            attempt = (
                await session.execute(
                    select(QuizAttempt).where(QuizAttempt.id == attempt_id).with_for_update()
                )
            ).scalar_one_or_none()
            if attempt is not None and attempt.status == "generating":
                attempt.ai_request_log_id = log_id
                attempt.updated_at = _now()


async def _persist_generation_success(
    factory: async_sessionmaker[AsyncSession], *, context: _GenContext, result: dict
) -> None:
    parsed: PostClassQuiz = result["parsed"]
    async with factory() as session:
        async with session.begin():
            attempt = (
                await session.execute(
                    select(QuizAttempt)
                    .where(QuizAttempt.id == context.attempt_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            # Fence: idempotent — a concurrent/duplicate run that already flipped the attempt no-ops.
            if attempt is None or attempt.status != "generating":
                return
            has_questions = (
                await session.execute(
                    select(QuizQuestion.id)
                    .where(QuizQuestion.quiz_attempt_id == context.attempt_id)
                    .limit(1)
                )
            ).first()
            if has_questions is not None:
                return

            log = await session.get(AIRequestLog, result["ai_request_log_id"])
            if log is None:  # pragma: no cover - defensive
                raise QuizGenerationError("AIRequestLog row missing for generated quiz")

            for q_index, question in enumerate(parsed.questions):
                row = QuizQuestion(
                    quiz_attempt_id=attempt.id,
                    question_text=question.question_text,
                    display_order=q_index,
                    question_type="multiple_choice",
                    explanation=question.explanation,
                    source_type="new_generated",
                    source_module_id=context.module_id,
                    source_section_id=context.section_id,
                    source_summary_id=context.source_summary_id,
                    model_name=log.model_id,
                    prompt_version=log.prompt_version,
                )
                session.add(row)
                await session.flush()
                # Shuffle display order so the correct option's position is not predictable; correctness
                # rides on is_correct (option identity), never the slot (lock 7).
                display_orders = list(range(len(question.options)))
                random.shuffle(display_orders)
                for option, display_order in zip(question.options, display_orders):
                    session.add(
                        AnswerOption(
                            quiz_question_id=row.id,
                            text=option.text,
                            display_order=display_order,
                            is_correct=option.is_correct,
                        )
                    )

            now = _now()
            attempt.status = "in_progress"
            attempt.total_questions = len(parsed.questions)
            attempt.new_question_count = len(parsed.questions)
            attempt.mistake_review_question_count = 0
            attempt.model_name = log.model_id
            attempt.prompt_version = log.prompt_version
            attempt.backend_used = log.backend_used
            attempt.ai_request_log_id = log.id
            attempt.generation_completed_at = now
            attempt.updated_at = now


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
                return  # never overwrite a terminal/in_progress attempt
            now = _now()
            attempt.status = "failed"
            attempt.failure_category = failure_category
            attempt.failure_message_sanitized = message
            attempt.generation_completed_at = now
            attempt.updated_at = now
    logger.warning(
        "Quiz generation failed",
        extra={"quiz_attempt_id": str(attempt_id), "failure_category": failure_category},
    )


def _sanitize_error(exc: GatewayError) -> str:
    code = f" ({exc.error_code})" if exc.error_code else ""
    return f"{exc.status}{code}"
