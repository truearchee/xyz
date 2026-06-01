from __future__ import annotations

import re

from app.domains.transcripts.parsers.types import TranscriptParseError


_TIMESTAMP_RE = re.compile(
    r"^(?:(?P<hours>\d{2,}):)?(?P<minutes>\d{2}):(?P<seconds>\d{2})\.(?P<millis>\d{3})$"
)


def parse(timestamp: str) -> int:
    if timestamp.startswith("-"):
        raise TranscriptParseError("invalid timestamp")
    match = _TIMESTAMP_RE.match(timestamp.strip())
    if match is None:
        raise TranscriptParseError("invalid timestamp")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis = int(match.group("millis"))
    if minutes >= 60 or seconds >= 60:
        raise TranscriptParseError("invalid timestamp")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def validate_range(start_ms: int | None, end_ms: int | None) -> None:
    if (start_ms is None) != (end_ms is None):
        raise TranscriptParseError("invalid timestamp range")
    if start_ms is not None and end_ms is not None and end_ms <= start_ms:
        raise TranscriptParseError("invalid timestamp range")
