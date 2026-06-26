"""Stage 12f — baseline security response headers.

A pure-ASGI middleware (like ``request_id.py``, deliberately NOT ``BaseHTTPMiddleware``) that stamps a
conservative set of security headers on every HTTP response. ``setdefault`` is used so a route that
already set a header (e.g. the asset-download ``X-Content-Type-Options: nosniff``) is never clobbered.

HSTS is emitted ONLY outside dev (``not settings.IS_NON_PROD`` → production/staging). It is meaningless
over plain-HTTP localhost and pinning it there would wedge a developer's browser onto HTTPS, so the dev
and E2E stacks never send it. The frontend sets its own CSP/HSTS via ``next.config.ts`` (12f Commit 4);
these backend headers are defense-in-depth for the JSON API + file-download responses.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.config import settings

_STATIC_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
_HSTS_NAME = "Strict-Transport-Security"
_HSTS_VALUE = "max-age=63072000; includeSubDomains"


def apply_security_headers(headers: MutableHeaders) -> None:
    """Apply the baseline security headers to a mutable response header mapping."""
    for name, value in _STATIC_SECURITY_HEADERS.items():
        headers.setdefault(name, value)
    if not settings.IS_NON_PROD:
        headers.setdefault(_HSTS_NAME, _HSTS_VALUE)


class SecurityHeadersMiddleware:
    """Add baseline security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                apply_security_headers(MutableHeaders(scope=message))
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
