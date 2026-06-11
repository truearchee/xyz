"""Is an IngestionJob still live in RQ? (ADR-46-C liveness signal — no heartbeat columns.)

embed/summary jobs are enqueued with stable RQ job_ids (``embed-{id}`` / ``summary-brief-{id}`` /
``summary-detailed-{id}``), so we can ask RQ directly. parse/chunk are enqueued WITHOUT a stable id, so
their liveness is unknowable from RQ (``None``) — the reaper falls back to per-step age there.
"""

from __future__ import annotations

import logging
from uuid import UUID

from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.workers.queues import get_redis_connection


logger = logging.getLogger(__name__)

_STABLE_JOB_ID = {
    "embed": lambda i: f"embed-{i}",
    "generate_brief_summary": lambda i: f"summary-brief-{i}",
    "generate_detailed_summary": lambda i: f"summary-detailed-{i}",
}
_LIVE_STATUSES = {"queued", "started", "deferred", "scheduled"}


def is_job_live_in_rq(job_type: str, ingestion_job_id: UUID) -> bool | None:
    """True/False if known; None when unknowable (parse/chunk have no stable id, or Redis is unreachable)."""
    builder = _STABLE_JOB_ID.get(job_type)
    if builder is None:
        return None  # parse/chunk: no stable RQ job_id
    job_id = builder(ingestion_job_id)
    try:
        job = Job.fetch(job_id, connection=get_redis_connection())
    except NoSuchJobError:
        return False
    except Exception:  # pragma: no cover - Redis hiccup → unknown (do not reap on uncertainty)
        logger.warning("RQ liveness check failed for %s; treating as unknown", job_id)
        return None
    return job.get_status(refresh=False) in _LIVE_STATUSES
