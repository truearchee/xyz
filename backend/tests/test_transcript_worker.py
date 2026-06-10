from __future__ import annotations

import asyncio
import hashlib
import inspect
import math
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.transcripts import chunk_service
from app.domains.transcripts import chunker
from app.domains.transcripts import embedding_service
from app.domains.transcripts import jobs as transcript_jobs
from app.domains.transcripts import service as transcript_service
from app.domains.transcripts import parse_service
from app.domains.transcripts.chunker import ChunkDraft, ChunkingResult
from app.domains.transcripts.embedding_encoder import DeterministicEmbeddingEncoder
from app.domains.transcripts.parse_service import ParseClaim, parse_transcript_async
from app.domains.transcripts.parsers.types import ParsedSegment, TranscriptParseError
from app.platform.config import settings
from app.platform.db.models import IngestionJob, Transcript, TranscriptChunk, TranscriptSegment
from app.platform.storage.base import StorageProviderError
from app.workers import queues
from app.workers import worker as worker_module
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


async def _chunk_job(session: AsyncSession, transcript_id: UUID) -> IngestionJob:
    return (
        await session.execute(
            select(IngestionJob).where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type == "chunk",
            )
        )
    ).scalar_one()


async def _embed_job(session: AsyncSession, transcript_id: UUID) -> IngestionJob:
    return (
        await session.execute(
            select(IngestionJob).where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type == "embed",
            )
        )
    ).scalar_one()


async def _chunks(session: AsyncSession, transcript_id: UUID) -> list[TranscriptChunk]:
    return (
        await session.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == transcript_id)
            .order_by(TranscriptChunk.chunk_index)
        )
    ).scalars().all()


async def _create_parsed_transcript(
    session: AsyncSession,
    *,
    texts: list[str],
) -> tuple[Transcript, UUID]:
    transcript = await _create_worker_transcript(session, raw=VTT_BYTES)
    transcript.status = "parsing"
    parse_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="parse",
        status="completed",
        idempotency_key=f"parse:{transcript.id}:{transcript.checksum}",
        processor_version="parse:v1",
        completed_at=datetime.now(UTC),
    )
    session.add(parse_job)
    await session.flush()
    session.add_all(
        [
            TranscriptSegment(
                transcript_id=transcript.id,
                sequence_number=index,
                start_ms=index * 1000,
                end_ms=(index + 1) * 1000,
                text=text,
            )
            for index, text in enumerate(texts)
        ]
    )
    chunk_job_id = await chunk_service.create_chunk_job_for_parse_success(
        session,
        transcript=transcript,
        parse_job=parse_job,
    )
    assert chunk_job_id is not None
    await session.commit()
    return transcript, chunk_job_id


async def _create_chunked_transcript(
    session: AsyncSession,
    *,
    texts: list[str],
) -> tuple[Transcript, UUID]:
    transcript = await _create_worker_transcript(session, raw=VTT_BYTES)
    transcript.status = "completed"
    parse_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="parse",
        status="completed",
        idempotency_key=f"parse:{transcript.id}:{transcript.checksum}",
        processor_version="parse:v1",
        completed_at=datetime.now(UTC),
    )
    chunk_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="chunk",
        status="completed",
        idempotency_key=(
            f"{transcript.id}:chunk:{transcript.checksum}:"
            "parse:v1:norm-v1-structural:chunk-v1-no-overlap-180w"
        ),
        processor_version=chunk_service.CHUNK_PROCESSOR_VERSION,
        completed_at=datetime.now(UTC),
        result_metadata={"chunk_count": len(texts), "oversized_segment_count": 0},
    )
    session.add_all([parse_job, chunk_job])
    await session.flush()
    segments: list[TranscriptSegment] = []
    for index, text in enumerate(texts):
        segment = TranscriptSegment(
            transcript_id=transcript.id,
            sequence_number=index,
            start_ms=index * 1000,
            end_ms=(index + 1) * 1000,
            text=text,
        )
        segments.append(segment)
        session.add(segment)
    await session.flush()
    session.add_all(
        [
            TranscriptChunk(
                transcript_id=transcript.id,
                chunk_index=index,
                start_segment_id=segments[index].id,
                end_segment_id=segments[index].id,
                start_sequence_number=index,
                end_sequence_number=index,
                start_time=index * 1000,
                end_time=(index + 1) * 1000,
                text=text,
                token_count=len(text.split()),
                token_count_method="words",
                normalization_version="norm-v1-structural",
                chunking_version="chunk-v1-no-overlap-180w",
            )
            for index, text in enumerate(texts)
        ]
    )
    embed_job_id = await embedding_service.create_embed_job_for_chunk_success(
        session,
        transcript=transcript,
        chunk_job=chunk_job,
    )
    assert embed_job_id is not None
    await session.commit()
    return transcript, embed_job_id


