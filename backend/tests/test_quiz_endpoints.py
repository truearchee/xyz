"""Stage 5c — student quiz HTTP surface (endpoint behaviour, seams S2/S4/S5/S7).

Drives the real router via auth_client + signed JWTs: 403/404 gating, the answer-endpoint ordering
(integrity + option-identity + DB-idempotent re-answer + mistake), the atomic complete (score + events +
idempotency + strict in_progress), and the S7 unpublish-mid-attempt seam.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.quiz.generation_service import (
    generate_post_class_quiz_async,
    start_quiz_attempt,
)
from app.platform.db.models import (
    AIRequestLog,
    AnswerOption,
    AppUser,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    MistakeRecord,
    ModuleSection,
    QuizAttempt,
    QuizQuestion,
    StudentActivityEvent,
    StudentAnswer,
    Transcript,
)
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider

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


def _gateway(factory) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(), limiter=_FakeLimiter(), session_factory=factory
    )


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


async def _seed(db_session: AsyncSession) -> SimpleNamespace:
    student = AppUser(auth_provider_id=f"auth-{uuid4()}", email=f"s-{uuid4()}@e.com", full_name="S", role="student", timezone="UTC")
    other = AppUser(auth_provider_id=f"auth-{uuid4()}", email=f"o-{uuid4()}@e.com", full_name="O", role="student", timezone="UTC")
    lecturer = AppUser(auth_provider_id=f"auth-{uuid4()}", email=f"l-{uuid4()}@e.com", full_name="L", role="lecturer", timezone="UTC")
    admin = AppUser(auth_provider_id=f"auth-{uuid4()}", email=f"a-{uuid4()}@e.com", full_name="A", role="admin", timezone="UTC")
    db_session.add_all([student, other, lecturer, admin])
    await db_session.flush()
    module = CourseModule(title="M", owner_id=lecturer.id, timezone="UTC", is_active=True)
    db_session.add(module)
    await db_session.flush()
    db_session.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    section = ModuleSection(course_module_id=module.id, title="Lecture 1", type="lecture", order_index=0, publish_status="published", status="active")
    db_session.add(section)
    await db_session.flush()
    checksum = hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest()
    transcript = Transcript(module_section_id=section.id, source_type="manual_upload", original_file_name="t.vtt", storage_key=f"m/x/{uuid4()}/t.vtt", mime_type="text/vtt", file_size=10, checksum=checksum, status="completed", uploaded_by_user_id=lecturer.id, lifecycle_state="active")
    db_session.add(transcript)
    await db_session.flush()
    log = AIRequestLog(ingestion_job_id=None, feature="summary_detailed", model_id="m", prompt_version="v1", prompt_content_hash="h", rendered_prompt_hash="rh", input_content_hash="ih", status="succeeded")
    db_session.add(log)
    await db_session.flush()
    summary = GeneratedLectureSummary(transcript_id=transcript.id, module_section_id=section.id, summary_type="detailed_study", content_json={"overview": "O", "keyConcepts": ["a"], "importantDefinitions": [{"term": "t", "definition": "d"}], "mainExplanations": ["e"], "examples": ["x"], "examRelevantPoints": ["p"]}, content_schema_version="detailed-v1", model_id="m", prompt_version="v1", prompt_content_hash="h", backend_used="nvidia", source_transcript_checksum=checksum, input_hash="ih", ai_request_log_id=log.id)
    db_session.add(summary)
    await db_session.flush()
    await db_session.commit()
    return SimpleNamespace(student=student, other=other, lecturer=lecturer, admin=admin, module=module, section=section)


async def _in_progress_attempt(db_session: AsyncSession, seed) -> QuizAttempt:
    factory = _factory(db_session)
    start = await start_quiz_attempt(factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False)
    await generate_post_class_quiz_async(start.attempt_id, gateway=_gateway(factory), session_factory=factory)
    async with factory() as s:
        return await s.get(QuizAttempt, start.attempt_id)


async def _question_with_options(db_session: AsyncSession, attempt_id) -> tuple[QuizQuestion, list[AnswerOption]]:
    factory = _factory(db_session)
    async with factory() as s:
        q = (await s.execute(select(QuizQuestion).where(QuizQuestion.quiz_attempt_id == attempt_id).order_by(QuizQuestion.display_order).limit(1))).scalar_one()
        opts = (await s.execute(select(AnswerOption).where(AnswerOption.quiz_question_id == q.id))).scalars().all()
        return q, list(opts)


async def _answer_all(client: AsyncClient, headers, attempt_id, db_session, *, all_correct: bool):
    factory = _factory(db_session)
    async with factory() as s:
        questions = (await s.execute(select(QuizQuestion).where(QuizQuestion.quiz_attempt_id == attempt_id))).scalars().all()
        opts_by_q = {}
        for q in questions:
            opts = (await s.execute(select(AnswerOption).where(AnswerOption.quiz_question_id == q.id))).scalars().all()
            opts_by_q[q.id] = list(opts)
    for q in questions:
        opts = opts_by_q[q.id]
        chosen = next(o for o in opts if o.is_correct) if all_correct else next(o for o in opts if not o.is_correct)
        r = await client.post(f"/student/quiz/attempts/{attempt_id}/answer", headers=headers, json={"questionId": str(q.id), "selectedAnswerOptionId": str(chosen.id)})
        assert r.status_code == 200, r.text


# ── 403 / 404 gating ───────────────────────────────────────────────────────────────────────────
async def test_non_student_403_on_every_endpoint(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    for actor in (seed.lecturer, seed.admin):
        h = _headers(actor, jwt_factory)
        assert (await auth_client.get(f"/student/sections/{seed.section.id}/quiz/availability", headers=h)).status_code == 403
        assert (await auth_client.post(f"/student/sections/{seed.section.id}/quiz/start", headers=h)).status_code == 403
        assert (await auth_client.get(f"/student/quiz/attempts/{attempt.id}", headers=h)).status_code == 403
        assert (await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)).status_code == 403


async def test_unassigned_student_404_and_availability(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    # assigned student → available
    r = await auth_client.get(f"/student/sections/{seed.section.id}/quiz/availability", headers=_headers(seed.student, jwt_factory))
    assert r.status_code == 200 and r.json()["availability"] == "available"
    # unassigned student → 404
    r2 = await auth_client.get(f"/student/sections/{seed.section.id}/quiz/availability", headers=_headers(seed.other, jwt_factory))
    assert r2.status_code == 404


# ── attempt detail: no isCorrect leak ──────────────────────────────────────────────────────────
async def test_attempt_detail_hides_correctness_preanswer(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    r = await auth_client.get(f"/student/quiz/attempts/{attempt.id}", headers=_headers(seed.student, jwt_factory))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "in_progress" and len(body["questions"]) == 10
    for q in body["questions"]:
        assert q["answer"] is None
        for o in q["options"]:
            assert "isCorrect" not in o and "is_correct" not in o
    assert r.headers["cache-control"] == "private, no-store"


# ── answer endpoint ─────────────────────────────────────────────────────────────────────────────
async def test_answer_correct_no_mistake(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    q, opts = await _question_with_options(db_session, attempt.id)
    correct = next(o for o in opts if o.is_correct)
    r = await auth_client.post(f"/student/quiz/attempts/{attempt.id}/answer", headers=_headers(seed.student, jwt_factory), json={"questionId": str(q.id), "selectedAnswerOptionId": str(correct.id)})
    assert r.status_code == 200
    fb = r.json()
    assert fb["isCorrect"] is True and fb["correctAnswerOptionId"] == str(correct.id) and fb["mistakeSaved"] is False


async def test_answer_incorrect_creates_mistake(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    q, opts = await _question_with_options(db_session, attempt.id)
    wrong = next(o for o in opts if not o.is_correct)
    correct = next(o for o in opts if o.is_correct)
    r = await auth_client.post(f"/student/quiz/attempts/{attempt.id}/answer", headers=_headers(seed.student, jwt_factory), json={"questionId": str(q.id), "selectedAnswerOptionId": str(wrong.id)})
    assert r.status_code == 200
    fb = r.json()
    assert fb["isCorrect"] is False and fb["correctAnswerOptionId"] == str(correct.id) and fb["mistakeSaved"] is True
    n = await db_session.scalar(select(func.count()).select_from(MistakeRecord).where(MistakeRecord.source_quiz_attempt_id == attempt.id, MistakeRecord.source_question_id == q.id))
    assert n == 1


async def test_answer_idempotent_returns_original(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    q, opts = await _question_with_options(db_session, attempt.id)
    correct = next(o for o in opts if o.is_correct)
    wrong = next(o for o in opts if not o.is_correct)
    h = _headers(seed.student, jwt_factory)
    first = await auth_client.post(f"/student/quiz/attempts/{attempt.id}/answer", headers=h, json={"questionId": str(q.id), "selectedAnswerOptionId": str(correct.id)})
    assert first.json()["isCorrect"] is True
    # Re-answer with a DIFFERENT (wrong) option → original (correct) wins, alreadyAnswered.
    second = await auth_client.post(f"/student/quiz/attempts/{attempt.id}/answer", headers=h, json={"questionId": str(q.id), "selectedAnswerOptionId": str(wrong.id)})
    assert second.status_code == 200
    body = second.json()
    assert body["alreadyAnswered"] is True
    assert body["selectedAnswerOptionId"] == str(correct.id)
    assert body["isCorrect"] is True
    n = await db_session.scalar(select(func.count()).select_from(StudentAnswer).where(StudentAnswer.quiz_attempt_id == attempt.id, StudentAnswer.quiz_question_id == q.id))
    assert n == 1  # no second StudentAnswer
    m = await db_session.scalar(select(func.count()).select_from(MistakeRecord).where(MistakeRecord.source_quiz_attempt_id == attempt.id, MistakeRecord.source_question_id == q.id))
    assert m == 0  # original was correct → no mistake despite the wrong re-submit


async def test_answer_cross_attempt_question_404(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    q, opts = await _question_with_options(db_session, attempt.id)
    r = await auth_client.post(f"/student/quiz/attempts/{uuid4()}/answer", headers=_headers(seed.student, jwt_factory), json={"questionId": str(q.id), "selectedAnswerOptionId": str(opts[0].id)})
    assert r.status_code == 404


async def test_answer_option_from_other_question_422(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    factory = _factory(db_session)
    async with factory() as s:
        qs = (await s.execute(select(QuizQuestion).where(QuizQuestion.quiz_attempt_id == attempt.id).order_by(QuizQuestion.display_order).limit(2))).scalars().all()
        other_opt = (await s.execute(select(AnswerOption).where(AnswerOption.quiz_question_id == qs[1].id).limit(1))).scalar_one()
    r = await auth_client.post(f"/student/quiz/attempts/{attempt.id}/answer", headers=_headers(seed.student, jwt_factory), json={"questionId": str(qs[0].id), "selectedAnswerOptionId": str(other_opt.id)})
    assert r.status_code == 422


# ── complete endpoint ───────────────────────────────────────────────────────────────────────────
async def test_complete_scores_and_emits_event(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    h = _headers(seed.student, jwt_factory)
    await _answer_all(auth_client, h, attempt.id, db_session, all_correct=False)
    r = await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed" and body["totalQuestions"] == 10 and body["correctCount"] == 0
    events = await db_session.scalar(select(func.count()).select_from(StudentActivityEvent).where(StudentActivityEvent.source_id == attempt.id, StudentActivityEvent.event_type == "completed_quiz"))
    assert events == 1


async def test_complete_all_correct_emits_perfect(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    h = _headers(seed.student, jwt_factory)
    await _answer_all(auth_client, h, attempt.id, db_session, all_correct=True)
    r = await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)
    assert r.status_code == 200 and float(r.json()["scorePercentage"]) == 100.0
    perfect = await db_session.scalar(select(func.count()).select_from(StudentActivityEvent).where(StudentActivityEvent.source_id == attempt.id, StudentActivityEvent.event_type == "perfect_quiz_score"))
    assert perfect == 1


async def test_complete_idempotent_no_duplicate_event(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    h = _headers(seed.student, jwt_factory)
    await _answer_all(auth_client, h, attempt.id, db_session, all_correct=False)
    assert (await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)).status_code == 200
    assert (await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)).status_code == 200
    events = await db_session.scalar(select(func.count()).select_from(StudentActivityEvent).where(StudentActivityEvent.source_id == attempt.id, StudentActivityEvent.event_type == "completed_quiz"))
    assert events == 1


async def test_complete_strict_in_progress_409(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    # A generating attempt (no questions yet) must not complete.
    factory = _factory(db_session)
    start = await start_quiz_attempt(factory, student_id=seed.student.id, section_id=seed.section.id, enqueue=False)
    r = await auth_client.post(f"/student/quiz/attempts/{start.attempt_id}/complete", headers=_headers(seed.student, jwt_factory))
    assert r.status_code == 409


# ── S7: unpublish mid-attempt ────────────────────────────────────────────────────────────────────
async def test_s7_unpublish_hides_then_republish_resumes(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    h = _headers(seed.student, jwt_factory)
    await _answer_all(auth_client, h, attempt.id, db_session, all_correct=False)

    # Unpublish the section → every endpoint 404s; no event fires while hidden.
    factory = _factory(db_session)
    async with factory() as s:
        sec = await s.get(ModuleSection, seed.section.id)
        sec.publish_status = "unpublished"
        await s.commit()
    assert (await auth_client.get(f"/student/quiz/attempts/{attempt.id}", headers=h)).status_code == 404
    assert (await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)).status_code == 404
    events = await db_session.scalar(select(func.count()).select_from(StudentActivityEvent).where(StudentActivityEvent.source_id == attempt.id))
    assert events == 0  # nothing emitted while hidden

    # Re-publish → resume + complete works.
    async with factory() as s:
        sec = await s.get(ModuleSection, seed.section.id)
        sec.publish_status = "published"
        await s.commit()
    assert (await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)).status_code == 200


# ── start / start-over + attempts aggregate ──────────────────────────────────────────────────────
async def test_start_endpoint_resume_and_start_over(auth_client, db_session, jwt_factory, mock_jwks_client, monkeypatch):
    seed = await _seed(db_session)
    # The start endpoint enqueues; no-op the enqueue so tests stay hermetic (no worker).
    monkeypatch.setattr("app.domains.quiz.generation_service.enqueue_generate_post_class_quiz", lambda _id: None)
    h = _headers(seed.student, jwt_factory)
    first = await auth_client.post(f"/student/sections/{seed.section.id}/quiz/start", headers=h)
    assert first.status_code == 200 and first.json()["status"] == "generating"
    attempt_id = first.json()["id"]
    # Re-start mid-(generating) → resumes the same attempt.
    again = await auth_client.post(f"/student/sections/{seed.section.id}/quiz/start", headers=h)
    assert again.json()["id"] == attempt_id

    # Drive the generating attempt to completed, then Start Over → a NEW attempt.
    factory = _factory(db_session)
    await generate_post_class_quiz_async(attempt_id, gateway=_gateway(factory), session_factory=factory)
    await _answer_all(auth_client, h, attempt_id, db_session, all_correct=False)
    assert (await auth_client.post(f"/student/quiz/attempts/{attempt_id}/complete", headers=h)).status_code == 200
    over = await auth_client.post(f"/student/sections/{seed.section.id}/quiz/start", headers=h)
    assert over.status_code == 200 and over.json()["id"] != attempt_id and over.json()["attemptNumber"] == 2


async def test_attempts_aggregate(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    attempt = await _in_progress_attempt(db_session, seed)
    h = _headers(seed.student, jwt_factory)
    await _answer_all(auth_client, h, attempt.id, db_session, all_correct=True)
    await auth_client.post(f"/student/quiz/attempts/{attempt.id}/complete", headers=h)
    r = await auth_client.get(f"/student/sections/{seed.section.id}/quiz/attempts", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["attemptCount"] == 1 and float(body["bestScorePercentage"]) == 100.0
