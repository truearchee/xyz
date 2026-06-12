"""Stage 4.8c (C1, §7.C2) — internal SSE probe: gated (404 when off), admin-only, event-stream shape.

§7.C2 acceptance: 3–5 chunks, no compression, admin-auth, registered only when enabled. Progressive
(not buffered) delivery is the hosted browser check (over D1) — not assertable from an in-process client.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.platform.db.session import get_db_session
from tests.test_transcripts import _create_user, _headers


@pytest.fixture
async def probe_client(db_session: AsyncSession, mock_jwks_client, monkeypatch):
    """A client on a flag-ON app (the default `app` is created at import with the probe OFF)."""
    monkeypatch.setenv("ENABLE_INTERNAL_SSE_PROBE", "true")
    import app.api.routers.sse_probe as probe_mod

    monkeypatch.setattr(probe_mod, "_INTERVAL_SECONDS", 0.0)  # no wall-clock wait in tests
    app_on = create_app()

    async def _override_db():
        yield db_session

    app_on.dependency_overrides[get_db_session] = _override_db
    async with AsyncClient(transport=ASGITransport(app=app_on), base_url="http://test") as client:
        yield client
    app_on.dependency_overrides.clear()


@pytest.mark.anyio
async def test_probe_absent_when_disabled(auth_client: AsyncClient) -> None:
    # Default app (ENABLE_INTERNAL_SSE_PROBE off) → the route is not registered at all → 404.
    response = await auth_client.get("/internal/sse-probe")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_probe_requires_admin(
    probe_client: AsyncClient, db_session: AsyncSession, jwt_factory
) -> None:
    lecturer = await _create_user(db_session, email=f"lec-{uuid4()}@example.com", role="lecturer")
    await db_session.commit()
    forbidden = await probe_client.get("/internal/sse-probe", headers=_headers(lecturer, jwt_factory))
    assert forbidden.status_code == 403
    unauth = await probe_client.get("/internal/sse-probe")
    assert unauth.status_code == 401


@pytest.mark.anyio
async def test_probe_streams_event_stream(
    probe_client: AsyncClient, db_session: AsyncSession, jwt_factory
) -> None:
    admin = await _create_user(db_session, email=f"admin-{uuid4()}@example.com", role="admin")
    await db_session.commit()
    response = await probe_client.get("/internal/sse-probe", headers=_headers(admin, jwt_factory))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get("x-accel-buffering") == "no"  # anti-buffering
    assert "content-encoding" not in response.headers  # no compression on the event-stream
    events = [block for block in response.text.split("\n\n") if block.startswith("data:")]
    assert 3 <= len(events) <= 5  # §7.C2: 3–5 chunks
