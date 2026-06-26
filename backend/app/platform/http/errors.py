"""Stage 12a — global exception handlers + consistent error envelope.

Every error response carries a uniform ``{"error": {"code", "message", "request_id"}}`` object.
The change is ADDITIVE (decision D2 / ADR-061): the legacy ``detail`` field is preserved alongside
the new ``error`` object so existing frontend readers and tests keep working; new or changed code
should read ``error``, never ``detail``. The catch-all 500 handler never leaks a stack trace or
internal exception text.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.platform.config import settings
from app.platform.http.request_id import REQUEST_ID_HEADER, get_request_id
from app.platform.http.security_headers import apply_security_headers

logger = logging.getLogger(__name__)

INTERNAL_ERROR_CODE = "INTERNAL_ERROR"
VALIDATION_ERROR_CODE = "VALIDATION_ERROR"


def _code_and_message(detail: Any, status_code: int) -> tuple[str, str]:
    """Derive the envelope ``code``/``message`` from an HTTPException ``detail``.

    Domain code strings (``CONTENT_FORBIDDEN``, ``SECTION_NOT_FOUND``, …) are carried verbatim as
    the code. The assistant raises structured ``detail={"code": ...}`` dicts — lift their ``code``.
    Anything else (framework defaults, lists) falls back to a generic ``HTTP_<status>`` code.
    """
    if isinstance(detail, str) and detail:
        return detail, detail
    if isinstance(detail, dict):
        code = detail.get("code")
        if isinstance(code, str) and code:
            message = detail.get("message")
            return code, message if isinstance(message, str) and message else code
    return f"HTTP_{status_code}", "Request failed"


def _error_object(code: str, message: str, request_id: str) -> dict[str, str]:
    return {"code": code, "message": message, "request_id": request_id}


def _apply_cors_headers(request: Request, response: JSONResponse) -> None:
    """Attach CORS headers to a 5xx response that bypasses ``CORSMiddleware`` (12f).

    The catch-all 500 handler runs inside Starlette's outermost ``ServerErrorMiddleware``, so its
    response never passes back out through ``CORSMiddleware`` — a cross-origin SPA would be unable to
    read the error envelope / ``request_id``. Echo the request ``Origin`` (only when it is an allowed
    origin) exactly as ``CORSMiddleware`` would. ``allow_credentials`` is False (pure Bearer auth), so
    no ``Access-Control-Allow-Credentials`` header is emitted. 4xx/422 already receive CORS headers via
    the inner ``ExceptionMiddleware`` path, so this is applied to the 500 handler only.
    """
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") in settings.CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    request_id = get_request_id(request)
    code, message = _code_and_message(exc.detail, exc.status_code)
    headers = dict(exc.headers or {})
    headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,  # additive: preserve the legacy field verbatim
            "error": _error_object(code, message, request_id),
        },
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = get_request_id(request)
    return JSONResponse(
        status_code=422,
        content={
            # Preserve FastAPI's standard 422 array shape (frontend validation parsers read it).
            "detail": jsonable_encoder(exc.errors()),
            "error": _error_object(
                VALIDATION_ERROR_CODE, "Request validation failed", request_id
            ),
        },
        headers={REQUEST_ID_HEADER: request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id(request)
    logger.exception("Unhandled request error", extra={"request_id": request_id})
    # No stack trace, no str(exc): never leak internal detail to the client.
    response = JSONResponse(
        status_code=500,
        content={
            "error": _error_object(INTERNAL_ERROR_CODE, "Internal server error", request_id)
        },
        headers={REQUEST_ID_HEADER: request_id},
    )
    # This handler runs outside CORSMiddleware (12f); re-attach CORS headers so cross-origin
    # SPAs can read the 5xx envelope.
    _apply_cors_headers(request, response)
    apply_security_headers(response.headers)
    return response
