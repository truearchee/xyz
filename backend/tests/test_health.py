from httpx import AsyncClient
import pytest

from app.main import app


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
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.anyio
async def test_health_cors_preflight():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
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
