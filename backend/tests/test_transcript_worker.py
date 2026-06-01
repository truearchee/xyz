from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.transcripts import service as transcript_service
from app.domains.transcripts import parse_service
from app.domains.transcripts.parse_service import ParseClaim, parse_transcript_async
from app.domains.transcripts.parsers.types import ParsedSegment, TranscriptParseError
from app.platform.db.models import IngestionJob, Transcript, TranscriptSegment
from app.platform.storage.base import StorageProviderError
from tests.test_content import FakeStorageProvider
from tests.test_transcripts import (
    TXT_BYTES,
    VTT_BYTES,
    _create_membership,
    _create_module,
    _create_section,
    _create_user,
)


async def _create_worker_transcript(
    session: AsyncSession,
    *,
    raw: bytes,
    storage_key: str | None = None,
    mime_type: str = "text/vtt",
) -> Transcript:
    lecturer = await _create_user(
        session,
        email=f"worker-{uuid4()}@example.com",
        role="lecturer",
    )
    module = await _create_module(session, owner_id=lecturer.id)
    await _create_membership(
        session,
        user_id=lecturer.id,
        module_id=module.id,
        role="lecturer",
    )
    section = await _create_section(session, module_id=module.id)
    transcript = Transcript(
        module_section_id=section.id,
        source_type="manual_upload",
        original_file_name="lecture.vtt" if mime_type == "text/vtt" else "notes.txt",
        storage_key=storage_key or f"modules/test/transcripts/{uuid4()}/lecture.vtt",
        mime_type=mime_type,
        file_size=len(raw),
        checksum=hashlib.sha256(raw).hexdigest(),
        status="uploaded",
        uploaded_by_user_id=lecturer.id,
        is_active=True,
    )
    session.add(transcript)
    await session.flush()
    return transcript


def _session_factory(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


async def _segments(session: AsyncSession, transcript_id: UUID) -> list[TranscriptSegment]:
    return (
        await session.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == transcript_id)
            .order_by(TranscriptSegment.sequence_number)
        )
    ).scalars().all()


async def _parse_job(session: AsyncSession, transcript_id: UUID) -> IngestionJob:
    return (
        await session.execute(
            select(IngestionJob).where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type == "parse",
            )
        )
    ).scalar_one()


@pytest.mark.anyio
async def test_parse_transcript_vtt_success_is_idempotent_and_contiguous(
    db_session: AsyncSession,
) -> None:
    raw = (
        b"WEBVTT\n\n"
        b"00:00.000 --> 00:01.000\n<v Dr Smith>Hello</v>\n\n"
        b"00:01.000 --> 00:02.500\nExample: Preserve this label\n"
    )
    storage = FakeStorageProvider()
    transcript = await _create_worker_transcript(db_session, raw=raw)
    storage.objects[transcript.storage_key] = raw
    transcript_id = transcript.id
    await db_session.commit()

    factory = _session_factory(db_session)
    await parse_transcript_async(transcript_id, storage_provider=storage, session_factory=factory)
    await parse_transcript_async(transcript_id, storage_provider=storage, session_factory=factory)
    db_session.expire_all()

    segments = await _segments(db_session, transcript_id)
    job = await _parse_job(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)

    assert refreshed is not None
    assert refreshed.status == "parsing"
    assert job.status == "completed"
    assert job.attempts == 1
    assert [segment.sequence_number for segment in segments] == [0, 1]
    assert [segment.text for segment in segments] == ["Hello", "Example: Preserve this label"]
    assert segments[0].speaker_name == "Dr Smith"
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 1000


