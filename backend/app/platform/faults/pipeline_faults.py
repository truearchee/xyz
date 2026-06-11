"""Deterministic pipeline fault-injection harness (Stage 4.6a, prereq #4).

The ONLY sanctioned way to test recovery is deterministic forced failure + seeded failed-job records
— never random failure, never manual DB edits. This harness is env-gated and a strict no-op when off,
and is inert (raises) outside non-prod so it can never fire in production/staging.

It is distinct from the LLM-transport ``LLM_FAULT_INJECTION`` double (which only fails summary jobs at
the provider boundary): ``maybe_fail_step`` can force ANY of the five pipeline steps to fail, and each
step's existing try/except turns the raise into a real failed ``IngestionJob`` row — exactly the input
4.6b retry tests consume.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.platform.config import settings
from app.platform.db.models import IngestionJob


FAULTABLE_STEPS = ("parse", "chunk", "embed", "summary_brief", "summary_detailed")


class PipelineFaultInjected(RuntimeError):
    """Raised by ``maybe_fail_step`` to deterministically fail the running pipeline step."""

    def __init__(self, step: str) -> None:
        super().__init__(f"pipeline fault injection forced step '{step}' to fail")
        self.step = step


def _assert_safe_to_inject() -> None:
    if not settings.IS_NON_PROD:
        raise RuntimeError(
            "PIPELINE_FAULT_INJECTION_ENABLED must never be set in production/staging"
        )


def maybe_fail_step(step: str) -> None:
    """No-op unless the harness is enabled AND the configured step matches ``step``.

    Call this once at the top of a step's running body (after the job is claimed) so the forced raise
    routes through the step's normal failure-persistence path.
    """
    if not settings.PIPELINE_FAULT_INJECTION_ENABLED:
        return
    _assert_safe_to_inject()
    if settings.PIPELINE_FAULT_INJECTION == step:
        raise PipelineFaultInjected(step)


async def seed_failed_ingestion_job(
    session: AsyncSession,
    *,
    transcript_id: UUID,
    job_type: str,
    failure_category: str | None = None,
    error_message: str = "seeded fault injection failure",
) -> UUID:
    """Insert a pre-failed ``IngestionJob`` for ``transcript_id`` (non-prod only).

    Lets recovery tests start from a failed-step record without running the pipeline. The caller owns
    the surrounding transaction (this flushes; it does not commit).
    """
    _assert_safe_to_inject()
    job = IngestionJob(
        id=uuid7(),
        transcript_id=transcript_id,
        job_type=job_type,
        status="failed",
        idempotency_key=f"seed-fault:{transcript_id}:{job_type}:{uuid7()}",
        error_message=error_message,
        failure_category=failure_category,
    )
    session.add(job)
    await session.flush()
    return job.id
