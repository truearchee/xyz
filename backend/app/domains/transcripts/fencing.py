"""Fencing guard for pipeline steps under retry / supersession (ADR-46-B §3.2).

Marking a job failed (by the reaper) or superseding a transcript does NOT kill an OS worker process
that is already mid-run. Before ANY destructive write (the delete that begins a retry, a
generated-output write, or a downstream enqueue), the worker must — in the same transaction as that
write, with the job and transcript already locked ``FOR UPDATE`` — verify that it is still the live
attempt for a non-superseded transcript. If not, it aborts and writes/enqueues nothing, so a stale
job can never clobber rows belonging to a newer valid attempt.

The "still the current job for (transcript, jobType)" half is already enforced per step (parse: the
attempt token + the one-active-parse index; chunk: the completed-key dedup; embed/summary: the
one-active index + the ``status == 'running'`` check in their persist paths). This helper adds the
two uniform guards: the transcript is not ``superseded`` and the job is still ``running``.
"""

from __future__ import annotations

from app.platform.db.models import IngestionJob, Transcript


def can_commit_step(*, job: IngestionJob, transcript: Transcript | None) -> bool:
    """Whether ``job`` may perform its destructive write for ``transcript``.

    Call inside the destructive-write transaction, with both rows already locked ``FOR UPDATE``.
    Returns False (caller must abort: no delete, no write, no enqueue) when the transcript is gone or
    superseded, or the job is no longer the running attempt.
    """
    if transcript is None or transcript.lifecycle_state == "superseded":
        return False
    if job.status != "running":
        return False
    return True
