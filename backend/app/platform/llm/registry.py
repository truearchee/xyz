"""PromptRegistry — flat-file prompt store (adr-026).

Loads and validates a versioned `prompts/` directory at startup; a malformed or missing file is a
boot failure. Each prompt is a YAML file with `name`, `version`, `content`, `max_tokens`, `model`,
`backend`, and optional `reasoning_level`. The registry computes a content hash per file (stored as
`promptContentHash` on every AIRequestLog / GeneratedLectureSummary row) so the CI drift guard can
detect content changes that skipped a version bump.

Prompts live at ``backend/prompts/`` (resolved via ``parents[3]``) rather than the spec's repo-root
``prompts/`` because the backend Docker build context is ``./backend`` (``COPY . .``) — a repo-root
directory would not be in the image. Override with ``LLM_PROMPTS_DIR``.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.platform.llm.models.prompt import Backend, PromptKey, RenderedPrompt

REQUIRED_FIELDS = ("name", "version", "content", "max_tokens", "model", "backend")
TRANSCRIPT_PLACEHOLDER = "{{transcript}}"
SECTION_TYPE_PLACEHOLDER = "{{section_type}}"
_VALID_BACKENDS = ("cerebras", "nvidia")


class PromptRegistryError(RuntimeError):
    """Raised on a missing/malformed prompt or an unknown lookup. A boot-time failure."""


@dataclass(frozen=True)
class PromptFile:
    key: PromptKey
    model_id: str
    backend: Backend
    max_tokens: int
    reasoning_level: str | None
    content: str
    content_hash: str
    source_path: Path


def default_prompts_dir() -> Path:
    override = os.environ.get("LLM_PROMPTS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "prompts"


def _load_prompt_file(path: Path) -> PromptFile:
    raw = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via malformed-file test
        raise PromptRegistryError(f"malformed YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PromptRegistryError(f"prompt file must be a mapping: {path}")

    missing = [f for f in REQUIRED_FIELDS if f not in data or data[f] in (None, "")]
    if missing:
        raise PromptRegistryError(f"prompt {path} missing required fields: {missing}")

    backend = str(data["backend"])
    if backend not in _VALID_BACKENDS:
        raise PromptRegistryError(
            f"prompt {path} backend must be one of {_VALID_BACKENDS}, got {backend!r}"
        )

    try:
        max_tokens = int(data["max_tokens"])
    except (TypeError, ValueError) as exc:
        raise PromptRegistryError(f"prompt {path} max_tokens must be an integer") from exc
    if max_tokens <= 0:
        raise PromptRegistryError(f"prompt {path} max_tokens must be > 0")

    content = str(data["content"])
    if TRANSCRIPT_PLACEHOLDER not in content:
        raise PromptRegistryError(
            f"prompt {path} content must include the {TRANSCRIPT_PLACEHOLDER} placeholder"
        )

    reasoning_level = data.get("reasoning_level")
    return PromptFile(
        key=PromptKey(name=str(data["name"]), version=str(data["version"])),
        model_id=str(data["model"]),
        backend=backend,  # type: ignore[arg-type]
        max_tokens=max_tokens,
        reasoning_level=str(reasoning_level) if reasoning_level else None,
        content=content,
        content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        source_path=path,
    )


class PromptRegistry:
    def __init__(self, prompts: dict[PromptKey, PromptFile]) -> None:
        self._prompts = prompts

    @classmethod
    def load_from_dir(cls, directory: Path) -> PromptRegistry:
        if not directory.is_dir():
            raise PromptRegistryError(f"prompts directory not found: {directory}")
        prompts: dict[PromptKey, PromptFile] = {}
        for path in sorted(directory.rglob("*.yaml")):
            prompt_file = _load_prompt_file(path)
            if prompt_file.key in prompts:
                raise PromptRegistryError(f"duplicate prompt {prompt_file.key} at {path}")
            prompts[prompt_file.key] = prompt_file
        if not prompts:
            raise PromptRegistryError(f"no prompt files found under {directory}")
        return cls(prompts)

    def get(self, key: PromptKey) -> PromptFile:
        try:
            return self._prompts[key]
        except KeyError:
            raise PromptRegistryError(f"unknown prompt {key}") from None

    def content_hash(self, key: PromptKey) -> str:
        return self.get(key).content_hash

    def keys(self) -> tuple[PromptKey, ...]:
        return tuple(self._prompts.keys())

    def all_files(self) -> tuple[PromptFile, ...]:
        return tuple(self._prompts.values())

    def render(
        self,
        key: PromptKey,
        *,
        transcript: str,
        section_type: str,
    ) -> RenderedPrompt:
        prompt_file = self.get(key)
        content = prompt_file.content.replace(TRANSCRIPT_PLACEHOLDER, transcript).replace(
            SECTION_TYPE_PLACEHOLDER, section_type
        )
        rendered_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return RenderedPrompt(
            prompt_key=prompt_file.key,
            model_id=prompt_file.model_id,
            backend=prompt_file.backend,
            max_tokens=prompt_file.max_tokens,
            reasoning_level=prompt_file.reasoning_level,
            content=content,
            prompt_content_hash=prompt_file.content_hash,
            rendered_prompt_hash=rendered_hash,
        )


_REGISTRY: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    """Process-wide singleton; loads + validates on first use (startup boot check)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PromptRegistry.load_from_dir(default_prompts_dir())
    return _REGISTRY


def reset_prompt_registry_cache() -> None:
    """Test helper — forces a reload on the next ``get_prompt_registry()``."""
    global _REGISTRY
    _REGISTRY = None
