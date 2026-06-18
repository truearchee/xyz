"""Assistant readiness read model (Stage 8.1, cross-session decision 9).

Read model ONLY (rule 8): given a section the caller has already confirmed visible (published + the
student is an active member — via ``get_visible_student_section``), report whether the lecture is
RETRIEVAL-ready for the assistant. The pipeline forks (4.6b): a summary can exist without embeddings,
so the assistant keys specifically off transcript **chunks + embeddings** existing on the active
transcript — not off the summary being ready.

  ready        — an active transcript exists with at least one embedded chunk (retrieval can run)
  processing   — an active transcript exists but is still being chunked/embedded
  unavailable  — no active transcript, or its processing failed
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import Transcript
from app.platform.query.student_summary_read import resolve_single_active
from app.platform.query.transcript_status import get_transcript_processing_status_read

READY = "ready"
PROCESSING = "processing"
UNAVAILABLE = "unavailable"


async def get_section_assistant_readiness(
    db: AsyncSession,
    *,
    section_id: UUID,
) -> str:
    """Retrieval readiness for the section's ACTIVE transcript. Visibility (published + assigned) is the
    caller's gate; this only answers "are chunks + embeddings present"."""
    actives = (
        (
            await db.execute(
                select(Transcript).where(
                    Transcript.module_section_id == section_id,
                    Transcript.lifecycle_state == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    active = resolve_single_active(list(actives), section_id=section_id)
    if active is None:
        return UNAVAILABLE

    status = await get_transcript_processing_status_read(db, transcript=active)
    if status.overall_state == "failed":
        return UNAVAILABLE
    # An embedded chunk is a chunk; >0 means both chunks and embeddings exist (decision 9).
    if status.embedded_chunk_count > 0:
        return READY
    return PROCESSING
