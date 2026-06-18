"""Stage 6b — recap + exam-prep + authorization (service-level).

Proves the binding Authorization & visibility rules and the multi-section scope mechanics: lecturer-on-
module AssessmentScope CRUD (403 paths), student 404-not-403 for unassigned, recap canonical-key dedup
(same span → ONE shared definition), eligibility (assignment/supplementary + unpublished excluded silently),
D3 all-or-wait (a still-generating summary blocks), exam-prep pre-warm (idempotent), exam-prep scope
correctness (sampled questions only from in-scope eligible sections), and the unified visibility for
multi-section attempts. The deterministic adapter runs the full pool path.
"""

from __future__ import annotations

import hashlib
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.domains.quiz.assembly_service as assembly_service
import app.domains.quiz.pool_service as pool_service
from app.domains.assessments import service as ascope
from app.domains.assessments.schemas import (
    CreateAssessmentScopeRequest,
    UpdateAssessmentScopeRequest,
)
from app.domains.quiz import service as quiz_service
from app.domains.quiz.assembly_service import try_assemble_attempt_async
from app.domains.quiz.pool_service import ensure_section_pool, generate_section_pool_async
from app.domains.quiz.schemas import RecapScopeRequest
from app.domains.quiz.scope_service import canonical_scope_key
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AIRequestLog,
    AppUser,
    AssessmentScope,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    IngestionJob,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    QuizQuestion,
    Transcript,
)
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider
from app.platform.query.quiz_read import get_visible_attempt

pytestmark = pytest.mark.anyio


class _FakeLease:
    async def release(self) -> None:
        return None


class _FakeLimiter:
    async def acquire(self, *, backend, estimated_tokens, priority):
        return _FakeLease()


