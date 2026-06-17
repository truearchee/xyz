from __future__ import annotations

import asyncio
from uuid import UUID

from app.domains.quiz.generation_service import generate_post_class_quiz_async


def generate_post_class_quiz(attempt_id: str) -> None:
    asyncio.run(generate_post_class_quiz_async(UUID(attempt_id)))


def generate_section_pool(pool_id: str) -> None:
    """RQ entry for Stage 6a per-section pool generation."""
    from app.domains.quiz.pool_service import generate_section_pool_async

    asyncio.run(generate_section_pool_async(UUID(pool_id)))


def try_assemble_attempt(attempt_id: str) -> None:
    """RQ entry for Stage 6a pooled-attempt assembly (the fan-in target)."""
    from app.domains.quiz.assembly_service import try_assemble_attempt_async

    asyncio.run(try_assemble_attempt_async(UUID(attempt_id)))