@pytest.mark.anyio
async def test_parse_transcript_vtt_success_is_idempotent_and_contiguous(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
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
    enqueued: list[UUID] = []
    monkeypatch.setattr(parse_service, "enqueue_chunk_transcript", lambda job_id: enqueued.append(job_id))
    await db_session.commit()

    factory = _session_factory(db_session)
    await parse_transcript_async(transcript_id, storage_provider=storage, session_factory=factory)
    await parse_transcript_async(transcript_id, storage_provider=storage, session_factory=factory)
    db_session.expire_all()

    segments = await _segments(db_session, transcript_id)
    job = await _parse_job(db_session, transcript_id)
    chunk_job = await _chunk_job(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)

    assert refreshed is not None
    assert refreshed.status == "parsing"
    assert job.status == "completed"
    assert chunk_job.status == "queued"
    assert chunk_job.processor_version == chunk_service.CHUNK_PROCESSOR_VERSION
    assert chunk_job.result_metadata is None
    assert enqueued == [chunk_job.id]
    assert job.attempts == 1
    assert [segment.sequence_number for segment in segments] == [0, 1]
    assert [segment.text for segment in segments] == ["Hello", "Example: Preserve this label"]
    assert segments[0].speaker_name == "Dr Smith"
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 1000


@pytest.mark.anyio
async def test_chunk_transcript_persists_chunks_and_completion_metadata(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world", "WEBVTT\n\n1\n00:00.000 --> 00:01.000", "next segment"],
    )
    transcript_id = transcript.id
    enqueued: list[UUID] = []
    monkeypatch.setattr(
        chunk_service,
        "enqueue_embed_transcript",
        lambda job_id: enqueued.append(job_id),
    )

    await chunk_service.chunk_transcript_async(
        chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    segments = await _segments(db_session, transcript_id)
    chunks = await _chunks(db_session, transcript_id)
    job = await _chunk_job(db_session, transcript_id)
    embed_job = await _embed_job(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)

    assert refreshed is not None
    assert refreshed.status == "completed"
    assert job.status == "completed"
    assert embed_job.status == "queued"
    assert embed_job.processor_version == embedding_service.EMBED_PROCESSOR_VERSION
    assert enqueued == [embed_job.id]
    assert job.result_metadata == {"chunk_count": 1, "oversized_segment_count": 0}
    assert len(segments) > 0
    assert len(chunks) > 0
    assert [chunk.chunk_index for chunk in chunks] == [0]
    assert chunks[0].text == "hello world next segment"
    assert segments[0].text == "hello world"
    assert chunks[0].start_sequence_number == 0
    assert chunks[0].end_sequence_number == 2
    assert chunks[0].start_time == 0
    assert chunks[0].end_time == 3000


@pytest.mark.anyio
async def test_embed_transcript_persists_vectors_and_provenance(
    db_session: AsyncSession,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["first chunk", "second chunk"],
    )
    transcript_id = transcript.id

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
        batch_size=1,
    )
    db_session.expire_all()

    chunks = await _chunks(db_session, transcript_id)
    job = await _embed_job(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)

    assert refreshed is not None
    assert refreshed.status == "completed"
    assert job.status == "completed"
    assert job.attempts == 1
    assert job.result_metadata == {
        "chunk_count": 2,
        "embedded_chunk_count": 2,
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_model_revision": settings.EMBEDDING_MODEL_REVISION,
        "embedding_dimension": 384,
        "embedding_normalization": "l2",
    }
    for chunk in chunks:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 384
        assert math.isclose(
            math.sqrt(sum(value * value for value in chunk.embedding)),
            1.0,
            rel_tol=1e-5,
            abs_tol=1e-5,
        )
        assert chunk.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert chunk.embedding_model_revision == settings.EMBEDDING_MODEL_REVISION
        assert chunk.embedding_dimension == 384
        assert chunk.embedding_normalization == "l2"
        assert chunk.embedding_version == "embedding-v1"
        assert chunk.embedding_input_hash == embedding_service.expected_embedding_input_hash(
            chunk_text=chunk.text,
            model_revision=settings.EMBEDDING_MODEL_REVISION,
            chunking_version=chunk.chunking_version,
        )


@pytest.mark.anyio
async def test_embed_transcript_partial_failure_resume_reuses_same_job(
    db_session: AsyncSession,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["first chunk", "second chunk"],
    )
    transcript_id = transcript.id
    deterministic = DeterministicEmbeddingEncoder()

    class FailsAfterFirstBatch:
        def __init__(self) -> None:
            self.calls = 0

        def encode(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("raw model stack trace with secret text")
            return deterministic.encode(texts)

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=FailsAfterFirstBatch(),
        session_factory=_session_factory(db_session),
        batch_size=1,
    )
    db_session.expire_all()

    failed_job = await _embed_job(db_session, transcript_id)
    chunks_after_failure = await _chunks(db_session, transcript_id)
    assert failed_job.status == "failed"
    assert failed_job.attempts == 1
    assert failed_job.error_message == "transcript embedding failed"
    assert sum(chunk.embedding is not None for chunk in chunks_after_failure) == 1

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=deterministic,
        session_factory=_session_factory(db_session),
        batch_size=1,
    )
    db_session.expire_all()

    completed_job = await _embed_job(db_session, transcript_id)
    chunks_after_retry = await _chunks(db_session, transcript_id)
    assert completed_job.id == embed_job_id
    assert completed_job.status == "completed"
    assert completed_job.attempts == 2
    assert all(chunk.embedding is not None for chunk in chunks_after_retry)


