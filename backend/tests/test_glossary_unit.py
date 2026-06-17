"""Stage 7a — pure glossary unit tests (no DB): normalization + key derivation."""

from __future__ import annotations

from uuid import uuid4

from app.domains.glossary.cache_keys import definition_cache_key, definition_input_hash
from app.domains.glossary.normalize import NORMALIZE_VERSION, normalize_term


def test_normalize_collapses_case_and_whitespace():
    assert normalize_term("  Mitochondria  ") == "mitochondria"
    assert normalize_term("Krebs   Cycle") == "krebs cycle"
    assert normalize_term("ATP\tSynthase\n") == "atp synthase"


def test_normalize_is_unicode_nfkc_and_casefold():
    # Fullwidth letters NFKC-fold to ASCII; ẞ casefolds to ss.
    assert normalize_term("ＡＴＰ") == "atp"
    assert normalize_term("STRAẞE") == "strasse"


def test_normalize_version_pinned():
    assert NORMALIZE_VERSION == "v1"


def test_cache_key_is_deterministic_and_axis_sensitive():
    subject = uuid4()
    base = definition_cache_key(
        normalized_term="mitochondria", subject_id=subject, entry_type="term", language="en"
    )
    assert base == definition_cache_key(
        normalized_term="mitochondria", subject_id=subject, entry_type="term", language="en"
    )
    # Every axis changes the key.
    assert base != definition_cache_key(
        normalized_term="mitochondria", subject_id=subject, entry_type="term", language="ar"
    )
    assert base != definition_cache_key(
        normalized_term="mitochondria", subject_id=subject, entry_type="concept", language="en"
    )
    assert base != definition_cache_key(
        normalized_term="mitochondria", subject_id=uuid4(), entry_type="term", language="en"
    )
    assert base != definition_cache_key(
        normalized_term="nucleus", subject_id=subject, entry_type="term", language="en"
    )


def test_input_hash_is_deterministic_and_context_sensitive():
    a = definition_input_hash(cache_key="k", prompt_version="v1", context_text="ctx")
    assert a == definition_input_hash(cache_key="k", prompt_version="v1", context_text="ctx")
    assert a != definition_input_hash(cache_key="k", prompt_version="v1", context_text="other")
    assert a != definition_input_hash(cache_key="k", prompt_version="v2", context_text="ctx")