def _factory(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def _gateway(factory):
    return LLMGateway(
        provider=DeterministicTestProvider(), limiter=_FakeLimiter(), session_factory=factory
    )


def _ctx(user, role: str | None = None) -> CurrentUserContext:
    return CurrentUserContext(
        user_id=user.id,
        auth_provider_id=user.auth_provider_id,
        email=user.email,
        full_name=user.full_name,
        role=role or user.role,
        is_active=True,
        timezone="UTC",
    )


@pytest.fixture
def captured(monkeypatch) -> SimpleNamespace:
    pools: list = []
    assemblies: list = []
    monkeypatch.setattr(
        pool_service, "enqueue_generate_section_pool", lambda pid: pools.append(pid) or f"quiz-pool-{pid}"
    )
    monkeypatch.setattr(
        pool_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"q:{aid}"
    )
    monkeypatch.setattr(
        assembly_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"q:{aid}"
    )
    return SimpleNamespace(pools=pools, assemblies=assemblies)


def _user(role: str) -> AppUser:
    return AppUser(
        auth_provider_id=f"auth-{uuid4()}", email=f"{role}-{uuid4()}@e.com",
        full_name=role.title(), role=role, timezone="UTC",
    )


async def _seed_base(db_session: AsyncSession) -> SimpleNamespace:
    student = _user("student")
    lecturer = _user("lecturer")
    outsider = _user("lecturer")  # a lecturer NOT a member of the module
    db_session.add_all([student, lecturer, outsider])
    await db_session.flush()
    module = CourseModule(title="M", owner_id=lecturer.id, timezone="UTC", is_active=True)
    db_session.add(module)
    await db_session.flush()
    db_session.add_all(
        [
            CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"),
            CourseMembership(user_id=lecturer.id, module_id=module.id, role="lecturer", status="active"),
        ]
    )
    await db_session.flush()
    return SimpleNamespace(student=student, lecturer=lecturer, outsider=outsider, module=module)


async def _section(db_session, base, *, title, order, week, publish="published", typ="lecture"):
    section = ModuleSection(
        course_module_id=base.module.id, title=title, type=typ, order_index=order,
        publish_status=publish, status="active", week_number=week,
        session_date=date(2026, 5, 4 + week),
    )
    db_session.add(section)
    await db_session.flush()
    return section


async def _attach_ready_summary(db_session, base, section):
    checksum = hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest()
    transcript = Transcript(
        module_section_id=section.id, source_type="manual_upload", original_file_name="t.vtt",
        storage_key=f"m/x/t/{uuid4()}/t.vtt", mime_type="text/vtt", file_size=10,
        checksum=checksum, status="completed", uploaded_by_user_id=base.lecturer.id,
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
    db_session.add(
        GeneratedLectureSummary(
            transcript_id=transcript.id, module_section_id=section.id, summary_type="detailed_study",
            content_json={
                "overview": f"Overview of {section.title}.", "keyConcepts": ["c"],
                "importantDefinitions": [{"term": "T", "definition": "D"}],
                "mainExplanations": ["x"], "examples": ["e"], "examRelevantPoints": ["p"],
            },
            content_schema_version="detailed-v1", model_id="MBZUAI-IFM/K2-Think-v2", prompt_version="v1",
            prompt_content_hash="h", backend_used="nvidia", source_transcript_checksum=checksum,
            input_hash="ih", ai_request_log_id=log.id,
        )
    )
    await db_session.flush()


async def _attach_generating_summary(db_session, base, section):
    """Active transcript + a RUNNING generate_detailed_summary job, no summary row → derive=GENERATING."""
    checksum = hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest()
    transcript = Transcript(
        module_section_id=section.id, source_type="manual_upload", original_file_name="t.vtt",
        storage_key=f"m/x/t/{uuid4()}/t.vtt", mime_type="text/vtt", file_size=10,
        checksum=checksum, status="completed", uploaded_by_user_id=base.lecturer.id,
        lifecycle_state="active",
    )
    db_session.add(transcript)
    await db_session.flush()
    db_session.add(
        IngestionJob(
            transcript_id=transcript.id, job_type="generate_detailed_summary", status="running",
            idempotency_key=f"detail-{uuid4()}",
        )
    )
    await db_session.flush()


async def _ready_section(db_session, base, *, title, order, week, publish="published"):
    section = await _section(db_session, base, title=title, order=order, week=week, publish=publish)
    await _attach_ready_summary(db_session, base, section)
    return section


async def _count(factory, model, **where) -> int:
    async with factory() as session:
        stmt = select(func.count()).select_from(model)
        for col, val in where.items():
            stmt = stmt.where(getattr(model, col) == val)
        return int(await session.scalar(stmt) or 0)


# ── AssessmentScope authorization ─────────────────────────────────────────────────────────────────
async def test_assessment_scope_create_authz(db_session, captured):
    base = await _seed_base(db_session)
    await _ready_section(db_session, base, title="W1", order=0, week=1)
    await db_session.commit()
    payload = CreateAssessmentScopeRequest(name="Midterm", coveredWeeks=[1])

    # lecturer-on-module → OK
    scope = await ascope.create_scope(
        db_session, current_user=_ctx(base.lecturer), module_id=base.module.id, payload=payload
    )
    assert scope.id is not None and scope.covered_weeks == [1]

    # a student → 403
    with pytest.raises(HTTPException) as exc:
        await ascope.create_scope(
            db_session, current_user=_ctx(base.student), module_id=base.module.id, payload=payload
        )
    assert exc.value.status_code == 403

    # a lecturer NOT a member of the module → 403
    with pytest.raises(HTTPException) as exc:
        await ascope.create_scope(
            db_session, current_user=_ctx(base.outsider), module_id=base.module.id, payload=payload
        )
    assert exc.value.status_code == 403


async def test_assessment_scope_prewarm_idempotent(db_session, captured):
    base = await _seed_base(db_session)
    await _ready_section(db_session, base, title="W1", order=0, week=1)
    await _ready_section(db_session, base, title="W2", order=1, week=2)
    await db_session.commit()

    await ascope.create_scope(
        db_session,
        current_user=_ctx(base.lecturer),
        module_id=base.module.id,
        payload=CreateAssessmentScopeRequest(name="Mid", coveredWeeks=[1, 2]),
    )
    # Pre-warm ensured one pool per eligible section.
    assert len(captured.pools) == 2
    # Editing the scope (same weeks) re-warms but skips the now-fresh-generating pools → no new generation.
    before = len(captured.pools)
    scope = (await db_session.scalars(select(AssessmentScope))).one()
    await ascope.update_scope(
        db_session,
        current_user=_ctx(base.lecturer),
        scope_id=scope.id,
        payload=UpdateAssessmentScopeRequest(name="Mid v2"),
    )
    assert len(captured.pools) == before  # idempotent — the generating pools were skipped


# ── recap: 404 unassigned, dedup, eligibility, D3 ─────────────────────────────────────────────────
async def test_recap_start_404_for_unassigned_student(db_session, captured):
    base = await _seed_base(db_session)
    await _ready_section(db_session, base, title="W1", order=0, week=1)
    # A student with NO membership in this module.
    outsider_student = _user("student")
    db_session.add(outsider_student)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await quiz_service.start_recap(
            db_session,
            current_user=_ctx(outsider_student),
            module_id=base.module.id,
            payload=RecapScopeRequest(weeks=[1]),
        )
    assert exc.value.status_code == 404  # not 403 — never reveal existence


async def test_recap_dedup_one_shared_definition(db_session, captured):
    base = await _seed_base(db_session)
    s1 = await _ready_section(db_session, base, title="W1", order=0, week=1)
    s2 = await _ready_section(db_session, base, title="W2", order=1, week=2)
    student_b = _user("student")
    db_session.add(student_b)
    await db_session.flush()
    db_session.add(
        CourseMembership(user_id=student_b.id, module_id=base.module.id, role="student", status="active")
    )
    await db_session.commit()

    await quiz_service.start_recap(
        db_session, current_user=_ctx(base.student), module_id=base.module.id,
        payload=RecapScopeRequest(weeks=[1, 2]),
    )
    await quiz_service.start_recap(
        db_session, current_user=_ctx(student_b), module_id=base.module.id,
        payload=RecapScopeRequest(weeks=[1, 2]),
    )
    factory = _factory(db_session)
    # ONE shared recap definition; its scope_key is the canonical sorted-eligible-ids hash.
    assert await _count(factory, QuizDefinition, quiz_mode="recap") == 1
    async with factory() as session:
        definition = (await session.scalars(select(QuizDefinition).where(QuizDefinition.quiz_mode == "recap"))).one()
    assert definition.scope_key == canonical_scope_key([s1.id, s2.id])
    assert definition.module_section_id is None  # multi-section
    # Two students → two attempts against the one definition.
    assert await _count(factory, QuizAttempt) == 2


async def test_recap_eligibility_excludes_assignment_and_unpublished(db_session, captured):
    base = await _seed_base(db_session)
    await _ready_section(db_session, base, title="L", order=0, week=1)
    # An assignment section (structurally ineligible) + an unpublished ready lecture, same week.
    await _section(db_session, base, title="A", order=1, week=1, typ="assignment")
    await _ready_section(db_session, base, title="Draft", order=2, week=1, publish="draft")
    await db_session.commit()

    resolution = await quiz_service.recap_availability(
        db_session, current_user=_ctx(base.student), module_id=base.module.id,
        payload=RecapScopeRequest(weeks=[1]),
    )
    assert resolution.available is True
    assert resolution.ready_section_count == 1  # only the published lecture
    assert resolution.processing_section_count == 0  # assignment/unpublished are silent, NOT "processing"


async def test_recap_d3_all_or_wait_blocks_on_processing(db_session, captured):
    base = await _seed_base(db_session)
    await _ready_section(db_session, base, title="Ready", order=0, week=1)
    generating = await _section(db_session, base, title="Generating", order=1, week=1)
    await _attach_generating_summary(db_session, base, generating)
    await db_session.commit()

    resolution = await quiz_service.recap_availability(
        db_session, current_user=_ctx(base.student), module_id=base.module.id,
        payload=RecapScopeRequest(weeks=[1]),
    )
    assert resolution.available is False
    assert resolution.reason_code == "processing"
    assert resolution.processing_section_count == 1
    # And start is 409 while a section is still processing.
    with pytest.raises(HTTPException) as exc:
        await quiz_service.start_recap(
            db_session, current_user=_ctx(base.student), module_id=base.module.id,
            payload=RecapScopeRequest(weeks=[1]),
        )
    assert exc.value.status_code == 409


# ── exam-prep scope correctness + multi-section visibility ────────────────────────────────────────
async def test_exam_prep_scope_correctness_and_visibility(db_session, captured):
    base = await _seed_base(db_session)
    s1 = await _ready_section(db_session, base, title="W1", order=0, week=1)
    s2 = await _ready_section(db_session, base, title="W2", order=1, week=2)
    # An out-of-scope ready lecture (week 5) that must NEVER be sampled.
    await _ready_section(db_session, base, title="W5", order=2, week=5)
    await db_session.commit()
    in_scope = {s1.id, s2.id}

    scope = await ascope.create_scope(
        db_session, current_user=_ctx(base.lecturer), module_id=base.module.id,
        payload=CreateAssessmentScopeRequest(name="Midterm", coveredWeeks=[1, 2]),
    )
    factory = _factory(db_session)
    # Generate the in-scope pools (pre-warm ensured them; run the deterministic generation).
    for section_id in in_scope:
        ensured = await ensure_section_pool(factory, section_id=section_id)
        await generate_section_pool_async(ensured.pool_id, gateway=_gateway(factory), session_factory=factory)

    attempt = await quiz_service.start_exam_prep(
        db_session, current_user=_ctx(base.student), scope_id=scope.id
    )
    await try_assemble_attempt_async(attempt.id, session_factory=factory)

    async with factory() as session:
        sampled = (
            await session.execute(
                select(QuizQuestion.source_section_id).where(QuizQuestion.quiz_attempt_id == attempt.id)
            )
        ).scalars().all()
        assembled = await session.get(QuizAttempt, attempt.id)
    assert assembled.status == "in_progress"
    assert set(sampled).issubset(in_scope)  # scope correctness — never the week-5 section
    assert len(sampled) == 10  # 5 per section × 2 in-scope sections

    # Unified visibility: owner sees the multi-section attempt; a different student does not.
    visible = await get_visible_attempt(db_session, student_id=base.student.id, attempt_id=attempt.id)
    assert visible is not None and visible.module_section_id is None
    other = _user("student")
    db_session.add(other)
    await db_session.commit()
    assert await get_visible_attempt(db_session, student_id=other.id, attempt_id=attempt.id) is None
