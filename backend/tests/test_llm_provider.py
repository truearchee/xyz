"""K2ThinkProvider transport + §8 HTTP error classification, and the DeterministicTestProvider fault
modes. No network and no real key: the real provider's ``httpx.Client`` is backed by a MockTransport.
Proves the model id is config-driven (rule 11), the JSON-mode flag, and that 4xx config/auth errors
are terminal and carry NO key/body — only a status code (§0/§8)."""

from __future__ import annotations

import json

import httpx
import pytest

import app.platform.llm.provider as provider_mod
from app.platform.config import SettingsError
from app.platform.llm.errors import (
    InvalidOutput,
    ProviderAuthError,
    ProviderConfigError,
    ProviderTransient,
    RateLimited,
)
from app.platform.llm.models.prompt import PromptKey, RenderedPrompt
from app.platform.llm.provider import (
    DeterministicTestProvider,
    K2ThinkProvider,
    RawCompletion,
    get_provider,
)

API_KEY = "sk-test-do-not-log-me"


def _rendered(*, model_id: str = "MBZUAI-IFM/K2-Think-v2") -> RenderedPrompt:
    return RenderedPrompt(
        prompt_key=PromptKey("brief_summary", "v1"),
        model_id=model_id,
        backend="cerebras",
        max_tokens=600,
        reasoning_level=None,
        content="Summarize this. SECTION lecture TRANSCRIPT hello world",
        prompt_content_hash="h" * 64,
        rendered_prompt_hash="r" * 64,
    )


