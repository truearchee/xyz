from __future__ import annotations

import re

from app.domains.transcripts.parsers.types import ParsedSegment


def parse(raw: bytes) -> list[ParsedSegment]:
    text = raw.decode("utf-8-sig", errors="replace")
    if re.search(r"\n\s*\n", text):
        candidates = re.split(r"\n\s*\n+", text)
    else:
        candidates = text.splitlines()
    return [
        ParsedSegment(text=candidate.strip())
        for candidate in candidates
        if candidate.strip()
    ]
