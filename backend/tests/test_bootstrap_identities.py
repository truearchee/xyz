"""Stage 4.8b (B3, MF6) — idempotent first-admin + seed-identity bootstrap.

Properties asserted: creates the admin (which the admin API forbids) + the gated seed identities;
re-run is idempotent (no duplicate rows); an existing user's password is NEVER rotated; the seed gate
(BOOTSTRAP_SEED_IDENTITIES + not IS_PRODUCTION) is enforced IN the CLI. Supabase is faked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import bootstrap_identities as boot
from app.platform.db.models import AppUser


class FakeAdmin:
    def __init__(self) -> None:
        self.users: dict[str, str] = {}  # email -> supabase id
        self.create_calls: list[dict] = []
        self.update_calls: list = []
        self.list_calls = 0

    async def create_user(self, payload: dict):
        self.create_calls.append(payload)
        email = payload["email"]
        if email in self.users:
            raise RuntimeError("User already registered")  # Supabase conflict
        uid = f"sb-{len(self.users) + 1}"
        self.users[email] = uid
        return SimpleNamespace(user=SimpleNamespace(id=uid))

    async def list_users(self, *args, **kwargs):
        self.list_calls += 1
        return [SimpleNamespace(email=email, id=uid) for email, uid in self.users.items()]

    async def update_user_by_id(self, *args, **kwargs):  # must NEVER be called by the bootstrap
        self.update_calls.append((args, kwargs))
        return None


@pytest.fixture
def fake_supabase(monkeypatch: pytest.MonkeyPatch) -> FakeAdmin:
    admin = FakeAdmin()
    client = SimpleNamespace(auth=SimpleNamespace(admin=admin))

    async def _get_client():
        return client

    monkeypatch.setattr(boot, "get_supabase_admin_client", _get_client)
    return admin


def _factory(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)


def _set_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    env: str = "staging",
    flag: bool = True,
    seeds: bool = True,
    admin_password: str = "adminpw1",
) -> None:
    monkeypatch.setenv("ENVIRONMENT", env)
    if flag:
        monkeypatch.setenv("BOOTSTRAP_SEED_IDENTITIES", "true")
    else:
        monkeypatch.delenv("BOOTSTRAP_SEED_IDENTITIES", raising=False)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@staging.test")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", admin_password)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_NAME", "Staging Admin")
    if seeds:
        monkeypatch.setenv("BOOTSTRAP_LECTURER_EMAIL", "lecturer@staging.test")
        monkeypatch.setenv("BOOTSTRAP_LECTURER_PASSWORD", "lecturerpw1")
        monkeypatch.setenv("BOOTSTRAP_STUDENT_EMAIL", "student@staging.test")
        monkeypatch.setenv("BOOTSTRAP_STUDENT_PASSWORD", "studentpw1")


async def _emails(factory) -> set[str]:
    async with factory() as session:
        return set((await session.scalars(select(AppUser.email))).all())


@pytest.mark.anyio
async def test_creates_admin_and_seeds_then_idempotent(
    db_session: AsyncSession, fake_supabase: FakeAdmin, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env(monkeypatch)
    factory = _factory(db_session)

    first = await boot.bootstrap(session_factory=factory)
    assert first == {"created": 3, "updated": 0}
    async with factory() as session:
        rows = {u.email: u for u in (await session.scalars(select(AppUser))).all()}
    assert rows["admin@staging.test"].role == "admin"  # the admin API forbids this — bootstrap is the path
    assert rows["lecturer@staging.test"].role == "lecturer"
    assert rows["student@staging.test"].role == "student"
    assert all(u.is_active for u in rows.values())

    second = await boot.bootstrap(session_factory=factory)
    assert second == {"created": 0, "updated": 3}  # idempotent
    assert len(await _emails(factory)) == 3  # no duplicate rows


@pytest.mark.anyio
async def test_existing_user_password_is_never_rotated(
    db_session: AsyncSession, fake_supabase: FakeAdmin, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env(monkeypatch, seeds=False, admin_password="firstpw")
    factory = _factory(db_session)

    await boot.bootstrap(session_factory=factory)
    assert fake_supabase.create_calls[0]["password"] == "firstpw"

    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "rotatedpw")
    await boot.bootstrap(session_factory=factory)
    # the existing user is fetched (create raised conflict); the password is NEVER applied via update.
    assert fake_supabase.update_calls == []


@pytest.mark.anyio
async def test_seed_identities_blocked_in_production(
    db_session: AsyncSession, fake_supabase: FakeAdmin, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env(monkeypatch, env="production", flag=True)  # flag on, but production → seeds refused
    factory = _factory(db_session)
    result = await boot.bootstrap(session_factory=factory)
    assert result == {"created": 1, "updated": 0}  # admin only
    assert await _emails(factory) == {"admin@staging.test"}


@pytest.mark.anyio
async def test_seed_identities_blocked_when_flag_off(
    db_session: AsyncSession, fake_supabase: FakeAdmin, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env(monkeypatch, env="staging", flag=False)  # staging but flag off → seeds refused
    factory = _factory(db_session)
    result = await boot.bootstrap(session_factory=factory)
    assert result == {"created": 1, "updated": 0}  # admin only
    assert await _emails(factory) == {"admin@staging.test"}
