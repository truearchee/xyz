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

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code

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
