from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ModuleAccessContext:
    module_id: UUID
    is_active: bool
    global_role: str
    can_publish: bool
    membership_id: UUID


@dataclass(frozen=True)
class CurrentUserContext:
    user_id: UUID
    auth_provider_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    timezone: str
    # Defaulted: the auth dependency always resolves it from the user row; synthetic contexts
    # (e.g. the dev-reseed admin) and tests that don't exercise the glossary fall back to English.
    preferred_language: str = "en"
