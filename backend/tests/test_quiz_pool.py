"""Stage 6a — per-section pool foundation hard gate (engine, DB-backed).

Proves: (1) pool reuse + the one-active herd lock (incl. simultaneous first-requests → exactly ONE
generation), (3) the MistakeRecord pooled-upsert identity (re-missing a re-sampled question updates ONE
record), (4) snapshot-at-assembly immunity (pool supersession never mutates a started attempt), (5) the
reaper does NOT reap a pooled attempt while an in-scope pool is generating but DOES self-heal a stuck pool;
plus the end-to-end multi-section assemble + reuse (a second attempt samples fresh with NO new generation).
The deterministic adapter runs the full gateway path at the provider boundary, so "no new generation
AIRequestLog at section granularity" holds in CI exactly as in the browser gate.
"""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.domains.quiz.assembly_service as assembly_service
import app.domains.quiz.pool_service as pool_service
from app.domains.quiz.assembly_service import (
    start_pooled_attempt,
    try_assemble_attempt_async,
)
from app.domains.quiz.mistakes import upsert_pool_mistake
from app.domains.quiz.pool_service import (
    ensure_section_pool,
    generate_section_pool_async,
    retry_section_pool,
)
from app.domains.recovery.reaper import run_stuck_row_reaper
from app.platform.db.models import (
    AIRequestLog,
    AppUser,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    ModuleSection,
    MistakeRecord,
    PoolQuestion,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    SectionQuestionPool,
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


def _gateway(factory, *, fault: str | None = None) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(fault=fault),
        limiter=_FakeLimiter(),
        session_factory=factory,
    )


@pytest.fixture
def captured(monkeypatch) -> SimpleNamespace:
    """Capture enqueues so tests drive the pool/assembly jobs manually (no real RQ worker)."""
    pools: list = []
    assemblies: list = []
    monkeypatch.setattr(
        pool_service, "enqueue_generate_section_pool", lambda pid: pools.append(pid) or f"quiz-pool:{pid}"
    )
    monkeypatch.setattr(
        pool_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"quiz-generate:{aid}"
    )
    monkeypatch.setattr(
        assembly_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"quiz-generate:{aid}"
    )
    return SimpleNamespace(pools=pools, assemblies=assemblies)


async def _seed_base(db_session: AsyncSession) -> SimpleNamespace:
    student = AppUser(
        auth_provider_id=f"auth-{uuid4()}", email=f"s-{uuid4()}@e.com",
        full_name="S", role="student", timezone="UTC",
    )
    owner = AppUser(
        auth_provider_id=f"auth-{uuid4()}", email=f"o-{uuid4()}@e.com",
        full_name="O", role="lecturer", timezone="UTC",
    )
    db_session.add_all([student, owner])
    await db_session.flush()
    module = CourseModule(title="M", owner_id=owner.id, timezone="UTC", is_active=True)
    db_session.add(module)
    await db_session.flush()
    db_session.add(
        CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active")
    )
    await db_session.flush()
    return SimpleNamespace(student=student, owner=owner, module=module)


