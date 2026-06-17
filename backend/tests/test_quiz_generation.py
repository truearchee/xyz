"""Stage 5b — quiz generation pipeline + recovery (locks 1–6, seams S3/S5/S6).

Exercises the full generation path through the 4.5 gateway with the deterministic adapter: lazy start +
enqueue-after-commit + compensation, the atomic persist+provenance+flip, fencing/idempotency, the
worker failure handler, per-request fault injection (inject→clear→succeed), the liveness-not-age reaper
that finalizes the orphaned AIRequestLog, and the summary app-layer ingestion_job_id guard.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.quiz.generation_service import (
    QuizUnavailableError,
    generate_post_class_quiz_async,
    start_quiz_attempt,
)
import app.domains.quiz.generation_service as gen_service
from app.domains.recovery.reaper import run_stuck_row_reaper
from app.platform.db.models import (
    AIRequestLog,
    AnswerOption,
    AppUser,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    Transcript,
)
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.quiz import PostClassQuiz
from app.platform.llm.models.summary import BriefSummary
from app.platform.llm.provider import (
    DeterministicTestProvider,
    clear_request_faults,
    set_request_faults,
)
from app.platform.llm.validation import OutputValidator

pytestmark = pytest.mark.anyio


# ── harness ──────────────────────────────────────────────────────────────────────────────────────
class _FakeLease:
    async def release(self) -> None:
        return None


class _FakeLimiter:
    async def acquire(self, *, backend, estimated_tokens, priority):
        return _FakeLease()


def _factory(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def _gateway(factory, *, fault: str | None = None) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(fault=fault),
        limiter=_FakeLimiter(),
        session_factory=factory,
    )


@pytest.fixture(autouse=True)
def _clear_faults():
    clear_request_faults()
    yield
    clear_request_faults()


async def _seed(db_session: AsyncSession, *, with_summary: bool = True) -> SimpleNamespace:
    student = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"student-{uuid4()}@example.com",
        full_name="Quiz Student",
        role="student",
        timezone="UTC",
    )
    owner = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"owner-{uuid4()}@example.com",
        full_name="Quiz Owner",
        role="lecturer",
        timezone="UTC",
    )
    db_session.add_all([student, owner])
    await db_session.flush()
    module = CourseModule(title="Quiz Module", owner_id=owner.id, timezone="UTC", is_active=True)
    db_session.add(module)
    await db_session.flush()
    db_session.add(
        CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active")
    )
    section = ModuleSection(
        course_module_id=module.id,
        title="Lecture 1",
        type="lecture",
        order_index=0,
        publish_status="published",
        status="active",
    )
    db_session.add(section)
    await db_session.flush()

    checksum = hashlib.sha256(f"transcript-{uuid4()}".encode()).hexdigest()
    transcript = Transcript(
        module_section_id=section.id,
        source_type="manual_upload",
        original_file_name="t.vtt",
        storage_key=f"modules/x/transcripts/{uuid4()}/t.vtt",
        mime_type="text/vtt",
        file_size=10,
        checksum=checksum,
        status="completed",
        uploaded_by_user_id=owner.id,
        lifecycle_state="active",
    )
    db_session.add(transcript)
    await db_session.flush()

    summary = None
    if with_summary:
        log = AIRequestLog(
            ingestion_job_id=None,
            feature="summary_detailed",
            model_id="MBZUAI-IFM/K2-Think-v2",
            prompt_version="v1",
            prompt_content_hash="h",
            rendered_prompt_hash="rh",
            input_content_hash="ih",
            status="succeeded",
        )
        db_session.add(log)
        await db_session.flush()
        summary = GeneratedLectureSummary(
            transcript_id=transcript.id,
            module_section_id=section.id,
            summary_type="detailed_study",
            content_json={
                "overview": "An overview of the session.",
                "keyConcepts": ["concept one"],
                "importantDefinitions": [{"term": "T", "definition": "D"}],
                "mainExplanations": ["explanation"],
                "examples": ["example"],
                "examRelevantPoints": ["point"],
            },
            content_schema_version="detailed-v1",
            model_id="MBZUAI-IFM/K2-Think-v2",
            prompt_version="v1",
            prompt_content_hash="h",
            backend_used="nvidia",
            source_transcript_checksum=checksum,
            input_hash="ih",
            ai_request_log_id=log.id,
        )
        db_session.add(summary)
        await db_session.flush()

    await db_session.commit()
    return SimpleNamespace(
        student=student, owner=owner, module=module, section=section, transcript=transcript,
        summary=summary,
    )


async def _attempt(factory, attempt_id):
    async with factory() as session:
        return await session.get(QuizAttempt, attempt_id)


# ── start: resume / unavailable ────────────────────────────────────────────────────────────────
async def test_start_creates_generating_attempt_no_questions(db_session: AsyncSession):
    seed = await _seed(db_session)
    factory = _factory(db_session)

    result = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )
    assert result.created is True
    assert result.status == "generating"

    attempt = await _attempt(factory, result.attempt_id)
    assert attempt.status == "generating"
    assert attempt.source_summary_id == seed.summary.id
    assert attempt.source_transcript_checksum == seed.transcript.checksum
    # generating PROVABLY implies no questions persisted.
    async with factory() as session:
        n = await session.scalar(
            select(func.count()).select_from(QuizQuestion).where(
                QuizQuestion.quiz_attempt_id == result.attempt_id
            )
        )
    assert n == 0


async def test_start_resumes_non_terminal_attempt(db_session: AsyncSession):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    first = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )
    second = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )
    assert second.created is False
    assert second.attempt_id == first.attempt_id
    # exactly one definition, one attempt.
    async with factory() as session:
        defs = await session.scalar(select(func.count()).select_from(QuizDefinition))
        attempts = await session.scalar(select(func.count()).select_from(QuizAttempt))
    assert defs == 1
    assert attempts == 1


async def test_start_without_detailed_summary_raises_unavailable(db_session: AsyncSession):
    seed = await _seed(db_session, with_summary=False)
    factory = _factory(db_session)
    with pytest.raises(QuizUnavailableError):
        await start_quiz_attempt(
            factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
        )


async def test_start_enqueue_failure_compensates_to_failed(
    db_session: AsyncSession, monkeypatch
):
    seed = await _seed(db_session)
    factory = _factory(db_session)

    def _boom(_attempt_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr(gen_service, "enqueue_generate_post_class_quiz", _boom)
    result = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=True
    )
    assert result.status == "failed"
    attempt = await _attempt(factory, result.attempt_id)
    assert attempt.status == "failed"
    assert attempt.failure_category == "enqueue_failed"


async def test_start_successful_enqueue_stamps_generation_job_id(
    db_session: AsyncSession, monkeypatch
):
    seed = await _seed(db_session)
    factory = _factory(db_session)

    def _enqueue(attempt_id):
        return f"quiz-generate-{attempt_id}"

    monkeypatch.setattr(gen_service, "enqueue_generate_post_class_quiz", _enqueue)
    result = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=True
    )

    attempt = await _attempt(factory, result.attempt_id)
    assert attempt.generation_job_id == f"quiz-generate-{result.attempt_id}"


# ── generation: success / fence / failure ────────────────────────────────────────────────────────
async def test_generation_success_atomic_persist_and_flip(db_session: AsyncSession):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    start = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )

    await generate_post_class_quiz_async(
        start.attempt_id, gateway=_gateway(factory), session_factory=factory
    )

    attempt = await _attempt(factory, start.attempt_id)
    assert attempt.status == "in_progress"
    assert attempt.total_questions == 10
    assert attempt.new_question_count == 10
    assert attempt.mistake_review_question_count == 0
    assert attempt.ai_request_log_id is not None
    assert attempt.backend_used == "nvidia"
    assert attempt.generation_completed_at is not None

    async with factory() as session:
        questions = (
            await session.execute(
                select(QuizQuestion).where(QuizQuestion.quiz_attempt_id == start.attempt_id)
            )
        ).scalars().all()
        assert len(questions) == 10
        for q in questions:
            options = (
                await session.execute(
                    select(AnswerOption).where(AnswerOption.quiz_question_id == q.id)
                )
            ).scalars().all()
            assert len(options) == 4
            assert sum(1 for o in options if o.is_correct) == 1
            assert q.source_type == "new_generated"
        # AIRequestLog: quiz feature, NO ingestion job (0020), succeeded.
        log = await session.get(AIRequestLog, attempt.ai_request_log_id)
        assert log.feature == "post_class_quiz"
        assert log.ingestion_job_id is None
        assert log.status == "succeeded"


async def test_generation_is_idempotent_on_rerun(db_session: AsyncSession):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    start = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )
    await generate_post_class_quiz_async(
        start.attempt_id, gateway=_gateway(factory), session_factory=factory
    )
    # A duplicate run (e.g. a stray re-enqueue) must no-op — fenced on status != generating.
    await generate_post_class_quiz_async(
        start.attempt_id, gateway=_gateway(factory), session_factory=factory
    )
    async with factory() as session:
        n = await session.scalar(
            select(func.count()).select_from(QuizQuestion).where(
                QuizQuestion.quiz_attempt_id == start.attempt_id
            )
        )
    assert n == 10  # not 20


async def test_invalid_output_fails_attempt_and_reraises(db_session: AsyncSession):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    start = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )
    # The forced-invalid fixture (9 questions) trips the validator's exactly-10 rule → invalid_output.
    with pytest.raises(GatewayError):
        await generate_post_class_quiz_async(
            start.attempt_id, gateway=_gateway(factory, fault="invalid_output"),
            session_factory=factory,
        )
    attempt = await _attempt(factory, start.attempt_id)
    assert attempt.status == "failed"
    assert attempt.failure_category == "invalid_output"


async def test_provider_transient_fails_with_provider_error(db_session: AsyncSession):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    start = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )
    with pytest.raises(GatewayError):
        await generate_post_class_quiz_async(
            start.attempt_id, gateway=_gateway(factory, fault="provider_transient"),
            session_factory=factory,
        )
    attempt = await _attempt(factory, start.attempt_id)
    assert attempt.status == "failed"
    assert attempt.failure_category == "provider_error"


async def test_per_request_fault_inject_then_succeed(db_session: AsyncSession):
    """S6: a transient failure then a clean retry (inject→clear→succeed) — the sequence the global flag
    cannot express. The RQ retry re-activates the transiently-failed attempt and succeeds."""
    seed = await _seed(db_session)
    factory = _factory(db_session)
    start = await start_quiz_attempt(
        factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False
    )
    # First run: one queued transient fault → the attempt fails (retryable, re-raises like RQ would).
    set_request_faults(["provider_transient"])
    with pytest.raises(GatewayError):
        await generate_post_class_quiz_async(
            start.attempt_id, gateway=_gateway(factory), session_factory=factory
        )
    assert (await _attempt(factory, start.attempt_id)).status == "failed"

    # Second run (simulated RQ retry): the fault queue is now empty → the attempt re-activates and
    # generation succeeds.
    await generate_post_class_quiz_async(
        start.attempt_id, gateway=_gateway(factory), session_factory=factory
    )
    attempt = await _attempt(factory, start.attempt_id)
    assert attempt.status == "in_progress"
    assert attempt.total_questions == 10


# ── reaper: liveness-not-age + AIRequestLog finalize ─────────────────────────────────────────────
async def _seed_generating_attempt_with_running_log(db_session: AsyncSession) -> SimpleNamespace:
    seed = await _seed(db_session)
    log = AIRequestLog(
        ingestion_job_id=None,
        feature="post_class_quiz",
        model_id="MBZUAI-IFM/K2-Think-v2",
        prompt_version="v1",
        prompt_content_hash="h",
        rendered_prompt_hash="rh",
        input_content_hash="ih",
        status="running",
    )
    db_session.add(log)
    await db_session.flush()
    definition = QuizDefinition(
        module_section_id=seed.section.id,
        module_id=seed.module.id,
        quiz_mode="post_class",
        source_scope={"sectionType": "lecture", "moduleSectionId": str(seed.section.id)},
    )
    db_session.add(definition)
    await db_session.flush()
    attempt = QuizAttempt(
        quiz_definition_id=definition.id,
        student_id=seed.student.id,
        attempt_number=1,
        status="generating",
        ai_request_log_id=log.id,
    )
    db_session.add(attempt)
    await db_session.flush()
    await db_session.commit()
    return SimpleNamespace(attempt_id=attempt.id, log_id=log.id)


async def test_reaper_reaps_lost_quiz_job_and_finalizes_log(db_session: AsyncSession):
    s = await _seed_generating_attempt_with_running_log(db_session)
    factory = _factory(db_session)

    # Liveness says the job is LOST (absent from RQ registries).
    result = await run_stuck_row_reaper(
        session_factory=factory,
        engine=db_session.bind,
        rq_liveness=lambda job_type, _id: False if job_type == "quiz_generate" else None,
    )
    assert result is not None and result["crashed"] >= 1

    async with factory() as session:
        attempt = await session.get(QuizAttempt, s.attempt_id)
        log = await session.get(AIRequestLog, s.log_id)
    assert attempt.status == "failed"
    assert attempt.failure_category == "crashed"
    assert log.status == "failed"
    assert log.error_code == "abandoned_crashed"


async def test_reaper_does_not_reap_live_or_unknown_quiz_job(db_session: AsyncSession):
    s = await _seed_generating_attempt_with_running_log(db_session)
    factory = _factory(db_session)

    # Live (queued behind a backed-up AI queue) → must NOT be reaped (liveness, not age).
    await run_stuck_row_reaper(
        session_factory=factory,
        engine=db_session.bind,
        rq_liveness=lambda job_type, _id: True,
    )
    assert (await _attempt(factory, s.attempt_id)).status == "generating"

    # Unknown (Redis hiccup) → also not reaped (uncertainty principle).
    await run_stuck_row_reaper(
        session_factory=factory,
        engine=db_session.bind,
        rq_liveness=lambda job_type, _id: None,
    )
    assert (await _attempt(factory, s.attempt_id)).status == "generating"


# ── summary app-layer guard (D-B) ────────────────────────────────────────────────────────────────
async def test_summary_feature_still_requires_ingestion_job_id(db_session: AsyncSession):
    """The 0020 column is nullable platform-wide, but the gateway STILL requires ingestion_job_id for
    the summary features — the optionality is a property of the quiz feature, not a hole in the summary
    contract (validated, not assumed)."""
    factory = _factory(db_session)
    gateway = _gateway(factory)
    with pytest.raises(ValueError):
        await gateway.complete(
            prompt_key=gen_service.QUIZ_PROMPT_KEY,  # any key; the guard fires before render
            output_schema=BriefSummary,
            context_refs=ContextRefs(
                ingestion_job_id=None,
                transcript_text="x",
                input_content_hash="h",
                section_type="lecture",
            ),
            priority="background",
            feature="summary_brief",
        )


# ── quiz OutputValidator (structure + size + escape-not-reject) ───────────────────────────────────
def _valid_quiz_payload() -> dict:
    return {
        "questions": [
            {
                "questionText": f"Q{i} text?",
                "options": [
                    {"text": f"Q{i} A", "isCorrect": True},
                    {"text": f"Q{i} B", "isCorrect": False},
                    {"text": f"Q{i} C", "isCorrect": False},
                    {"text": f"Q{i} D", "isCorrect": False},
                ],
                "explanation": f"Q{i} explanation.",
            }
            for i in range(10)
        ]
    }


def test_quiz_validator_accepts_valid_and_preserves_angle_brackets():
    import json

    payload = _valid_quiz_payload()
    payload["questions"][0]["questionText"] = "Does 3 < x < 5 hold?"
    quiz = OutputValidator().validate(
        raw_text=json.dumps(payload), output_schema=PostClassQuiz, section_type="lecture"
    )
    assert isinstance(quiz, PostClassQuiz)
    # escape-not-reject: the angle brackets are stored faithfully (escaping is the UI's job).
    assert quiz.questions[0].question_text == "Does 3 < x < 5 hold?"


def test_quiz_validator_rejects_wrong_question_count():
    import json
    from app.platform.llm.errors import InvalidOutput

    payload = _valid_quiz_payload()
    payload["questions"].pop()
    with pytest.raises(InvalidOutput):
        OutputValidator().validate(
            raw_text=json.dumps(payload), output_schema=PostClassQuiz, section_type="lecture"
        )


def test_quiz_validator_rejects_multiple_correct_options():
    import json
    from app.platform.llm.errors import InvalidOutput

    payload = _valid_quiz_payload()
    payload["questions"][0]["options"][1]["isCorrect"] = True  # two correct
    with pytest.raises(InvalidOutput):
        OutputValidator().validate(
            raw_text=json.dumps(payload), output_schema=PostClassQuiz, section_type="lecture"
        )
