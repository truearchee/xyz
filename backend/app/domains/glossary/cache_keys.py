"""Glossary cache / provenance key derivation (Stage 7a). Pure → unit-tested directly.

Hashing mirrors ``summary_service._summary_input_hash`` (canonical JSON → sha256 hexdigest).
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from app.domains.glossary.normalize import NORMALIZE_VERSION


def definition_cache_key(
    *, normalized_term: str, subject_id: UUID, entry_type: str, language: str
) -> str:
    """The shared-across-students cache key. Language-AWARE (a term has a distinct definition per
    language). A cache hit on ``(cache_key, prompt_version)`` = no model call."""
    payload = {
        "normalizeVersion": NORMALIZE_VERSION,
        "normalizedTerm": normalized_term,
        "subjectId": str(subject_id),
        "entryType": entry_type,
        "language": language,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def definition_input_hash(*, cache_key: str, prompt_version: str, context_text: str) -> str:
    """The ``input_content_hash`` recorded on the AIRequestLog + entry + cache (provenance). The
    ``cache_key`` already folds in normalizeVersion + term + subject + entryType + language; this adds
    the prompt version and the (capped) context that actually went into the prompt."""
    payload = {
        "cacheKey": cache_key,
        "promptVersion": prompt_version,
        "contextText": context_text,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
