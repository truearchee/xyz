"""The platform pagination envelope (Stage 5 lock 9), defined once and reused everywhere.

``PaginatedResponse[T] = { items: T[], pagination: { limit, offset, total } }`` (offset-based). Glossary,
conversations, and events all reuse this verbatim — defining it now avoids retrofitting pagination at
Stage 7. camelCase aliasing keeps the generated TS client consistent with the rest of the API.

``KeysetPage[T] = { items: T[], nextCursor: str | null, hasMore: bool }`` is the Stage 8.4 SIBLING
envelope (rule-10 escalation, ADR-053): a chat thread mutates under the reader (new turns append while
older pages load on scroll), so an offset window shifts on every insert. Offset stays the DEFAULT for
ordinary lists; reach for ``KeysetPage`` only for deep, high-churn, poll-while-appending feeds (the
assistant message history). The offset envelope above is intentionally left UNCHANGED.
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


class KeysetPage(BaseModel, Generic[T]):
    """Cursor-paginated page (Stage 8.4, ADR-053). ``next_cursor`` is an opaque token to pass back as
    ``before`` to fetch the NEXT (older) page; ``has_more`` is false on the last page. ``items`` are in
    display order (oldest→newest within the page)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