async def _seed_section(db_session, base, *, title: str, order: int, overview: str = "An overview.") -> SimpleNamespace:
    section = ModuleSection(
        course_module_id=base.module.id, title=title, type="lecture",
        order_index=order, publish_status="published", status="active",
    )
    db_session.add(section)
    await db_session.flush()
    checksum = hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest()
    transcript = Transcript(
        module_section_id=section.id, source_type="manual_upload", original_file_name="t.vtt",
        storage_key=f"m/x/t/{uuid4()}/t.vtt", mime_type="text/vtt", file_size=10,
        checksum=checksum, status="completed", uploaded_by_user_id=base.owner.id,
        lifecycle_state="active",
    )
    db_session.add(transcript)
    await db_session.flush()
    log = AIRequestLog(
        ingestion_job_id=None, feature="summary_detailed", model_id="MBZUAI-IFM/K2-Think-v2",
        prompt_version="v1", prompt_content_hash="h", rendered_prompt_hash="rh",
        input_content_hash="ih", status="succeeded",
    )
    db_session.add(log)
    await db_session.flush()
    summary = GeneratedLectureSummary(
        transcript_id=transcript.id, module_section_id=section.id, summary_type="detailed_study",
        content_json={
            "overview": overview, "keyConcepts": ["c1"], "importantDefinitions": [{"term": "T", "definition": "D"}],
            "mainExplanations": ["x"], "examples": ["e"], "examRelevantPoints": ["p"],
        },
        content_schema_version="detailed-v1", model_id="MBZUAI-IFM/K2-Think-v2", prompt_version="v1",
        prompt_content_hash="h", backend_used="nvidia", source_transcript_checksum=checksum,
        input_hash="ih", ai_request_log_id=log.id,
    )
    db_session.add(summary)
    await db_session.flush()
    await db_session.commit()
    return SimpleNamespace(section=section, summary=summary, transcript=transcript)


async def _make_pooled_definition(factory, base, sections: list, *, mode: str = "recap") -> QuizDefinition:
    async with factory() as session:
        async with session.begin():
            definition = QuizDefinition(
                module_section_id=sections[0].section.id,  # NOT NULL until 0025 (6b); engine reads scope
                module_id=base.module.id,
                quiz_mode=mode,
                source_scope={"sectionIds": [str(s.section.id) for s in sections], "quizMode": mode},
            )
            session.add(definition)
        return await session.get(QuizDefinition, definition.id)


async def _count(factory, model, **where) -> int:
    async with factory() as session:
        stmt = select(func.count()).select_from(model)
        for col, val in where.items():
            stmt = stmt.where(getattr(model, col) == val)
        return int(await session.scalar(stmt) or 0)


# ── (1) one-active lock + reuse ──────────────────────────────────────────────────────────────────
async def test_pool_one_active_lock_concurrent_first_requests(db_session, captured):
    base = await _seed_base(db_session)
    sec = await _seed_section(db_session, base, title="L1", order=0)
    factory = _factory(db_session)

    r1, r2 = await asyncio.gather(
        ensure_section_pool(factory, section_id=sec.section.id),
        ensure_section_pool(factory, section_id=sec.section.id),
    )
    assert r1.status == "generating" and r2.status == "generating"
    assert r1.pool_id == r2.pool_id  # both attached to the SAME pool (herd lock)
    assert await _count(factory, SectionQuestionPool) == 1  # exactly one pool row
    assert len(captured.pools) == 1  # exactly one generation enqueued


async def test_pool_generate_then_reuse_no_new_generation(db_session, captured):
    base = await _seed_base(db_session)
    sec = await _seed_section(db_session, base, title="L1", order=0)
    factory = _factory(db_session)

    ensured = await ensure_section_pool(factory, section_id=sec.section.id)
    await generate_section_pool_async(ensured.pool_id, gateway=_gateway(factory), session_factory=factory)

    async with factory() as session:
        pool = await session.get(SectionQuestionPool, ensured.pool_id)
        nq = await session.scalar(
            select(func.count()).select_from(PoolQuestion).where(
                PoolQuestion.section_question_pool_id == ensured.pool_id
            )
        )
    assert pool.status == "ready"
    assert nq == 24  # the deterministic pool fixture size
    assert pool.ai_request_log_id is not None
    assert await _count(factory, AIRequestLog, feature="quiz_pool") == 1

    # Reuse: a second ensure returns the ready pool with NO new generation enqueue / log row.
    pools_before = len(captured.pools)
    reuse = await ensure_section_pool(factory, section_id=sec.section.id)
    assert reuse.status == "ready" and reuse.pool_id == ensured.pool_id
    assert len(captured.pools) == pools_before  # no new generation
    assert await _count(factory, AIRequestLog, feature="quiz_pool") == 1  # section granularity holds


