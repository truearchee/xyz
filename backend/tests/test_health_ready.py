"""Stage 4.8 (B3, MF2) — /health/ready states + /health liveness is DB-free.

readiness() is exercised directly (it returns a JSONResponse) with its DB/Redis/migration probes
monkeypatched, so each status-code path is deterministic without a configured module engine or a live
Redis. One real-DB test proves the head reader against the migrated test schema.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import health


async def _call() -> tuple[int, dict]:
    response = await health.readiness()
    return response.status_code, json.loads(response.body)


def _all_green(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "_database_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(health, "_redis_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(health, "_applied_revision", AsyncMock(return_value="0013_head"))
    monkeypatch.setattr(health, "_expected_head", lambda: "0013_head")


@pytest.mark.anyio
async def test_ready_200_when_all_green(monkeypatch: pytest.MonkeyPatch) -> None:
    _all_green(monkeypatch)
    status, body = await _call()
    assert status == 200
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok", "redis": "ok", "migrations": "head"}


@pytest.mark.anyio
async def test_ready_503_no_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    # The literal 4.8a end state: DB + Redis up, but no migration has run → alembic_version absent.
    # MUST be 503 (not 500) so a legitimately-red readiness does not look like a crash.
    _all_green(monkeypatch)
    monkeypatch.setattr(health, "_applied_revision", AsyncMock(return_value=None))
    status, body = await _call()
    assert status == 503
    assert body["status"] == "not_ready"
    assert body["checks"]["migrations"] == "no_schema"


@pytest.mark.anyio
async def test_ready_503_behind_head(monkeypatch: pytest.MonkeyPatch) -> None:
    _all_green(monkeypatch)
    monkeypatch.setattr(health, "_applied_revision", AsyncMock(return_value="0009_old"))
    status, body = await _call()
    assert status == 503
    assert body["checks"]["migrations"] == "behind_head"


@pytest.mark.anyio
async def test_ready_503_when_db_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _all_green(monkeypatch)
    monkeypatch.setattr(health, "_database_ok", AsyncMock(return_value=False))
    status, body = await _call()
    assert status == 503
    assert body["checks"]["database"] == "unavailable"


@pytest.mark.anyio
async def test_ready_503_when_redis_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _all_green(monkeypatch)
    monkeypatch.setattr(health, "_redis_ok", AsyncMock(return_value=False))
    status, body = await _call()
    assert status == 503
    assert body["checks"]["redis"] == "unavailable"


@pytest.mark.anyio
async def test_ready_503_on_branched_heads(monkeypatch: pytest.MonkeyPatch) -> None:
    # MF2: get_current_head() raises on branched heads → 503 'error', never a 500.
    _all_green(monkeypatch)

    def _branched() -> str:
        raise RuntimeError("Multiple head revisions are present")

    monkeypatch.setattr(health, "_expected_head", _branched)
    status, body = await _call()
    assert status == 503
    assert body["checks"]["migrations"] == "error"


@pytest.mark.anyio
async def test_health_liveness_is_db_free() -> None:
    # /health must never depend on the DB (a blip must not restart-loop the machine — §7.K).
    body = await health.health()
    assert body == {"status": "ok", "service": "xyz-lms-backend"}


@pytest.mark.anyio
async def test_applied_revision_matches_filesystem_head(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Real migrated DB: the applied alembic_version equals the single filesystem head.
    monkeypatch.setattr(health, "engine", db_session.bind)
    applied = await health._applied_revision()
    assert applied is not None
    assert applied == health._expected_head()
