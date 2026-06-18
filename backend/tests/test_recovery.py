"""Stage 4.6c — stuck-row reaper + loss-safe storage reconciliation + MaintenanceRun (ADR-46-C/D).

Reaper liveness is injected (``rq_liveness`` stub) and time is injected (``now``) so tests are
deterministic without Redis. Reconciliation runs against the in-memory FakeStorageProvider.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.recovery import reaper as reaper_module
from app.domains.recovery.locks import maintenance_advisory_lock
from app.domains.recovery.reaper import run_stuck_row_reaper
from app.domains.recovery.reconciliation import run_storage_reconciliation
from app.domains.transcripts import parse_service
from app.platform.embeddings import DeterministicEmbeddingEncoder
from app.domains.transcripts.embedding_service import embed_transcript_async
from app.domains.transcripts.parse_service import ParseClaim
from app.domains.transcripts.parsers import ParsedSegment
from app.domains.transcripts.retry import apply_retry, resolve_retry_scope
from app.platform.db.models import (
    GeneratedLectureSummary,
    IngestionJob,
    MaintenanceRun,
    Transcript,
    TranscriptSegment,
)
from app.platform.query.transcript_status import get_transcript_processing_status_read
from tests.test_content import FakeStorageProvider
from tests.test_transcript_lifecycle import _create_summary_row
from tests.test_transcript_worker import (
    _chunks,
    _create_chunked_transcript,
    _create_worker_transcript,
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
    fake_storage,  # noqa: F401 — re-exported so pytest resolves it as a fixture here
)


def _now() -> datetime:
    return datetime.now(UTC)


def _future(hours: int = 2) -> datetime:
    return _now() + timedelta(hours=hours)


def _job(transcript_id, job_type, status, *, started_at=None) -> IngestionJob:
    return IngestionJob(
        transcript_id=transcript_id,
        job_type=job_type,
        status=status,
        idempotency_key=f"{transcript_id}:{job_type}:{uuid4()}",
        started_at=started_at,
    )


async def _maintenance_runs(db_session, run_type):
    return (
        await db_session.execute(
            select(MaintenanceRun).where(MaintenanceRun.run_type == run_type)
        )
    ).scalars().all()


_NOT_LIVE = lambda job_type, job_id: False  # noqa: E731
_LIVE = lambda job_type, job_id: True  # noqa: E731


# ───────────────────────── advisory lock ─────────────────────────


@pytest.mark.anyio
async def test_advisory_lock_is_singleton(db_session: AsyncSession) -> None:
    engine = db_session.bind
    async with maintenance_advisory_lock(engine, "stuck_row_reaper") as first:
        assert first is True
        async with maintenance_advisory_lock(engine, "stuck_row_reaper") as second:
            assert second is False  # a different connection cannot take the held lock
    # released — re-acquirable now
    async with maintenance_advisory_lock(engine, "stuck_row_reaper") as third:
        assert third is True


# ───────────────────────── reaper ─────────────────────────


@pytest.mark.anyio
async def test_reaper_reenqueues_never_enqueued_parse(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)  # status 'uploaded', no parse job
    transcript_id = transcript.id
    await db_session.commit()

    captured: list = []
    monkeypatch.setattr(reaper_module, "enqueue_parse_transcript", lambda tid: captured.append(tid))

    result = await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_NOT_LIVE,
        now=_future(),
    )
    assert captured == [transcript_id]
    assert result["recovered"] >= 1
    runs = await _maintenance_runs(db_session, "stuck_row_reaper")
    assert len(runs) == 1 and runs[0].status == "completed"
    assert runs[0].summary_json["recovered"] >= 1


@pytest.mark.anyio
async def test_reaper_reenqueues_stuck_queued_embed_not_in_rq(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "completed"  # keep scan-A (never-enqueued parse) from firing
    job = _job(transcript.id, "embed", "queued")
    db_session.add(job)
    await db_session.flush()
    job_id = job.id
    await db_session.commit()

    captured: list = []
    monkeypatch.setattr(reaper_module, "enqueue_embed_transcript", lambda jid: captured.append(jid))

    await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_NOT_LIVE,
        now=_future(),
    )
    assert captured == [job_id]


@pytest.mark.anyio
async def test_reaper_skips_queued_job_live_in_rq(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "completed"
    db_session.add(_job(transcript.id, "embed", "queued"))
    await db_session.commit()

    captured: list = []
    monkeypatch.setattr(reaper_module, "enqueue_embed_transcript", lambda jid: captured.append(jid))

    await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_LIVE,  # live in RQ → not stuck
        now=_future(),
    )
    assert captured == []


@pytest.mark.anyio
async def test_reaper_marks_crashed_running_job_fenced(db_session: AsyncSession) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "embedding"
    job = _job(transcript.id, "embed", "running", started_at=_now() - timedelta(hours=1))
    db_session.add(job)
    await db_session.flush()
    job_id, transcript_id = job.id, transcript.id
    await db_session.commit()

    result = await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_NOT_LIVE,
        now=_now(),  # started_at is 1h ago, embed threshold 30m → stale
    )
    assert result["crashed"] >= 1

    db_session.expire_all()
    reaped = await db_session.get(IngestionJob, job_id)
    assert reaped.status == "failed"
    assert reaped.failure_category == "crashed"
    transcript_after = await db_session.get(Transcript, transcript_id)
    assert transcript_after.status == "failed"


@pytest.mark.anyio
async def test_reaper_leaves_fresh_running_job(db_session: AsyncSession) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "embedding"
    job = _job(transcript.id, "embed", "running", started_at=_now())  # just started
    db_session.add(job)
    await db_session.flush()
    job_id = job.id
    await db_session.commit()

    await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_NOT_LIVE,
        now=_now(),
    )
    db_session.expire_all()
    assert (await db_session.get(IngestionJob, job_id)).status == "running"


@pytest.mark.anyio
async def test_reaper_fences_superseded_transcript(db_session: AsyncSession) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.lifecycle_state = "superseded"
    transcript.superseded_at = _now()
    transcript.supersession_reason = "replaced_active"
    job = _job(transcript.id, "embed", "running", started_at=_now() - timedelta(hours=1))
    db_session.add(job)
    await db_session.flush()
    job_id = job.id
    await db_session.commit()

    await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_NOT_LIVE,
        now=_now(),
    )
    db_session.expire_all()
    # Fenced: a superseded transcript's job is never marked crashed.
    assert (await db_session.get(IngestionJob, job_id)).status == "running"


@pytest.mark.anyio
async def test_reaper_report_only_does_not_act(db_session: AsyncSession) -> None:
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "embedding"
    job = _job(transcript.id, "embed", "running", started_at=_now() - timedelta(hours=1))
    db_session.add(job)
    await db_session.flush()
    job_id = job.id
    await db_session.commit()

    result = await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_NOT_LIVE,
        report_only=True,
        now=_now(),
    )
    assert result["crashed"] >= 1  # counted...
    db_session.expire_all()
    assert (await db_session.get(IngestionJob, job_id)).status == "running"  # ...but not acted on


# ───────── reaper → projection → retry seam (Task 4.6c-V1) ─────────


@pytest.mark.anyio
async def test_reaper_crashed_job_projects_retryable_then_retries(db_session: AsyncSession) -> None:
    """The full seam for a genuinely-crashed mid-pipeline job (reaper case b: running + stale + not
    live in RQ — NOT the re-enqueue case): reaper marks it failed+crashed → the status projection
    surfaces failureCategory=crashed AND retryable=true → resolve_retry_scope picks it at its DAG
    position → fenced re-run reaches overallState=summarized with no duplicate rows. Summaries are
    already completed (4.6b DAG: they fork from parse, independent of embed)."""
    transcript, embed_job_id = await _create_chunked_transcript(db_session, texts=["alpha", "beta"])
    transcript_id = transcript.id

    embed_job = await db_session.get(IngestionJob, embed_job_id)
    embed_job.status = "running"
    embed_job.started_at = _now() - timedelta(hours=1)  # stale (embed threshold is 30m)
    transcript.status = "embedding"

    now = _now()
    brief_job = IngestionJob(
        transcript_id=transcript_id,
        job_type="generate_brief_summary",
        status="completed",
        idempotency_key=f"{transcript_id}:brief:{uuid4()}",
        completed_at=now,
    )
    detailed_job = IngestionJob(
        transcript_id=transcript_id,
        job_type="generate_detailed_summary",
        status="completed",
        idempotency_key=f"{transcript_id}:detailed:{uuid4()}",
        completed_at=now,
    )
    db_session.add_all([brief_job, detailed_job])
    await db_session.flush()
    await _create_summary_row(
        db_session, transcript, summary_type="brief", feature="summary_brief", job=brief_job
    )
    await _create_summary_row(
        db_session, transcript, summary_type="detailed_study", feature="summary_detailed", job=detailed_job
    )
    await db_session.commit()

    # --- reaper marks the crashed embed job ---
    await run_stuck_row_reaper(
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        rq_liveness=_NOT_LIVE,
        now=_now(),
    )
    db_session.expire_all()

    # (1) Same terminal state a normal step-failure uses, only the category label differs.
    crashed = await db_session.get(IngestionJob, embed_job_id)
    assert crashed.status == "failed"
    assert crashed.failure_category == "crashed"

    # (2) Projection surfaces crashed AND retryable (crashed must be in the retryable set).
    transcript = await db_session.get(Transcript, transcript_id)
    projection = await get_transcript_processing_status_read(db_session, transcript=transcript)
    assert projection.failed_step == "embed"
    assert projection.failure_category == "crashed"
    assert projection.retryable is True

    # (3) Retry scope picks the crashed job at its DAG position (embed branch; summaries already done).
    scope = resolve_retry_scope(projection)
    assert scope == ["embed"]

    chunks_before = len(await _chunks(db_session, transcript_id))
    summaries_before = len(
        (
            await db_session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript_id
                )
            )
        ).scalars().all()
    )

    # --- retry: reset the failed step, then re-run the embed worker (fenced) ---
    to_enqueue = await apply_retry(db_session, transcript=transcript, scope=scope)
    await db_session.commit()
    assert ("embed", embed_job_id) in to_enqueue
    await embed_transcript_async(
        embed_job_id,
        encoder=DeterministicEmbeddingEncoder(),
        session_factory=_session_factory(db_session),
    )
    db_session.expire_all()

    # (4) Reaches summarized; no duplicate chunks/summaries on the reaper-crash → retry path.
    transcript = await db_session.get(Transcript, transcript_id)
    final = await get_transcript_processing_status_read(db_session, transcript=transcript)
    assert final.overall_state == "summarized"
    assert len(await _chunks(db_session, transcript_id)) == chunks_before
    summaries_after = len(
        (
            await db_session.execute(
                select(GeneratedLectureSummary).where(
                    GeneratedLectureSummary.transcript_id == transcript_id
                )
            )
        ).scalars().all()
    )
    assert summaries_after == summaries_before


@pytest.mark.anyio
async def test_stale_worker_aborts_after_reaper_then_retry(db_session: AsyncSession) -> None:
    """Browser-gate fencing flow (deterministic): seed a stale running parse job → the reaper marks it
    crashed → retry resets it and a NEW attempt claims it → the OLD stale worker tries to commit and
    ABORTS (attempt-token fence), writing nothing. (A backend race, proven here, not in the browser.)"""
    transcript = await _create_worker_transcript(db_session, raw=VTT_BYTES)
    transcript.status = "parsing"
    idempotency_key = parse_service._idempotency_key(transcript)
    parse_job = IngestionJob(
        transcript_id=transcript.id,
        job_type="parse",
        status="running",
        idempotency_key=idempotency_key,
        processor_version=parse_service.PARSE_PROCESSOR_VERSION,
        attempts=1,
        started_at=_now() - timedelta(hours=1),  # stale
    )
    db_session.add(parse_job)
    await db_session.flush()
    transcript_id, parse_job_id = transcript.id, parse_job.id
    # The OLD worker's claim (attempt 1) — captured before the reaper/retry bump the attempt.
    stale_claim = ParseClaim(
        transcript_id=transcript_id,
        storage_key=transcript.storage_key,
        mime_type=transcript.mime_type,
        idempotency_key=idempotency_key,
        claimed_attempt=1,
        job_id=parse_job_id,
    )
    await db_session.commit()

    factory = _session_factory(db_session)
    # Reaper marks the stale running parse job crashed.
    await run_stuck_row_reaper(
        session_factory=factory, engine=db_session.bind, rq_liveness=_NOT_LIVE, now=_now()
    )
    db_session.expire_all()
    assert (await db_session.get(IngestionJob, parse_job_id)).failure_category == "crashed"

    # Retry resets the parse job, then a NEW worker claims it (attempt → 2).
    transcript = await db_session.get(Transcript, transcript_id)
    projection = await get_transcript_processing_status_read(db_session, transcript=transcript)
    assert resolve_retry_scope(projection) == ["parse"]
    await apply_retry(db_session, transcript=transcript, scope=["parse"])
    await db_session.commit()
    async with factory() as session:
        new_claim = await parse_service._claim_parse_job(session, transcript_id=transcript_id)
    assert new_claim is not None and new_claim.claimed_attempt == 2

    # The OLD stale worker (attempt 1) tries to commit → fenced, writes nothing.
    async with factory() as session:
        result = await parse_service._persist_success(
            session,
            claim=stale_claim,
            segments=[ParsedSegment(text="stale", start_ms=0, end_ms=1000, speaker_name=None)],
        )
    assert result is None
    db_session.expire_all()
    segment_count = len(
        (
            await db_session.execute(
                select(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript_id)
            )
        ).scalars().all()
    )
    assert segment_count == 0  # the stale attempt wrote nothing


# ───────────────────────── storage reconciliation ─────────────────────────


async def _transcript_with_key(db_session, storage_key, *, lifecycle_state="active"):
    lecturer = await _create_user(db_session, email=f"rec-{uuid4()}@example.com", role="lecturer")
    module = await _create_module(db_session, owner_id=lecturer.id)
    await _create_membership(db_session, user_id=lecturer.id, module_id=module.id, role="lecturer")
    section = await _create_section(db_session, module_id=module.id)
    return await _create_transcript(
        db_session,
        section_id=section.id,
        uploaded_by_user_id=lecturer.id,
        lifecycle_state=lifecycle_state,
        storage_key=storage_key,
    )


def _put(storage: FakeStorageProvider, key: str, *, created_at: datetime) -> None:
    storage.objects[key] = b"data"
    storage.object_created_at[key] = created_at


@pytest.mark.anyio
async def test_reconciliation_reports_orphans_and_missing_report_only(
    db_session: AsyncSession,
) -> None:
    referenced = "modules/m/sections/s/transcripts/t1/a.vtt"
    orphan_old = "modules/m/sections/s/transcripts/t2/b.vtt"
    orphan_fresh = "modules/m/sections/s/transcripts/t3/c.vtt"
    missing = "modules/m/sections/s/transcripts/t4/d.vtt"
    asset = "modules/m/sections/s/assets/a1/x.pdf"  # must be ignored

    await _transcript_with_key(db_session, referenced)
    await _transcript_with_key(db_session, missing)  # DB ref, no object → missing
    await db_session.commit()

    storage = FakeStorageProvider()
    _put(storage, referenced, created_at=_now() - timedelta(days=2))  # referenced → not orphan
    _put(storage, orphan_old, created_at=_now() - timedelta(days=2))  # orphan
    _put(storage, orphan_fresh, created_at=_now())  # within grace → not orphan
    _put(storage, asset, created_at=_now() - timedelta(days=2))  # asset → out of scope

    result = await run_storage_reconciliation(
        storage,
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        mode="report_only",
    )
    assert result["orphans_found"] == 1  # only orphan_old
    assert result["missing_refs"] == 1  # only `missing`
    assert missing in result["missing_ref_keys"]
    assert result["deleted"] == 0  # report-only never deletes
    assert storage.delete_calls == []

    runs = await _maintenance_runs(db_session, "storage_reconciliation")
    assert len(runs) == 1 and runs[0].status == "completed"


@pytest.mark.anyio
async def test_reconciliation_cleanup_deletes_orphans_when_enabled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RECONCILIATION_CLEANUP_ENABLED", "true")
    orphan = "modules/m/sections/s/transcripts/t9/b.vtt"
    await db_session.commit()

    storage = FakeStorageProvider()
    _put(storage, orphan, created_at=_now() - timedelta(days=2))

    result = await run_storage_reconciliation(
        storage,
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        mode="cleanup",
    )
    assert result["orphans_found"] == 1
    assert result["deleted"] == 1
    assert storage.delete_calls == [orphan]


@pytest.mark.anyio
async def test_reconciliation_cleanup_disabled_by_default(db_session: AsyncSession) -> None:
    orphan = "modules/m/sections/s/transcripts/t9/b.vtt"
    await db_session.commit()
    storage = FakeStorageProvider()
    _put(storage, orphan, created_at=_now() - timedelta(days=2))

    result = await run_storage_reconciliation(
        storage,
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        mode="cleanup",  # requested, but RECONCILIATION_CLEANUP_ENABLED is off by default
    )
    assert result["orphans_found"] == 1
    assert result["deleted"] == 0
    assert storage.delete_calls == []


@pytest.mark.anyio
async def test_reconciliation_keeps_superseded_transcript_object(db_session: AsyncSession) -> None:
    key = "modules/m/sections/s/transcripts/sup/old.vtt"
    await _transcript_with_key(db_session, key, lifecycle_state="superseded")
    await db_session.commit()
    storage = FakeStorageProvider()
    _put(storage, key, created_at=_now() - timedelta(days=2))

    result = await run_storage_reconciliation(
        storage,
        session_factory=_session_factory(db_session),
        engine=db_session.bind,
        mode="report_only",
    )
    # Superseded transcripts are RETAINED → their storage_key is referenced, never an orphan.
    assert result["orphans_found"] == 0
    assert result["missing_refs"] == 0


# ───────────────────────── admin endpoints ─────────────────────────


@pytest.mark.anyio
async def test_admin_can_trigger_reaper(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    admin = await _create_user(db_session, email=f"admin-{uuid4()}@example.com", role="admin")
    await db_session.commit()
    response = await auth_client.post(
        "/admin/maintenance/reap-stuck-rows", headers=_headers(admin, jwt_factory)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["runType"] == "stuck_row_reaper"


@pytest.mark.anyio
async def test_non_admin_cannot_trigger_maintenance(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client
) -> None:
    lecturer = await _create_user(db_session, email=f"lec-{uuid4()}@example.com", role="lecturer")
    await db_session.commit()
    response = await auth_client.post(
        "/admin/maintenance/reap-stuck-rows", headers=_headers(lecturer, jwt_factory)
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_admin_can_trigger_reconciliation(
    auth_client, db_session: AsyncSession, jwt_factory, mock_jwks_client, fake_storage  # noqa: F811
) -> None:
    admin = await _create_user(db_session, email=f"admin2-{uuid4()}@example.com", role="admin")
    await db_session.commit()
    response = await auth_client.post(
        "/admin/maintenance/reconcile-storage", headers=_headers(admin, jwt_factory)
    )
    assert response.status_code == 200
    assert response.json()["runType"] == "storage_reconciliation"
