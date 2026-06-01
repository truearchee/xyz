from __future__ import annotations

from app.domains.transcripts.parsers.types import ParsedSegment

from . import txt, vtt


def route_and_parse(raw: bytes, *, mime_type: str | None = None) -> list[ParsedSegment]:
    if _sniffs_as_vtt(raw):
        return vtt.parse(raw)
    return txt.parse(raw)


def _sniffs_as_vtt(raw: bytes) -> bool:
    sniff_text = raw.decode("utf-8-sig", errors="replace")
    first_line = next((line.strip() for line in sniff_text.splitlines() if line.strip()), "")
    return first_line == "WEBVTT" or first_line.startswith("WEBVTT ")
