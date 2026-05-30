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


class CreateModuleRequest(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    owner_id: UUID
    timezone: str = "UTC"
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> CreateModuleRequest:
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            raise ValueError("startsOn must be on or before endsOn")
        return self


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
    is_active: bool
    created_at: datetime


class MembershipResponse(CamelModel):
    id: UUID
    user_id: UUID
    module_id: UUID
    role: str
    status: str
    created_at: datetime


class StatusResponse(CamelModel):
    status: str
