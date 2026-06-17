"""Glossary domain constants (Stage 7). Pure data, no I/O."""

from __future__ import annotations

from app.platform.llm.models.prompt import PromptKey

# Definition generation goes through the EXISTING gateway/queue/limiter (no new AI infra).
GLOSSARY_DEFINITION_PROMPT_KEY = PromptKey("glossary_definition", "v1")
GLOSSARY_DEFINITION_PROMPT_VERSION = GLOSSARY_DEFINITION_PROMPT_KEY.version
GLOSSARY_FEATURE = "glossary_definition"

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "ar", "zh", "es", "fr")
LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "ar": "Arabic",
    "zh": "Chinese",
    "es": "Spanish",
    "fr": "French",
}
ENTRY_TYPES: tuple[str, ...] = ("term", "concept", "formula")
DEFAULT_ENTRY_TYPE = "term"

# Server-side context cap (spec).
CONTEXT_CHAR_CAP = 500

# RTL languages — the frontend sets dir="rtl"; kept here for any server-side use.
RTL_LANGUAGES: frozenset[str] = frozenset({"ar"})
