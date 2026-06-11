"""Gateway error taxonomy (spec §6/§7.5).

Each error maps to an ``AIRequestLog.status`` and a retry disposition. The gateway catches
these to classify a completion attempt; the summary job handler maps the terminal status to
``IngestionJob.failure_category``.
"""

from __future__ import annotations


class GatewayError(RuntimeError):
    """Base for gateway-classified failures."""

    status: str = "failed"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        # HTTP status seen at the provider boundary, when there was one (None for non-transport
        # failures and the deterministic provider). Recorded in AIRequestLog.last_provider_status_code
        # and retry_events_json. Never carries a body, header, or key — status code only (§0/§8).
        self.status_code = status_code

    @property
    def error_class(self) -> str:
        return type(self).__name__


class InvalidInput(GatewayError):
    """Over-context with no viable route, or otherwise un-sendable input. NON-retryable (D3)."""

    status = "invalid_input"
    retryable = False


class RateLimited(GatewayError):
    """Limiter denied capacity / provider 429. Retryable / delayed."""

    status = "rate_limited"
    retryable = True


class ProviderTransient(GatewayError):
    """Provider 5xx / timeout. Retryable via RQ."""

    status = "provider_transient"
    retryable = True


class ProviderConfigError(GatewayError):
    """Provider 400 — invalid model id / malformed request. A misconfiguration, NOT transient:
    retrying a bad model id burns the request budget for nothing. Terminal, non-retryable (§8).
    The response body is never logged (redacted to nothing); only the status code is kept."""

    status = "provider_config_error"
    retryable = False


class ProviderAuthError(GatewayError):
    """Provider 401/403 — bad/expired key or forbidden. Terminal, non-retryable: retrying a bad key
    is a denial-of-wallet strategy (§8). Body and headers are never logged (§0); status code only."""

    status = "provider_auth_error"
    retryable = False


class InvalidOutput(GatewayError):
    """Response failed schema/structure validation. Retryable, bounded."""

    status = "invalid_output"
    retryable = True


class GatewayFailed(GatewayError):
    """Unexpected gateway failure not classifiable as a typed status (§6.6).

    This is the exception, not the catch-all drawer — prefer a typed status whenever the
    failure mode is known.
    """

    status = "failed"
    retryable = False
