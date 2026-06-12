"""Stage 4.6b — retry over the DAG, fencing, and the sanitized failure taxonomy.

Covers (backend; the lecturer UI + browser gate are 4.6d):
  - resolve_retry_scope over the DAG (parse cascade; chunk/embed + independent summaries)
  - the retry endpoint authz matrix + 409s (superseded / nothing-retryable)
  - reset-and-re-enqueue + idempotency
  - fencing: a superseded transcript's worker step aborts (writes nothing)
  - DAG decouple: summaries fork from parse, an embed failure does not block summaries
  - projection failureCategory + retryable
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.transcripts import chunk_service, embedding_service, parse_service
from app.domains.transcripts import retry as retry_module
from app.domains.transcripts.embedding_encoder import DeterministicEmbeddingEncoder
from app.domains.transcripts.fencing import can_commit_step
from app.domains.transcripts.retry import resolve_retry_scope
from app.platform.db.models import (
    GeneratedLectureSummary,
    IngestionJob,
    Transcript,
    TranscriptChunk,
)
from app.platform.query.transcript_status import get_transcript_processing_status_read
from tests.test_transcript_lifecycle import _make_summarized
from tests.test_transcript_worker import (
    _chunks,
    _create_chunked_transcript,
    _create_parsed_transcript,
    _create_worker_transcript,
    _segments,
    _session_factory,
)
from tests.test_transcripts import (  # noqa: F401 — fake_storage re-exported as a fixture
    VTT_BYTES,
    _create_membership,
    _create_module,
    _create_section,
    _create_transcript,
    _create_user,
    _headers,
    _transcript_file,
    fake_storage,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ───────────────────────── resolve_retry_scope (pure) ─────────────────────────


def _projection(**step_status: str) -> SimpleNamespace:
    steps = {
        key: SimpleNamespace(status=step_status.get(key, "not_started"))
        for key in ("parse", "chunk", "embed", "summary_brief", "summary_detailed")
    }
    return SimpleNamespace(steps=steps)


def test_scope_parse_failed_returns_only_parse() -> None:
    # parse owns the cascade — its success re-enqueues chunk + brief + detailed.
    scope = resolve_retry_scope(_projection(parse="failed", embed="failed", summary_brief="failed"))
    assert scope == ["parse"]


def test_scope_embed_failed_with_failed_summary_is_independent() -> None:
    scope = resolve_retry_scope(_projection(embed="failed", summary_detailed="failed"))
    assert scope == ["embed", "summary_detailed"]


def test_scope_only_summaries_failed() -> None:
    scope = resolve_retry_scope(_projection(summary_brief="failed", summary_detailed="failed"))
    assert scope == ["summary_brief", "summary_detailed"]


def test_scope_chunk_before_embed() -> None:
    scope = resolve_retry_scope(_projection(chunk="failed", embed="failed"))
    assert scope == ["chunk"]


def test_scope_nothing_failed_is_empty() -> None:
    assert resolve_retry_scope(_projection()) == []


# ───────────────────────── fencing ─────────────────────────


def test_can_commit_step_predicate() -> None:
    running = SimpleNamespace(status="running")
    active = SimpleNamespace(lifecycle_state="active")
    superseded = SimpleNamespace(lifecycle_state="superseded")
    assert can_commit_step(job=running, transcript=active) is True
    assert can_commit_step(job=running, transcript=superseded) is False
    assert can_commit_step(job=running, transcript=None) is False
    assert can_commit_step(job=SimpleNamespace(status="failed"), transcript=active) is False


@pytest.mark.anyio
async def test_superseded_transcript_chunk_worker_aborts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(db_session, texts=["hello world"])
    transcript_id = transcript.id
    factory = _session_factory(db_session)
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)

    async with factory() as session:
        async with session.begin():
            t = await session.get(Transcript, transcript_id)
            t.lifecycle_state = "superseded"
            t.superseded_at = _now()
            t.supersession_reason = "replaced_active"

    await chunk_service.chunk_transcript_async(chunk_job_id, session_factory=factory)
    db_session.expire_all()

    chunks = await _chunks(db_session, transcript_id)
    job = await db_session.get(IngestionJob, chunk_job_id)
    assert chunks == []  # fenced: no chunks written
    assert job.status == "queued"  # not advanced, not failed


@pytest.mark.anyio
async def test_superseded_transcript_embed_worker_aborts(
    db_session: AsyncSession,
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(db_session, texts=["a", "b"])
    transcript_id = transcript.id
    factory = _session_factory(db_session)

    async with factory() as session:
        async with session.begin():
            t = await session.get(Transcript, transcript_id)
            t.lifecycle_state = "superseded"
            t.superseded_at = _now()
            t.supersession_reason = "replaced_active"

    await embedding_service.embed_transcript_async(
        embed_job_id, encoder=DeterministicEmbeddingEncoder(), session_factory=factory, batch_size=1
    )
    db_session.expire_all()

    chunks = await _chunks(db_session, transcript_id)
    job = await db_session.get(IngestionJob, embed_job_id)
    assert all(c.embedding is None for c in chunks)  # fenced: no vectors written
    assert job.status != "completed"


# ───────────────────────── retry resets and re-runs without duplicates ─────────────────────────


def _force_fault(monkeypatch: pytest.MonkeyPatch, step: str) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION", step)


def _clear_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_FAULT_INJECTION_ENABLED", "false")
    monkeypatch.delenv("PIPELINE_FAULT_INJECTION", raising=False)


async def _reset_job(factory, job_id: UUID) -> None:
    async with factory() as session:
        async with session.begin():
            job = await session.get(IngestionJob, job_id)
            job.status = "queued"
            job.error_message = None
            job.failure_category = None
            job.completed_at = None


@pytest.mark.anyio
async def test_embed_failure_then_retry_completes_without_duplicate(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript, embed_job_id = await _create_chunked_transcript(db_session, texts=["a", "b"])
    transcript_id = transcript.id
    factory = _session_factory(db_session)

    _force_fault(monkeypatch, "embed")
    await embedding_service.embed_transcript_async(
        embed_job_id, encoder=DeterministicEmbeddingEncoder(), session_factory=factory, batch_size=1
    )
    db_session.expire_all()
    job = await db_session.get(IngestionJob, embed_job_id)
    assert job.status == "failed"
    assert job.failure_category == "embedding_failed"

    _clear_fault(monkeypatch)
    await _reset_job(factory, embed_job_id)
    await embedding_service.embed_transcript_async(
        embed_job_id, encoder=DeterministicEmbeddingEncoder(), session_factory=factory, batch_size=1
    )
    db_session.expire_all()

    job = await db_session.get(IngestionJob, embed_job_id)
    chunks = await _chunks(db_session, transcript_id)
    assert job.status == "completed"
    assert len(chunks) == 2  # no duplicate chunks
    assert all(c.embedding is not None for c in chunks)


@pytest.mark.anyio
async def test_chunk_failure_then_retry_completes_without_duplicate(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript, chunk_job_id = await _create_parsed_transcript(db_session, texts=["hello world"])
    transcript_id = transcript.id
    factory = _session_factory(db_session)
    monkeypatch.setattr(chunk_service, "enqueue_embed_transcript", lambda _job_id: None)

    _force_fault(monkeypatch, "chunk")
    await chunk_service.chunk_transcript_async(chunk_job_id, session_factory=factory)
    db_session.expire_all()
    job = await db_session.get(IngestionJob, chunk_job_id)
    assert job.status == "failed"
    assert job.failure_category == "chunk_failed"

    _clear_fault(monkeypatch)
    await _reset_job(factory, chunk_job_id)
    await chunk_service.chunk_transcript_async(chunk_job_id, session_factory=factory)
    db_session.expire_all()

    job = await db_session.get(IngestionJob, chunk_job_id)
    chunks = await _chunks(db_session, transcript_id)
    assert job.status == "completed"
    assert [c.chunk_index for c in chunks] == [0]  # exactly one chunk, no duplicate


# ───────────────────────── DAG decouple: parse forks summaries ─────────────────────────


@pytest.mark.anyio
async def test_parse_success_enqueues_chunk_brief_and_detailed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Summaries fork from PARSE (not embed), so the parse worker enqueues chunk + brief + detailed.
    monkeypatch.setenv("ENABLE_DETAILED_SUMMARY", "true")
    raw = (
        b"WEBVTT\n\n"
        b"00:00.000 --> 00:01.000\n<v Dr Smith>Hello</v>\n\n"
        b"00:01.000 --> 00:02.500\nExample: Preserve this label\n"
    )
    from tests.test_content import FakeStorageProvider

    storage = FakeStorageProvider()
    transcript = await _create_worker_transcript(db_session, raw=raw)
    storage.objects[transcript.storage_key] = raw
    transcript_id = transcript.id
    enqueued_chunk: list[UUID] = []
    enqueued_summaries: list[tuple[str, UUID]] = []
    monkeypatch.setattr(parse_service, "enqueue_chunk_transcript", lambda jid: enqueued_chunk.append(jid))
    monkeypatch.setattr(
        parse_service, "enqueue_summary_job", lambda jt, jid: enqueued_summaries.append((jt, jid))
    )
    await db_session.commit()

    await parse_service.parse_transcript_async(
        transcript_id, storage_provider=storage, session_factory=_session_factory(db_session)
    )
    db_session.expire_all()

    assert len(enqueued_chunk) == 1
    assert {jt for jt, _ in enqueued_summaries} == {
        "generate_brief_summary",
        "generate_detailed_summary",
    }
    summary_jobs = (
        await db_session.execute(
            select(IngestionJob).where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type.in_(
                    ("generate_brief_summary", "generate_detailed_summary")
                ),
            )
        )
    ).scalars().all()
    assert {j.job_type for j in summary_jobs} == {
        "generate_brief_summary",
        "generate_detailed_summary",
    }


@pytest.mark.anyio
async def test_embed_does_not_create_summary_jobs(
    db_session: AsyncSession,
) -> None:
    # Embed no longer creates summary jobs (they fork from parse) → an embed run leaves none.
    transcript, embed_job_id = await _create_chunked_transcript(db_session, texts=["a", "b"])
    transcript_id = transcript.id
    await embedding_service.embed_transcript_async(
        embed_job_id, encoder=DeterministicEmbeddingEncoder(), session_factory=_session_factory(db_session)
    )
    db_session.expire_all()

    summary_jobs = (
        await db_session.execute(
            select(IngestionJob).where(
                IngestionJob.transcript_id == transcript_id,
                IngestionJob.job_type.in_(
                    ("generate_brief_summary", "generate_detailed_summary")
                ),
            )
        )
    ).scalars().all()
    assert summary_jobs == []


# ───────────────────────── failure taxonomy projection ─────────────────────────


async def _completed_job(db_session, transcript_id, job_type) -> None:
    db_session.add(
        IngestionJob(
            transcript_id=transcript_id,
            job_type=job_type,
            status="completed",
            idempotency_key=f"{transcript_id}:{job_type}:{uuid4()}",
            completed_at=_now(),
        )
    )
    await db_session.flush()


async def _failed_job(db_session, transcript_id, job_type, failure_category) -> IngestionJob:
    job = IngestionJob(
        transcript_id=transcript_id,
        job_type=job_type,
        status="failed",
        idempotency_key=f"{transcript_id}:{job_type}:{uuid4()}",
        error_message="internal detail not exposed",
        failure_category=failure_category,
    )
    db_session.add(job)
    await db_session.flush()
    return job


@pytest.mark.anyio
@pytest.mark.parametrize(
    "job_type,internal,expected_category,expected_retryable",
    [
        ("parse", "storage_missing", "storage_missing", False),
        ("parse", "parse_failed", "parse_failed", True),
        ("chunk", "chunk_failed", "chunk_failed", True),
        ("embed", "embedding_failed", "embedding_failed", True),
        ("generate_detailed_summary", "invalid_output", "invalid_output", True),
        ("generate_detailed_summary", "provider_config_error", "provider_error", False),
        ("generate_brief_summary", "invalid_input", "summary_generation_failed", False),
    ],
)
async def test_projection_sanitized_failure_category(
    db_session: AsyncSession,
    job_type: str,
    internal: str,
    expected_category: str,
    expected_retryable: bool,
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    await _failed_job(db_session, transcript.id, job_type, internal)
    await db_session.commit()

    projection = await get_transcript_processing_status_read(db_session, transcript=transcript)
    assert projection.failure_category == expected_category
    assert projection.retryable is expected_retryable
    assert projection.overall_state == "failed"


# ── F-4.6d-3: overallState derives from STEP states, never the transcript.status breadcrumb ──


@pytest.mark.anyio
async def test_overall_state_ignores_stale_failed_breadcrumb_after_retry(
    db_session: AsyncSession,
) -> None:
    """The exact F-4.6d-3 case: apply_retry re-enqueues the failed step (embed → queued) but leaves
    `transcript.status='failed'`. The projection must report in-progress (the steps say retrying), NOT
    the stale 'failed' breadcrumb — else the lecturer badge settles on a transcript that is retrying.
    (Fails on the pre-fix code, which short-circuited overall_state on transcript.status == 'failed'.)"""
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "failed"  # the stale breadcrumb apply_retry leaves behind
    await _completed_job(db_session, transcript.id, "parse")
    await _completed_job(db_session, transcript.id, "chunk")
    await _completed_job(db_session, transcript.id, "generate_brief_summary")
    await _completed_job(db_session, transcript.id, "generate_detailed_summary")
    db_session.add(
        IngestionJob(
            transcript_id=transcript.id,
            job_type="embed",
            status="queued",  # re-enqueued by retry — NOT failed
            idempotency_key=f"{transcript.id}:embed:{uuid4()}",
        )
    )
    await db_session.flush()
    await db_session.commit()

    projection = await get_transcript_processing_status_read(db_session, transcript=transcript)
    assert projection.overall_state == "embedding"  # in-progress, not 'failed'
    assert projection.failed_step is None
    assert projection.failure_category is None
    assert projection.retryable is False
    assert projection.transcript_status == "failed"  # the demoted breadcrumb is exposed, not trusted


@pytest.mark.anyio
async def test_overall_state_failed_on_genuine_step_failure(db_session: AsyncSession) -> None:
    """The fix must NOT break the genuine-failure case: a step actually `failed` (no retry) → the
    projection is `failed` + retryable, derived purely from the step state."""
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    await _completed_job(db_session, transcript.id, "parse")
    await _completed_job(db_session, transcript.id, "chunk")
    await _failed_job(db_session, transcript.id, "embed", "embedding_failed")
    await db_session.commit()

    projection = await get_transcript_processing_status_read(db_session, transcript=transcript)
    assert projection.overall_state == "failed"
    assert projection.failed_step == "embed"
    assert projection.failure_category == "embedding_failed"
    assert projection.retryable is True


@pytest.mark.anyio
async def test_overall_state_summarized_when_all_leaves_complete(db_session: AsyncSession) -> None:
    """Happy path unchanged: every leaf complete → `summarized` (even if the breadcrumb lags)."""
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "embedding"  # breadcrumb lags the steps; doneness comes from the steps
    await _make_summarized(db_session, transcript)
    await db_session.commit()

    projection = await get_transcript_processing_status_read(db_session, transcript=transcript)
    assert projection.overall_state == "summarized"
    assert projection.failed_step is None


# ───────────────────────── retry endpoint (authz + 409s + happy path) ─────────────────────────


async def _section_with_active_transcript(db_session, *, lifecycle_state="active"):
    lecturer = await _create_user(db_session, email=f"retry-{uuid4()}@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        lifecycle_state=lifecycle_state,
        status="failed",
    )
    return lecturer, module, section, transcript


@pytest.mark.anyio
async def test_retry_endpoint_happy_path_resets_and_enqueues(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client, monkeypatch
) -> None:
    lecturer, module, section, transcript = await _section_with_active_transcript(db_session)
    await _completed_job(db_session, transcript.id, "parse")
    await _completed_job(db_session, transcript.id, "chunk")
    embed_job = await _failed_job(db_session, transcript.id, "embed", "embedding_failed")
    embed_job_id = embed_job.id
    module_id, section_id, transcript_id = module.id, section.id, transcript.id
    await db_session.commit()

    enqueued: list[UUID] = []
    monkeypatch.setattr(retry_module, "enqueue_embed_transcript", lambda jid: enqueued.append(jid))

    response = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript/{transcript_id}/retry",
        headers=_headers(lecturer, jwt_factory),
    )
    assert response.status_code == 200
    assert enqueued == [embed_job_id]

    db_session.expire_all()
    job = await db_session.get(IngestionJob, embed_job_id)
    assert job.status == "queued"
    assert job.failure_category is None


@pytest.mark.anyio
async def test_retry_endpoint_rejects_student_and_unassigned(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    lecturer, module, section, transcript = await _section_with_active_transcript(db_session)
    await _failed_job(db_session, transcript.id, "embed", "embedding_failed")
    student = await _create_user(db_session, email=f"stu-{uuid4()}@example.com", role="student")
    await _create_membership(db_session, user_id=student.id, module_id=module.id, role="student")
    other = await _create_user(db_session, email=f"other-{uuid4()}@example.com", role="lecturer")
    module_id, section_id, transcript_id = module.id, section.id, transcript.id
    await db_session.commit()

    path = f"/modules/{module_id}/sections/{section_id}/transcript/{transcript_id}/retry"
    student_resp = await auth_client.post(path, headers=_headers(student, jwt_factory))
    other_resp = await auth_client.post(path, headers=_headers(other, jwt_factory))
    assert student_resp.status_code == 403
    assert other_resp.status_code == 404


@pytest.mark.anyio
async def test_retry_endpoint_superseded_is_409(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    lecturer, module, section, transcript = await _section_with_active_transcript(
        db_session, lifecycle_state="superseded"
    )
    await _failed_job(db_session, transcript.id, "embed", "embedding_failed")
    module_id, section_id, transcript_id = module.id, section.id, transcript.id
    await db_session.commit()

    response = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript/{transcript_id}/retry",
        headers=_headers(lecturer, jwt_factory),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "TRANSCRIPT_SUPERSEDED"


@pytest.mark.anyio
async def test_retry_endpoint_nothing_failed_is_409(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    lecturer = await _create_user(db_session, email=f"nf-{uuid4()}@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section = await _create_section(db_session, module_id=module.id)
    transcript = await _create_transcript(
        db_session, section_id=section.id, uploaded_by_user_id=lecturer.id, status="completed"
    )
    await _completed_job(db_session, transcript.id, "parse")
    module_id, section_id, transcript_id = module.id, section.id, transcript.id
    await db_session.commit()

    response = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript/{transcript_id}/retry",
        headers=_headers(lecturer, jwt_factory),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "NO_RETRYABLE_FAILURE"


@pytest.mark.anyio
async def test_retry_endpoint_allows_pending_failed_replacement(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client, monkeypatch
) -> None:
    # A failed pending replacement is retryable (only superseded is rejected).
    lecturer = await _create_user(db_session, email=f"pend-{uuid4()}@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section = await _create_section(db_session, module_id=module.id)
    active = await _create_transcript(
        db_session, section_id=section.id, uploaded_by_user_id=lecturer.id, lifecycle_state="active"
    )
    pending = await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        lifecycle_state="pending",
        status="failed",
    )
    await _failed_job(db_session, pending.id, "parse", "parse_failed")
    module_id, section_id, pending_id = module.id, section.id, pending.id
    await db_session.commit()

    enqueued: list[UUID] = []
    monkeypatch.setattr(retry_module, "enqueue_parse_transcript", lambda tid: enqueued.append(tid))

    response = await auth_client.post(
        f"/modules/{module_id}/sections/{section_id}/transcript/{pending_id}/retry",
        headers=_headers(lecturer, jwt_factory),
    )
    assert response.status_code == 200
    assert enqueued == [pending_id]
    _ = active  # the active transcript is untouched by the pending's retry
