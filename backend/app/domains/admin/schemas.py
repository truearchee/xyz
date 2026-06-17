from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class CreateUserRequest(CamelModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: Literal["student", "lecturer", "admin"]
    password: str = Field(min_length=8, max_length=128)
    timezone: str = "UTC"


class ResetPasswordRequest(CamelModel):
    new_password: str = Field(min_length=8, max_length=128)


WeekdayName = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
GeneratedSectionType = Literal["lecture", "lab"]


class SessionPatternEntry(CamelModel):
    weekday: WeekdayName
    section_type: GeneratedSectionType


class ModuleScheduleInput(CamelModel):
    """Creation-time schedule (Stage 5.5, D1/D10). Course dates are calendar dates (YYYY-MM-DD),
    never JS timestamps. weekStartDay defaults to Monday. sessionPattern drives generation; the quiz
    day is recorded but generates no section here."""

    course_start_date: date
    course_end_date: date
    week_start_day: WeekdayName = "monday"
    session_pattern: list[SessionPatternEntry] = Field(min_length=1)
    quiz_day: WeekdayName | None = None

    @model_validator(mode="after")
    def _validate(self) -> ModuleScheduleInput:
        if self.course_start_date > self.course_end_date:
            raise ValueError("courseStartDate must be on or before courseEndDate")
        weekdays = [entry.weekday for entry in self.session_pattern]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("sessionPattern weekdays must be unique")
        if self.quiz_day is not None and self.quiz_day in set(weekdays):
            raise ValueError("quizDay must not overlap a sessionPattern weekday")
        return self


class CreateModuleRequest(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    owner_id: UUID
    timezone: str = "UTC"
    schedule: ModuleScheduleInput


class AssignMemberRequest(CamelModel):
    user_id: UUID
    role: Literal["student", "lecturer"]


class UserResponse(CamelModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    timezone: str
    created_at: datetime


class ModuleResponse(CamelModel):
    id: UUID
    title: str
    description: str | None
    owner_id: UUID
    timezone: str
    starts_on: date | None
    ends_on: date | None
    week_start_day: WeekdayName | None
    session_pattern: list[SessionPatternEntry] | None
    quiz_day: WeekdayName | None
    is_active: bool
    created_at: datetime


class ModuleSectionPreview(CamelModel):
    title: str
    type: GeneratedSectionType
    order_index: int
    week_number: int
    session_date: date


class ModuleSchedulePreviewResponse(CamelModel):
    total_sections: int
    week_count: int
    lecture_count: int
    lab_count: int
    friday_section_count: int
    sections: list[ModuleSectionPreview]


class MembershipResponse(CamelModel):
    id: UUID
    user_id: UUID
    module_id: UUID
    role: str
    status: str
    created_at: datetime


class ModuleMemberResponse(CamelModel):
    membership_id: UUID
    user_id: UUID
    module_id: UUID
    email: str
    full_name: str
    role: Literal["lecturer", "student"]
    membership_status: Literal["active"]
    user_is_active: bool
    created_at: datetime


class StatusResponse(CamelModel):
    status: str
