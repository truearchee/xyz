"""Stage 12a — per-request correlation id.

A pure-ASGI middleware (deliberately NOT ``BaseHTTPMiddleware``) so the id lives on the ASGI
``scope["state"]`` and is therefore visible to every downstream handler AND to the exception
handlers — including the catch-all 500 handler, which runs in Starlette's ``ServerErrorMiddleware``
*outside* the user-middleware stack and so cannot rely on this middleware's response
post-processing for its header. The middleware echoes ``X-Request-ID`` on every response it wraps
(2xx + handled errors); the 500 handler sets the header itself from the shared scope id.
"""

from __future__ import annotations

import re

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uuid6 import uuid7

REQUEST_ID_HEADER = "X-Request-ID"
_STATE_KEY = "request_id"
# An incoming X-Request-ID is client-controlled; only honour a conservative, bounded token (so a caller
# can't reflect CRLF/header-splitting bytes, oversized values, or a forged log-correlation id). Otherwise
# generate a fresh id.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _new_request_id() -> str:
    return str(uuid7())


class RequestIdMiddleware:
    """Assign every HTTP request a correlation id and echo it on the response header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        candidate = incoming.strip() if incoming else ""
        request_id = candidate if _VALID_REQUEST_ID.match(candidate) else _new_request_id()

        # Backs `request.state.request_id` for handlers and exception handlers.
        scope.setdefault("state", {})[_STATE_KEY] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def get_request_id(request) -> str:
    """Read the correlation id from the request scope, generating one if absent.

    Exception handlers call this; the generate-on-miss fallback keeps them robust on any path
    where the middleware did not run (e.g. a failure raised before it executes)."""
    state = request.scope.get("state")
    if isinstance(state, dict):
        request_id = state.get(_STATE_KEY)
        if isinstance(request_id, str) and request_id:
            return request_id
    request_id = _new_request_id()
    request.scope.setdefault("state", {})[_STATE_KEY] = request_id
    return request_id
