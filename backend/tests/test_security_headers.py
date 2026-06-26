from httpx import AsyncClient
import pytest

from app.main import app


@pytest.mark.anyio
async def test_baseline_security_headers_present():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.anyio
async def test_hsts_absent_in_dev_present_in_prod(monkeypatch):
    # HSTS is meaningless over local plain HTTP, so dev/E2E never send it.
    async with AsyncClient(app=app, base_url="http://test") as client:
        dev_response = await client.get("/health")
    assert "strict-transport-security" not in dev_response.headers

    monkeypatch.setenv("ENVIRONMENT", "production")
    async with AsyncClient(app=app, base_url="http://test") as client:
        prod_response = await client.get("/health")
    assert "strict-transport-security" in prod_response.headers
