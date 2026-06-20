"""Stage 8.5 — the highlight containment normalizer (anti-spoofing primitive). Pure unit tests.

Direct coverage of ``snippet.py`` (previously only exercised indirectly through the save path). Documents
the deliberately-conservative ADR-055 tradeoff: the normalizer strips inline emphasis/code markers and
collapses whitespace, so it over-matches an intraword underscore and under-matches a selection spanning
list markers — both accepted because entries are personal-scoped, the term/selectedText containment gate
bounds the blast radius, and an under-match only yields a clean 422 (manual add remains the fallback).
"""

from __future__ import annotations

from app.domains.glossary.snippet import normalize_for_containment, selected_text_in_message


def test_normalize_strips_inline_markers_and_collapses_whitespace() -> None:
    assert normalize_for_containment("**Mito**chondria") == "mitochondria"
    assert normalize_for_containment("  a   b\tc \n") == "a b c"
    assert normalize_for_containment("`code`") == "code"
    assert normalize_for_containment("") == ""
    assert normalize_for_containment("   ") == ""


def test_containment_matches_across_markdown_emphasis_and_case() -> None:
    assert selected_text_in_message("mitochondria", "The **mitochondria** is the powerhouse.") is True
    assert selected_text_in_message("Mitochondria", "the mitochondria") is True  # casefold


def test_containment_rejects_absent_text_blank_needle_and_none_message() -> None:
    assert selected_text_in_message("not in here", "The mitochondria is the powerhouse.") is False
    assert selected_text_in_message("", "anything") is False
    assert selected_text_in_message("   ", "anything") is False
    assert selected_text_in_message("x", None) is False  # pending message → no content


def test_known_conservative_tradeoffs_are_documented() -> None:
    # ADR-055 accepted boundaries — pinned so a future normalizer change is a conscious decision.
    assert selected_text_in_message("foobar", "foo_bar") is True  # over-match (intraword underscore)
    assert selected_text_in_message("apple banana", "- apple\n- banana") is False  # under-match (list)
