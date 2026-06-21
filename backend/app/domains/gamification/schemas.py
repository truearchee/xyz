from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class EarnedBadgeRead(CamelModel):
    badge_key: str
    family: str
    title: str
    description: str
    icon: str
    scope_type: str
    scope_id: UUID
    earned_at: datetime
    qualified_value: int | None = None
    threshold: int | None = None


class LockedBadgeRead(CamelModel):
    badge_key: str
    family: str
    title: str
    description: str
    icon: str
    scope_type: str
    scope_id: UUID
    current: int
    target: int


class ProgressItemRead(CamelModel):
    key: str
    label: str
    current: int
    target: int


class GamificationRead(CamelModel):
    current_streak: int
    longest_streak: int
    today_is_scheduled: bool
    today_satisfied: bool
    next_scheduled_day: date | None
    streak_status: str
    earned_badges: list[EarnedBadgeRead]
    locked_badges: list[LockedBadgeRead]
    progress_items: list[ProgressItemRead]
    new_badge_ids: list[str]
    last_seen_at: datetime | None
