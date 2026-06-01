from __future__ import annotations

import pytest

from app.domains.transcripts.parsers import route_and_parse
from app.domains.transcripts.parsers.speaker import extract
from app.domains.transcripts.parsers.timestamps import parse, validate_range
from app.domains.transcripts.parsers.types import TranscriptParseError


def test_timestamp_parser_accepts_supported_formats() -> None:
    assert parse("00:01.250") == 1250
    assert parse("01:02:03.004") == 3_723_004


def test_timestamp_parser_rejects_malformed_negative_and_bad_ranges() -> None:
    for value in ["bad", "-00:01.000", "00:61.000", "00:00:99.000"]:
        with pytest.raises(TranscriptParseError):
            parse(value)
    with pytest.raises(TranscriptParseError):
        validate_range(1000, 1000)


def test_vtt_parser_extracts_voice_span_speaker_and_text() -> None:
    segments = route_and_parse(
        b"WEBVTT\n\n00:00.000 --> 00:01.000\n<v Dr Smith>Hello</v>\n"
    )

    assert len(segments) == 1
    assert segments[0].speaker_name == "Dr Smith"
    assert segments[0].text == "Hello"
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 1000


def test_vtt_parser_handles_zoom_prefix_multiline_blocks_bom_and_settings() -> None:
    raw = (
        "\ufeffWEBVTT - Zoom transcript\r\n\r\n"
        "NOTE ignored\r\n\r\n"
        "STYLE\r\n::cue { color: red; }\r\n\r\n"
        "REGION\r\nid:fred\r\n\r\n"
        "1\r\n"
        "00:00.000 --> 00:02.000 align:start\r\n"
        "Dr Smith: Hello\r\nworld\r\n\r\n"
        "2\r\n"
        "00:02.000 --> 00:03.000\r\n"
        "   \r\n"
    ).encode()

    segments = route_and_parse(raw, mime_type="text/plain")

    assert len(segments) == 1
    assert segments[0].speaker_name == "Dr Smith"
    assert segments[0].text == "Hello world"


def test_vtt_parser_fails_strict_utf8_decode() -> None:
    with pytest.raises(TranscriptParseError):
        route_and_parse(b"WEBVTT\n\n00:00.000 --> 00:01.000\n\xff\n")


def test_txt_parser_splits_paragraphs_and_lines_and_replaces_bad_bytes() -> None:
    paragraph_segments = route_and_parse(b"First paragraph\n\n\nSecond paragraph")
    line_segments = route_and_parse(b"One\nTwo")
    bad_byte_segments = route_and_parse(b"Plain \xff text")

    assert [segment.text for segment in paragraph_segments] == [
        "First paragraph",
        "Second paragraph",
    ]
    assert [segment.text for segment in line_segments] == ["One", "Two"]
    assert bad_byte_segments[0].text == "Plain \ufffd text"


def test_txt_parser_returns_zero_segments_for_whitespace() -> None:
    assert route_and_parse(b" \n\t\n") == []


def test_speaker_extraction_preserves_stoplisted_educational_labels() -> None:
    stoplisted = [
        "Definition",
        "Example",
        "Question",
        "Important",
        "Note",
        "Theorem",
        "Proof",
        "Lemma",
        "Corollary",
        "Remark",
        "Intuition",
        "Formula",
        "Algorithm",
        "Solution",
        "Case",
        "Observation",
    ]
    for label in stoplisted:
        payload = f"{label}: keep this as text"
        assert extract(payload) == (None, payload)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("<i>Definition:</i> A loss function...", (None, "<i>Definition:</i> A loss function...")),
        ("Definition: <i>A loss function</i>", (None, "Definition: <i>A loss function</i>")),
        ("<v Dr Smith><i>Hello</i></v>", ("Dr Smith", "<i>Hello</i>")),
        ("<v Dr Smith>Hello</v>", ("Dr Smith", "Hello")),
        ("<v Dr Smith><b>Hello</b> world", ("Dr Smith", "<b>Hello</b> world")),
        ("Example: <b>Suppose x = 2</b>", (None, "Example: <b>Suppose x = 2</b>")),
    ],
)
def test_speaker_extraction_preserves_payload_and_inner_voice_markup(
    payload: str, expected: tuple[str | None, str]
) -> None:
    assert extract(payload) == expected


def test_speaker_extraction_accepts_zoom_prefix_and_ignores_mid_sentence_colon() -> None:
    assert extract("Dr Smith: Let's begin") == ("Dr Smith", "Let's begin")
    payload = "Today we discuss loss: convex and non-convex"
    assert extract(payload) == (None, payload)
