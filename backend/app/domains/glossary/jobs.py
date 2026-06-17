from __future__ import annotations

import asyncio
from uuid import UUID

from app.domains.glossary.definition_service import generate_glossary_definition_async


def generate_glossary_definition(cache_row_id: str) -> None:
    asyncio.run(generate_glossary_definition_async(UUID(cache_row_id)))
