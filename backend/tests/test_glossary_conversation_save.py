"""Stage 8.5 — conversation-sourced glossary save (save-to-glossary from the assistant).

The seam between the assistant domain and the glossary domain: a student highlights a term in a COMPLETED
assistant reply and saves it through the EXISTING glossary save endpoint with a discriminated
``conversation`` source. These tests pin the anti-spoofing + ownership + visibility verification, the
idempotent duplicate-source attach, and the load-bearing ADR-055 invariant: a chat save feeds NO chat text
to the definition prompt (empty context → the same cache key + input hash as a manual add).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.domains.glossary.save_service as save_service
from app.domains.glossary.cache_keys import definition_input_hash
from app.domains.glossary.definition_service import generate_glossary_definition_async
from app.domains.glossary.schemas import (
    ConversationSaveSource,
    ManualEntryRequest,
    SaveHighlightRequest,
)
from app.domains.glossary.service import save_from_highlight, save_manual
from app.domains.glossary.specs import GLOSSARY_DEFINITION_PROMPT_VERSION
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AppUser,
    AssistantConversation,
    AssistantMessage,
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

DEFAULT_CONTENT = "The **mitochondria** is the powerhouse of the cell."


# ── harness (mirrors test_glossary_save) ──
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
        provider=DeterministicTestProvider(),
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


async def _make_student(db: AsyncSession) -> AppUser:
    student = AppUser(
        auth_provider_id=f"auth-{uuid4()}",
        email=f"student-{uuid4()}@example.com",
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
        db.add(CourseMembership(user_id=s.id, module_id=module.id, role="student", status="active"))
        student_users.append(s)
    await db.commit()
    return SimpleNamespace(owner=owner, module=module, section=section, students=student_users)


async def _conversation(
    db: AsyncSession,
    *,
    student: AppUser,
    attached_section_id,
    kind: str = "lecture_default",
    deleted_at: datetime | None = None,
) -> AssistantConversation:
    conv = AssistantConversation(
        student_id=student.id,
        conversation_kind=kind,
        attached_section_id=attached_section_id,
        deleted_at=deleted_at,
    )
    db.add(conv)
    await db.flush()
    return conv


async def _message(
    db: AsyncSession,
    *,
    conv: AssistantConversation,
    role: str = "assistant",
    status: str = "completed",
    content: str | None = DEFAULT_CONTENT,
) -> AssistantMessage:
    msg = AssistantMessage(conversation_id=conv.id, role=role, status=status, content=content)
    db.add(msg)
    await db.flush()
    return msg


def _payload(conv, msg, *, term: str = "Mitochondria", selected_text: str = "mitochondria"):
    return SaveHighlightRequest(
        conversation=ConversationSaveSource(conversation_id=conv.id, message_id=msg.id),
        term=term,
        selected_text=selected_text,
    )


async def _conversation_sources(db: AsyncSession, entry_id) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(GlossarySourceReference)
        .where(
            GlossarySourceReference.glossary_entry_id == entry_id,
            GlossarySourceReference.source_type == "conversation",
        )
    )


# ── (l) happy path — provenance + the ADR-055 empty-context proof ──
async def test_conversation_save_creates_entry_with_empty_context_definition(
    db_session: AsyncSession, _capture_enqueue: list
):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv, content="Diffusion moves particles down a gradient.")

    resp = await save_from_highlight(
        db_session, current_user=ctx, payload=_payload(conv, msg, term="Diffusion", selected_text="Diffusion")
    )
    assert resp.duplicate is False
    assert resp.entry.subject_id == seed.module.id  # subject resolved from the conversation's section
    assert resp.entry.module_section_id == seed.section.id
    assert len(_capture_enqueue) == 1

    src = (
        await db_session.execute(
            select(GlossarySourceReference).where(
                GlossarySourceReference.glossary_entry_id == resp.entry.id
            )
        )
    ).scalar_one()
    assert src.source_type == "conversation"
    assert src.source_conversation_id == conv.id
    assert src.source_message_id == msg.id
    assert src.module_section_id == seed.section.id
    assert src.selected_text == "Diffusion"  # provenance snippet stored on the source reference

    # glossary_term_saved emitted in the same txn (reused event type).
    events = (
        await db_session.execute(
            select(StudentActivityEvent).where(StudentActivityEvent.source_id == resp.entry.id)
        )
    ).scalars().all()
    assert [e.event_type for e in events] == ["glossary_term_saved"]

    # Run the definition job and PROVE no chat text reached the prompt: the cache stores NO context, and
    # the recorded input hash equals the empty-context hash (== a manual add of the same term, ADR-055).
    factory = _factory(db_session)
    await generate_glossary_definition_async(
        _capture_enqueue[-1], gateway=_gateway(factory), session_factory=factory
    )
    async with factory() as s:
        entry = await s.get(GlossaryEntry, resp.entry.id)
        cache = (
            await s.execute(
                select(GlossaryDefinitionCache).where(
                    GlossaryDefinitionCache.cache_key == entry.cache_key
                )
            )
        ).scalar_one()
        assert entry.definition_status == "generated"
        assert cache.context_text is None  # the highlighted chat text never became prompt context
        assert cache.source_content_hash == definition_input_hash(
            cache_key=cache.cache_key,
            prompt_version=GLOSSARY_DEFINITION_PROMPT_VERSION,
            context_text="",
        )


# ── (k) cross-collapse: a chat save shares a manual add's cache row (one model call, ADR-055) ──
async def test_conversation_save_shares_manual_add_cache_row(
    db_session: AsyncSession, _capture_enqueue: list
):
    # Student A adds the term manually (empty context); Student B saves the SAME term from a chat. They
    # are different students (so two entries), but the empty-context chat definition lands on the SAME
    # cache row as the manual add — proving the chat save uses the identical subject-level input.
    seed = await _seed(db_session, students=2)
    factory = _factory(db_session)

    manual = await save_manual(
        db_session,
        current_user=_ctx(seed.students[0]),
        payload=ManualEntryRequest(subject_id=seed.module.id, term="Respiration"),
    )
    assert len(_capture_enqueue) == 1
    await generate_glossary_definition_async(
        _capture_enqueue[-1], gateway=_gateway(factory), session_factory=factory
    )

    conv = await _conversation(db_session, student=seed.students[1], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv, content="Respiration releases energy from glucose.")
    chat = await save_from_highlight(
        db_session,
        current_user=_ctx(seed.students[1]),
        payload=_payload(conv, msg, term="Respiration", selected_text="Respiration"),
    )

    assert chat.duplicate is False
    assert chat.entry.id != manual.entry.id
    assert len(_capture_enqueue) == 1  # cache HIT — the chat save enqueued NO new job
    async with factory() as s:
        chat_entry = await s.get(GlossaryEntry, chat.entry.id)
        manual_entry = await s.get(GlossaryEntry, manual.entry.id)
        assert chat_entry.cache_key == manual_entry.cache_key  # same subject+term+lang → same key
        assert chat_entry.definition_status == "generated"
    cache_count = await db_session.scalar(select(func.count()).select_from(GlossaryDefinitionCache))
    assert cache_count == 1  # one cache row total → one model call shared


# ── (j) idempotent double-submit ──
async def test_double_submit_is_idempotent(db_session: AsyncSession, _capture_enqueue: list):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv, content="Photosynthesis converts light into sugar.")
    payload = _payload(conv, msg, term="Photosynthesis", selected_text="Photosynthesis")

    first = await save_from_highlight(db_session, current_user=ctx, payload=payload)
    second = await save_from_highlight(db_session, current_user=ctx, payload=payload)

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.entry.id == first.entry.id

    entries = await db_session.scalar(
        select(func.count()).select_from(GlossaryEntry).where(GlossaryEntry.student_id == ctx.user_id)
    )
    assert entries == 1  # no second entry
    assert await _conversation_sources(db_session, first.entry.id) == 1  # source attached at most once
    events = await db_session.scalar(
        select(func.count())
        .select_from(StudentActivityEvent)
        .where(StudentActivityEvent.source_id == first.entry.id)
    )
    assert events == 1  # only the first save emitted an event
    assert len(_capture_enqueue) == 1  # only the first save enqueued a job


# ── (e) selected text must occur in the message (anti-spoofing) ──
async def test_selected_text_not_in_message_rejected(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv, content="The mitochondria is the powerhouse.")

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(
            db_session,
            current_user=ctx,
            payload=_payload(conv, msg, term="Spoof", selected_text="the assistant never said this"),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == {"code": "GLOSSARY_SELECTED_TEXT_NOT_IN_MESSAGE"}


async def test_selected_text_matches_across_markdown(db_session: AsyncSession, _capture_enqueue: list):
    # The browser selection is rendered text ("mitochondria"); the stored message is markdown
    # ("**mitochondria**"). The normalizer must not false-reject across the emphasis markers.
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv, content="The **mitochondria** is the powerhouse.")

    resp = await save_from_highlight(
        db_session, current_user=ctx, payload=_payload(conv, msg, term="Mitochondria", selected_text="mitochondria")
    )
    assert resp.duplicate is False
    assert resp.entry.term == "Mitochondria"


async def test_blank_selected_text_rejected(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv)

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(
            db_session, current_user=ctx, payload=_payload(conv, msg, selected_text="   ")
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == {"code": "GLOSSARY_SELECTED_TEXT_REQUIRED"}


# ── (a) a student's OWN message cannot be a save source ──
async def test_user_message_rejected(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv, role="user", content="what is mitochondria")

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(db_session, current_user=ctx, payload=_payload(conv, msg))
    assert exc.value.status_code == 422
    assert exc.value.detail == {"code": "GLOSSARY_SOURCE_NOT_ASSISTANT_MESSAGE"}


# ── (b/c) pending or failed assistant message cannot be a save source ──
@pytest.mark.parametrize("status", ["pending", "failed"])
async def test_non_completed_message_rejected(db_session: AsyncSession, status: str):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    content = None if status == "pending" else DEFAULT_CONTENT
    msg = await _message(db_session, conv=conv, status=status, content=content)

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(db_session, current_user=ctx, payload=_payload(conv, msg))
    assert exc.value.status_code == 409
    assert exc.value.detail == {"code": "GLOSSARY_SOURCE_MESSAGE_NOT_COMPLETED"}


# ── (d) messageId must belong to the referenced conversation ──
async def test_message_from_other_conversation_rejected(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    other = await _conversation(
        db_session, student=seed.students[0], attached_section_id=None, kind="workspace"
    )
    other_msg = await _message(db_session, conv=other)

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(db_session, current_user=ctx, payload=_payload(conv, other_msg))
    assert exc.value.status_code == 404
    assert exc.value.detail == "CONVERSATION_NOT_FOUND"


# ── (f) unbound conversation cannot be a save source ──
async def test_unbound_conversation_rejected(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(
        db_session, student=seed.students[0], attached_section_id=None, kind="workspace"
    )
    msg = await _message(db_session, conv=conv)

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(db_session, current_user=ctx, payload=_payload(conv, msg))
    assert exc.value.status_code == 404
    assert exc.value.detail == "CONVERSATION_NOT_FOUND"


# ── (g) another student's conversation cannot be a save source (404, never 403) ──
async def test_not_owned_conversation_rejected(db_session: AsyncSession):
    seed = await _seed(db_session, students=2)
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv)

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(
            db_session, current_user=_ctx(seed.students[1]), payload=_payload(conv, msg)
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "CONVERSATION_NOT_FOUND"


# ── (m) ownership is checked BEFORE role (no role leak on another's conversation) ──
async def test_not_owned_takes_precedence_over_role(db_session: AsyncSession):
    seed = await _seed(db_session, students=2)
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    user_msg = await _message(db_session, conv=conv, role="user", content="hello")

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(
            db_session, current_user=_ctx(seed.students[1]), payload=_payload(conv, user_msg)
        )
    assert exc.value.status_code == 404  # 404 (ownership), not 422 (role)


# ── (h) soft-deleted conversation cannot be a save source ──
async def test_soft_deleted_conversation_rejected(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(
        db_session,
        student=seed.students[0],
        attached_section_id=seed.section.id,
        deleted_at=datetime.now(UTC),
    )
    msg = await _message(db_session, conv=conv)

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(db_session, current_user=ctx, payload=_payload(conv, msg))
    assert exc.value.status_code == 404
    assert exc.value.detail == "CONVERSATION_NOT_FOUND"


# ── (i) a no-longer-visible (unpublished) section cannot be a save source ──
async def test_unpublished_section_rejected(db_session: AsyncSession):
    seed = await _seed(db_session)
    ctx = _ctx(seed.students[0])
    conv = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg = await _message(db_session, conv=conv)
    section = await db_session.get(ModuleSection, seed.section.id)
    section.publish_status = "draft"
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await save_from_highlight(db_session, current_user=ctx, payload=_payload(conv, msg))
    assert exc.value.status_code == 404
    assert exc.value.detail == "CONVERSATION_NOT_FOUND"


# ── (k') cache key has NO conversation/message/student component ──
async def test_cache_key_excludes_conversation(db_session: AsyncSession, _capture_enqueue: list):
    # Two students save the SAME term/subject/language from their OWN (different) conversations → two
    # personal entries, but ONE shared cache row (concurrent-miss collapse) → the cache key did not gain a
    # conversation/message dimension.
    seed = await _seed(db_session, students=2)
    conv_a = await _conversation(db_session, student=seed.students[0], attached_section_id=seed.section.id)
    msg_a = await _message(db_session, conv=conv_a, content="Osmosis is water diffusion.")
    a = await save_from_highlight(
        db_session,
        current_user=_ctx(seed.students[0]),
        payload=_payload(conv_a, msg_a, term="Osmosis", selected_text="Osmosis"),
    )
    conv_b = await _conversation(db_session, student=seed.students[1], attached_section_id=seed.section.id)
    msg_b = await _message(db_session, conv=conv_b, content="Osmosis moves water across a membrane.")
    b = await save_from_highlight(
        db_session,
        current_user=_ctx(seed.students[1]),
        payload=_payload(conv_b, msg_b, term="Osmosis", selected_text="Osmosis"),
    )

    assert a.entry.id != b.entry.id  # two personal entries
    cache_count = await db_session.scalar(select(func.count()).select_from(GlossaryDefinitionCache))
    assert cache_count == 1  # one cache row → the cache key has no conversation/message component
    assert len(_capture_enqueue) == 1  # the second save collapsed onto the in-flight job
