from dataclasses import dataclass
from typing import Literal
from uuid import UUID


MembershipRole = Literal["student", "lecturer"]


@dataclass(frozen=True)
class ModuleMembership:
    module_id: UUID
    role: MembershipRole
    is_owner: bool
    can_publish: bool


@dataclass(frozen=True)
class CurrentUserContext:
    user_id: UUID
    auth_provider_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    timezone: str
    module_memberships: tuple[ModuleMembership, ...]
