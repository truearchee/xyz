"""Idempotent first-admin + seed-identity bootstrap (Stage 4.8b, B3).

Runs in the release phase AFTER ``alembic upgrade head`` (see ``scripts/release.sh``). For each
configured identity: ensure a CONFIRMED Supabase auth user (create-or-fetch — the password is set
ONLY on create and is NEVER rotated on a re-run, MF6), then upsert the ``AppUser`` row. The ADMIN row
is created here because the admin API forbids it (``domains/admin/service.py`` rejects ``role=='admin'``)
— this is the sole sanctioned admin-creation path. USERS ONLY; module memberships are created in-smoke
(4.8d). Passwords are never logged.

Gate (the CLI is the authoritative gate — ``check-staging-env`` is a second layer the operator can
skip): the ADMIN runs whenever ``BOOTSTRAP_ADMIN_*`` are set (the legitimate prod first-admin). The
known-credential LECTURER/STUDENT seed identities require ``BOOTSTRAP_SEED_IDENTITIES=true`` AND
``not IS_PRODUCTION`` — note this is **not** ``IS_NON_PROD`` (which excludes staging): the seeds are
REQUIRED in staging for the smoke; they must only be blocked in real production.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.config import settings
from app.platform.db.models import AppUser
from app.platform.db.session import create_direct_engine
from app.platform.supabase_client import get_supabase_admin_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Identity:
    key: str  # admin | lecturer | student
    email: str
    password: str
    full_name: str
    role: str


def _identity_from_env(key: str, role: str) -> Identity | None:
    prefix = f"BOOTSTRAP_{key.upper()}_"
    email = (os.environ.get(prefix + "EMAIL") or "").strip()
    password = os.environ.get(prefix + "PASSWORD") or ""
    if not email or not password:
        return None
    name = (os.environ.get(prefix + "NAME") or "").strip() or email
    return Identity(key=key, email=email, password=password, full_name=name, role=role)


def configured_identities() -> list[Identity]:
    """The identities to bootstrap, after applying the seed gate. ADMIN always (if its vars are set);
    lecturer/student only when BOOTSTRAP_SEED_IDENTITIES AND not IS_PRODUCTION."""
    identities: list[Identity] = []
    admin = _identity_from_env("admin", "admin")
    if admin is not None:
        identities.append(admin)

    seeds = [
        ident
        for ident in (_identity_from_env("lecturer", "lecturer"), _identity_from_env("student", "student"))
        if ident is not None
    ]
    if seeds:
        if settings.BOOTSTRAP_SEED_IDENTITIES and not settings.IS_PRODUCTION:
            identities.extend(seeds)
        else:
            logger.info(
                "Seed identities present but GATED OFF "
                "(BOOTSTRAP_SEED_IDENTITIES=%s, IS_PRODUCTION=%s) — skipping lecturer/student",
                settings.BOOTSTRAP_SEED_IDENTITIES,
                settings.IS_PRODUCTION,
            )
    return identities


def _extract_id(candidate: Any) -> str | None:
    user = getattr(candidate, "user", None) or getattr(candidate, "data", None) or candidate
    if isinstance(user, dict):
        value = user.get("id")
    else:
        value = getattr(user, "id", None)
    return str(value) if value else None


def _iter_users(result: Any):
    """Supabase list_users may return a list, or an object/dict with a ``users`` field."""
    if isinstance(result, dict):
        return result.get("users", []) or []
    return getattr(result, "users", None) or (result if isinstance(result, list) else [])


async def _find_supabase_user_id(admin: Any, email: str) -> str | None:
    result = await admin.list_users()
    for user in _iter_users(result):
        user_email = user.get("email") if isinstance(user, dict) else getattr(user, "email", None)
        if user_email and user_email.lower() == email.lower():
            return _extract_id(user)
    return None


async def ensure_supabase_user(email: str, password: str) -> str:
    """Create-or-fetch a CONFIRMED Supabase auth user. The password is applied ONLY on create; an
    existing user is fetched and its password is left untouched (MF6 — no rotation on re-run)."""
    supabase = await get_supabase_admin_client()
    admin = supabase.auth.admin
    try:
        response = await admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        created_id = _extract_id(response)
        if created_id:
            return created_id
    except Exception:  # already exists (or create raced) → fetch; never rotate the password
        logger.info("Supabase user for %s exists or create deferred — fetching (no password rotation)", email)
    found = await _find_supabase_user_id(admin, email)
    if found is None:
        raise RuntimeError(f"could not create or find a Supabase auth user for {email}")
    return found


async def _upsert_app_user(session: AsyncSession, ident: Identity, supabase_user_id: str) -> str:
    existing = await session.scalar(select(AppUser).where(AppUser.email == ident.email))
    if existing is None:
        session.add(
            AppUser(
                auth_provider_id=supabase_user_id,
                email=ident.email,
                full_name=ident.full_name,
                role=ident.role,
                is_active=True,
            )
        )
        return "created"
    existing.auth_provider_id = supabase_user_id
    existing.full_name = ident.full_name
    existing.role = ident.role
    existing.is_active = True
    return "updated"


async def bootstrap(
    *, session_factory: async_sessionmaker[AsyncSession] | None = None
) -> dict[str, int]:
    """Idempotently ensure the configured identities. Injectable session_factory for tests; otherwise
    opens a DIRECT (session-endpoint) engine — consistent with migrations-over-direct (O3)."""
    identities = configured_identities()
    counts = {"created": 0, "updated": 0}
    if not identities:
        logger.info("No bootstrap identities configured — nothing to do.")
        return counts

    own_engine = session_factory is None
    engine = None
    if own_engine:
        engine = create_direct_engine()
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    else:
        factory = session_factory
    try:
        async with factory() as session:
            for ident in identities:
                supabase_user_id = await ensure_supabase_user(ident.email, ident.password)
                action = await _upsert_app_user(session, ident, supabase_user_id)
                counts[action] += 1
                logger.info("bootstrap identity email=%s role=%s -> %s", ident.email, ident.role, action)
            await session.commit()
    finally:
        if own_engine and engine is not None:
            await engine.dispose()
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(bootstrap())
    logger.info("Identity bootstrap complete: %s", result)


if __name__ == "__main__":
    main()
