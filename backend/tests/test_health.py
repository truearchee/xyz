from httpx import AsyncClient
import pytest

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