def _ok_body(model: str = "MBZUAI-IFM/K2-Think-v2") -> dict:
    return {
        "id": "cmpl-abc123",
        "model": model,
        "choices": [
            {"message": {"content": json.dumps({"text": "A concise paragraph."}),
                         "reasoning_content": None}}
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def _provider(monkeypatch, handler, *, json_mode: bool = False, captured: list | None = None):
    """K2ThinkProvider whose httpx.Client is bound to a MockTransport running ``handler``."""
    real_client = httpx.Client  # capture BEFORE patching to avoid recursing into the patch

    def wrapped_handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return handler(request)

    transport = httpx.MockTransport(wrapped_handler)
    monkeypatch.setattr(
        provider_mod.httpx, "Client", lambda **kwargs: real_client(transport=transport)
    )
    return K2ThinkProvider(api_key=API_KEY, json_mode=json_mode)


# --- request building -------------------------------------------------------

def test_payload_uses_prompt_model_id_and_messages(monkeypatch):
    captured: list[httpx.Request] = []
    provider = _provider(monkeypatch, lambda req: httpx.Response(200, json=_ok_body()), captured=captured)
    provider.send(rendered=_rendered(model_id="some/configured-model"), backend="cerebras")

    sent = json.loads(captured[0].content)
    assert sent["model"] == "some/configured-model"  # config (prompt YAML), never hardcoded
    assert sent["messages"][0]["role"] == "user"
    assert "hello world" in sent["messages"][0]["content"]
    assert sent["max_tokens"] == 600
    assert "response_format" not in sent  # json mode OFF by default
    assert str(captured[0].url).endswith("/v1/chat/completions")


def test_payload_includes_response_format_when_json_mode(monkeypatch):
    captured: list[httpx.Request] = []
    provider = _provider(
        monkeypatch, lambda req: httpx.Response(200, json=_ok_body()), json_mode=True, captured=captured
    )
    provider.send(rendered=_rendered(), backend="cerebras")
    sent = json.loads(captured[0].content)
    assert sent["response_format"] == {"type": "json_object"}


def test_detailed_route_gets_a_longer_timeout_than_brief(monkeypatch):
    # F-4.5-49: the detailed (Nvidia) reasoning call needs more wall-clock; the provider selects a
    # per-route timeout (detailed > brief) so brief is not inflated and detailed does not time out.
    monkeypatch.setenv("LLM_PROVIDER_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("LLM_DETAILED_TIMEOUT_SECONDS", "240")
    provider = K2ThinkProvider(api_key=API_KEY)
    assert provider._timeout_for("cerebras") == 60
    assert provider._timeout_for("nvidia") == 240


def test_payload_requests_use_nvidia_only_for_the_nvidia_route(monkeypatch):
    # 4.5c routing split (Option A): the Nvidia route is requested via metadata.use_nvidia; the
    # Cerebras route is the provider default (no metadata).
    captured: list[httpx.Request] = []
    provider = _provider(
        monkeypatch, lambda req: httpx.Response(200, json=_ok_body()), captured=captured
    )
    provider.send(rendered=_rendered(), backend="nvidia")
    assert json.loads(captured[0].content)["metadata"] == {"use_nvidia": True}

    captured.clear()
    provider.send(rendered=_rendered(), backend="cerebras")
    assert "metadata" not in json.loads(captured[0].content)


# --- 200 happy path ---------------------------------------------------------

def test_200_returns_completion_with_usage_model_echo_and_null_reasoning(monkeypatch):
    provider = _provider(monkeypatch, lambda req: httpx.Response(200, json=_ok_body()))
    raw = provider.send(rendered=_rendered(), backend="cerebras")
    assert isinstance(raw, RawCompletion)
    assert json.loads(raw.text)["text"] == "A concise paragraph."
    assert raw.usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert raw.model_id_echoed == "MBZUAI-IFM/K2-Think-v2"  # rule-11 echo is LIVE
    assert raw.status_code == 200
    assert raw.reasoning_level is None  # reasoning_content present-but-null; never faked (F-4.5-04)
    assert raw.provider_request_id == "cmpl-abc123"


# --- §8 error classification ------------------------------------------------

def test_400_is_terminal_provider_config_error(monkeypatch):
    provider = _provider(monkeypatch, lambda req: httpx.Response(400, json={"error": "bad model"}))
    with pytest.raises(ProviderConfigError) as exc:
        provider.send(rendered=_rendered(), backend="cerebras")
    assert exc.value.retryable is False
    assert exc.value.status_code == 400


@pytest.mark.parametrize("status", [401, 403])
def test_401_403_is_terminal_provider_auth_error_and_redacts(monkeypatch, status):
    def handler(req):
        return httpx.Response(status, json={"error": "forbidden", "echo": API_KEY})

    provider = _provider(monkeypatch, handler)
    with pytest.raises(ProviderAuthError) as exc:
        provider.send(rendered=_rendered(), backend="cerebras")
    assert exc.value.retryable is False
    assert exc.value.status_code == status
    # The body is never surfaced: no key, no Authorization header text in the exception (§0).
    message = str(exc.value)
    assert API_KEY not in message
    assert "Bearer" not in message and "Authorization" not in message


def test_408_is_provider_transient(monkeypatch):
    provider = _provider(monkeypatch, lambda req: httpx.Response(408))
    with pytest.raises(ProviderTransient) as exc:
        provider.send(rendered=_rendered(), backend="cerebras")
    assert exc.value.retryable is True


def test_network_timeout_is_provider_transient(monkeypatch):
    def handler(req):
        raise httpx.TimeoutException("timed out", request=req)

    provider = _provider(monkeypatch, handler)
    with pytest.raises(ProviderTransient) as exc:
        provider.send(rendered=_rendered(), backend="cerebras")
    assert exc.value.error_code == "provider_timeout"
    assert API_KEY not in str(exc.value)


def test_connection_error_is_provider_transient(monkeypatch):
    def handler(req):
        raise httpx.ConnectError("no route", request=req)

    provider = _provider(monkeypatch, handler)
    with pytest.raises(ProviderTransient):
        provider.send(rendered=_rendered(), backend="cerebras")


def test_429_is_rate_limited(monkeypatch):
    provider = _provider(monkeypatch, lambda req: httpx.Response(429))
    with pytest.raises(RateLimited) as exc:
        provider.send(rendered=_rendered(), backend="cerebras")
    assert exc.value.status_code == 429


def test_5xx_is_provider_transient(monkeypatch):
    provider = _provider(monkeypatch, lambda req: httpx.Response(503))
    with pytest.raises(ProviderTransient) as exc:
        provider.send(rendered=_rendered(), backend="cerebras")
    assert exc.value.status_code == 503


def test_other_4xx_is_terminal_config_error(monkeypatch):
    # A 404/422 is a misconfiguration, not transient — terminate, do not retry-storm.
    provider = _provider(monkeypatch, lambda req: httpx.Response(404))
    with pytest.raises(ProviderConfigError):
        provider.send(rendered=_rendered(), backend="cerebras")


def test_200_with_missing_content_is_invalid_output(monkeypatch):
    provider = _provider(monkeypatch, lambda req: httpx.Response(200, json={"choices": []}))
    with pytest.raises(InvalidOutput):
        provider.send(rendered=_rendered(), backend="cerebras")


def test_200_with_non_json_body_is_invalid_output(monkeypatch):
    provider = _provider(monkeypatch, lambda req: httpx.Response(200, text="not json"))
    with pytest.raises(InvalidOutput):
        provider.send(rendered=_rendered(), backend="cerebras")


# --- config gate ------------------------------------------------------------

def test_missing_api_key_raises_settings_error(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(SettingsError):
        K2ThinkProvider(api_key=None)


# --- DeterministicTestProvider fault modes ----------------------------------

@pytest.mark.parametrize(
    "fault, exc_type, status_code",
    [
        ("rate_limited", RateLimited, 429),
        ("provider_config", ProviderConfigError, 400),
        ("provider_auth", ProviderAuthError, 403),
        ("timeout", ProviderTransient, 408),
        ("provider_transient", ProviderTransient, 503),
    ],
)
def test_deterministic_fault_modes_raise_classified(fault, exc_type, status_code):
    provider = DeterministicTestProvider(fault=fault)
    with pytest.raises(exc_type) as exc:
        provider.send(rendered=_rendered(), backend="cerebras")
    assert exc.value.status_code == status_code


def test_deterministic_rejects_unknown_fault():
    with pytest.raises(ValueError):
        DeterministicTestProvider(fault="bogus")


# --- LLM_PROVIDER gate: no accidental real calls (§11) ----------------------

def test_get_provider_is_deterministic_by_default(monkeypatch):
    # Default config never constructs the real transport → a real K2Think call cannot be made.
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(get_provider(), DeterministicTestProvider)


def test_get_provider_is_real_only_with_explicit_env_and_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "k2think")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
    assert isinstance(get_provider(), K2ThinkProvider)


def test_get_provider_k2think_without_key_is_settings_error(monkeypatch):
    # Real provider selected but no key → boot-time SettingsError, never a keyless doomed call.
    monkeypatch.setenv("LLM_PROVIDER", "k2think")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(SettingsError):
        get_provider()
