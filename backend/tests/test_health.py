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
