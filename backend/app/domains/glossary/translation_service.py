"""TranslationService — the language-aware definition-generation path (Stage 7a).

This IS the roadmap-required ``TranslationService`` abstraction: given a term + context + target
language it returns a localized definition. The one concrete impl (``GatewayTranslationService``) is a
thin adapter over the EXISTING ``LLMGateway`` — it builds the localized prompt input (the language is
baked into the input text, decision B1, so no ``platform/llm`` renderer change is needed), calls the
gateway at BACKGROUND priority with the reused ``BriefSummary`` output schema (decision D3), and runs
the language soft-check. A future provider (e.g. a dedicated translation API) is a new class
implementing the same Protocol; callers do not change. The gateway stays the single LLM orchestration
point — this is an adapter, never a second gateway.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domains.glossary.cache_keys import definition_input_hash
from app.domains.glossary.specs import (
    CONTEXT_CHAR_CAP,
    GLOSSARY_DEFINITION_PROMPT_KEY,
    GLOSSARY_DEFINITION_PROMPT_VERSION,
    GLOSSARY_FEATURE,
    LANGUAGE_LABELS,
)
from app.platform.llm.gateway import ContextRefs, LLMGateway
from app.platform.llm.models.summary import BriefSummary

logger = logging.getLogger(__name__)

# Cheap script-presence heuristics for the language soft-check (D3). Only non-Latin scripts get a
# heuristic — Latin-script languages (en/es/fr) share an alphabet, so a heuristic would be noise.
_SCRIPT_RANGES = {
    "ar": ("؀", "ۿ"),
    "zh": ("一", "鿿"),
}


@dataclass(frozen=True)
class TranslationResult:
    short_definition: str
    ai_request_log_id: UUID
    source_content_hash: str


def _build_input_text(
    *, term: str, subject_label: str, entry_type: str, language: str, context_text: str
) -> str:
    label = LANGUAGE_LABELS.get(language, "English")
    context = (context_text or "").strip()[:CONTEXT_CHAR_CAP]
    lines = [
        f"Target language: {label}. Write the definition ENTIRELY in {label}.",
        f'Course / subject: "{subject_label}".',
        f"Entry type: {entry_type}.",
        f"Term: {term}",
    ]
    if context:
        lines.append(f"Context from the lecture: {context}")
    return "\n".join(lines)


def _looks_like_target_language(text: str, language: str) -> bool:
    bounds = _SCRIPT_RANGES.get(language)
    if bounds is None:
        return True  # no heuristic for Latin-script languages — never warn
    low, high = bounds
    return any(low <= ch <= high for ch in text)


class TranslationService(Protocol):
    async def translate(
        self,
        *,
        term: str,
        subject_label: str,
        entry_type: str,
        language: str,
        context_text: str,
        cache_key: str,
    ) -> TranslationResult: ...


class GatewayTranslationService:
    """The Stage-7 concrete impl — a thin adapter over the existing LLMGateway."""

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def translate(
        self,
        *,
        term: str,
        subject_label: str,
        entry_type: str,
        language: str,
        context_text: str,
        cache_key: str,
    ) -> TranslationResult:
        input_text = _build_input_text(
            term=term,
            subject_label=subject_label,
            entry_type=entry_type,
            language=language,
            context_text=context_text,
        )
        input_hash = definition_input_hash(
            cache_key=cache_key,
            prompt_version=GLOSSARY_DEFINITION_PROMPT_VERSION,
            context_text=(context_text or "").strip()[:CONTEXT_CHAR_CAP],
        )
        result = await self._gateway.complete(
            prompt_key=GLOSSARY_DEFINITION_PROMPT_KEY,
            output_schema=BriefSummary,
            context_refs=ContextRefs(
                ingestion_job_id=None,  # glossary has no IngestionJob (mirrors quiz, 0020)
                transcript_text=input_text,
                input_content_hash=input_hash,
                section_type=entry_type,
            ),
            priority="background",  # interactive headroom stays reserved for Stage 8 (rule 15)
            feature=GLOSSARY_FEATURE,
            attempt_number=1,
        )
        parsed: BriefSummary = result["parsed"]
        definition = parsed.text.strip()
        # Language soft-check (D3): LOG a mismatch, NEVER reject — bilingual technical definitions
        # (e.g. a Chinese definition full of Latin-script formulae) trip naive detectors; rejecting
        # would cause spurious retries (rule-15 waste) and stuck 'generating' states.
        if not _looks_like_target_language(definition, language):
            logger.warning(
                "glossary definition language mismatch",
                extra={"language": language, "cacheKey": cache_key},
            )
        return TranslationResult(
            short_definition=definition,
            ai_request_log_id=result["ai_request_log_id"],
            source_content_hash=input_hash,
        )
