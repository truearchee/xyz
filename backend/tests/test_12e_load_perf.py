"""Stage 12e — load & performance check (measure-and-verify; TEST-ONLY harness, no product code).

Two concerns, two methods (master spec §5 12e):

(A) **Limiter / queueing under an exam-week peak** — fire N concurrent section-pool generations through the
    **real ``RedisRateLimiter``** with the **deterministic provider EXPLICITLY injected** so the limiter is
    NOT bypassed (``gateway.py`` bypasses it only for a *non-injected* deterministic provider, lines 325-329)
    and a per-call latency injected in the ``asyncio.to_thread`` send (``gateway.py:203``). Concurrency is the
    binding dimension (rpm/tpm set ample) so the queue drains as leases release — proving the pass envelope:
    **no error, no deadlock, no lost request; concurrency never exceeds the budget; queued calls back off and
    then complete.** No real-provider spend (rule 11 does not require a real call to test queueing).

(B1) **D1 pre-warm invariant** — the real ``prewarm_scope_pools`` makes a section's pool ``ready``; a student
    start then serves from that warm pool with **no new generation enqueued** (no ~264s cold wait), whereas a
    cold (never-pre-warmed) section's first start is the one that enqueues the generation job. The small
    *real-provider* confirmation (B2) is **owner-run** (no real ``LLM_API_KEY`` in a fresh workspace) — see
    ``knowledge/steps/stage-12/12e-real-provider-smoke.md``.

Also pins the live limiter budgets to the rule-15 documented values (confirm-don't-assume).

Backoff is tuned fast here (small delays, generous cap) so the harness runs in well under a second: the
assertion is *graceful drain + concurrency cap*, not production backoff timing. Run against the compose
``redis`` + ``db`` services (``docker compose run --rm --no-deps -v "$PWD/backend:/app" backend pytest
tests/test_12e_load_perf.py``).
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.domains.quiz.assembly_service as assembly_service
import app.domains.quiz.pool_service as pool_service
from app.domains.quiz.assembly_service import start_pooled_attempt, try_assemble_attempt_async
from app.domains.quiz.pool_service import (
    ensure_section_pool,
    generate_section_pool_async,
    _pool_model,
    _pool_prompt_version,
)
from app.domains.quiz.scope_service import prewarm_scope_pools
from app.platform.config import settings
from app.platform.db.models import (
    AIRequestLog,
    AppUser,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    ModuleSection,
    QuizAttempt,
    QuizDefinition,
    SectionQuestionPool,
    Transcript,
)
from app.platform.llm.gateway import LLMGateway
from app.platform.llm.limiter import (
    BackoffPolicy,
    RedisRateLimiter,
    effective_limit,
    limits_for,
)
from app.platform.llm.provider import DeterministicTestProvider

pytestmark = pytest.mark.anyio

# Fast, generous backoff so queued calls retry quickly and none spuriously exhaust to terminal
# rate_limited during the short test window (production defaults are 500ms base / 4 backoffs).
_FAST_BACKOFF = BackoffPolicy(
    max_backoffs=500, base_delay_ms=20, max_delay_ms=100, max_elapsed_ms=60_000
)
# Per-call lease hold. Long enough that the hold dominates scheduler/DB-claim jitter, so the budget is
# reliably saturated (peak hits the cap) and queued calls reliably back off — not timing-sensitive.
_LEASE_HOLD_S = 0.15


# ── harness ────────────────────────────────────────────────────────────────────────────────────────
class _FakeLease:
    async def release(self) -> None:
        return None


class _FakeLimiter:
    """For paths where the limiter is not under test (B1)."""

    async def acquire(self, *, backend, estimated_tokens, priority):
        return _FakeLease()


class _PeakTracker:
    """Thread-safe max-in-flight counter — the send runs in a worker thread (``asyncio.to_thread``)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.current = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self.current += 1
            self.peak = max(self.peak, self.current)

    def exit(self) -> None:
        with self._lock:
            self.current -= 1


