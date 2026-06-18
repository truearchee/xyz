from __future__ import annotations

import asyncio
from uuid import UUID

from app.domains.assistant.generation_service import generate_assistant_answer_async


def generate_assistant_answer(message_id: str) -> None:
    """RQ entry for Stage 8.1 interactive assistant answer generation."""
    asyncio.run(generate_assistant_answer_async(UUID(message_id)))