async def test_pool_failure_then_explicit_retry(db_session, captured):
    base = await _seed_base(db_session)
    sec = await _seed_section(db_session, base, title="L1", order=0)
    factory = _factory(db_session)

    ensured = await ensure_section_pool(factory, section_id=sec.section.id)
    # Forced-invalid fixture (5 questions) trips the pool count rule → invalid_output → bounded RQ retry.
    with pytest.raises(Exception):
        await generate_section_pool_async(
            ensured.pool_id, gateway=_gateway(factory, fault="invalid_output"), session_factory=factory
        )
    async with factory() as session:
        assert (await session.get(SectionQuestionPool, ensured.pool_id)).status == "failed"
    # A new ensure surfaces the terminal failure (no auto-retry storm).
    assert (await ensure_section_pool(factory, section_id=sec.section.id)).status == "failed"
    # Explicit retry re-enqueues under the lock; a clean generation succeeds.
    await retry_section_pool(factory, pool_id=ensured.pool_id)
    await generate_section_pool_async(ensured.pool_id, gateway=_gateway(factory), session_factory=factory)
    async with factory() as session:
        assert (await session.get(SectionQuestionPool, ensured.pool_id)).status == "ready"


# ── (3) MistakeRecord pooled-upsert identity ─────────────────────────────────────────────────────
async def test_mistake_upsert_collapses_re_miss_to_one_record(db_session, captured):
    base = await _seed_base(db_session)
    sec = await _seed_section(db_session, base, title="L1", order=0)
    factory = _factory(db_session)
    definition = await _make_pooled_definition(factory, base, [sec])
    # A pool + one pool question, then two attempts each snapshotting it.
    async with factory() as session:
        async with session.begin():
            pool = SectionQuestionPool(
                module_section_id=sec.section.id, model="m", prompt_version="v1",
                source_summary_content_hash="hash", status="ready",
            )
            session.add(pool)
            await session.flush()
            poolq = PoolQuestion(
                section_question_pool_id=pool.id, question_text="Q", explanation="E",
                options=[{"text": "a", "isCorrect": True}, {"text": "b", "isCorrect": False}],
            )
            session.add(poolq)
            await session.flush()
            attempts, questions = [], []
            for n in range(2):
                a = QuizAttempt(
                    quiz_definition_id=definition.id, student_id=base.student.id,
                    # Both terminal: the one-active invariant forbids two concurrent non-terminal attempts;
                    # a real re-miss spans two SEPARATE completed attempts of the same quiz.
                    attempt_number=n + 1, status="completed",
                )
                session.add(a)
                await session.flush()
                q = QuizQuestion(
                    quiz_attempt_id=a.id, question_text="Q", display_order=0,
                    source_type="new_generated", source_pool_question_id=poolq.id,
                )
                session.add(q)
                await session.flush()
                attempts.append(a.id)
                questions.append(q.id)
        ids = SimpleNamespace(pool=poolq.id, attempts=attempts, questions=questions)

    snap = {"questionText": "Q", "displayOrder": 0, "explanation": "E"}
    opts = {"options": [{"id": "x", "text": "a", "isCorrect": True}]}
    # First miss (attempt 1), then bump the retake counter, then re-miss the SAME pool question (attempt 2).
    async with factory() as session:
        async with session.begin():
            await upsert_pool_mistake(
                session, student_id=base.student.id, module_id=base.module.id,
                module_section_id=sec.section.id, source_quiz_definition_id=definition.id,
                source_quiz_attempt_id=ids.attempts[0], source_question_id=ids.questions[0],
                source_pool_question_id=ids.pool, question_snapshot=snap,
                answer_options_snapshot=opts, selected_wrong_answer="b", correct_answer="a", explanation="E",
            )
    async with factory() as session:
        async with session.begin():
            row = (await session.execute(select(MistakeRecord))).scalar_one()
            row.retake_correct_count = 1  # simulate one correct retake before the re-miss
    async with factory() as session:
        async with session.begin():
            await upsert_pool_mistake(
                session, student_id=base.student.id, module_id=base.module.id,
                module_section_id=sec.section.id, source_quiz_definition_id=definition.id,
                source_quiz_attempt_id=ids.attempts[1], source_question_id=ids.questions[1],
                source_pool_question_id=ids.pool, question_snapshot=snap,
                answer_options_snapshot=opts, selected_wrong_answer="b", correct_answer="a", explanation="E",
            )

    async with factory() as session:
        rows = (await session.execute(select(MistakeRecord))).scalars().all()
    assert len(rows) == 1  # ONE record, not two — the re-miss upserted
    assert rows[0].source_quiz_attempt_id == ids.attempts[1]  # refreshed to the latest occurrence
    assert rows[0].retake_correct_count == 1  # progress PRESERVED across the re-miss (D2 default)


