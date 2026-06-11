"""Atomic activation of a completed pending replacement transcript (ADR-46-A §3.1).

``try_activate_pending_transcript`` is the ONLY way a ``pending`` transcript becomes ``active``. It runs
under the section lock, verifies the pending has fully completed (``overall_state == 'summarized'``)
with eligible brief + detailed summaries (via the transcript-domain eligibility service, NOT the
read-only resolver), then swaps old active → superseded and pending → active in one transaction.

The function is a NO-OP for any transcript that is not a ready pending, so it is safe to call
opportunistically from the summary-completion path: a non-replacement pipeline (active-first-upload)
returns ``NOT_PENDING`` and nothing happens; a pending that is not yet summarized returns ``NOT_READY``
and stays pending for a later trigger (or 4.6b retry).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.transcripts.summary_eligibility import get_activation_ready_summaries
from app.platform.config import settings
from app.platform.db.models import ModuleSection, Transcript
from app.platform.query.transcript_status import get_transcript_processing_status_read


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
