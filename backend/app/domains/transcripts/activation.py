"""Atomic activation of a completed pending replacement transcript (ADR-46-A §3.1).

``try_activate_pending_transcript`` is the ONLY way a ``pending`` transcript becomes ``active``. It runs
under the section lock, verifies the pending has fully completed (``overall_state == 'summarized'``)
with eligible brief + detailed summaries (via the transcript-domain eligibility service, NOT the
read-only resolver), then swaps old active → superseded and pending → active in one transaction.

The function is a NO-OP for any transcript that is not a ready pending, so it is safe to call
opportunistically from EVERY pipeline leaf on success (embed, brief, detailed — `attempt_pending_activation`
below). The pipeline is a forked DAG (4.6b: summaries fork from parse, parallel to embed), so which leaf
finishes last is a race; keying activation to any single "last" step re-breaks on the next DAG reshape
(this is exactly F-4.6b-2). Every leaf attempts it; the readiness gate no-ops the early calls; whichever
leaf finishes last fires the swap. A non-replacement pipeline returns ``NOT_PENDING``; a not-yet-summarized
pending returns ``NOT_READY``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.transcripts.summary_eligibility import get_activation_ready_summaries
from app.platform.config import settings
from app.platform.db.models import ModuleSection, Transcript
from app.platform.query.transcript_status import get_transcript_processing_status_read

logger = logging.getLogger(__name__)


class ActivationOutcome(str, Enum):
    ACTIVATED = "activated"
    NOT_PENDING = "not_pending"
    NOT_READY = "not_ready"
    SUPERSEDED_BY_NEWER = "superseded_by_newer"


def _now() -> datetime:
    return datetime.now(UTC)


async def try_activate_pending_transcript(
    session: AsyncSession,
    *,
    transcript_id: UUID,
) -> ActivationOutcome:
    async with session.begin():
        # Read (no lock) to discover the section, then lock the SECTION first — same lock order as
        # upload_transcript (section → transcript) so the two paths can never deadlock.
        candidate = (
            await session.execute(
                select(Transcript).where(Transcript.id == transcript_id)
            )
        ).scalar_one_or_none()
        if candidate is None or candidate.lifecycle_state != "pending":
            return ActivationOutcome.NOT_PENDING

        await session.execute(
            select(ModuleSection.id)
            .where(ModuleSection.id == candidate.module_section_id)
            .with_for_update()
        )

        # Re-read under the section lock + row lock. A newer upload would have discarded this
        # candidate (→ superseded) while holding the same section lock.
        candidate = (
            await session.execute(
                select(Transcript)
                .where(Transcript.id == transcript_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if candidate is None or candidate.lifecycle_state != "pending":
            return ActivationOutcome.SUPERSEDED_BY_NEWER

        # Readiness gate: fully summarized AND exactly one eligible brief (+ detailed when enabled).
        status = await get_transcript_processing_status_read(session, transcript=candidate)
        if status.overall_state != "summarized":
            return ActivationOutcome.NOT_READY
        readiness = await get_activation_ready_summaries(
            session,
            transcript=candidate,
            require_detailed=settings.ENABLE_DETAILED_SUMMARY,
        )
        if not readiness.is_ready:
            return ActivationOutcome.NOT_READY

        now = _now()
        # Supersede the old active FIRST so the one-active partial-unique index never sees two
        # 'active' rows at a statement boundary, THEN promote the candidate.
        active = (
            await session.execute(
                select(Transcript)
                .where(
                    Transcript.module_section_id == candidate.module_section_id,
                    Transcript.lifecycle_state == "active",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if active is not None and active.id != candidate.id:
            active.lifecycle_state = "superseded"
            active.superseded_at = now
            active.superseded_by_transcript_id = candidate.id
            active.supersession_reason = "replaced_active"
            active.updated_at = now
            # Flush the demotion BEFORE the promotion so the one-active partial-unique index never
            # sees two 'active' rows (the unit of work does not preserve assignment order).
            await session.flush()

        candidate.lifecycle_state = "active"
        candidate.updated_at = now
        return ActivationOutcome.ACTIVATED


async def attempt_pending_activation(
    factory: async_sessionmaker[AsyncSession],
    *,
    transcript_id: UUID,
) -> None:
    """Best-effort activation hook for EVERY pipeline leaf (embed, brief, detailed) on success.

    Whichever leaf finishes last fires the swap; the readiness gate no-ops the earlier calls
    (F-4.6b-2: keying activation to a single "last" step breaks under the forked DAG). Activation must
    NEVER fail the step that triggered it, so all errors are swallowed and the transcript is left pending
    for a later trigger / retry."""
    try:
        async with factory() as session:
            await try_activate_pending_transcript(session, transcript_id=transcript_id)
    except Exception:  # pragma: no cover - defensive; activation never breaks step completion
        logger.warning(
            "Pending-transcript activation attempt failed; left pending",
            extra={"transcript_id": str(transcript_id)},
        )
