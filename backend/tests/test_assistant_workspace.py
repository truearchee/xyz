"""Stage 8.4 — assistant Workspace + floating widget (conversation management).

Covers the bug-prone invariants A–E the navigation stage introduces, plus the new list/rename/
soft-delete surface, derive-on-read titles, keyset message pagination, and last_activity_at ordering:

  A  one ACTIVE conversation per (student, section): delete-then-reopen creates a FRESH row
  B  send idempotency survives the index rebuild (no duplicate user message)
  C  current-access-wins: access-revoked conversation is filtered from the list AND 404s on open
  D  supersession does NOT revoke access; old answers keep their snapshot; a new turn re-grounds
  E  delete-while-pending: a worker finishing later never resurrects the soft-deleted conversation

The grounding harness mirrors tests/test_assistant_grounding.py (deterministic embedding encoder +
deterministic provider) so the real resolve→retrieve→ground→snapshot path runs — nothing is faked.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.assistant import service
from app.domains.assistant.cursor import encode_cursor
from app.domains.assistant.generation_service import generate_assistant_answer_async
from app.domains.assistant.grounding import GENERAL_NOT_FROM_LECTURE, LECTURE_GROUNDED
from app.domains.assistant.schemas import SendMessageRequest
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AppUser,
    AssistantConversation,
    AssistantMessage,
    CourseMembership,
    CourseModule,
    ModuleSection,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)
from app.platform.embeddings import DEFAULT_EMBEDDING_CONFIG, DeterministicEmbeddingEncoder
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider

pytestmark = pytest.mark.anyio


# ── harness ────────────────────────────────────────────────────────────────────────────────────────
class _FakeLease:
    async def release(self) -> None:
        return None


class _RecordingLimiter:
    def __init__(self) -> None:
        self.priorities: list[str] = []

    async def acquire(self, *, backend, estimated_tokens, priority):
        self.priorities.append(priority)
        return _FakeLease()


def _now() -> datetime:
    return datetime.now(UTC)


def _factory(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def _gateway(factory, *, fault: str | None = None) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(fault=fault),
        limiter=_RecordingLimiter(),
        session_factory=factory,
    )


def _ctx(user: AppUser) -> CurrentUserContext:
    return CurrentUserContext(
        user_id=user.id, auth_provider_id=user.auth_provider_id, email=user.email,
        full_name=user.full_name, role=user.role, is_active=True, timezone="UTC",
    )


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


def _embed(text: str) -> list[float]:
    return DeterministicEmbeddingEncoder().encode([text])[0]


@pytest.fixture
def captured_enqueue(monkeypatch):
    ids: list = []
    monkeypatch.setattr(service, "enqueue_generate_assistant_answer", lambda mid: ids.append(mid))
    return ids


async def _seed(
    db_session: AsyncSession,
    *,
    module_title: str = "Biology 101",
    section_title: str = "Lecture 1",
    section_type: str = "lecture",
    published: bool = True,
    with_transcript: bool = True,
) -> SimpleNamespace:
    student = AppUser(auth_provider_id=f"auth-{uuid4()}", email=f"s-{uuid4()}@e.com", full_name="S", role="student", timezone="UTC")
    other = AppUser(auth_provider_id=f"auth-{uuid4()}", email=f"o-{uuid4()}@e.com", full_name="O", role="student", timezone="UTC")
    lecturer = AppUser(auth_provider_id=f"auth-{uuid4()}", email=f"l-{uuid4()}@e.com", full_name="L", role="lecturer", timezone="UTC")
    db_session.add_all([student, other, lecturer])
    await db_session.flush()
    module = CourseModule(title=module_title, owner_id=lecturer.id, timezone="UTC", is_active=True)
    db_session.add(module)
    await db_session.flush()
    db_session.add(CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active"))
    section = ModuleSection(
        course_module_id=module.id, title=section_title, type=section_type, order_index=0,
        publish_status="published" if published else "draft", status="active",
    )
    db_session.add(section)
    await db_session.flush()
    transcript = None
    if with_transcript:
        transcript = Transcript(
            module_section_id=section.id, source_type="manual_upload", original_file_name="t.vtt",
            storage_key=f"m/x/{uuid4()}/t.vtt", mime_type="text/vtt", file_size=10,
            checksum=hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest(), status="completed",
            uploaded_by_user_id=lecturer.id, lifecycle_state="active",
        )
        db_session.add(transcript)
        await db_session.flush()
    await db_session.commit()
    if transcript is not None:
        await _add_chunk(
            db_session,
            transcript=transcript,
            index=99,
            text="default ready assistant workspace context",
        )
    return SimpleNamespace(
        student=student, other=other, lecturer=lecturer, module=module, section=section,
        transcript=transcript,
    )


async def _add_section(db_session: AsyncSession, seed, *, title: str, text: str) -> SimpleNamespace:
    """A second published+embedded lecture in the SAME module the student belongs to."""
    section = ModuleSection(
        course_module_id=seed.module.id, title=title, type="lecture", order_index=1,
        publish_status="published", status="active",
    )
    db_session.add(section)
    await db_session.flush()
    transcript = Transcript(
        module_section_id=section.id, source_type="manual_upload", original_file_name="t.vtt",
        storage_key=f"m/x/{uuid4()}/t.vtt", mime_type="text/vtt", file_size=10,
        checksum=hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest(), status="completed",
        uploaded_by_user_id=seed.lecturer.id, lifecycle_state="active",
    )
    db_session.add(transcript)
    await db_session.flush()
    await db_session.commit()
    s = SimpleNamespace(section=section, transcript=transcript)
    await _add_chunk(db_session, transcript=transcript, index=0, text=text)
    return s


async def _add_chunk(db_session: AsyncSession, *, transcript: Transcript, index: int, text: str) -> TranscriptChunk:
    segment = TranscriptSegment(
        transcript_id=transcript.id, sequence_number=index, start_ms=index * 1000,
        end_ms=index * 1000 + 1000, text=text,
    )
    db_session.add(segment)
    await db_session.flush()
    chunk = TranscriptChunk(
        transcript_id=transcript.id, chunk_index=index, start_segment_id=segment.id,
        end_segment_id=segment.id, start_sequence_number=index, end_sequence_number=index,
        text=text, token_count=max(1, len(text.split())), token_count_method="words",
        normalization_version="norm-v1-structural", chunking_version="chunk-v1-no-overlap-180w",
        embedding=_embed(text), embedding_model=DEFAULT_EMBEDDING_CONFIG.model_name,
        embedding_model_revision="rev-test", embedding_dimension=384, embedding_normalization="l2",
        embedding_version=DEFAULT_EMBEDDING_CONFIG.embedding_version,
        embedding_input_hash=hashlib.sha256(text.encode()).hexdigest(), embedding_generated_at=_now(),
    )
    db_session.add(chunk)
    await db_session.commit()
    return chunk


async def _open(db_session, seed, *, section=None):
    return await service.open_or_create_conversation(
        db_session, current_user=_ctx(seed.student), section_id=(section or seed.section).id
    )


async def _send(db_session, seed, conv_id, content, *, key=None):
    return await service.send_message(
        db_session, current_user=_ctx(seed.student), conversation_id=conv_id,
        payload=SendMessageRequest(content=content, client_idempotency_key=key or f"k-{uuid4()}"),
    )


async def _run_turn(db_session, seed, conv_id, content, *, key=None, fault=None):
    factory = _factory(db_session)
    sent = await _send(db_session, seed, conv_id, content, key=key)
    await generate_assistant_answer_async(
        sent.assistant_message.id, gateway=_gateway(factory, fault=fault), session_factory=factory
    )
    return sent.assistant_message.id, factory


async def _get_conv(db_session, conv_id) -> AssistantConversation:
    async with _factory(db_session)() as s:
        return await s.get(AssistantConversation, conv_id)


# ── A: one active per (student, section) — delete-then-reopen creates a FRESH row ──────────────────
async def test_delete_then_reopen_creates_fresh_conversation(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    first = await _open(db_session, seed)
    await service.soft_delete_conversation(db_session, current_user=ctx, conversation_id=first.id)
    second = await _open(db_session, seed)

    assert second.id != first.id  # the tombstone freed the one-active slot
    deleted = await _get_conv(db_session, first.id)
    fresh = await _get_conv(db_session, second.id)
    assert deleted.deleted_at is not None
    assert fresh.deleted_at is None
    active_count = (
        await db_session.execute(
            select(func.count()).select_from(AssistantConversation).where(
                AssistantConversation.student_id == seed.student.id,
                AssistantConversation.attached_section_id == seed.section.id,
                AssistantConversation.conversation_kind == "lecture_default",
                AssistantConversation.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    assert active_count == 1  # exactly one ACTIVE; the soft-deleted one does not count


async def test_two_opens_return_same_active_row(db_session, captured_enqueue):
    seed = await _seed(db_session)
    a = await _open(db_session, seed)
    b = await _open(db_session, seed)  # the inline entry + the floating widget resolve to the SAME row
    assert a.id == b.id


# ── B: send idempotency survives the index rebuild ─────────────────────────────────────────────────
async def test_send_idempotent_no_duplicate_user_message(db_session, captured_enqueue):
    seed = await _seed(db_session)
    conv = await _open(db_session, seed)
    first = await _send(db_session, seed, conv.id, "hi", key="dup")
    second = await _send(db_session, seed, conv.id, "hi again", key="dup")
    assert second.user_message.id == first.user_message.id
    user_count = (
        await db_session.execute(
            select(func.count()).select_from(AssistantMessage).where(
                AssistantMessage.conversation_id == conv.id, AssistantMessage.role == "user"
            )
        )
    ).scalar_one()
    assert user_count == 1


# ── C: current-access-wins — filtered from the list AND direct open 404 ────────────────────────────
async def test_access_revoked_filtered_from_list_and_open_404(auth_client, db_session, jwt_factory, mock_jwks_client, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await _open(db_session, seed)
    # visible while published
    items, total = await service.list_conversations(db_session, current_user=ctx, limit=30, offset=0)
    assert total == 1 and [i.id for i in items] == [conv.id]

    section = await db_session.get(ModuleSection, seed.section.id)
    section.publish_status = "unpublished"
    await db_session.commit()

    items, total = await service.list_conversations(db_session, current_user=ctx, limit=30, offset=0)
    assert total == 0 and items == []  # invariant C: filtered from the Workspace list
    h = _headers(seed.student, jwt_factory)
    assert (await auth_client.get(f"/student/assistant/conversations/{conv.id}/messages", headers=h)).status_code == 404


# ── D: supersession does NOT revoke access; old snapshot frozen; new turn re-grounds ───────────────
async def test_supersession_keeps_access_and_new_turn_regrounds(db_session, captured_enqueue):
    seed = await _seed(db_session)
    old_text = "alpha original lecture content about cells"
    await _add_chunk(db_session, transcript=seed.transcript, index=0, text=old_text)
    conv = await _open(db_session, seed)
    mid1, factory = await _run_turn(db_session, seed, conv.id, old_text, key="t1")
    async with factory() as s:
        old_msg = await s.get(AssistantMessage, mid1)
        assert old_msg.grounding_status == LECTURE_GROUNDED
        assert old_msg.context_snapshot["activeTranscriptId"] == str(seed.transcript.id)

    # Replace the transcript: old → superseded, a new active transcript with DIFFERENT material.
    new_text = "beta replacement lecture content about genetics"
    old = await db_session.get(Transcript, seed.transcript.id)
    old.lifecycle_state = "superseded"
    old.superseded_at = _now()  # Stage 4.6 invariant: a superseded transcript carries its timestamp
    await db_session.flush()
    new_t = Transcript(
        module_section_id=seed.section.id, source_type="manual_upload", original_file_name="t2.vtt",
        storage_key=f"m/x/{uuid4()}/t2.vtt", mime_type="text/vtt", file_size=10,
        checksum=hashlib.sha256(f"t2-{uuid4()}".encode()).hexdigest(), status="completed",
        uploaded_by_user_id=seed.lecturer.id, lifecycle_state="active",
    )
    db_session.add(new_t)
    await db_session.flush()
    await _add_chunk(db_session, transcript=new_t, index=0, text=new_text)

    # Section still published → conversation REMAINS accessible.
    items, total = await service.list_conversations(db_session, current_user=_ctx(seed.student), limit=30, offset=0)
    assert total == 1 and items[0].id == conv.id

    # A NEW message grounds against the CURRENT (replacement) transcript; the OLD answer's snapshot is frozen.
    mid2, factory2 = await _run_turn(db_session, seed, conv.id, new_text, key="t2")
    async with factory2() as s:
        new_msg = await s.get(AssistantMessage, mid2)
        old_msg = await s.get(AssistantMessage, mid1)
        assert new_msg.grounding_status == LECTURE_GROUNDED
        assert new_msg.context_snapshot["activeTranscriptId"] == str(new_t.id)
        assert old_msg.context_snapshot["activeTranscriptId"] == str(seed.transcript.id)  # unchanged


# ── E: delete-while-pending — the worker that finishes later never resurrects the conversation ──────
async def test_delete_while_pending_no_resurrection(db_session, captured_enqueue):
    seed = await _seed(db_session)
    text = "kinetics describes reaction rates"
    await _add_chunk(db_session, transcript=seed.transcript, index=0, text=text)
    ctx = _ctx(seed.student)
    conv = await _open(db_session, seed)
    sent = await _send(db_session, seed, conv.id, text, key="pending")  # assistant row is PENDING

    before = await _get_conv(db_session, conv.id)
    activity_before_delete = before.last_activity_at
    await service.soft_delete_conversation(db_session, current_user=ctx, conversation_id=conv.id)

    # The worker finishes AFTER the delete.
    factory = _factory(db_session)
    await generate_assistant_answer_async(
        sent.assistant_message.id, gateway=_gateway(factory), session_factory=factory
    )

    async with factory() as s:
        msg = await s.get(AssistantMessage, sent.assistant_message.id)
        conv_row = await s.get(AssistantConversation, conv.id)
        assert msg.status == "completed"  # the message itself completes (harmless — never shown)
        assert conv_row.deleted_at is not None  # still a tombstone
        assert conv_row.last_activity_at == activity_before_delete  # NOT bumped → never resurfaces
    # filtered from the list and 404 on open
    items, total = await service.list_conversations(db_session, current_user=ctx, limit=30, offset=0)
    assert total == 0 and items == []
    with pytest.raises(Exception):
        await service.list_messages(db_session, current_user=ctx, conversation_id=conv.id, before=None, limit=30)


# ── list: ordering, counts, preview, grouping, empty ───────────────────────────────────────────────
async def test_list_orders_newest_activity_first_and_reorders_on_send(db_session, captured_enqueue):
    seed = await _seed(db_session, section_title="Lecture A")
    second = await _add_section(db_session, seed, title="Lecture B", text="b content")
    conv_a = await _open(db_session, seed)
    conv_b = await _open(db_session, seed, section=second.section)
    await _run_turn(db_session, seed, conv_a.id, "first to A", key="a1")
    await _run_turn(db_session, seed, conv_b.id, "then to B", key="b1")  # B now newest

    items, _ = await service.list_conversations(db_session, current_user=_ctx(seed.student), limit=30, offset=0)
    assert [i.id for i in items] == [conv_b.id, conv_a.id]

    await _send(db_session, seed, conv_a.id, "back to A", key="a2")  # A bumped to newest
    items, _ = await service.list_conversations(db_session, current_user=_ctx(seed.student), limit=30, offset=0)
    assert [i.id for i in items] == [conv_a.id, conv_b.id]


async def test_list_row_hierarchy_count_preview_and_chip(db_session, captured_enqueue):
    seed = await _seed(db_session, module_title="Chem 200", section_title="Acids")
    await _add_chunk(db_session, transcript=seed.transcript, index=0, text="acids donate protons")
    conv = await _open(db_session, seed)
    await _run_turn(db_session, seed, conv.id, "acids donate protons", key="q1")

    items, _ = await service.list_conversations(db_session, current_user=_ctx(seed.student), limit=30, offset=0)
    row = items[0]
    assert row.module_title == "Chem 200"
    assert row.section_title == "Acids"
    assert row.section_type == "lecture"
    assert row.grounding_chip == "Lecture grounded"
    assert row.message_count == 2  # one user + one assistant
    assert row.last_message_preview  # latest content-bearing message
    assert row.display_title == "Acids"  # auto title derives from the section


async def test_list_empty_for_fresh_student(db_session, captured_enqueue):
    seed = await _seed(db_session)
    items, total = await service.list_conversations(db_session, current_user=_ctx(seed.student), limit=30, offset=0)
    assert total == 0 and items == []


async def test_list_excludes_soft_deleted(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await _open(db_session, seed)
    await service.soft_delete_conversation(db_session, current_user=ctx, conversation_id=conv.id)
    items, total = await service.list_conversations(db_session, current_user=ctx, limit=30, offset=0)
    assert total == 0 and items == []


# ── title: derive-on-read + manual rename ──────────────────────────────────────────────────────────
async def test_rename_sets_manual_collapses_whitespace_and_persists(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await _open(db_session, seed)
    renamed = await service.rename_conversation(
        db_session, current_user=ctx, conversation_id=conv.id, title="  My   Exam\n\nPrep  "
    )
    assert renamed.title == "My Exam Prep"  # whitespace-collapsed, trimmed
    assert renamed.title_source == "manual"
    items, _ = await service.list_conversations(db_session, current_user=ctx, limit=30, offset=0)
    assert items[0].display_title == "My Exam Prep"  # manual title wins over the section title


async def test_rename_empty_after_collapse_is_422(db_session, captured_enqueue):
    from fastapi import HTTPException

    seed = await _seed(db_session)
    conv = await _open(db_session, seed)
    with pytest.raises(HTTPException) as exc:
        await service.rename_conversation(
            db_session, current_user=_ctx(seed.student), conversation_id=conv.id, title="   \n\t  "
        )
    assert exc.value.status_code == 422


async def test_rename_does_not_reorder(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await _open(db_session, seed)
    before = (await _get_conv(db_session, conv.id)).last_activity_at
    await service.rename_conversation(db_session, current_user=ctx, conversation_id=conv.id, title="Renamed")
    after = (await _get_conv(db_session, conv.id)).last_activity_at
    assert after == before  # rename must NOT bump last_activity_at


# ── last_activity_at bumps ─────────────────────────────────────────────────────────────────────────
async def test_send_bumps_last_activity_to_user_message_time(db_session, captured_enqueue):
    seed = await _seed(db_session)
    conv = await _open(db_session, seed)
    sent = await _send(db_session, seed, conv.id, "q", key="k")
    row = await _get_conv(db_session, conv.id)
    assert row.last_activity_at == sent.user_message.created_at


async def test_completion_bumps_last_activity_and_failure_does_not(db_session, captured_enqueue):
    seed = await _seed(db_session)
    await _add_chunk(db_session, transcript=seed.transcript, index=0, text="ohms law relates voltage current resistance")
    conv = await _open(db_session, seed)
    # success completion bumps to the assistant generated_at
    mid, factory = await _run_turn(db_session, seed, conv.id, "ohms law relates voltage current resistance", key="ok")
    async with factory() as s:
        msg = await s.get(AssistantMessage, mid)
        conv_row = await s.get(AssistantConversation, conv.id)
        assert conv_row.last_activity_at == msg.generated_at

    # a FAILED turn does not bump activity
    activity_before = (await _get_conv(db_session, conv.id)).last_activity_at
    sent = await _send(db_session, seed, conv.id, "another", key="fail")
    after_send = (await _get_conv(db_session, conv.id)).last_activity_at
    assert after_send == sent.user_message.created_at  # the send bumped it
    with pytest.raises(GatewayError):
        await generate_assistant_answer_async(
            sent.assistant_message.id, gateway=_gateway(factory, fault="provider_transient"),
            session_factory=factory,
        )
    assert (await _get_conv(db_session, conv.id)).last_activity_at == after_send  # failure left it alone


# ── keyset message pagination ──────────────────────────────────────────────────────────────────────
async def _insert_message(db_session, *, conv_id, content, created_at) -> AssistantMessage:
    msg = AssistantMessage(
        conversation_id=conv_id, role="user", status="completed", content=content,
        client_idempotency_key=None, retryable=False, created_at=created_at, updated_at=created_at,
    )
    db_session.add(msg)
    await db_session.commit()
    return msg


async def test_keyset_newest_page_then_older(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await _open(db_session, seed)
    base = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)
    for i in range(5):
        await _insert_message(db_session, conv_id=conv.id, content=f"m{i}", created_at=base + timedelta(minutes=i))

    items, next_cursor, has_more = await service.list_messages(
        db_session, current_user=ctx, conversation_id=conv.id, before=None, limit=2
    )
    assert [m.content for m in items] == ["m3", "m4"]  # newest page, display order oldest→newest
    assert has_more is True and next_cursor is not None

    older, next2, has_more2 = await service.list_messages(
        db_session, current_user=ctx, conversation_id=conv.id, before=next_cursor, limit=2
    )
    assert [m.content for m in older] == ["m1", "m2"]
    assert has_more2 is True and next2 is not None

    last, next3, has_more3 = await service.list_messages(
        db_session, current_user=ctx, conversation_id=conv.id, before=next2, limit=2
    )
    assert [m.content for m in last] == ["m0"]
    assert has_more3 is False and next3 is None


async def test_keyset_stable_under_equal_created_at(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await _open(db_session, seed)
    ts = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)
    first = await _insert_message(db_session, conv_id=conv.id, content="same-a", created_at=ts)
    second = await _insert_message(db_session, conv_id=conv.id, content="same-b", created_at=ts)
    assert first.id < second.id  # uuid7 monotonic — the id is the tiebreak

    page1, cursor1, more1 = await service.list_messages(
        db_session, current_user=ctx, conversation_id=conv.id, before=None, limit=1
    )
    assert [m.content for m in page1] == ["same-b"] and more1 is True  # larger id first (DESC)
    page2, _c2, more2 = await service.list_messages(
        db_session, current_user=ctx, conversation_id=conv.id, before=cursor1, limit=1
    )
    assert [m.content for m in page2] == ["same-a"] and more2 is False  # id tiebreak walks to the older row


async def test_invalid_cursor_is_422(db_session, captured_enqueue):
    from fastapi import HTTPException

    seed = await _seed(db_session)
    conv = await _open(db_session, seed)
    with pytest.raises(HTTPException) as exc:
        await service.list_messages(
            db_session, current_user=_ctx(seed.student), conversation_id=conv.id,
            before="not-a-valid-cursor!!", limit=10,
        )
    assert exc.value.status_code == 422


def test_cursor_round_trips() -> None:
    from app.domains.assistant.cursor import decode_cursor

    when = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)
    mid = uuid4()
    ts, parsed = decode_cursor(encode_cursor(when, mid))
    assert ts == when and parsed == mid


# ── HTTP surface: status codes for the new endpoints ───────────────────────────────────────────────
async def test_list_endpoint_403_for_non_student(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    for actor in (seed.lecturer,):
        r = await auth_client.get("/student/assistant/conversations", headers=_headers(actor, jwt_factory))
        assert r.status_code == 403


async def test_rename_other_owner_is_404(auth_client, db_session, jwt_factory, mock_jwks_client, captured_enqueue):
    seed = await _seed(db_session)
    conv = await _open(db_session, seed)
    r = await auth_client.patch(
        f"/student/assistant/conversations/{conv.id}", headers=_headers(seed.other, jwt_factory),
        json={"title": "hijack"},
    )
    assert r.status_code == 404  # not-owner → 404, never 403


async def test_delete_endpoint_204_then_open_404(auth_client, db_session, jwt_factory, mock_jwks_client, captured_enqueue):
    seed = await _seed(db_session)
    conv = await _open(db_session, seed)
    h = _headers(seed.student, jwt_factory)
    d = await auth_client.delete(f"/student/assistant/conversations/{conv.id}", headers=h)
    assert d.status_code == 204
    assert d.headers["Cache-Control"] == "private, no-store"
    # reopen by id → 404 (soft-deleted); listing no longer shows it
    assert (await auth_client.get(f"/student/assistant/conversations/{conv.id}/messages", headers=h)).status_code == 404
    listed = await auth_client.get("/student/assistant/conversations", headers=h)
    assert listed.status_code == 200 and listed.json()["pagination"]["total"] == 0


async def test_get_conversation_detail_titles_and_owner_gate(auth_client, db_session, jwt_factory, mock_jwks_client, captured_enqueue):
    seed = await _seed(db_session, module_title="Chem 200", section_title="Acids")
    conv = await _open(db_session, seed)
    detail = await service.get_conversation_detail(
        db_session, current_user=_ctx(seed.student), conversation_id=conv.id
    )
    assert detail.module_title == "Chem 200"
    assert detail.section_title == "Acids"
    assert detail.display_title == "Acids"  # auto title derives from the section
    assert detail.grounding_chip == "Lecture grounded"
    # owner via HTTP → 200; other owner → 404 (never reveal existence)
    h = _headers(seed.student, jwt_factory)
    ok = await auth_client.get(f"/student/assistant/conversations/{conv.id}", headers=h)
    assert ok.status_code == 200 and ok.json()["sectionTitle"] == "Acids"
    other = await auth_client.get(
        f"/student/assistant/conversations/{conv.id}", headers=_headers(seed.other, jwt_factory)
    )
    assert other.status_code == 404
