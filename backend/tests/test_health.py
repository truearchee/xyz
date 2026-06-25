from httpx import AsyncClient
import pytest

import app.api.routers.health as health_router
from app.main import app
from app.platform.config import settings


def _configured_allowed_origin() -> str:
    return settings.CORS_ORIGINS[0]


@pytest.mark.anyio
async def test_health_returns_ok():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "xyz-lms-backend"


@pytest.mark.anyio
async def test_health_cors_allowed_origin():
    origin = _configured_allowed_origin()
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"Origin": origin},
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


@pytest.mark.anyio
async def test_health_cors_preflight():
    origin = _configured_allowed_origin()
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == origin
    assert "GET" in response.headers.get("access-control-allow-methods", "")


@pytest.mark.anyio
async def test_health_cors_rejects_unlisted_origin():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"Origin": "http://evil.example"},
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "http://evil.example"


# ─── Readiness probe (12f): /health/ready is 200 only when DB AND Redis are reachable ───

async def _async_true() -> bool:
    return True


async def _async_false() -> bool:
    return False


@pytest.mark.anyio
async def test_readiness_ok_when_both_dependencies_reachable(monkeypatch):
    monkeypatch.setattr(health_router, "_check_database", _async_true)
    monkeypatch.setattr(health_router, "_check_redis", lambda: True)
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": True, "redis": True}


@pytest.mark.anyio
async def test_readiness_503_when_redis_unreachable(monkeypatch):
    monkeypatch.setattr(health_router, "_check_database", _async_true)
    monkeypatch.setattr(health_router, "_check_redis", lambda: False)
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    # Routed through the Stage 12a error envelope (dict detail -> code lifted).
    assert body["error"]["code"] == "NOT_READY"
    assert body["detail"]["checks"] == {"database": True, "redis": False}


@pytest.mark.anyio
async def test_readiness_503_when_database_unreachable(monkeypatch):
    monkeypatch.setattr(health_router, "_check_database", _async_false)
    monkeypatch.setattr(health_router, "_check_redis", lambda: True)
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["database"] is False