@pytest.mark.anyio
async def test_embed_transcript_rewrites_stale_provenance(
    db_session: AsyncSession,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["first chunk"],
    )
    transcript_id = transcript.id

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    chunk = (await _chunks(db_session, transcript_id))[0]
    original_hash = chunk.embedding_input_hash
    assert original_hash is not None
    chunk.embedding_version = "stale-version"
    job = await _embed_job(db_session, transcript_id)
    job.status = "queued"
    job.completed_at = None
    await db_session.commit()

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    refreshed_chunk = (await _chunks(db_session, transcript_id))[0]
    refreshed_job = await _embed_job(db_session, transcript_id)
    assert refreshed_job.status == "completed"
    assert refreshed_chunk.embedding_version == "embedding-v1"
    assert refreshed_chunk.embedding_input_hash == original_hash


def test_embed_stale_batch_uses_skip_locked_row_selection() -> None:
    source = inspect.getsource(embedding_service._next_stale_batch)

    assert ".with_for_update(skip_locked=True)" in source


def test_embed_batch_persist_rechecks_staleness_before_write() -> None:
    source = inspect.getsource(embedding_service._persist_embedding_batch)

    write = "chunk.embedding = vector_by_id[chunk.id]"
    assert "_chunk_embedding_is_current(" in source
    assert "if expected_hash != stale_chunk.input_hash:" in source
    assert source.index("_chunk_embedding_is_current(") < source.index(write)
    assert source.index("if expected_hash != stale_chunk.input_hash:") < source.index(write)


@pytest.mark.anyio
async def test_running_embed_job_can_be_reclaimed_for_retry(
    db_session: AsyncSession,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["first chunk"],
    )
    transcript_id = transcript.id
    job = await _embed_job(db_session, transcript_id)
    job.status = "running"
    await db_session.commit()

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    refreshed_job = await _embed_job(db_session, transcript_id)
    assert refreshed_job.status == "completed"
    assert refreshed_job.attempts == 1