# ── (4) snapshot-at-assembly immunity ────────────────────────────────────────────────────────────
async def test_snapshot_immunity_pool_supersession_does_not_mutate_attempt(db_session, captured):
    base = await _seed_base(db_session)
    sec = await _seed_section(db_session, base, title="L1", order=0)
    factory = _factory(db_session)
    definition = await _make_pooled_definition(factory, base, [sec])

    ensured = await ensure_section_pool(factory, section_id=sec.section.id)
    await generate_section_pool_async(ensured.pool_id, gateway=_gateway(factory), session_factory=factory)
    start = await start_pooled_attempt(factory, student_id=base.student.id, quiz_definition_id=definition.id)
    await try_assemble_attempt_async(start.attempt_id, session_factory=factory)

    async with factory() as session:
        before = (
            await session.execute(
                select(QuizQuestion.id, QuizQuestion.question_text)
                .where(QuizQuestion.quiz_attempt_id == start.attempt_id)
                .order_by(QuizQuestion.display_order)
            )
        ).all()
        attempt = await session.get(QuizAttempt, start.attempt_id)
    assert attempt.status == "in_progress"
    assert len(before) == 5  # RECAP_EXAM_QUESTIONS_PER_SECTION

    # Change the summary content → the next ensure detects staleness and supersedes the live pool.
    async with factory() as session:
        async with session.begin():
            summary = await session.get(GeneratedLectureSummary, sec.summary.id)
            summary.content_json = {**summary.content_json, "overview": "A DIFFERENT overview entirely."}
    superseded = await ensure_section_pool(factory, section_id=sec.section.id)
    assert superseded.status == "generating" and superseded.pool_id != ensured.pool_id
    await generate_section_pool_async(superseded.pool_id, gateway=_gateway(factory), session_factory=factory)

    async with factory() as session:
        after = (
            await session.execute(
                select(QuizQuestion.id, QuizQuestion.question_text)
                .where(QuizQuestion.quiz_attempt_id == start.attempt_id)
                .order_by(QuizQuestion.display_order)
            )
        ).all()
        old_pool = await session.get(SectionQuestionPool, ensured.pool_id)
    assert after == before  # the started attempt's snapshot is untouched by supersession
    assert old_pool.status == "superseded"


# ── (5) reaper: pooled-attempt liveness + stuck-pool self-heal ───────────────────────────────────
async def test_reaper_skips_pooled_attempt_while_pool_generating_and_reaps_pool(db_session, captured):
    base = await _seed_base(db_session)
    sec = await _seed_section(db_session, base, title="L1", order=0)
    factory = _factory(db_session)
    definition = await _make_pooled_definition(factory, base, [sec])

    ensured = await ensure_section_pool(factory, section_id=sec.section.id)  # generating pool, not run
    async with factory() as session:
        async with session.begin():
            attempt = QuizAttempt(
                quiz_definition_id=definition.id, student_id=base.student.id,
                attempt_number=1, status="generating",
            )
            session.add(attempt)
        attempt_id = attempt.id

    # Everything is "lost" in RQ. The attempt must NOT be reaped (its pool is generating); the stuck pool
    # MUST be reaped so the herd lock self-heals.
    result = await run_stuck_row_reaper(
        session_factory=factory, engine=db_session.bind, rq_liveness=lambda jt, _id: False
    )
    assert result is not None
    async with factory() as session:
        assert (await session.get(QuizAttempt, attempt_id)).status == "generating"  # NOT reaped (waiting)
        assert (await session.get(SectionQuestionPool, ensured.pool_id)).status == "failed"  # pool reaped


