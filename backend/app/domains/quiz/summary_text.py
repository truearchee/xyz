"""Detailed-summary → prompt text + content hash (the pooled quiz generation source).

Kept in the quiz domain (no cross-domain import). ``summary_content_hash`` mirrors the canonical hashing
the Stage 5 post_class attempt uses for ``source_summary_content_hash`` (``generation_service.py``), so the
pool's STORED hash and the staleness RE-CHECK use the same function and always agree. The pool is built
from the detailed summary ONLY — never a raw transcript (Stage 6 exclusion).
"""

from __future__ import annotations

import hashlib
import json


def summary_content_hash(content_json: dict) -> str:
    """sha256 of the canonicalized detailed-summary ``content_json`` — the pool staleness signal."""
    canonical = json.dumps(content_json, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def summary_to_text(content_json: dict) -> str:
    """Flatten a stored detailed-summary ``content_json`` to plain prompt input text. The deterministic
    adapter ignores it; the real provider reads it."""
    cj = content_json or {}
    parts: list[str] = []
    overview = str(cj.get("overview", "")).strip()
    if overview:
        parts.append(overview)
    for label, key in (
        ("Key concepts", "keyConcepts"),
        ("Main explanations", "mainExplanations"),
        ("Examples", "examples"),
        ("Exam-relevant points", "examRelevantPoints"),
        ("Lab notes", "labNotes"),
    ):
        items = cj.get(key) or []
        if items:
            parts.append(label + ": " + "; ".join(str(i) for i in items))
    definitions = cj.get("importantDefinitions") or []
    if definitions:
        rendered = "; ".join(
            f"{d.get('term', '')}: {d.get('definition', '')}".strip(": ")
            for d in definitions
            if isinstance(d, dict)
        )
        if rendered:
            parts.append("Important definitions: " + rendered)
    return "\n".join(parts).strip()
