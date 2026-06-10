from __future__ import annotations

import asyncio
from uuid import UUID

from app.domains.transcripts.chunk_service import chunk_transcript_async
from app.domains.transcripts.embedding_service import embed_transcript_async
from app.domains.transcripts.parse_service import parse_transcript_async


def parse_transcript(transcript_id: str) -> None:
    asyncio.run(parse_transcript_async(UUID(transcript_id)))


def chunk_transcript(ingestion_job_id: str) -> None:
    asyncio.run(chunk_transcript_async(UUID(ingestion_job_id)))


def embed_transcript(ingestion_job_id: str) -> None:
    asyncio.run(embed_transcript_async(UUID(ingestion_job_id), raise_on_failure=True))
