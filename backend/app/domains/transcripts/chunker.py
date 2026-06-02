from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID


NORMALIZATION_VERSION = "norm-v1-structural"
CHUNKING_VERSION = "chunk-v1-no-overlap-180w"
TOKEN_COUNT_METHOD = "heuristic_word_count_v1"

TARGET_CHUNK_WORDS = 160
HARD_CHUNK_WORDS = 180

_TIMESTAMP_ARROW_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s+-->\s+.+$")
_CUE_INDEX_RE = re.compile(r"^\d+$")
_STRUCTURAL_LINES = {"WEBVTT", "NOTE", "STYLE", "REGION"}
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ChunkableSegment:
    id: UUID
    transcript_id: UUID
    sequence_number: int
    start_ms: int | None
    end_ms: int | None
    text: str


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    start_segment_id: UUID
    end_segment_id: UUID
    start_sequence_number: int
    end_sequence_number: int
    start_time: int | None
    end_time: int | None
    text: str
    token_count: int
    token_count_method: str
    normalization_version: str
    chunking_version: str
    is_oversized: bool


@dataclass(frozen=True)
class ChunkingResult:
    chunks: list[ChunkDraft]
    oversized_segment_count: int


@dataclass(frozen=True)
class _NormalizedSegment:
    source: ChunkableSegment
    text: str
    token_count: int


def normalize_segment_text(text: str) -> str:
    kept_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in _STRUCTURAL_LINES:
            continue
        if _CUE_INDEX_RE.fullmatch(line):
            continue
        if _TIMESTAMP_ARROW_RE.match(line):
            continue
        kept_lines.append(line)
    return _WHITESPACE_RE.sub(" ", " ".join(kept_lines)).strip()


def token_count(text: str) -> int:
    return len(text.split())


def chunk_segments(segments: list[ChunkableSegment]) -> ChunkingResult:
    normalized = _normalize_segments(segments)
    chunks: list[ChunkDraft] = []
    current: list[_NormalizedSegment] = []
    current_words = 0
    oversized_count = 0

    def flush_current() -> None:
        nonlocal current, current_words
        if not current:
            return
        chunks.append(_build_chunk(len(chunks), current, is_oversized=False))
        current = []
        current_words = 0

    for segment in normalized:
        if segment.token_count >= HARD_CHUNK_WORDS:
            flush_current()
            chunks.append(_build_chunk(len(chunks), [segment], is_oversized=True))
            oversized_count += 1
            continue

        if segment.token_count > TARGET_CHUNK_WORDS:
            flush_current()
            chunks.append(_build_chunk(len(chunks), [segment], is_oversized=False))
            continue

        if current and current_words + segment.token_count > TARGET_CHUNK_WORDS:
            flush_current()

        current.append(segment)
        current_words += segment.token_count

    flush_current()
    return ChunkingResult(chunks=chunks, oversized_segment_count=oversized_count)


def _normalize_segments(segments: list[ChunkableSegment]) -> list[_NormalizedSegment]:
    normalized: list[_NormalizedSegment] = []
    previous_text: str | None = None
    for segment in sorted(segments, key=lambda item: item.sequence_number):
        text = normalize_segment_text(segment.text)
        if not text or text == previous_text:
            continue
        previous_text = text
        normalized.append(
            _NormalizedSegment(
                source=segment,
                text=text,
                token_count=token_count(text),
            )
        )
    return normalized


def _build_chunk(
    chunk_index: int,
    segments: list[_NormalizedSegment],
    *,
    is_oversized: bool,
) -> ChunkDraft:
    first = segments[0].source
    last = segments[-1].source
    text = " ".join(segment.text for segment in segments)
    return ChunkDraft(
        chunk_index=chunk_index,
        start_segment_id=first.id,
        end_segment_id=last.id,
        start_sequence_number=first.sequence_number,
        end_sequence_number=last.sequence_number,
        start_time=first.start_ms,
        end_time=last.end_ms,
        text=text,
        token_count=sum(segment.token_count for segment in segments),
        token_count_method=TOKEN_COUNT_METHOD,
        normalization_version=NORMALIZATION_VERSION,
        chunking_version=CHUNKING_VERSION,
        is_oversized=is_oversized,
    )