def _latency_provider(tracker: _PeakTracker, latency_s: float) -> DeterministicTestProvider:
    """Deterministic provider whose (sync) ``send`` sleeps ``latency_s`` to hold the limiter lease. The
    gateway calls ``send`` via ``asyncio.to_thread`` so the sleep runs off the event loop → real
    concurrency. Injecting the provider keeps the real limiter in the path."""
    provider = DeterministicTestProvider()
    original_send = provider.send

    def send(*, rendered, backend):
        tracker.enter()
        try:
            time.sleep(latency_s)
            return original_send(rendered=rendered, backend=backend)
        finally:
            tracker.exit()

    provider.send = send  # instance attribute shadows the bound method
    return provider


def _factory(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def _b1_gateway(factory) -> LLMGateway:
    return LLMGateway(
        provider=DeterministicTestProvider(), limiter=_FakeLimiter(), session_factory=factory
    )


@pytest.fixture
def captured(monkeypatch) -> SimpleNamespace:
    """Capture RQ enqueues so the harness drives the pool/assembly jobs manually (no real worker)."""
    pools: list = []
    assemblies: list = []
    monkeypatch.setattr(
        pool_service, "enqueue_generate_section_pool", lambda pid: pools.append(pid) or f"pool-{pid}"
    )
    monkeypatch.setattr(
        pool_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"asm-{aid}"
    )
    monkeypatch.setattr(
        assembly_service, "enqueue_try_assemble_attempt", lambda aid: assemblies.append(aid) or f"asm-{aid}"
    )
    return SimpleNamespace(pools=pools, assemblies=assemblies)


@pytest.fixture
async def redis_client():
    # 12e is an ACCEPTANCE proof that the real RedisRateLimiter caps concurrency — so a missing Redis must
    # FAIL (not skip): a silent skip would be green-without-proof. The compose `redis` service must be up.
    client = aioredis.from_url(settings.REDIS_URL)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        pytest.fail(
            f"12e limiter acceptance tests REQUIRE Redis at {settings.REDIS_URL} (the whole point is to "
            f"prove the real limiter queues concurrency — a skip would pass without running the proof). "
            f"Bring up the compose `redis` service. ({type(exc).__name__}: {exc})"
        )
    yield client
    await client.aclose()


async def _seed_base(db_session: AsyncSession) -> SimpleNamespace:
    student = AppUser(
        auth_provider_id=f"auth-{uuid4()}", email=f"s-{uuid4()}@e.com",
        full_name="S", role="student", timezone="UTC",
    )
    owner = AppUser(
        auth_provider_id=f"auth-{uuid4()}", email=f"o-{uuid4()}@e.com",
        full_name="O", role="lecturer", timezone="UTC",
    )
    db_session.add_all([student, owner])
    await db_session.flush()
    module = CourseModule(title="M", owner_id=owner.id, timezone="UTC", is_active=True)
    db_session.add(module)
    await db_session.flush()
    db_session.add(
        CourseMembership(user_id=student.id, module_id=module.id, role="student", status="active")
    )
    await db_session.flush()
    return SimpleNamespace(student=student, owner=owner, module=module)


async def _seed_section(db_session, base, *, title: str, order: int) -> SimpleNamespace:
    """A published/active lecture section with a completed transcript + a ready detailed summary — the
    'quiz-bearing' shape ``resolve_quiz_source_summary`` requires before a pool can generate."""
    section = ModuleSection(
        course_module_id=base.module.id, title=title, type="lecture",
        order_index=order, publish_status="published", status="active",
    )
    db_session.add(section)
    await db_session.flush()
    checksum = hashlib.sha256(f"t-{uuid4()}".encode()).hexdigest()
    transcript = Transcript(
        module_section_id=section.id, source_type="manual_upload", original_file_name="t.vtt",
        storage_key=f"m/x/t/{uuid4()}/t.vtt", mime_type="text/vtt", file_size=10,
        checksum=checksum, status="completed", uploaded_by_user_id=base.owner.id,
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
    summary = GeneratedLectureSummary(
        transcript_id=transcript.id, module_section_id=section.id, summary_type="detailed_study",
        content_json={
            "overview": "An overview.", "keyConcepts": ["c1"],
            "importantDefinitions": [{"term": "T", "definition": "D"}],
            "mainExplanations": ["x"], "examples": ["e"], "examRelevantPoints": ["p"],
        },
        content_schema_version="detailed-v1", model_id="MBZUAI-IFM/K2-Think-v2", prompt_version="v1",
        prompt_content_hash="h", backend_used="nvidia", source_transcript_checksum=checksum,
        input_hash="ih", ai_request_log_id=log.id,
    )
    db_session.add(summary)
    await db_session.flush()
    await db_session.commit()
    return SimpleNamespace(section=section, summary=summary, transcript=transcript)


async def _make_pooled_definition(factory, base, sections: list, *, mode: str = "recap") -> QuizDefinition:
    async with factory() as session:
        async with session.begin():
            definition = QuizDefinition(
                module_section_id=sections[0].section.id,
                module_id=base.module.id,
                quiz_mode=mode,
                source_scope={"sectionIds": [str(s.section.id) for s in sections], "quizMode": mode},
            )
            session.add(definition)
        return await session.get(QuizDefinition, definition.id)


# ── confirm-don't-assume: live budgets == rule-15 documented values ─────────────────────────────────
async def test_12e_limiter_budgets_match_rule15():
    cere = limits_for("cerebras")
    nvidia = limits_for("nvidia")
    assert (cere.rpm, cere.tpm, cere.concurrency) == (20, 100_000, 10)
    assert (nvidia.rpm, nvidia.tpm, nvidia.concurrency) == (10, 105_000, 10)
    assert settings.LLM_INTERACTIVE_HEADROOM_PERCENT == 20
    # Interactive keeps reserved headroom over background (rule 15).
    assert effective_limit(10, "interactive", 20) == 10
    assert effective_limit(10, "background", 20) == 8


# ── (A) limiter queues an exam-week peak gracefully ─────────────────────────────────────────────────
async def test_12e_limiter_queues_exam_week_peak(db_session, captured, redis_client, monkeypatch):
    # Concurrency is the binding dimension; rpm/tpm ample so the queue drains as leases release (not on
    # the 60s rpm/tpm window). Pool generation routes to nvidia.
    monkeypatch.setenv("LLM_NVIDIA_CONCURRENCY", "4")
    monkeypatch.setenv("LLM_NVIDIA_RPM", "10000")
    monkeypatch.setenv("LLM_NVIDIA_TPM", "100000000")
    budget = 4
    n = 16

    base = await _seed_base(db_session)
    sections = [await _seed_section(db_session, base, title=f"L{i}", order=i) for i in range(n)]
    factory = _factory(db_session)
    ensured = [await ensure_section_pool(factory, section_id=s.section.id) for s in sections]
    assert all(e.status == "generating" for e in ensured)
    pool_ids = [e.pool_id for e in ensured]

    tracker = _PeakTracker()
    gateway = LLMGateway(
        provider=_latency_provider(tracker, latency_s=_LEASE_HOLD_S),
        limiter=RedisRateLimiter(redis_client, key_prefix=f"12e-peak:{uuid4().hex}", headroom_percent=0),
        backoff=_FAST_BACKOFF,
        session_factory=factory,
    )

    # The whole peak drains with no exception (gather would propagate one), no deadlock (it returns).
    await asyncio.gather(
        *(generate_section_pool_async(pid, gateway=gateway, session_factory=factory) for pid in pool_ids)
    )

    async with factory() as session:
        statuses = (
            await session.execute(
                select(SectionQuestionPool.status).where(SectionQuestionPool.id.in_(pool_ids))
            )
        ).scalars().all()
        backoffs = (
            await session.execute(
                select(func.coalesce(func.sum(AIRequestLog.rate_limit_backoff_count), 0)).where(
                    AIRequestLog.feature == "quiz_pool"
                )
            )
        ).scalar_one()

    # No lost request: every pool drained to ready; none failed (no terminal rate_limited / error).
    assert statuses.count("ready") == n
    assert statuses.count("failed") == 0
    # The limiter capped concurrency at the background budget (the invariant under test).
    eff = effective_limit(budget, "background", 0)  # == budget (0 headroom): the cap to assert against
    assert tracker.peak <= eff
    assert tracker.peak >= 2  # contention actually engaged (N=16 >> budget=4)
    # Queueing is observable: at least one call backed off under the limiter before completing.
    assert backoffs >= 1


# ── (A) the student wait-state holds under contention (ties to Step 0) ───────────────────────────────
async def test_12e_contended_attempt_stays_generating_then_resolves(
    db_session, captured, redis_client, monkeypatch
):
    monkeypatch.setenv("LLM_NVIDIA_CONCURRENCY", "1")  # serialize behind a single slot (peak contention)
    monkeypatch.setenv("LLM_NVIDIA_RPM", "10000")
    monkeypatch.setenv("LLM_NVIDIA_TPM", "100000000")

    base = await _seed_base(db_session)
    s1 = await _seed_section(db_session, base, title="S1", order=0)
    s2 = await _seed_section(db_session, base, title="S2", order=1)
    factory = _factory(db_session)
    definition = await _make_pooled_definition(factory, base, [s1, s2], mode="recap")

    start = await start_pooled_attempt(
        factory, student_id=base.student.id, quiz_definition_id=definition.id
    )
    # What the poller / QuizAttemptPanel ("Generating your quiz.") shows while pools are contended.
    assert start.status == "generating"

    e1 = await ensure_section_pool(factory, section_id=s1.section.id)
    e2 = await ensure_section_pool(factory, section_id=s2.section.id)
    tracker = _PeakTracker()
    gateway = LLMGateway(
        provider=_latency_provider(tracker, latency_s=_LEASE_HOLD_S),
        limiter=RedisRateLimiter(redis_client, key_prefix=f"12e-wait:{uuid4().hex}", headroom_percent=0),
        backoff=_FAST_BACKOFF,
        session_factory=factory,
    )
    await asyncio.gather(
        generate_section_pool_async(e1.pool_id, gateway=gateway, session_factory=factory),
        generate_section_pool_async(e2.pool_id, gateway=gateway, session_factory=factory),
    )
    assert tracker.peak <= effective_limit(1, "background", 0)  # == 1: serialized behind the budget

    async with factory() as session:
        mid = await session.get(QuizAttempt, start.attempt_id)
    assert mid.status == "generating"  # the attempt sat in the wait-state throughout the queueing

    # Pools are ready now → assembly resolves the attempt off 'generating' (the spinner clears).
    await try_assemble_attempt_async(start.attempt_id, session_factory=factory)
    async with factory() as session:
        resolved = await session.get(QuizAttempt, start.attempt_id)
    assert resolved.status != "generating"


# ── (B1) D1 pre-warm invariant: warm pool serves with no cold wait ──────────────────────────────────
async def test_12e_prewarm_warm_pool_serves_without_cold_wait(db_session, captured):
    base = await _seed_base(db_session)
    warm = await _seed_section(db_session, base, title="WARM", order=0)
    cold = await _seed_section(db_session, base, title="COLD", order=1)
    factory = _factory(db_session)

    # D1 pre-warm — the real path (AssessmentScope create/update → prewarm_scope_pools): ensure a pool per
    # in-scope section, then drain the (ai-queue) generation job so the pool is READY, as the ai worker does.
    await prewarm_scope_pools(factory, section_ids=[warm.section.id])
    async with factory() as session:
        pending = (
            await session.execute(
                select(SectionQuestionPool).where(
                    SectionQuestionPool.module_section_id == warm.section.id
                )
            )
        ).scalar_one()
    assert pending.status == "generating"
    await generate_section_pool_async(pending.id, gateway=_b1_gateway(factory), session_factory=factory)
    async with factory() as session:
        warm_pool = await session.get(SectionQuestionPool, pending.id)
    assert warm_pool.status == "ready"
    # Warm identity is the rule-15 route's (model, prompt_version) tuple.
    assert warm_pool.model == _pool_model()
    assert warm_pool.prompt_version == _pool_prompt_version()

    # WARM section: a student start serves from the ready pool with NO new generation enqueued (no cold wait).
    enq_before = len(captured.pools)
    warm_ensure = await ensure_section_pool(factory, section_id=warm.section.id)
    assert warm_ensure.status == "ready"
    assert warm_ensure.pool_id == warm_pool.id
    assert len(captured.pools) == enq_before  # the warm-pool invariant: no generation job

    # COLD section (never pre-warmed): the first start is the one that PAYS the generation wait.
    cold_ensure = await ensure_section_pool(factory, section_id=cold.section.id)
    assert cold_ensure.status == "generating"
    assert len(captured.pools) == enq_before + 1  # cold path enqueues the (~264s) generation job
