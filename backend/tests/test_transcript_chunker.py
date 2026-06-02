from __future__ import annotations

from uuid import UUID, uuid4

from app.domains.transcripts.chunker import (
    CHUNKING_VERSION,
    HARD_CHUNK_WORDS,
    NORMALIZATION_VERSION,
    TARGET_CHUNK_WORDS,
    TOKEN_COUNT_METHOD,
    ChunkableSegment,
    chunk_segments,
    normalize_segment_text,
    token_count,
)


def _segment(
    sequence_number: int,
    text: str,
    *,
    transcript_id: UUID | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> ChunkableSegment:
    return ChunkableSegment(
        id=uuid4(),
        transcript_id=transcript_id or uuid4(),
        sequence_number=sequence_number,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
    )


def _words(count: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(count))


def test_normalizer_is_structural_and_idempotent() -> None:
    raw = "WEBVTT\n\n1\n00:00.000 --> 00:01.000 align:start\n Hello\t world \n"
    normalized = normalize_segment_text(raw)

    assert normalized == "Hello world"
    assert normalize_segment_text(normalized) == normalized
    assert token_count(normalized) == 2


def test_chunker_accumulates_contiguous_segments_to_target() -> None:
    transcript_id = uuid4()
    segments = [
        _segment(0, _words(80), transcript_id=transcript_id, start_ms=0, end_ms=1000),
        _segment(1, _words(80, "x"), transcript_id=transcript_id, start_ms=1000, end_ms=2000),
        _segment(2, _words(1), transcript_id=transcript_id, start_ms=2000, end_ms=3000),
    ]

    result = chunk_segments(segments)

    assert len(result.chunks) == 2
    assert result.chunks[0].token_count == TARGET_CHUNK_WORDS
    assert result.chunks[0].start_segment_id == segments[0].id
    assert result.chunks[0].end_segment_id == segments[1].id
    assert result.chunks[0].start_time == 0
    assert result.chunks[0].end_time == 2000
    assert result.chunks[1].chunk_index == 1
    assert result.oversized_segment_count == 0


def test_medium_large_segment_is_normal_singleton() -> None:
    segment = _segment(0, _words(TARGET_CHUNK_WORDS + 5))

    result = chunk_segments([segment])

    assert len(result.chunks) == 1
    assert result.chunks[0].token_count == TARGET_CHUNK_WORDS + 5
    assert result.chunks[0].is_oversized is False
    assert result.oversized_segment_count == 0


def test_oversized_segment_is_oversized_singleton() -> None:
    segment = _segment(0, _words(HARD_CHUNK_WORDS))

    result = chunk_segments([segment])

    assert len(result.chunks) == 1
    assert result.chunks[0].token_count == HARD_CHUNK_WORDS
    assert result.chunks[0].is_oversized is True
    assert result.oversized_segment_count == 1


def test_empty_and_adjacent_duplicate_segments_are_skipped_without_mutating_text() -> None:
    original_text = "  Same text  "
    segments = [
        _segment(0, "WEBVTT"),
        _segment(1, original_text),
        _segment(2, "Same text"),
        _segment(3, "Next text", start_ms=None, end_ms=None),
    ]

    result = chunk_segments(segments)

    assert [chunk.text for chunk in result.chunks] == ["Same text Next text"]
    assert segments[1].text == original_text
    assert result.chunks[0].start_segment_id == segments[1].id
    assert result.chunks[0].end_segment_id == segments[3].id
    assert result.chunks[0].start_time is None
    assert result.chunks[0].end_time is None


def test_zero_usable_segments_produces_no_chunks() -> None:
    result = chunk_segments([_segment(0, "WEBVTT\n\n1\n00:00.000 --> 00:01.000")])

    assert result.chunks == []
    assert result.oversized_segment_count == 0


def test_chunk_metadata_versions_and_method_are_recorded() -> None:
    result = chunk_segments([_segment(0, "hello world")])
    chunk = result.chunks[0]

    assert chunk.token_count_method == TOKEN_COUNT_METHOD
    assert chunk.normalization_version == NORMALIZATION_VERSION
    assert chunk.chunking_version == CHUNKING_VERSION
