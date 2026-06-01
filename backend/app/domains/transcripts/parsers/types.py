from __future__ import annotations

from dataclasses import dataclass


class TranscriptParseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParsedSegment:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    speaker_name: str | None = None
