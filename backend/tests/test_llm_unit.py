"""Pure-unit tests for platform/llm — registry, validation, context, drift guard (no DB/Redis)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.platform.llm.context import ContextBuilder, estimate_tokens
from app.platform.llm.errors import InvalidInput, InvalidOutput
from app.platform.llm.models.prompt import PromptKey, RenderedPrompt
from app.platform.llm.models.summary import BriefSummary, DetailedSummary
from app.platform.llm.registry import (
    PromptRegistry,
    PromptRegistryError,
    default_prompts_dir,
)
from app.platform.llm.validation import OutputValidator
from tests.ci.prompt_drift_guard import check_prompt_drift

VALID_PROMPT = """\
name: sample
version: v1
model: test-model
backend: cerebras
max_tokens: 100
content: |
  Summarize this. {{transcript}} ({{section_type}})
"""


# --- PromptRegistry ---------------------------------------------------------

def test_registry_loads_and_validates_real_prompts():
    registry = PromptRegistry.load_from_dir(default_prompts_dir())
    keys = {str(k) for k in registry.keys()}
    assert "brief_summary/v1" in keys
    assert "detailed_summary/v1" in keys
    # content hash is stable + non-empty
    assert len(registry.content_hash(PromptKey("brief_summary", "v1"))) == 64


def test_registry_render_substitutes_and_hashes():
    registry = PromptRegistry.load_from_dir(default_prompts_dir())
    rendered = registry.render(
        PromptKey("brief_summary", "v1"), transcript="HELLO WORLD", section_type="lecture"
    )
    assert "HELLO WORLD" in rendered.content
    assert "{{transcript}}" not in rendered.content
    assert rendered.backend == "cerebras"
    assert len(rendered.rendered_prompt_hash) == 64
    assert rendered.prompt_content_hash == registry.content_hash(PromptKey("brief_summary", "v1"))


def test_registry_missing_field_is_boot_failure(tmp_path: Path):
    (tmp_path / "bad.yaml").write_text("name: x\nversion: v1\n", encoding="utf-8")
    with pytest.raises(PromptRegistryError):
        PromptRegistry.load_from_dir(tmp_path)


def test_registry_requires_transcript_placeholder(tmp_path: Path):
    (tmp_path / "p.yaml").write_text(
        "name: x\nversion: v1\nmodel: m\nbackend: cerebras\nmax_tokens: 10\ncontent: no placeholder\n",
        encoding="utf-8",
    )
    with pytest.raises(PromptRegistryError):
        PromptRegistry.load_from_dir(tmp_path)


def test_registry_malformed_yaml_is_boot_failure(tmp_path: Path):
    (tmp_path / "bad.yaml").write_text("name: x\n  : : :\n", encoding="utf-8")
    with pytest.raises(PromptRegistryError):
        PromptRegistry.load_from_dir(tmp_path)


# --- CI drift guard ---------------------------------------------------------

def test_committed_prompts_match_checksums():
    assert check_prompt_drift() == []


def test_drift_guard_detects_content_change_without_version_bump(tmp_path: Path):
    prompt = tmp_path / "sample" / "v1.yaml"
    prompt.parent.mkdir(parents=True)
    prompt.write_text(VALID_PROMPT, encoding="utf-8")
    registry = PromptRegistry.load_from_dir(tmp_path)
    good_hash = registry.content_hash(PromptKey("sample", "v1"))
    (tmp_path / "CHECKSUMS.json").write_text(json.dumps({"sample/v1": good_hash}), encoding="utf-8")
    assert check_prompt_drift(tmp_path) == []

    prompt.write_text(VALID_PROMPT + "\n# sneaky edit\n", encoding="utf-8")
    problems = check_prompt_drift(tmp_path)
    assert any("without a version bump" in p for p in problems)


def test_drift_guard_flags_unrecorded_new_prompt(tmp_path: Path):
    prompt = tmp_path / "sample" / "v1.yaml"
    prompt.parent.mkdir(parents=True)
    prompt.write_text(VALID_PROMPT, encoding="utf-8")
    (tmp_path / "CHECKSUMS.json").write_text("{}", encoding="utf-8")
    problems = check_prompt_drift(tmp_path)
    assert any("not recorded" in p for p in problems)


# --- OutputValidator --------------------------------------------------------

def _validator() -> OutputValidator:
    return OutputValidator()


def test_brief_validates_good_output():
    raw = json.dumps({"text": "This lecture introduced the core ideas and worked an example clearly."})
    parsed = _validator().validate(raw_text=raw, output_schema=BriefSummary, section_type="lecture")
    assert isinstance(parsed, BriefSummary)


def test_brief_rejects_wrong_shape():
    with pytest.raises(InvalidOutput):
        _validator().validate(
            raw_text=json.dumps({"nope": "x"}), output_schema=BriefSummary, section_type="lecture"
        )


def test_brief_rejects_too_short():
    with pytest.raises(InvalidOutput):
        _validator().validate(
            raw_text=json.dumps({"text": "tiny"}), output_schema=BriefSummary, section_type="lecture"
        )


def test_brief_rejects_non_json():
    with pytest.raises(InvalidOutput):
        _validator().validate(
            raw_text="I'm just chatting, no JSON here", output_schema=BriefSummary, section_type="lecture"
        )


def _good_detailed(include_lab: bool = True) -> str:
    payload = {
        "overview": "An overview.",
        "keyConcepts": ["c1"],
        "importantDefinitions": [{"term": "t", "definition": "d"}],
        "mainExplanations": ["e1"],
        "examples": ["ex1"],
        "examRelevantPoints": ["p1"],
    }
    if include_lab:
        payload["labNotes"] = ["n1"]
    return json.dumps(payload)


def test_detailed_validates_good_output():
    parsed = _validator().validate(
        raw_text=_good_detailed(), output_schema=DetailedSummary, section_type="lecture"
    )
    assert isinstance(parsed, DetailedSummary)
    assert parsed.exam_relevant_points == ["p1"]


def test_detailed_rejects_missing_section():
    payload = json.loads(_good_detailed())
    payload.pop("examples")
    with pytest.raises(InvalidOutput):
        _validator().validate(
            raw_text=json.dumps(payload), output_schema=DetailedSummary, section_type="lecture"
        )


def test_detailed_lab_requires_lab_notes():
    with pytest.raises(InvalidOutput):
        _validator().validate(
            raw_text=_good_detailed(include_lab=False),
            output_schema=DetailedSummary,
            section_type="lab",
        )


def test_detailed_tolerates_code_fences():
    fenced = "```json\n" + _good_detailed() + "\n```"
    parsed = _validator().validate(
        raw_text=fenced, output_schema=DetailedSummary, section_type="lecture"
    )
    assert isinstance(parsed, DetailedSummary)


# --- ContextBuilder ---------------------------------------------------------

def _rendered(backend: str, content: str, max_tokens: int) -> RenderedPrompt:
    return RenderedPrompt(
        prompt_key=PromptKey("p", "v1"),
        model_id="m",
        backend=backend,  # type: ignore[arg-type]
        max_tokens=max_tokens,
        reasoning_level=None,
        content=content,
        prompt_content_hash="h",
        rendered_prompt_hash="rh",
    )


def test_estimate_tokens_is_conservative():
    assert estimate_tokens("xxxxxxx") >= 2  # 7/3.5 = 2


def test_fit_uses_declared_backend_when_it_fits():
    result = ContextBuilder().fit(_rendered("cerebras", "short content", 50))
    assert result.backend == "cerebras"
    assert result.fell_back is False


def test_fit_brief_falls_back_to_nvidia(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_CEREBRAS_CONTEXT_WINDOW_TOKENS", "10")
    monkeypatch.setenv("LLM_NVIDIA_CONTEXT_WINDOW_TOKENS", "100000")
    result = ContextBuilder().fit(_rendered("cerebras", "word " * 100, 50))
    assert result.backend == "nvidia"
    assert result.fell_back is True


def test_fit_over_both_windows_is_invalid_input(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_CEREBRAS_CONTEXT_WINDOW_TOKENS", "10")
    monkeypatch.setenv("LLM_NVIDIA_CONTEXT_WINDOW_TOKENS", "10")
    with pytest.raises(InvalidInput):
        ContextBuilder().fit(_rendered("cerebras", "word " * 100, 50))


def test_fit_detailed_has_no_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_NVIDIA_CONTEXT_WINDOW_TOKENS", "10")
    with pytest.raises(InvalidInput):
        ContextBuilder().fit(_rendered("nvidia", "word " * 100, 50))
