from __future__ import annotations

import asyncio
from uuid import UUID

from app.domains.quiz.generation_service import generate_post_class_quiz_async


def generate_post_class_quiz(attempt_id: str) -> None:
    asyncio.run(generate_post_class_quiz_async(UUID(attempt_id)))
