"""Highlight containment normalizer (Stage 8.5) — pure → unit-tested directly.

Anti-spoofing for conversation-sourced saves: the server must confirm the student's ``selectedText``
actually occurs in the referenced assistant message before recording "the assistant said this." The
browser's text-selection API returns the *rendered* text (markdown already stripped), while the message
is stored as raw markdown — so we normalize BOTH sides the same conservative way and test containment.

Deliberately conservative: it strips only the handful of inline emphasis/code markers a highlight commonly
straddles (``** __ * _`` and backticks), then collapses whitespace and case-folds. It does NOT attempt to
parse links/lists/headings — over-stripping would risk masking a spoof, and under-matching a legitimate
highlight only yields a clean 422 (the student can still add the term manually). The threat model is FALSE
SOURCE ATTRIBUTION, not arbitrary terms (manual add already allows those).
"""

from __future__ import annotations

_INLINE_MARKERS = ("**", "__", "`", "*", "_")


def normalize_for_containment(s: str) -> str:
    out = s or ""
    for marker in _INLINE_MARKERS:
        out = out.replace(marker, "")
    return " ".join(out.split()).casefold()


def selected_text_in_message(selected_text: str, message_content: str | None) -> bool:
    """True iff the (normalized) highlighted text occurs in the (normalized) message content."""
    needle = normalize_for_containment(selected_text)
    if not needle:
        return False
    return needle in normalize_for_containment(message_content or "")
