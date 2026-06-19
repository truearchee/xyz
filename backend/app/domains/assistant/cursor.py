"""Opaque keyset cursor for assistant message pagination (Stage 8.4, ADR-053).

A chat thread mutates under the reader (new turns append while older pages load on scroll), so the
messages endpoint paginates by the stable composite ``(created_at, id)`` rather than an offset that
shifts on every insert. The cursor is a URL-safe base64 of ``f"{created_at_iso}|{message_id}"`` — base64
only to keep it opaque (treat-as-token), NOT for security: it merely paginates a conversation the caller
has ALREADY passed the ownership + visibility gate on, so a forged cursor can at worst page the same
owned conversation oddly, never cross to another student. Malformed input is rejected with a 422 rather
than silently ignored (a silent fallback would mask a client bug as "no older messages").
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status


def encode_cursor(created_at: datetime, message_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{message_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), UUID(id_str)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_cursor"},
        ) from exc
