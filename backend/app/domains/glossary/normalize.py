"""Deterministic term normalization (Stage 7a).

``normalized_term`` is the dedup/cache-key component. It is a PURE string transform — NFKC → casefold
→ trim → collapse internal whitespace — with NO AI call (spec: no second model call at save; there is
no "canonical English" generation). Versioned so a future transform change is detectable.
"""

from __future__ import annotations

import unicodedata

NORMALIZE_VERSION = "v1"


def normalize_term(raw: str) -> str:
    nfkc = unicodedata.normalize("NFKC", raw)
    folded = nfkc.casefold().strip()
    # collapse any run of internal whitespace to a single space
    return " ".join(folded.split())