@pytest.mark.anyio
async def test_parse_transcript_txt_success_has_null_timestamps(
    db_session: AsyncSession,
) -> None:
    storage = FakeStorageProvider()
    transcript = await _create_worker_transcript(
        db_session,
        raw=TXT_BYTES,
        mime_type="text/plain",
    )
    storage.objects[transcript.storage_key] = TXT_BYTES
    transcript_id = transcript.id
    await db_session.commit()

    await parse_transcript_async(
        transcript_id,
        storage_provider=storage,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    segments = await _segments(db_session, transcript_id)
    assert [segment.text for segment in segments] == ["Transcript line"]
    assert segments[0].start_ms is None
    assert segments[0].end_ms is None
    assert segments[0].speaker_name is None


@pytest.mark.anyio
async def test_parse_transcript_failures_are_sanitized_and_clear_segments(
    db_session: AsyncSession,
) -> None:
    raw = b"WEBVTT\n\n00:01.000 --> 00:00.500\nraw secret cue text\n"
    storage = FakeStorageProvider()
    transcript = await _create_worker_transcript(db_session, raw=raw)
    storage.objects[transcript.storage_key] = raw
    transcript_id = transcript.id
    await db_session.commit()

    await parse_transcript_async(
        transcript_id,
        storage_provider=storage,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    job = await _parse_job(db_session, transcript_id)
    segments = await _segments(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)

    assert refreshed is not None
    assert refreshed.status == "failed"
    assert job.status == "failed"
    assert job.error_message == "invalid timestamp range"
    assert "raw secret cue text" not in (job.error_message or "")
    assert segments == []


@pytest.mark.anyio
async def test_parse_transcript_storage_read_failure_uses_sanitized_error(
    db_session: AsyncSession,
) -> None:
    storage = FakeStorageProvider()
    storage.fail_get = StorageProviderError("secret-key raw transcript payload")
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript_id = transcript.id
    storage_key = transcript.storage_key
    await db_session.commit()

    await parse_transcript_async(
        transcript_id,
        storage_provider=storage,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    job = await _parse_job(db_session, transcript_id)
    assert job.status == "failed"
    assert job.error_message == "storage provider failed"
    assert storage_key not in job.error_message
    assert "raw transcript payload" not in job.error_message
    assert await _segments(db_session, transcript_id) == []


@pytest.mark.anyio
async def test_parse_transcript_empty_content_fails(
    db_session: AsyncSession,
) -> None:
    raw = b" \n\t\n"
    storage = FakeStorageProvider()
    transcript = await _create_worker_transcript(
        db_session,
        raw=raw,
        mime_type="text/plain",
    )
    storage.objects[transcript.storage_key] = raw
    transcript_id = transcript.id
    await db_session.commit()

    await parse_transcript_async(
        transcript_id,
        storage_provider=storage,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    job = await _parse_job(db_session, transcript_id)
    assert job.status == "failed"
    assert job.error_message == "no parsable content"


@pytest.mark.anyio
async def test_claim_returns_noop_when_job_is_already_running(
    db_session: AsyncSession,
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript_id = transcript.id
    await db_session.commit()
    factory = _session_factory(db_session)

    async with factory() as session:
        claim = await parse_service._claim_parse_job(session, transcript_id=transcript_id)
    async with factory() as session:
        second_claim = await parse_service._claim_parse_job(session, transcript_id=transcript_id)

    assert claim is not None
    assert second_claim is None


@pytest.mark.anyio
async def test_attempt_guard_blocks_stale_success_and_failure_mutations(
    db_session: AsyncSession,
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    stale_segment = TranscriptSegment(
        transcript_id=transcript.id,
        sequence_number=0,
        text="existing",
    )
    job = IngestionJob(
        transcript_id=transcript.id,
        job_type="parse",
        status="running",
        idempotency_key=f"parse:{transcript.id}:{transcript.checksum}",
        processor_version="parse:v1",
        attempts=2,
    )
    db_session.add_all([stale_segment, job])
    transcript_id = transcript.id
    await db_session.flush()
    job_id = job.id
    await db_session.commit()
    claim = ParseClaim(
        transcript_id=transcript_id,
        storage_key=transcript.storage_key,
        mime_type=transcript.mime_type,
        idempotency_key=f"parse:{transcript_id}:{transcript.checksum}",
        claimed_attempt=1,
        job_id=job_id,
    )
    factory = _session_factory(db_session)

    async with factory() as session:
        await parse_service._persist_success(
            session,
            claim=claim,
            segments=[ParsedSegment(text="new")],
        )
    async with factory() as session:
        await parse_service._persist_failure(
            session,
            claim=claim,
            exc=TranscriptParseError("no parsable content"),
        )
    db_session.expire_all()

    segments = await _segments(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)
    current_job = await db_session.get(IngestionJob, job_id)
    assert [segment.text for segment in segments] == ["existing"]
    assert refreshed is not None
    assert refreshed.status == "uploaded"
    assert current_job is not None
    assert current_job.status == "running"


@pytest.mark.anyio
async def test_conditional_queued_update_does_not_downgrade_parsing_status(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "parsing"
    transcript_id = transcript.id
    enqueued: list[UUID] = []
    monkeypatch.setattr(
        "app.domains.transcripts.service.enqueue_parse_transcript",
        lambda transcript_id: enqueued.append(transcript_id),
    )
    await db_session.commit()

    await transcript_service._enqueue_parse_job(db_session, transcript_id=transcript_id)

    db_session.expire_all()
    refreshed = await db_session.get(Transcript, transcript_id)
    assert enqueued == [transcript_id]
    assert refreshed is not None
    assert refreshed.status == "parsing"
