"""Assistant retrieval read model (Stage 8.2, review #10) — the first vector query in the codebase.

Read model ONLY (rule 8): an EXACT pgvector cosine scan (``<=>``, NO ANN index) over the chunks of one
section's ACTIVE transcript, joined through the SAME published+assigned visibility gate as Stage 4.7
(``get_visible_student_section``). It returns the nearest ``top_k`` chunks with their cosine distance;
the relevance threshold + grounding decision live in the domain, so this surface invents no policy.

Safety (review #10/#13):
  - Scope: the WHERE clause pins section + active transcript + module + publish/active/membership, so a
    chunk from another section, an unpublished section, or a transcript the student isn't entitled to
    can NEVER enter the candidate set — even if a chunk's text contains injection-looking content.
  - Same-model filter: only vectors produced by the configured embedding model/version are compared
    (mixing geometries would make distances meaningless).
  - Binding: the query vector is bound via pgvector's ``cosine_distance`` and every id/string is a bind
    parameter — NOTHING is string-interpolated into the SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import (
    CourseMembership,
    CourseModule,
    ModuleSection,
    Transcript,
    TranscriptChunk,
)
from app.platform.embeddings import DEFAULT_EMBEDDING_CONFIG


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    distance: float
    token_count: int
    text: str


async def retrieve_section_chunks(
    db: AsyncSession,
    *,
    student_id: UUID,
    section_id: UUID,
    module_id: UUID,
    active_transcript_id: UUID,
    query_vector: list[float],
    top_k: int,
) -> list[RetrievedChunk]:
    """Return up to ``top_k`` nearest chunks (cosine distance asc) of the section's active transcript,
    iff the section is published+active in an active module the student is an active student-member of.
    Zero rows when not visible / not ready / no same-model embeddings — the caller maps that, never this
    surface."""
    distance = TranscriptChunk.embedding.cosine_distance(query_vector).label("distance")
    result = await db.execute(
        select(
            TranscriptChunk.id,
            distance,
            TranscriptChunk.token_count,
            TranscriptChunk.text,
        )
        .join(Transcript, Transcript.id == TranscriptChunk.transcript_id)
        .join(ModuleSection, ModuleSection.id == Transcript.module_section_id)
        .join(CourseModule, CourseModule.id == ModuleSection.course_module_id)
        .join(CourseMembership, CourseMembership.module_id == CourseModule.id)
        .where(
            ModuleSection.id == section_id,
            Transcript.id == active_transcript_id,
            CourseModule.id == module_id,
            # ── same published+assigned gate as 4.7 (defense-in-depth; server already resolved these) ──
            ModuleSection.publish_status == "published",
            ModuleSection.status == "active",
            CourseModule.is_active.is_(True),
            CourseMembership.user_id == student_id,
            CourseMembership.role == "student",
            CourseMembership.status == "active",
            # ── scope to the still-active transcript's same-model embedded chunks ──
            Transcript.lifecycle_state == "active",
            TranscriptChunk.embedding.is_not(None),
            TranscriptChunk.embedding_model == DEFAULT_EMBEDDING_CONFIG.model_name,
            TranscriptChunk.embedding_version == DEFAULT_EMBEDDING_CONFIG.embedding_version,
        )
        .order_by(distance.asc())
        .limit(top_k)
    )
    return [
        RetrievedChunk(
            chunk_id=row.id,
            distance=float(row.distance),
            token_count=int(row.token_count),
            text=row.text,
        )
        for row in result.all()
    ]
