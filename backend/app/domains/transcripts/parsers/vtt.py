from __future__ import annotations

from io import StringIO

import webvtt

from . import speaker, timestamps
from app.domains.transcripts.parsers.types import ParsedSegment, TranscriptParseError


def parse(raw: bytes) -> list[ParsedSegment]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TranscriptParseError("invalid VTT encoding") from exc

    try:
        captions = webvtt.from_buffer(StringIO(text))
    except Exception as exc:
        raise TranscriptParseError("invalid VTT content") from exc

    segments: list[ParsedSegment] = []
    for caption in captions:
        start_ms = timestamps.parse(caption.start)
        end_ms = timestamps.parse(caption.end)
        timestamps.validate_range(start_ms, end_ms)

        raw_text = getattr(caption, "raw_text", None) or caption.text
        payload = " ".join(line.strip() for line in raw_text.splitlines() if line.strip())
        speaker_name, clean_text = speaker.extract(payload)
        if not clean_text:
            continue
        segments.append(
            ParsedSegment(
                text=clean_text,
                start_ms=start_ms,
                end_ms=end_ms,
                speaker_name=speaker_name,
            )
        )
    return segments
