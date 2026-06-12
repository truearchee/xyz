"""Stage 4.8c (C1, adr-043) — internal SSE probe.

The codebase's first ``text/event-stream`` — deliberate: Stage 8.3 will be the first PRODUCT SSE, and
discovering a buffering proxy there is expensive. This probe de-risks the transport now. It is
registered ONLY when ``ENABLE_INTERNAL_SSE_PROBE=true`` (else the route does not exist → 404),
admin-only, and carries the anti-buffering headers a real SSE endpoint would. Hit from the staging
browser over the D1 direct transport (browser → FastAPI), it must stream chunks PROGRESSIVELY (not
buffered into one flush). §7.C2 constraints are the acceptance criteria: 3–5 chunks, < 10 s, no
compression, admin-auth, gated.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.platform.auth.context import CurrentUserContext
from app.platform.auth.guards import require_role

router = APIRouter()

_CHUNKS = 5                # §7.C2: 3–5 chunks
_INTERVAL_SECONDS = 1.0    # 5 chunks × ~1 s ≈ 5 s < 10 s (monkeypatched to 0 in tests)


async def _events() -> AsyncIterator[bytes]:
    for index in range(1, _CHUNKS + 1):
        yield f"data: probe chunk {index}/{_CHUNKS}\n\n".encode()
        if index < _CHUNKS:
            await asyncio.sleep(_INTERVAL_SECONDS)


@router.get("/internal/sse-probe")
async def sse_probe(
    _current_user: Annotated[CurrentUserContext, Depends(require_role("admin"))],
) -> StreamingResponse:
    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # the point: defeat proxy buffering on the event-stream
        },
    )