async def test_reaper_reaps_pooled_attempt_when_no_pool_generating(db_session, captured):
    base = await _seed_base(db_session)
    sec = await _seed_section(db_session, base, title="L1", order=0)
    factory = _factory(db_session)
    definition = await _make_pooled_definition(factory, base, [sec])
    # Pool is READY (not generating); the attempt is generating with no questions (a fan-in miss) → stuck.
    async with factory() as session:
        async with session.begin():
            session.add(
                SectionQuestionPool(
                    module_section_id=sec.section.id, model="m", prompt_version="v1",
                    source_summary_content_hash="h", status="ready",
                )
            )
            attempt = QuizAttempt(
                quiz_definition_id=definition.id, student_id=base.student.id,
                attempt_number=1, status="generating",
            )
            session.add(attempt)
        attempt_id = attempt.id

    await run_stuck_row_reaper(
        session_factory=factory, engine=db_session.bind, rq_liveness=lambda jt, _id: False
    )
    async with factory() as session:
        reaped = await session.get(QuizAttempt, attempt_id)
    assert reaped.status == "failed" and reaped.failure_category == "crashed"  # backstop


# ── end-to-end: multi-section assemble + reuse + fresh sample ─────────────────────────────────────
async def test_multi_section_assemble_then_reuse_no_new_generation(db_session, captured):
    base = await _seed_base(db_session)
    s1 = await _seed_section(db_session, base, title="L1", order=0, overview="Section one material.")
    s2 = await _seed_section(db_session, base, title="L2", order=1, overview="Section two material.")
    factory = _factory(db_session)
    definition = await _make_pooled_definition(factory, base, [s1, s2])

    # Student A: ensure + generate both pools, then assemble.
    for sec in (s1, s2):
        ensured = await ensure_section_pool(factory, section_id=sec.section.id)
        await generate_section_pool_async(ensured.pool_id, gateway=_gateway(factory), session_factory=factory)
    assert await _count(factory, AIRequestLog, feature="quiz_pool") == 2  # one per section

    start_a = await start_pooled_attempt(factory, student_id=base.student.id, quiz_definition_id=definition.id)
    await try_assemble_attempt_async(start_a.attempt_id, session_factory=factory)
    async with factory() as session:
        qa = (
            await session.execute(
                select(QuizQuestion.source_section_id).where(QuizQuestion.quiz_attempt_id == start_a.attempt_id)
            )
        ).scalars().all()
        attempt_a = await session.get(QuizAttempt, start_a.attempt_id)
    assert attempt_a.status == "in_progress"
    assert len(qa) == 10  # 5 per section × 2 sections (even spread)
    assert {sec.section.id for sec in (s1, s2)} == set(qa)  # both sections represented

    # A second student opening the same scope assembles from the EXISTING pools — NO new generation.
    student_b = AppUser(
        auth_provider_id=f"auth-{uuid4()}", email=f"b-{uuid4()}@e.com",
        full_name="B", role="student", timezone="UTC",
    )
    async with factory() as session:
        async with session.begin():
            session.add(student_b)
            await session.flush()
            session.add(
                CourseMembership(user_id=student_b.id, module_id=base.module.id, role="student", status="active")
            )
        student_b_id = student_b.id
    start_b = await start_pooled_attempt(factory, student_id=student_b_id, quiz_definition_id=definition.id)
    await try_assemble_attempt_async(start_b.attempt_id, session_factory=factory)
    async with factory() as session:
        attempt_b = await session.get(QuizAttempt, start_b.attempt_id)
    assert attempt_b.status == "in_progress"
    assert await _count(factory, AIRequestLog, feature="quiz_pool") == 2  # still 2 — reuse, no new generation
