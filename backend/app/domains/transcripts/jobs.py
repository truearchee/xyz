from __future__ import annotations

import asyncio
from uuid import UUID

from app.domains.transcripts.parse_service import parse_transcript_async


def parse_transcript(transcript_id: str) -> None:
    asyncio.run(parse_transcript_async(UUID(transcript_id)))
