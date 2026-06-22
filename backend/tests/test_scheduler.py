from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.analytics import service as analytics_service
from app.domains.analytics.service import _prune_old_snapshots, get_or_create_agent_run, run_agent_run
from app.domains.progress.seed import seed_progress_dataset
from app.platform.db.models import AgentRun, AppUser, StudentRiskSnapshot
from app.platform.scheduler import service as scheduler_service
from app.workers import queues

pytestmark = pytest.mark.anyio


async def test_agent_run_is_idempotent_and_persists_module_snapshots(db_session: AsyncSession):
    summary = await seed_progress_dataset(db_session, prefix="stage11-run", reset=True, cohort_size=6)
    scheduled_for = datetime.now(UTC) + timedelta(seconds=1)

    first, created = await get_or_create_agent_run(
        db_session,
        trigger_type="manual_admin",
        scope_type="module",
        scope_id=summary.module_two_id,
        scheduled_for=scheduled_for,
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    second, second_created = await get_or_create_agent_run(
        db_session,
        trigger_type="manual_admin",
        scope_type="module",
        scope_id=summary.module_two_id,
        scheduled_for=scheduled_for,
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    await db_session.commit()

    assert created is True
    assert second_created is False
    assert first.id == second.id

    result = await run_agent_run(db_session, run_id=first.id)
    assert result.status == "completed"
    assert result.snapshot_count == 6

    snapshots = (
        await db_session.scalars(
            select(StudentRiskSnapshot).where(StudentRiskSnapshot.agent_run_id == first.id)
        )
    ).all()
    assert len(snapshots) == 6
    assert {snapshot.algorithm_version for snapshot in snapshots} == {"risk-v1"}
    assert any(snapshot.risk_tier == "needs_support" for snapshot in snapshots)
    for snapshot in snapshots:
        for reason in snapshot.risk_reasons:
            assert set(reason["metricKeys"]) == set(reason["supportingMetrics"])


async def test_scheduler_tick_singleton_creates_and_enqueues_one_run(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    enqueued: list[str] = []

    def fake_enqueue_if_needed(run_id):
        if str(run_id) in enqueued:
            return f"agent-run-{run_id}", False
        enqueued.append(str(run_id))
        return f"agent-run-{run_id}", True

    monkeypatch.setattr(scheduler_service, "enqueue_run_agent_if_needed", fake_enqueue_if_needed)
    session_factory = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    now = datetime(2026, 6, 20, 8, tzinfo=UTC)

    created = await scheduler_service.scheduler_tick(
        session_factory=session_factory,
        engine=db_session.bind,
        now=now,
    )
    created_again = await scheduler_service.scheduler_tick(
        session_factory=session_factory,
        engine=db_session.bind,
        now=now,
    )

    assert created is True
    assert created_again is False
    assert len(enqueued) == 1
    assert await db_session.scalar(select(func.count()).select_from(AgentRun)) == 1


async def test_scheduler_reenqueues_same_run_after_enqueue_failure(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    attempts: list[str] = []

    def flaky_enqueue(run_id):
        attempts.append(str(run_id))
        if len(attempts) == 1:
            raise RuntimeError("redis unavailable")
        return f"agent-run-{run_id}", True

    monkeypatch.setattr(scheduler_service, "enqueue_run_agent_if_needed", flaky_enqueue)
    session_factory = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    now = datetime(2026, 6, 20, 8, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="redis unavailable"):
        await scheduler_service.scheduler_tick(
            session_factory=session_factory,
            engine=db_session.bind,
            now=now,
        )

    run = await db_session.scalar(select(AgentRun))
    assert run is not None
    assert run.status == "queued"

    created_again = await scheduler_service.scheduler_tick(
        session_factory=session_factory,
        engine=db_session.bind,
        now=now,
    )

    assert created_again is False
    assert attempts == [str(run.id), str(run.id)]

    compute_calls = 0

    async def fake_compute(_db, **_kwargs):
        nonlocal compute_calls
        compute_calls += 1
        return []

    monkeypatch.setattr(analytics_service, "compute_risk_for_scope", fake_compute)

    result = await run_agent_run(db_session, run_id=run.id)
    second_result = await run_agent_run(db_session, run_id=run.id)

    assert result.status == "completed"
    assert second_result.status == "completed"
    assert compute_calls == 1


async def test_scheduler_reenqueues_existing_failed_run(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    enqueued: list[str] = []
    monkeypatch.setattr(
        scheduler_service,
        "enqueue_run_agent_if_needed",
        lambda run_id: (enqueued.append(str(run_id)) or f"agent-run-{run_id}", True),
    )
    now = datetime(2026, 6, 20, 8, tzinfo=UTC)
    scheduled_for = scheduler_service.daily_scheduled_for(now)
    run, created = await get_or_create_agent_run(
        db_session,
        trigger_type="scheduled_daily",
        scope_type="all",
        scope_id=None,
        scheduled_for=scheduled_for,
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    run.status = "failed"
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    created_again = await scheduler_service.scheduler_tick(
        session_factory=session_factory,
        engine=db_session.bind,
        now=now,
    )

    assert created is True
    assert created_again is False
    assert enqueued == [str(run.id)]


async def test_scheduler_tick_skips_when_advisory_lock_is_held(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def fake_lock(_engine):
        yield False

    monkeypatch.setattr(scheduler_service, "scheduler_advisory_lock", fake_lock)

    created = await scheduler_service.scheduler_tick(
        session_factory=None,  # not used when the lock is unavailable
        engine=object(),
        now=datetime(2026, 6, 20, 8, tzinfo=UTC),
    )

    assert created is False


async def test_failed_agent_run_is_recorded(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    run, _created = await get_or_create_agent_run(
        db_session,
        trigger_type="manual_admin",
        scope_type="all",
        scope_id=None,
        scheduled_for=datetime(2026, 6, 20, 6, tzinfo=UTC),
        triggered_by_user_id=None,
        algorithm_version="risk-v1",
    )
    await db_session.commit()

    async def fail_compute(_db, **_kwargs):
        raise RuntimeError("deterministic failure")

    monkeypatch.setattr(analytics_service, "compute_risk_for_scope", fail_compute)

    with pytest.raises(RuntimeError):
        await run_agent_run(db_session, run_id=run.id)

    failed = await db_session.get(AgentRun, run.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.completed_at is not None
    assert failed.failure_message_sanitized == "deterministic failure"


def test_agent_run_enqueue_uses_ingestion_queue_and_stable_job_id(monkeypatch: pytest.MonkeyPatch):
    captured: list[tuple[object, str, str | None]] = []

    class FakeQueue:
        def enqueue(self, func, run_id: str, *, job_id: str | None = None):
            captured.append((func, run_id, job_id))

    monkeypatch.setattr(queues, "get_ingestion_queue", lambda: FakeQueue())
    monkeypatch.setattr(queues, "get_ai_queue", lambda: pytest.fail("AgentRun must not use the AI queue"))

    run_id = uuid4()
    job_id = queues.enqueue_run_agent(run_id)

    assert job_id == f"agent-run-{run_id}"
    assert len(captured) == 1
    func, arg, queued_job_id = captured[0]
    assert func.__name__ == "run_agent"
    assert arg == str(run_id)
    assert queued_job_id == job_id


def test_agent_run_enqueue_if_needed_skips_live_rq_job(monkeypatch: pytest.MonkeyPatch):
    captured: list[tuple[object, str, str | None]] = []

    class FakeQueue:
        connection = object()

        def enqueue(self, func, run_id: str, *, job_id: str | None = None):
            captured.append((func, run_id, job_id))

    class FakeJob:
        def get_status(self, *, refresh: bool = True):
            return "queued"

        def delete(self):
            pytest.fail("live queued AgentRun job must not be deleted")

    monkeypatch.setattr(queues, "get_ingestion_queue", lambda: FakeQueue())
    monkeypatch.setattr(queues, "get_ai_queue", lambda: pytest.fail("AgentRun must not use the AI queue"))
    monkeypatch.setattr(queues, "_fetch_rq_job", lambda job_id, connection: FakeJob())

    run_id = uuid4()
    job_id, enqueued = queues.enqueue_run_agent_if_needed(run_id)

    assert job_id == f"agent-run-{run_id}"
    assert enqueued is False
    assert captured == []


def test_agent_run_enqueue_if_needed_replaces_stale_rq_job(monkeypatch: pytest.MonkeyPatch):
    captured: list[tuple[object, str, str | None]] = []
    deleted: list[bool] = []

    class FakeQueue:
        connection = object()

        def enqueue(self, func, run_id: str, *, job_id: str | None = None):
            captured.append((func, run_id, job_id))

    class FakeJob:
        def get_status(self, *, refresh: bool = True):
            return "failed"

        def delete(self):
            deleted.append(True)

    monkeypatch.setattr(queues, "get_ingestion_queue", lambda: FakeQueue())
    monkeypatch.setattr(queues, "get_ai_queue", lambda: pytest.fail("AgentRun must not use the AI queue"))
    monkeypatch.setattr(queues, "_fetch_rq_job", lambda job_id, connection: FakeJob())

    run_id = uuid4()
    job_id, enqueued = queues.enqueue_run_agent_if_needed(run_id)

    assert job_id == f"agent-run-{run_id}"
    assert enqueued is True
    assert deleted == [True]
    assert len(captured) == 1
    func, arg, queued_job_id = captured[0]
    assert func.__name__ == "run_agent"
    assert arg == str(run_id)
    assert queued_job_id == job_id


async def test_snapshot_retention_keeps_latest_snapshot_per_student_module(db_session: AsyncSession):
    summary = await seed_progress_dataset(db_session, prefix="stage11-retention", reset=True, cohort_size=6)
    student_a = await db_session.scalar(
        select(AppUser).where(AppUser.email == summary.student_emails_by_key["a"])
    )
    student_b = await db_session.scalar(
        select(AppUser).where(AppUser.email == summary.student_emails_by_key["b"])
    )
    assert student_a is not None
    assert student_b is not None
    now = datetime.now(UTC)
    old = now - timedelta(days=220)
    old_latest = now - timedelta(days=200)
    recent = now - timedelta(days=2)

    runs = []
    for index, scheduled_for in enumerate([old, old_latest, old, recent], start=1):
        run = AgentRun(
            trigger_type="manual_admin",
            scope_type="module",
            scope_id=summary.module_two_id,
            scheduled_for=scheduled_for,
            triggered_by_user_id=None,
            algorithm_version="risk-v1",
            idempotency_key=f"stage11-retention-{index}",
        )
        db_session.add(run)
        runs.append(run)
    await db_session.flush()

    db_session.add_all(
        [
            StudentRiskSnapshot(
                agent_run_id=runs[0].id,
                student_id=student_a.id,
                module_id=summary.module_two_id,
                risk_tier="watch",
                risk_reasons=[],
                algorithm_version="risk-v1",
                input_hash="old-a",
                source_cutoff_at=old,
                computed_at=old,
            ),
            StudentRiskSnapshot(
                agent_run_id=runs[1].id,
                student_id=student_a.id,
                module_id=summary.module_two_id,
                risk_tier="needs_support",
                risk_reasons=[],
                algorithm_version="risk-v1",
                input_hash="old-latest-a",
                source_cutoff_at=old_latest,
                computed_at=old_latest,
            ),
            StudentRiskSnapshot(
                agent_run_id=runs[2].id,
                student_id=student_b.id,
                module_id=summary.module_two_id,
                risk_tier="watch",
                risk_reasons=[],
                algorithm_version="risk-v1",
                input_hash="old-b",
                source_cutoff_at=old,
                computed_at=old,
            ),
            StudentRiskSnapshot(
                agent_run_id=runs[3].id,
                student_id=student_b.id,
                module_id=summary.module_two_id,
                risk_tier="on_track",
                risk_reasons=[],
                algorithm_version="risk-v1",
                input_hash="recent-b",
                source_cutoff_at=recent,
                computed_at=recent,
            ),
        ]
    )
    await db_session.flush()

    await _prune_old_snapshots(db_session)

    remaining_hashes = set(await db_session.scalars(select(StudentRiskSnapshot.input_hash)))
    assert "old-a" not in remaining_hashes
    assert "old-b" not in remaining_hashes
    assert "old-latest-a" in remaining_hashes
    assert "recent-b" in remaining_hashes
