"""Pure-unit tests for platform/llm — registry, validation, context, drift guard (no DB/Redis)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.platform.llm.context import ContextBuilder, estimate_tokens
from app.platform.llm.errors import InvalidInput, InvalidOutput
from app.platform.llm.gateway import reconcile_token_estimate
from app.platform.llm.limiter import BackoffPolicy, effective_limit
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


def test_detailed_extracts_object_after_reasoning_preamble():
    # 4.5c: detailed runs on the reasoning-lineage K2-Think-v2; the validator must extract the
    # structured object even if the model prefixes reasoning despite instructions (§4/§7).
    raw = "Let me organize the key sections of the lecture first.\n\n" + _good_detailed()
    parsed = _validator().validate(
        raw_text=raw, output_schema=DetailedSummary, section_type="lecture"
    )
    assert isinstance(parsed, DetailedSummary)
    assert parsed.exam_relevant_points == ["p1"]


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


def test_fit_fallback_disabled_makes_over_limit_invalid_input(monkeypatch: pytest.MonkeyPatch):
    # §12 / F-4.5-37: under the single-model deviation the Cerebras→Nvidia fallback is OFF, so a brief
    # over the (configured) Cerebras window becomes invalid_input — it does NOT reroute onto an
    # unverified window. The same inputs WOULD fall back with the flag default-on (test above).
    monkeypatch.setenv("LLM_CONTEXT_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("LLM_CEREBRAS_CONTEXT_WINDOW_TOKENS", "10")
    monkeypatch.setenv("LLM_NVIDIA_CONTEXT_WINDOW_TOKENS", "100000")
    with pytest.raises(InvalidInput):
        ContextBuilder().fit(_rendered("cerebras", "word " * 100, 50))


# --- BackoffPolicy (§10) ----------------------------------------------------

def test_backoff_delay_is_capped_exponential():
    policy = BackoffPolicy(max_backoffs=5, base_delay_ms=100, max_delay_ms=400, max_elapsed_ms=9999)
    assert policy.delay_ms(1) == 100
    assert policy.delay_ms(2) == 200
    assert policy.delay_ms(3) == 400
    assert policy.delay_ms(4) == 400  # capped at max_delay_ms


def test_backoff_exhausts_on_count_or_elapsed():
    policy = BackoffPolicy(max_backoffs=2, base_delay_ms=1, max_delay_ms=1, max_elapsed_ms=1000)
    assert policy.is_exhausted(backoffs_done=2, elapsed_ms=10) is False
    assert policy.is_exhausted(backoffs_done=3, elapsed_ms=10) is True  # over the count
    assert policy.is_exhausted(backoffs_done=1, elapsed_ms=1000) is True  # over the elapsed cap


# --- estimate-vs-actual reconciliation (§3.8) -------------------------------

def test_reconcile_returns_none_without_real_usage():
    assert (
        reconcile_token_estimate(
            content_chars=100, estimated_prompt_tokens=29, actual_prompt_tokens=None
        )
        is None
    )
    assert (
        reconcile_token_estimate(
            content_chars=100, estimated_prompt_tokens=29, actual_prompt_tokens=0
        )
        is None
    )


def test_reconcile_computes_ratio_and_observed_chars_per_token():
    result = reconcile_token_estimate(
        content_chars=350, estimated_prompt_tokens=100, actual_prompt_tokens=80
    )
    assert result["estimatedPromptTokens"] == 100
    assert result["actualPromptTokens"] == 80
    assert result["estimateRatio"] == 1.25
    assert result["observedCharsPerToken"] == round(350 / 80, 4)


# --- headroom reservation math (§3.12) --------------------------------------

def test_interactive_headroom_reserves_capacity_from_background():
    # Background traffic is capped to leave a reservation for interactive Stage-8 traffic.
    assert effective_limit(100, "interactive", 20) == 100  # interactive uses the full limit
    assert effective_limit(100, "background", 20) == 80  # background capped to 80%
    reserved_for_interactive = 100 - effective_limit(100, "background", 20)
    assert reserved_for_interactive == 20
    assert effective_limit(1, "background", 90) == 1  # never below 1


# --- tolerant extract + strict shape, brief (§7) ----------------------------

def test_brief_extracts_object_after_reasoning_preamble():
    raw = (
        "Let me think about the key points first. Okay, here is the summary:\n"
        '{"text": "This lecture introduced the core ideas and worked a clear example."}'
    )
    parsed = _validator().validate(raw_text=raw, output_schema=BriefSummary, section_type="lecture")
    assert parsed.text.startswith("This lecture introduced")


def test_brief_extracts_object_from_json_code_fence():
    raw = '```json\n{"text": "A concise paragraph summarizing the session content for a student."}\n```'
    parsed = _validator().validate(raw_text=raw, output_schema=BriefSummary, section_type="lecture")
    assert "concise paragraph" in parsed.text


def test_brief_stores_only_text_when_extra_keys_present():
    # Strict shape reads only `text`; surrounding chatter/extra keys never reach the student (§7).
    raw = '{"reasoning": "internal chain of thought", "text": "The student-facing summary paragraph."}'
    parsed = _validator().validate(raw_text=raw, output_schema=BriefSummary, section_type="lecture")
    assert parsed.text == "The student-facing summary paragraph."


def test_brief_with_no_object_anywhere_is_invalid_output():
    with pytest.raises(InvalidOutput):
        _validator().validate(
            raw_text="No JSON here at all, just chatter.",
            output_schema=BriefSummary,
            section_type="lecture",
        )


def test_brief_selects_real_answer_after_inline_reasoning():
    # F-4.5-48 (actual failure shape): K2-Think-v2 reasons inline in `content` for a long stretch —
    # containing a brace-bearing fragment {x: f(x)} and a narrated `Output exactly:\n\n{"text":
    # "<your paragraph>"}` example — then places the real answer LAST. Neither "first" nor "longest"
    # is safe; the validator must select the LAST object that fully validates.
    reasoning = (
        "We need to produce a JSON object with a single key 'text'. Let me think about the lecture. "
        "It covered supervised learning, the loss function, overfitting, and regularisation. "
        "Set-builder notation like {x: f(x)} shows up in my notes here. I should aim for 60-120 words. "
        'The format example says Output exactly:\n\n{"text": "<your paragraph>"}\n\n'
        "Let me draft it... that is about 100 words, within 60-120. Good. Now produce JSON.\n\n"
    )
    real = (
        '{"text": "This session introduced supervised learning, where a model learns a mapping from '
        "inputs to outputs using labelled examples. The loss function measures prediction error, and "
        "training minimises the average loss by gradient descent. Overfitting means fitting noise and "
        "failing to generalise, seen as a gap between training and validation error; regularisation "
        'penalises large weights to improve generalisation. A worked example fits a line by least squares."}'
    )
    parsed = _validator().validate(
        raw_text=reasoning + real, output_schema=BriefSummary, section_type="lecture"
    )
    assert "supervised learning" in parsed.text
    assert "<your paragraph>" not in parsed.text
