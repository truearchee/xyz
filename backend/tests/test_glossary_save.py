"""Stage 7a — glossary save flow, async definition generation, cache collapse, personal scoping.

Exercises the full path through the existing AI gateway with the deterministic adapter (FakeLimiter so
no Redis), with the AI-queue enqueue captured (the job is driven manually against the test factory).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.domains.glossary.save_service as save_service
from app.domains.glossary.definition_service import generate_glossary_definition_async
from app.domains.glossary.schemas import ManualEntryRequest, SaveHighlightRequest, UpdateEntryRequest
from app.domains.glossary.service import get_entry, save_from_highlight, save_manual, update_entry
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AIRequestLog,
    AppUser,
    CourseMembership,
    CourseModule,
    GlossaryDefinitionCache,
    GlossaryEntry,
    GlossarySourceReference,
    ModuleSection,
    StudentActivityEvent,
)
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider

pytestmark = pytest.mark.anyio


# ── harness ──
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
def _capture_enqueue(monkeypatch) -> list:
    captured: list = []
    monkeypatch.setattr(
        save_service,
        "enqueue_generate_glossary_definition",
        lambda cache_row_id: captured.append(cache_row_id),
    )
    return captured


def _ctx(user: AppUser, *, language: str = "en") -> CurrentUserContext:
    return CurrentUserContext(
        user_id=user.id,
        auth_provider_id=user.auth_provider_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=True,
        timezone="UTC",
        preferred_language=language,
    )


async def _make_student(db: AsyncSession, *, email: str | None = None) -> AppUser:
    student = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=email or f"student-{uuid4()}@example.com",
        full_name="Glossary Student",
        role="student",
        timezone="UTC",
    )
    db.add(student)
    await db.flush()
    return student


async def _seed(db: AsyncSession, *, students: int = 1) -> SimpleNamespace:
    owner = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"owner-{uuid4()}@example.com",
        full_name="Glossary Owner",
        role="lecturer",
        timezone="UTC",
    )
    db.add(owner)
    await db.flush()
    module = CourseModule(title="Bio 101", owner_id=owner.id, timezone="UTC", is_active=True)
    db.add(module)
    await db.flush()
    section = ModuleSection(
        course_module_id=module.id,
        title="Lecture 1",
        type="lecture",
        order_index=0,
        publish_status="published",
        status="active",
    )
    db.add(section)
    await db.flush()
    student_users = []
    for _ in range(students):
        s = await _make_student(db)
        db.add(
            CourseMembership(user_id=s.id, module_id=module.id, role="student", status="active")
        )
        student_users.append(s)
    await db.commit()
    return SimpleNamespace(owner=owner, module=module, section=section, students=student_users)


# ── save: highlight ──
async def test_highlight_save_creates_pending_entry_source_and_event(
    db_session: AsyncSession, _capture_enqueue: list
):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0], language="ar")

    resp = await save_from_highlight(
        db_session,
        current_user=ctx,
        payload=SaveHighlightRequest(
            module_section_id=seed.section.id, term="Mitochondria", selected_text="the mitochondria"
        ),
    )
    assert resp.duplicate is False
    assert resp.entry.definition_status == "pending"
    assert resp.entry.subject_id == seed.module.id  # subject derived from the section's module
    assert resp.entry.language == "ar"  # snapshot of preference at save
    assert len(_capture_enqueue) == 1  # the winner enqueued one job

    # source reference recorded as 'summary'; glossary_term_saved emitted in the same txn.
    src = (
        await db_session.execute(
            select(GlossarySourceReference).where(
                GlossarySourceReference.glossary_entry_id == resp.entry.id
            )
        )
    ).scalar_one()
    assert src.source_type == "summary"
    events = (
        await db_session.execute(
            select(StudentActivityEvent).where(
                StudentActivityEvent.source_id == resp.entry.id
            )
        )
    ).scalars().all()
    assert [e.event_type for e in events] == ["glossary_term_saved"]


async def test_definition_job_generates_and_stamps_provenance(
    db_session: AsyncSession, _capture_enqueue: list
):
    seed = await _seed(db_session)
    resp = await save_from_highlight(
        db_session,
        current_user=_ctx(seed.students[0]),
        payload=SaveHighlightRequest(module_section_id=seed.section.id, term="Krebs cycle"),
    )
    cache_row_id = _capture_enqueue[-1]
    factory = _factory(db_session)

    await generate_glossary_definition_async(
        cache_row_id, gateway=_gateway(factory), session_factory=factory
    )

    async with factory() as s:
        entry = await s.get(GlossaryEntry, resp.entry.id)
        assert entry.definition_status == "generated"
        assert entry.short_definition
        assert entry.ai_request_log_id is not None
        assert entry.model_id and entry.prompt_version == "v1"
        cache = await s.get(GlossaryDefinitionCache, cache_row_id)
        assert cache.status == "generated"
        assert cache.short_definition == entry.short_definition
        log = await s.get(AIRequestLog, entry.ai_request_log_id)
        assert log.feature == "glossary_definition"
        assert log.ingestion_job_id is None
        assert log.status == "succeeded"


async def test_enqueue_failure_marks_failed_and_duplicate_retry_reenqueues_to_completion(
    db_session: AsyncSession, monkeypatch, _capture_enqueue: list
):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    payload = SaveHighlightRequest(module_section_id=seed.section.id, term="Ribosome")

    def _boom(_cache_row_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr(save_service, "enqueue_generate_glossary_definition", _boom)
    failed = await save_from_highlight(db_session, current_user=ctx, payload=payload)
    assert failed.duplicate is False
    assert failed.entry.definition_status == "failed"
    assert _capture_enqueue == []

    cache = (
        await db_session.execute(select(GlossaryDefinitionCache))
    ).scalar_one()
    assert cache.status == "failed"

    monkeypatch.setattr(
        save_service,
        "enqueue_generate_glossary_definition",
        lambda cache_row_id: _capture_enqueue.append(cache_row_id),
    )
    retry = await save_from_highlight(db_session, current_user=ctx, payload=payload)
    assert retry.duplicate is True
    assert retry.entry.id == failed.entry.id
    assert retry.entry.definition_status == "pending"
    assert _capture_enqueue == [cache.id]

    factory = _factory(db_session)
    await generate_glossary_definition_async(
        _capture_enqueue[-1], gateway=_gateway(factory), session_factory=factory
    )

    async with factory() as s:
        entry = await s.get(GlossaryEntry, failed.entry.id)
        cache_after = await s.get(GlossaryDefinitionCache, cache.id)
        assert entry.definition_status == "generated"
        assert entry.short_definition
        assert cache_after.status == "generated"


# ── dedup ──
async def test_duplicate_save_attaches_source_no_second_entry_no_event(
    db_session: AsyncSession, _capture_enqueue: list
):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    payload = SaveHighlightRequest(module_section_id=seed.section.id, term="Osmosis")

    first = await save_from_highlight(db_session, current_user=ctx, payload=payload)
    second = await save_from_highlight(db_session, current_user=ctx, payload=payload)

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.entry.id == first.entry.id

    entries = await db_session.scalar(
        select(func.count()).select_from(GlossaryEntry).where(
            GlossaryEntry.student_id == ctx.user_id
        )
    )
    assert entries == 1  # no second entry
    sources = await db_session.scalar(
        select(func.count()).select_from(GlossarySourceReference).where(
            GlossarySourceReference.glossary_entry_id == first.entry.id
        )
    )
    assert sources == 2  # a new source reference attached on the duplicate
    events = await db_session.scalar(
        select(func.count()).select_from(StudentActivityEvent).where(
            StudentActivityEvent.source_id == first.entry.id
        )
    )
    assert events == 1  # only the first save emitted an event


async def test_update_entry_rejects_entry_type_change(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    created = await save_manual(
        db_session,
        current_user=ctx,
        payload=ManualEntryRequest(subject_id=seed.module.id, term="Cell wall"),
    )
    entry_before = await db_session.get(GlossaryEntry, created.entry.id)
    original_cache_key = entry_before.cache_key

    with pytest.raises(HTTPException) as exc:
        await update_entry(
            db_session,
            current_user=ctx,
            entry_id=created.entry.id,
            payload=UpdateEntryRequest(entry_type="formula"),
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == {"code": "GLOSSARY_ENTRY_TYPE_IMMUTABLE"}
    entry_after = await db_session.get(GlossaryEntry, created.entry.id)
    assert entry_after.entry_type == "term"
    assert entry_after.cache_key == original_cache_key


# ── cache hit (no model call) ──
async def test_cache_hit_second_student_copies_without_job(
    db_session: AsyncSession, _capture_enqueue: list
):
    seed = await _seed(db_session, students=2)
    factory = _factory(db_session)

    a = await save_from_highlight(
        db_session,
        current_user=_ctx(seed.students[0]),
        payload=SaveHighlightRequest(module_section_id=seed.section.id, term="Enzyme"),
    )
    assert len(_capture_enqueue) == 1
    await generate_glossary_definition_async(
        _capture_enqueue[-1], gateway=_gateway(factory), session_factory=factory
    )

    # Student B saves the SAME term/subject/language → cache hit, definition copied, NO new job.
    b = await save_from_highlight(
        db_session,
        current_user=_ctx(seed.students[1]),
        payload=SaveHighlightRequest(module_section_id=seed.section.id, term="Enzyme"),
    )
    assert b.duplicate is False
    assert b.entry.id != a.entry.id
    assert len(_capture_enqueue) == 1  # still one — B did not enqueue
    async with factory() as s:
        entry_b = await s.get(GlossaryEntry, b.entry.id)
        assert entry_b.definition_status == "generated"
        assert entry_b.short_definition


# ── concurrent miss collapse ──
async def test_concurrent_miss_collapses_to_one_job_and_fans_out(
    db_session: AsyncSession, _capture_enqueue: list
):
    seed = await _seed(db_session, students=2)
    factory = _factory(db_session)
    payload = SaveHighlightRequest(module_section_id=seed.section.id, term="Diffusion")

    a = await save_from_highlight(db_session, current_user=_ctx(seed.students[0]), payload=payload)
    b = await save_from_highlight(db_session, current_user=_ctx(seed.students[1]), payload=payload)

    # Two entries, ONE cache row, ONE enqueued job (the winner).
    assert a.entry.id != b.entry.id
    assert len(_capture_enqueue) == 1
    cache_count = await db_session.scalar(
        select(func.count()).select_from(GlossaryDefinitionCache)
    )
    assert cache_count == 1

    # Running the single job fans the definition out to BOTH students' entries.
    await generate_glossary_definition_async(
        _capture_enqueue[-1], gateway=_gateway(factory), session_factory=factory
    )
    async with factory() as s:
        for entry_id in (a.entry.id, b.entry.id):
            entry = await s.get(GlossaryEntry, entry_id)
            assert entry.definition_status == "generated"
            assert entry.short_definition


# ── manual add enrollment gate ──
async def test_manual_add_rejects_unenrolled_course(db_session: AsyncSession):
    seed = await _seed(db_session)
    other_student = await _make_student(db_session)  # not enrolled in the module
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await save_manual(
            db_session,
            current_user=_ctx(other_student),
            payload=ManualEntryRequest(subject_id=seed.module.id, term="Photosynthesis"),
        )
    assert exc.value.status_code == 404


# ── personal scoping ──
async def test_one_student_cannot_read_anothers_entry(
    db_session: AsyncSession, _capture_enqueue: list
):
    seed = await _seed(db_session, students=2)
    a = await save_from_highlight(
        db_session,
        current_user=_ctx(seed.students[0]),
        payload=SaveHighlightRequest(module_section_id=seed.section.id, term="Vacuole"),
    )

    # The owner reads their own entry fine.
    own = await get_entry(db_session, current_user=_ctx(seed.students[0]), entry_id=a.entry.id)
    assert own.entry.id == a.entry.id

    # A second student gets 404 (not 403) for the first student's entry.
    with pytest.raises(HTTPException) as exc:
        await get_entry(db_session, current_user=_ctx(seed.students[1]), entry_id=a.entry.id)
    assert exc.value.status_code == 404
