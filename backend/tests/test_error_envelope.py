"""Stage 12a — global error envelope + request-id middleware.

Exercises the real `create_app()` wiring (middleware + the three exception handlers) through a
fresh app instance with a few throwaway routes. No DB is required, so this module runs even
without `TEST_DATABASE_URL`. `raise_app_exceptions=False` lets the ASGI transport return the
500 response that `ServerErrorMiddleware` produces (it re-raises after sending).
"""

from collections.abc import AsyncIterator

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
import pytest

from app.main import create_app


def _build_app():
    app = create_app()

    @app.get("/__test__/ok")
    async def _ok() -> dict:
        return {"ok": True}

    @app.get("/__test__/boom")
    async def _boom() -> dict:
        raise RuntimeError("boom secret detail string")

    @app.get("/__test__/coded")
    async def _coded() -> dict:
        raise HTTPException(status_code=403, detail="CONTENT_FORBIDDEN")

    @app.get("/__test__/dict-detail")
    async def _dict_detail() -> dict:
        raise HTTPException(status_code=409, detail={"code": "not_failed", "extra": 1})

    @app.get("/__test__/needs-param")
    async def _needs_param(n: int) -> dict:
        return {"n": n}

    return app


@pytest.fixture
async def envelope_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.anyio
async def test_forced_500_returns_clean_envelope_without_leaking(envelope_client: AsyncClient) -> None:
    response = await envelope_client.get("/__test__/boom")

    assert response.status_code == 500
    body = response.json()
    # Exactly the clean envelope — no `detail`, no internal fields.
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Internal server error"
    request_id = body["error"]["request_id"]
    assert request_id
    assert response.headers["X-Request-ID"] == request_id
    # No stack trace or internal exception text leaks to the client.
    raw = response.text
    assert "boom secret" not in raw
    assert "Traceback" not in raw
    assert "RuntimeError" not in raw


@pytest.mark.anyio
async def test_http_exception_envelope_is_additive(envelope_client: AsyncClient) -> None:
    response = await envelope_client.get("/__test__/coded")

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "CONTENT_FORBIDDEN"
    assert body["error"]["message"] == "CONTENT_FORBIDDEN"
    assert body["error"]["request_id"]
    # Additive: the legacy `detail` field is preserved verbatim.
    assert body["detail"] == "CONTENT_FORBIDDEN"
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]


@pytest.mark.anyio
async def test_http_exception_dict_detail_preserved_and_code_lifted(
    envelope_client: AsyncClient,
) -> None:
    response = await envelope_client.get("/__test__/dict-detail")

    assert response.status_code == 409
    body = response.json()
    # Structured dict detail (the assistant convention) is preserved verbatim for FE readers.
    assert body["detail"] == {"code": "not_failed", "extra": 1}
    # The envelope lifts the dict's `code` into error.code.
    assert body["error"]["code"] == "not_failed"


@pytest.mark.anyio
async def test_validation_error_keeps_detail_array_and_adds_envelope(
    envelope_client: AsyncClient,
) -> None:
    response = await envelope_client.get("/__test__/needs-param")  # missing required ?n=

    assert response.status_code == 422
    body = response.json()
    # Standard 422 array shape preserved (frontend validation parsers read `detail` as a list).
    assert isinstance(body["detail"], list)
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert response.headers["X-Request-ID"] == body["error"]["request_id"]


@pytest.mark.anyio
async def test_request_id_echoed_when_client_provides_one(envelope_client: AsyncClient) -> None:
    response = await envelope_client.get(
        "/__test__/ok", headers={"X-Request-ID": "fixed-correlation-id-123"}
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "fixed-correlation-id-123"


@pytest.mark.anyio
@pytest.mark.parametrize("bad_id", ["has spaces", "x" * 200, "semi;colon", "at@sign", "slash/path"])
async def test_malformed_incoming_request_id_is_replaced_not_reflected(
    envelope_client: AsyncClient, bad_id: str
) -> None:
    # A client-controlled X-Request-ID is only honoured if it matches the bounded token pattern; a value
    # with spaces / oversize / unsafe chars must be replaced by a generated id, never reflected verbatim.
    response = await envelope_client.get("/__test__/ok", headers={"X-Request-ID": bad_id})

    assert response.status_code == 200
    echoed = response.headers.get("X-Request-ID", "")
    assert echoed
    assert echoed != bad_id


@pytest.mark.anyio
async def test_request_id_generated_and_present_on_success(envelope_client: AsyncClient) -> None:
    response = await envelope_client.get("/__test__/ok")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


@pytest.mark.anyio
async def test_request_id_header_present_on_real_health_route(envelope_client: AsyncClient) -> None:
    # Confirms the middleware wraps real application routes, not just the test routes.
    response = await envelope_client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


@pytest.mark.anyio
async def test_forced_500_carries_cors_headers_for_allowed_origin(monkeypatch) -> None:
    # The catch-all 500 handler runs inside Starlette's outermost ServerErrorMiddleware, so it bypasses
    # CORSMiddleware. 12f re-attaches CORS headers explicitly so a cross-origin SPA can still read the
    # 5xx envelope / request_id. Allowed origin → echoed; foreign origin → not granted.
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.get(
            "/__test__/boom", headers={"Origin": "http://localhost:3001"}
        )
        assert allowed.status_code == 500
        assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3001"
        assert "origin" in allowed.headers.get("vary", "").lower()

        foreign = await client.get(
            "/__test__/boom", headers={"Origin": "http://evil.example"}
        )
        assert foreign.status_code == 500
        assert "access-control-allow-origin" not in foreign.headers
