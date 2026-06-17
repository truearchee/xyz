"""The platform pagination envelope (Stage 5 lock 9), defined once and reused everywhere.

``PaginatedResponse[T] = { items: T[], pagination: { limit, offset, total } }`` (offset-based). Glossary,
conversations, and events all reuse this verbatim — defining it now avoids retrofitting pagination at
Stage 7. camelCase aliasing keeps the generated TS client consistent with the rest of the API.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    limit: int
    offset: int
    total: int


class PaginatedResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    items: list[T]
    pagination: PaginationMeta
