from __future__ import annotations

import re


STOPLIST = {
    "definition",
    "example",
    "note",
    "question",
    "answer",
    "important",
    "summary",
    "objective",
    "recall",
    "exercise",
    "task",
    "step",
    "warning",
    "hint",
    "theorem",
    "proof",
    "lemma",
    "corollary",
    "remark",
    "intuition",
    "formula",
    "algorithm",
    "solution",
    "case",
    "observation",
}

_VOICE_SPAN_RE = re.compile(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$", re.DOTALL)
_PREFIX_RE = re.compile(r"^([A-Z][A-Za-z .'\-]{0,39}):\s+(.*)$", re.DOTALL)


def extract(payload: str) -> tuple[str | None, str]:
    voice_match = _VOICE_SPAN_RE.match(payload)
    if voice_match is not None:
        speaker_name = voice_match.group(1).strip()
        if speaker_name:
            return speaker_name, voice_match.group(2)

    prefix_match = _PREFIX_RE.match(payload)
    if prefix_match is not None:
        candidate = prefix_match.group(1).strip()
        if candidate.lower() not in STOPLIST and _looks_like_speaker_name(candidate):
            return candidate, prefix_match.group(2)

    return None, payload


def _looks_like_speaker_name(candidate: str) -> bool:
    words = [word for word in re.split(r"\s+", candidate) if word]
    return all(not word[0].isalpha() or word[0].isupper() for word in words)