@pytest.mark.anyio
async def test_embed_transcript_raise_on_failure_preserves_safe_db_failure(
    db_session: AsyncSession,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["temporary chunk"],
    )
    transcript_id = transcript.id
    for chunk in await _chunks(db_session, transcript_id):
        await db_session.delete(chunk)
    await db_session.commit()

    with pytest.raises(
        embedding_service.TranscriptEmbeddingError,
        match="no transcript chunks available",
    ):
        await embedding_service.embed_transcript_async(
            embed_job_id,
            encoder=DeterministicEmbeddingEncoder(),
            session_factory=_session_factory(db_session),
            raise_on_failure=True,
        )
    db_session.expire_all()

    job = await _embed_job(db_session, transcript_id)
    assert job.status == "failed"
    assert job.error_message == "no transcript chunks available"


@pytest.mark.anyio
async def test_chunk_embed_enqueue_failure_marks_embed_job_failed(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world"],
    )
    transcript_id = transcript.id

    def fail_enqueue(_job_id: UUID) -> None:
        raise RuntimeError("redis unavailable with private details")

    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", fail_enqueue)

    await chunk_service.chunk_transcript_async(
        chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    embed_job = await _embed_job(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert embed_job.status == "failed"
    assert embed_job.error_message == embedding_service.EMBED_ENQUEUE_FAILED


@pytest.mark.anyio
async def test_active_embed_job_partial_index_blocks_duplicate_active_job(
    db_session: AsyncSession,
) -> None:
    transcript, _embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["first chunk"],
    )
    duplicate = IngestionJob(
        transcript_id=transcript.id,
        job_type="embed",
        status="running",
        idempotency_key=f"{transcript.id}:embed:duplicate",
        processor_version=embedding_service.EMBED_PROCESSOR_VERSION,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "ingestion_jobs_one_active_embed_per_transcript" in str(exc_info.value)


@pytest.mark.anyio
async def test_embed_transcript_zero_chunks_fails_safely(
    db_session: AsyncSession,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["temporary chunk"],
    )
    transcript_id = transcript.id
    for chunk in await _chunks(db_session, transcript_id):
        await db_session.delete(chunk)
    await db_session.commit()

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    job = await _embed_job(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert job.status == "failed"
    assert job.error_message == "no transcript chunks available"


@pytest.mark.anyio
async def test_embed_transcript_empty_chunk_validation_fails_safely(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(
        db_session,
        texts=["valid chunk"],
    )
    transcript_id = transcript.id

    def fail_empty(_chunk) -> None:
        raise embedding_service.TranscriptEmbeddingError("transcript chunk text is empty")

    monkeypatch.setattr(embedding_service, "_validate_chunk_for_embedding", fail_empty)

    await embedding_service.embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    job = await _embed_job(db_session, transcript_id)
    assert job.status == "failed"
    assert job.error_message == "transcript chunk text is empty"


def test_embedding_worker_startup_validation_uses_configured_snapshot(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = tmp_path / "model"
    (model_path / "1_Pooling").mkdir(parents=True)
    for relative_path in (
        "config.json",
        "modules.json",
        "tokenizer_config.json",
        "sentence_bert_config.json",
        "1_Pooling/config.json",
        "model.safetensors",
        "tokenizer.json",
    ):
        (model_path / relative_path).write_text("{}", encoding="utf-8")
    (model_path / "MODEL_REVISION").write_text(
        settings.EMBEDDING_MODEL_REVISION + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("EMBEDDING_MODEL_PATH", str(model_path))
    monkeypatch.setenv("EMBEDDING_MODEL_REVISION", settings.EMBEDDING_MODEL_REVISION)
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "2")
    monkeypatch.setenv("EMBEDDING_WORKER_CONCURRENCY", "1")

    worker_module._validate_embedding_worker_startup()


def test_embed_job_wrapper_raises_for_rq_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fail_embed(*args, **kwargs) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs
        raise embedding_service.TranscriptEmbeddingError("safe failure")

    monkeypatch.setattr(transcript_jobs, "embed_transcript_async", fail_embed)

    with pytest.raises(embedding_service.TranscriptEmbeddingError, match="safe failure"):
        transcript_jobs.embed_transcript(str(uuid4()))

    assert captured["kwargs"] == {"raise_on_failure": True}


def test_enqueue_embed_transcript_uses_embed_only_retry_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeQueue:
        def enqueue(self, *args, **kwargs) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(queues, "get_embedding_queue", lambda: FakeQueue())

    job_id = uuid4()
    queues.enqueue_embed_transcript(job_id)

    kwargs = captured["kwargs"]
    assert kwargs["job_id"] == f"embed-{job_id}"
    retry = kwargs["retry"]
    assert retry.max == queues.EMBEDDING_RQ_RETRY_MAX
    assert retry.intervals == queues.EMBEDDING_RQ_RETRY_INTERVALS


@pytest.mark.anyio
async def test_chunk_transcript_idempotent_rerun_does_not_duplicate_chunks(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world"],
    )
    transcript_id = transcript.id
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)

    await chunk_service.chunk_transcript_async(
        chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    await chunk_service.chunk_transcript_async(
        chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    chunks = await _chunks(db_session, transcript_id)
    job = await _chunk_job(db_session, transcript_id)
    refreshed = await db_session.get(Transcript, transcript_id)
    assert len(chunks) == 1
    assert job.attempts == 1
    assert refreshed is not None
    assert refreshed.status == "completed"


@pytest.mark.anyio
async def test_same_chunk_job_concurrent_workers_complete_once(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world"],
    )
    transcript_id = transcript.id
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)

    await asyncio.gather(
        chunk_service.chunk_transcript_async(
            chunk_job_id,
            session_factory=_session_factory(db_session),
        ),
        chunk_service.chunk_transcript_async(
            chunk_job_id,
            session_factory=_session_factory(db_session),
        ),
    )
    db_session.expire_all()

    chunks = await _chunks(db_session, transcript_id)
    job = await db_session.get(IngestionJob, chunk_job_id)
    assert [chunk.text for chunk in chunks] == ["hello world"]
    assert job is not None
    assert job.status == "completed"
    assert job.attempts == 1
    assert job.result_metadata == {"chunk_count": 1, "oversized_segment_count": 0}


@pytest.mark.anyio
async def test_running_chunk_job_noops_without_replacing_existing_chunks(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["existing valid chunk"],
    )
    transcript_id = transcript.id
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)

    await chunk_service.chunk_transcript_async(
        chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    chunks_before = await _chunks(db_session, transcript_id)
    assert [chunk.text for chunk in chunks_before] == ["existing valid chunk"]

    job = await db_session.get(IngestionJob, chunk_job_id)
    assert job is not None
    job.status = "running"
    job.result_metadata = {"chunk_count": 1, "oversized_segment_count": 0}
    await db_session.commit()

    await chunk_service.chunk_transcript_async(
        chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    chunks_after = await _chunks(db_session, transcript_id)
    current_job = await db_session.get(IngestionJob, chunk_job_id)
    refreshed = await db_session.get(Transcript, transcript_id)
    assert [chunk.text for chunk in chunks_after] == ["existing valid chunk"]
    assert [chunk.chunk_index for chunk in chunks_after] == [0]
    assert current_job is not None
    assert current_job.status == "running"
    assert current_job.attempts == 1
    assert current_job.result_metadata == {"chunk_count": 1, "oversized_segment_count": 0}
    assert refreshed is not None
    assert refreshed.status == "completed"


def test_chunk_replacement_locks_transcript_row_before_delete() -> None:
    source = inspect.getsource(chunk_service._persist_chunks)

    transcript_lock = (
        "select(Transcript)" in source
        and ".where(Transcript.id == job.transcript_id)" in source
        and ".with_for_update()" in source
    )
    assert transcript_lock
    assert source.index("select(Transcript)") < source.index("delete(TranscriptChunk)")


@pytest.mark.anyio
async def test_same_transcript_different_chunk_keys_serialize_replacement(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, old_chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world"],
    )
    transcript_id = transcript.id
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)
    parse_job = await _parse_job(db_session, transcript_id)
    parse_job.processor_version = "parse:v2"
    new_chunk_job_id = await chunk_service.create_chunk_job_for_parse_success(
        db_session,
        transcript=transcript,
        parse_job=parse_job,
    )
    assert new_chunk_job_id is not None
    assert new_chunk_job_id != old_chunk_job_id
    await db_session.commit()

    await asyncio.gather(
        chunk_service.chunk_transcript_async(
            old_chunk_job_id,
            session_factory=_session_factory(db_session),
        ),
        chunk_service.chunk_transcript_async(
            new_chunk_job_id,
            session_factory=_session_factory(db_session),
        ),
    )
    db_session.expire_all()

    chunks = await _chunks(db_session, transcript_id)
    old_job = await db_session.get(IngestionJob, old_chunk_job_id)
    new_job = await db_session.get(IngestionJob, new_chunk_job_id)
    assert [chunk.chunk_index for chunk in chunks] == [0]
    assert [chunk.text for chunk in chunks] == ["hello world"]
    assert old_job is not None
    assert new_job is not None
    assert old_job.status == "completed"
    assert new_job.status == "completed"
    assert old_job.attempts == 1
    assert new_job.attempts == 1
    assert old_job.idempotency_key != new_job.idempotency_key


@pytest.mark.anyio
async def test_chunking_version_bump_creates_new_key_and_rechunks(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, old_chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world"],
    )
    transcript_id = transcript.id
    parse_job = await _parse_job(db_session, transcript_id)
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)

    await chunk_service.chunk_transcript_async(
        old_chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    old_job = await db_session.get(IngestionJob, old_chunk_job_id)
    assert old_job is not None
    old_key = old_job.idempotency_key

    monkeypatch.setattr(chunk_service, "CHUNKING_VERSION", "chunk-v2-no-overlap-200w")
    monkeypatch.setattr(chunk_service, "CHUNK_PROCESSOR_VERSION", "chunk-v2-no-overlap-200w")
    monkeypatch.setattr(chunker, "CHUNKING_VERSION", "chunk-v2-no-overlap-200w")
    new_chunk_job_id = await chunk_service.create_chunk_job_for_parse_success(
        db_session,
        transcript=transcript,
        parse_job=parse_job,
    )
    assert new_chunk_job_id is not None
    await db_session.commit()

    await chunk_service.chunk_transcript_async(
        new_chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    new_job = await db_session.get(IngestionJob, new_chunk_job_id)
    chunks = await _chunks(db_session, transcript_id)
    assert new_job is not None
    assert new_job.idempotency_key != old_key
    assert new_job.status == "completed"
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].chunking_version == "chunk-v2-no-overlap-200w"
    assert chunks[0].normalization_version == "norm-v1-structural"


@pytest.mark.anyio
async def test_normalization_version_bump_creates_new_key_and_rechunks(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, old_chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world"],
    )
    transcript_id = transcript.id
    parse_job = await _parse_job(db_session, transcript_id)
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)

    await chunk_service.chunk_transcript_async(
        old_chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    old_job = await db_session.get(IngestionJob, old_chunk_job_id)
    assert old_job is not None
    old_key = old_job.idempotency_key

    monkeypatch.setattr(chunk_service, "NORMALIZATION_VERSION", "norm-v2-structural")
    monkeypatch.setattr(chunker, "NORMALIZATION_VERSION", "norm-v2-structural")
    new_chunk_job_id = await chunk_service.create_chunk_job_for_parse_success(
        db_session,
        transcript=transcript,
        parse_job=parse_job,
    )
    assert new_chunk_job_id is not None
    await db_session.commit()

    await chunk_service.chunk_transcript_async(
        new_chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    new_job = await db_session.get(IngestionJob, new_chunk_job_id)
    chunks = await _chunks(db_session, transcript_id)
    assert new_job is not None
    assert new_job.idempotency_key != old_key
    assert new_job.status == "completed"
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].normalization_version == "norm-v2-structural"
    assert chunks[0].chunking_version == "chunk-v1-no-overlap-180w"


@pytest.mark.anyio
async def test_chunk_key_uses_persisted_parse_processor_version(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["hello world"],
    )
    transcript_id = transcript.id
    parse_job = await _parse_job(db_session, transcript_id)
    parse_job.processor_version = "parser-v-old"
    monkeypatch.setattr(parse_service, "PARSE_PROCESSOR_VERSION", "parser-v-new")

    old_version_job_id = await chunk_service.create_chunk_job_for_parse_success(
        db_session,
        transcript=transcript,
        parse_job=parse_job,
    )
    assert old_version_job_id is not None
    old_version_job = await db_session.get(IngestionJob, old_version_job_id)
    original_job = await db_session.get(IngestionJob, chunk_job_id)
    assert old_version_job is not None
    assert original_job is not None
    assert ":parser-v-old:" in old_version_job.idempotency_key
    assert ":parser-v-new:" not in old_version_job.idempotency_key
    assert old_version_job.idempotency_key != original_job.idempotency_key

    parse_job.processor_version = "parser-v-new"
    new_version_job_id = await chunk_service.create_chunk_job_for_parse_success(
        db_session,
        transcript=transcript,
        parse_job=parse_job,
    )
    assert new_version_job_id is not None
    new_version_job = await db_session.get(IngestionJob, new_version_job_id)
    assert new_version_job is not None
    assert ":parser-v-new:" in new_version_job.idempotency_key
    assert new_version_job.idempotency_key != old_version_job.idempotency_key


@pytest.mark.anyio
async def test_chunk_precondition_failure_leaves_transcript_unchanged(
    db_session: AsyncSession,
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "parsing"
    job = IngestionJob(
        transcript_id=transcript.id,
        job_type="chunk",
        status="queued",
        idempotency_key=f"{transcript.id}:chunk:{transcript.checksum}:parse:v1:norm-v1-structural:chunk-v1-no-overlap-180w",
        processor_version=chunk_service.CHUNK_PROCESSOR_VERSION,
    )
    db_session.add(job)
    await db_session.flush()
    transcript_id = transcript.id
    job_id = job.id
    await db_session.commit()

    await chunk_service.chunk_transcript_async(
        job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    refreshed = await db_session.get(Transcript, transcript_id)
    current_job = await db_session.get(IngestionJob, job_id)
    assert refreshed is not None
    assert refreshed.status == "parsing"
    assert current_job is not None
    assert current_job.status == "failed"
    assert current_job.error_message == chunk_service.PRECONDITION_PARSE_NOT_COMPLETED
    assert await _chunks(db_session, transcript_id) == []


@pytest.mark.anyio
async def test_chunk_failure_rolls_back_replacement_and_records_sanitized_error(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(
        db_session,
        texts=["old text"],
    )
    transcript_id = transcript.id
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)
    await chunk_service.chunk_transcript_async(
        chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    existing_chunks = await _chunks(db_session, transcript_id)
    assert len(existing_chunks) == 1

    parse_job = await _parse_job(db_session, transcript_id)
    parse_job.processor_version = "parse:v2"
    new_chunk_job_id = await chunk_service.create_chunk_job_for_parse_success(
        db_session,
        transcript=transcript,
        parse_job=parse_job,
    )
    assert new_chunk_job_id is not None

    def bad_chunk_segments(_segments):
        return ChunkingResult(
            chunks=[
                ChunkDraft(
                    chunk_index=0,
                    start_segment_id=uuid4(),
                    end_segment_id=uuid4(),
                    start_sequence_number=0,
                    end_sequence_number=0,
                    start_time=0,
                    end_time=1,
                    text="secret raw chunk text",
                    token_count=4,
                    token_count_method="heuristic_word_count_v1",
                    normalization_version="norm-v1-structural",
                    chunking_version="chunk-v1-no-overlap-180w",
                    is_oversized=False,
                )
            ],
            oversized_segment_count=0,
        )

    monkeypatch.setattr(chunk_service, "chunk_segments", bad_chunk_segments)
    await db_session.commit()

    await chunk_service.chunk_transcript_async(
        new_chunk_job_id,
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    chunks = await _chunks(db_session, transcript_id)
    failed_job = await db_session.get(IngestionJob, new_chunk_job_id)
    refreshed = await db_session.get(Transcript, transcript_id)
    assert [chunk.text for chunk in chunks] == ["old text"]
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert failed_job is not None
    assert failed_job.status == "failed"
    assert failed_job.error_message == "chunk start segment transcript mismatch"
    assert "secret raw chunk text" not in (failed_job.error_message or "")


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
