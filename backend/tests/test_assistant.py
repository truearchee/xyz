"""Stage 8.1 — assistant conversation foundation (domain + HTTP surface).

Covers: availability readiness (ready/processing/unavailable), 403-before-lookup for non-students,
race-safe open-or-create of the lecture_default conversation, 404-not-403 for unassigned / other-owner /
lost-access, send idempotency (no duplicate user message or AI call), the create-then-complete turn
through the real gateway (deterministic provider) at INTERACTIVE priority writing an AIRequestLog row
with feature='assistant', and retry of a failed turn that never duplicates the user message.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.assistant import service
from app.domains.assistant.generation_service import generate_assistant_answer_async
from app.domains.assistant.schemas import SendMessageRequest
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AIRequestLog,
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
from app.platform.llm.errors import GatewayError
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.provider import DeterministicTestProvider

pytestmark = pytest.mark.anyio


# ── harness ──────────────────────────────────────────────────────────────────────────────────────
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


def _gateway(factory, *, limiter=None, fault: str | None = None) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(fault=fault),
        limiter=limiter or _RecordingLimiter(),
        session_factory=factory,
    )


def _headers(user: AppUser, jwt_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt_factory(sub=user.auth_provider_id)}"}


def _ctx(user: AppUser) -> CurrentUserContext:
    return CurrentUserContext(
        user_id=user.id,
        auth_provider_id=user.auth_provider_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=True,
        timezone="UTC",
    )


@pytest.fixture
def captured_enqueue(monkeypatch):
    """Replace the RQ enqueue with a recorder so domain/HTTP tests never touch Redis; the worker job is
    then driven directly via ``generate_assistant_answer_async``."""
    ids: list = []

    def fake(message_id):
        ids.append(message_id)
        return f"assistant-answer-{message_id}"

    monkeypatch.setattr(service, "enqueue_generate_assistant_answer", fake)
    return ids


async def _seed(
    db_session: AsyncSession,
    *,
    active_transcript: bool = True,
    embedded: bool = True,
    published: bool = True,
) -> SimpleNamespace:
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
    section = ModuleSection(
        course_module_id=module.id,
        title="Lecture 1",
        type="lecture",
        order_index=0,
        publish_status="published" if published else "draft",
        status="active",
    )
    db_session.add(section)
    await db_session.flush()

    transcript = None
    if active_transcript:
        checksum = hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest()
        transcript = Transcript(
            module_section_id=section.id,
            source_type="manual_upload",
            original_file_name="t.vtt",
            storage_key=f"m/x/{uuid4()}/t.vtt",
            mime_type="text/vtt",
            file_size=10,
            checksum=checksum,
            status="completed",
            uploaded_by_user_id=lecturer.id,
            lifecycle_state="active",
        )
        db_session.add(transcript)
        await db_session.flush()
        segment = TranscriptSegment(
            transcript_id=transcript.id, sequence_number=0, start_ms=0, end_ms=1000, text="hello"
        )
        db_session.add(segment)
        await db_session.flush()
        db_session.add(
            TranscriptChunk(
                transcript_id=transcript.id,
                chunk_index=0,
                start_segment_id=segment.id,
                end_segment_id=segment.id,
                start_sequence_number=0,
                end_sequence_number=0,
                text="hello world",
                token_count=2,
                token_count_method="words",
                normalization_version="norm-v1-structural",
                chunking_version="chunk-v1-no-overlap-180w",
                embedding=([0.0] * 384) if embedded else None,
                embedding_model="m" if embedded else None,
                embedding_model_revision="r" if embedded else None,
                embedding_dimension=384 if embedded else None,
                embedding_normalization="l2" if embedded else None,
                embedding_version="ev" if embedded else None,
                embedding_input_hash="h" if embedded else None,
                embedding_generated_at=_now() if embedded else None,
            )
        )
    await db_session.commit()
    return SimpleNamespace(
        student=student, other=other, lecturer=lecturer, admin=admin,
        module=module, section=section, transcript=transcript,
    )


# ── availability readiness (decision 9) ───────────────────────────────────────────────────────────
async def test_availability_ready_with_embedded_chunk(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session, embedded=True)
    r = await auth_client.get(
        f"/student/sections/{seed.section.id}/assistant/availability", headers=_headers(seed.student, jwt_factory)
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "ready"
    assert r.headers["Cache-Control"] == "private, no-store"


async def test_availability_processing_without_embeddings(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session, active_transcript=True, embedded=False)
    r = await auth_client.get(
        f"/student/sections/{seed.section.id}/assistant/availability", headers=_headers(seed.student, jwt_factory)
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "processing"


async def test_availability_unavailable_without_transcript(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session, active_transcript=False)
    r = await auth_client.get(
        f"/student/sections/{seed.section.id}/assistant/availability", headers=_headers(seed.student, jwt_factory)
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "unavailable"


# ── 403 before lookup / 404 not 403 ───────────────────────────────────────────────────────────────
async def test_non_student_403(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    for actor in (seed.lecturer, seed.admin):
        h = _headers(actor, jwt_factory)
        assert (await auth_client.get(f"/student/sections/{seed.section.id}/assistant/availability", headers=h)).status_code == 403
        assert (await auth_client.post(f"/student/sections/{seed.section.id}/assistant/conversation", headers=h)).status_code == 403


async def test_unassigned_student_404_not_403(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)  # `other` is a student but NOT a member of the module
    h = _headers(seed.other, jwt_factory)
    assert (await auth_client.get(f"/student/sections/{seed.section.id}/assistant/availability", headers=h)).status_code == 404
    assert (await auth_client.post(f"/student/sections/{seed.section.id}/assistant/conversation", headers=h)).status_code == 404


# ── open-or-create lecture_default (race-safe, idempotent) ─────────────────────────────────────────
async def test_open_or_create_is_idempotent(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    h = _headers(seed.student, jwt_factory)
    r1 = await auth_client.post(f"/student/sections/{seed.section.id}/assistant/conversation", headers=h)
    r2 = await auth_client.post(f"/student/sections/{seed.section.id}/assistant/conversation", headers=h)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["conversationKind"] == "lecture_default"
    assert r1.json()["attachedSectionId"] == str(seed.section.id)
    count = (
        await db_session.execute(
            select(func.count()).select_from(AssistantConversation).where(
                AssistantConversation.student_id == seed.student.id,
                AssistantConversation.attached_section_id == seed.section.id,
            )
        )
    ).scalar_one()
    assert count == 1


async def test_open_or_create_rejects_processing_or_unavailable_sections(
    auth_client, db_session, jwt_factory, mock_jwks_client
):
    processing = await _seed(db_session, active_transcript=True, embedded=False)
    unavailable = await _seed(db_session, active_transcript=False)

    processing_response = await auth_client.post(
        f"/student/sections/{processing.section.id}/assistant/conversation",
        headers=_headers(processing.student, jwt_factory),
    )
    unavailable_response = await auth_client.post(
        f"/student/sections/{unavailable.section.id}/assistant/conversation",
        headers=_headers(unavailable.student, jwt_factory),
    )

    assert processing_response.status_code == 409, processing_response.text
    assert processing_response.json()["detail"] == {
        "code": "assistant_not_ready",
        "state": "processing",
    }
    assert unavailable_response.status_code == 409, unavailable_response.text
    assert unavailable_response.json()["detail"] == {
        "code": "assistant_not_ready",
        "state": "unavailable",
    }


# ── the create-then-complete turn through the gateway ─────────────────────────────────────────────
async def test_send_then_generate_completes_with_provenance(db_session, captured_enqueue):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    conv = await service.open_or_create_conversation(db_session, current_user=_ctx(seed.student), section_id=seed.section.id)

    sent = await service.send_message(
        db_session,
        current_user=_ctx(seed.student),
        conversation_id=conv.id,
        payload=SendMessageRequest(content="What is this lecture about?", client_idempotency_key="k1"),
    )
    assert sent.user_message.role == "user" and sent.user_message.status == "completed"
    assert sent.assistant_message.role == "assistant" and sent.assistant_message.status == "pending"
    assert captured_enqueue == [sent.assistant_message.id]

    limiter = _RecordingLimiter()
    await generate_assistant_answer_async(
        sent.assistant_message.id, gateway=_gateway(factory, limiter=limiter), session_factory=factory
    )
    assert limiter.priorities == ["interactive"]  # rule 15: interactive headroom consumed

    async with factory() as s:
        msg = await s.get(AssistantMessage, sent.assistant_message.id)
        assert msg.status == "completed"
        assert msg.content and len(msg.content) > 0
        assert msg.ai_request_log_id is not None
        assert msg.model_id and msg.generated_at is not None
        log = await s.get(AIRequestLog, msg.ai_request_log_id)
        assert log.feature == "assistant"
        assert log.status == "succeeded"
        # user message saved first, then the assistant reply
        rows = (
            await s.execute(
                select(AssistantMessage)
                .where(AssistantMessage.conversation_id == conv.id)
                .order_by(AssistantMessage.created_at.asc(), AssistantMessage.id.asc())
            )
        ).scalars().all()
        assert [m.role for m in rows] == ["user", "assistant"]


async def test_send_is_idempotent_on_client_key(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await service.open_or_create_conversation(db_session, current_user=ctx, section_id=seed.section.id)
    first = await service.send_message(
        db_session, current_user=ctx, conversation_id=conv.id,
        payload=SendMessageRequest(content="hi", client_idempotency_key="dup-key"),
    )
    second = await service.send_message(
        db_session, current_user=ctx, conversation_id=conv.id,
        payload=SendMessageRequest(content="hi again", client_idempotency_key="dup-key"),
    )
    assert second.user_message.id == first.user_message.id
    assert second.assistant_message.id == first.assistant_message.id
    user_count = (
        await db_session.execute(
            select(func.count()).select_from(AssistantMessage).where(
                AssistantMessage.conversation_id == conv.id, AssistantMessage.role == "user"
            )
        )
    ).scalar_one()
    assert user_count == 1
    # only the FIRST send enqueued a turn
    assert captured_enqueue == [first.assistant_message.id]


async def test_send_rejects_new_turn_while_assistant_turn_pending(db_session, captured_enqueue):
    seed = await _seed(db_session)
    ctx = _ctx(seed.student)
    conv = await service.open_or_create_conversation(
        db_session, current_user=ctx, section_id=seed.section.id
    )
    first = await service.send_message(
        db_session,
        current_user=ctx,
        conversation_id=conv.id,
        payload=SendMessageRequest(content="first", client_idempotency_key="first-key"),
    )

    duplicate_retry = await service.send_message(
        db_session,
        current_user=ctx,
        conversation_id=conv.id,
        payload=SendMessageRequest(content="first", client_idempotency_key="first-key"),
    )
    assert duplicate_retry.user_message.id == first.user_message.id

    with pytest.raises(Exception) as exc:
        await service.send_message(
            db_session,
            current_user=ctx,
            conversation_id=conv.id,
            payload=SendMessageRequest(content="second", client_idempotency_key="second-key"),
        )
    assert getattr(exc.value, "status_code", None) == 409
    assert exc.value.detail == {"code": "assistant_turn_pending"}


async def test_retry_failed_turn_never_duplicates_user_message(db_session, captured_enqueue):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    ctx = _ctx(seed.student)
    conv = await service.open_or_create_conversation(db_session, current_user=ctx, section_id=seed.section.id)
    sent = await service.send_message(
        db_session, current_user=ctx, conversation_id=conv.id,
        payload=SendMessageRequest(content="explain", client_idempotency_key="k-retry"),
    )

    # First attempt fails transiently (deterministic provider fault) → marked failed + retryable, re-raises.
    with pytest.raises(GatewayError):
        await generate_assistant_answer_async(
            sent.assistant_message.id, gateway=_gateway(factory, fault="provider_transient"), session_factory=factory
        )
    async with factory() as s:
        msg = await s.get(AssistantMessage, sent.assistant_message.id)
        assert msg.status == "failed" and msg.retryable is True

    retried = await service.retry_message(db_session, current_user=ctx, message_id=sent.assistant_message.id)
    assert retried.status == "pending"
    await generate_assistant_answer_async(
        sent.assistant_message.id, gateway=_gateway(factory), session_factory=factory
    )

    async with factory() as s:
        msg = await s.get(AssistantMessage, sent.assistant_message.id)
        assert msg.status == "completed" and msg.content
        user_count = (
            await s.execute(
                select(func.count()).select_from(AssistantMessage).where(
                    AssistantMessage.conversation_id == conv.id, AssistantMessage.role == "user"
                )
            )
        ).scalar_one()
        assert user_count == 1  # retry never duplicates the user message (decision 11)


# ── ownership + live access re-check (404, never 403) ─────────────────────────────────────────────
async def test_other_students_conversation_is_404(auth_client, db_session, jwt_factory, mock_jwks_client, captured_enqueue):
    seed = await _seed(db_session)
    conv = await service.open_or_create_conversation(db_session, current_user=_ctx(seed.student), section_id=seed.section.id)
    h = _headers(seed.other, jwt_factory)
    assert (await auth_client.get(f"/student/assistant/conversations/{conv.id}/messages", headers=h)).status_code == 404
    r = await auth_client.post(
        f"/student/assistant/conversations/{conv.id}/messages", headers=h,
        json={"content": "x", "clientIdempotencyKey": "k"},
    )
    assert r.status_code == 404


async def test_lost_access_returns_404_after_unpublish(auth_client, db_session, jwt_factory, mock_jwks_client):
    seed = await _seed(db_session)
    h = _headers(seed.student, jwt_factory)
    conv = await service.open_or_create_conversation(db_session, current_user=_ctx(seed.student), section_id=seed.section.id)
    # listing works while published
    assert (await auth_client.get(f"/student/assistant/conversations/{conv.id}/messages", headers=h)).status_code == 200
    # unpublish the section → access revoked → 404, no messages render (decision 5)
    section = await db_session.get(ModuleSection, seed.section.id)
    section.publish_status = "unpublished"
    await db_session.commit()
    assert (await auth_client.get(f"/student/assistant/conversations/{conv.id}/messages", headers=h)).status_code == 404


async def test_list_messages_paginated_in_order(db_session, captured_enqueue):
    seed = await _seed(db_session)
    factory = _factory(db_session)
    ctx = _ctx(seed.student)
    conv = await service.open_or_create_conversation(db_session, current_user=ctx, section_id=seed.section.id)
    sent = await service.send_message(
        db_session, current_user=ctx, conversation_id=conv.id,
        payload=SendMessageRequest(content="q", client_idempotency_key="k1"),
    )
    await generate_assistant_answer_async(sent.assistant_message.id, gateway=_gateway(factory), session_factory=factory)

    items, next_cursor, has_more = await service.list_messages(
        db_session, current_user=ctx, conversation_id=conv.id, before=None, limit=50
    )
    assert has_more is False and next_cursor is None
    assert [m.role for m in items] == ["user", "assistant"]
    assert items[1].status == "completed" and items[1].content
