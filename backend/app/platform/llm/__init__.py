"""platform/llm — AI gateway infrastructure (Stage 4.5).

Infrastructure consumed by domains (rule 8): a feature job calls ``LLMGateway.complete`` and never
touches a provider, limiter, or log directly.
"""

from app.platform.llm.context import ContextBuilder, estimate_tokens
from app.platform.llm.errors import (
    GatewayError,
    GatewayFailed,
    InvalidInput,
    InvalidOutput,
    ProviderTransient,
    RateLimited,
)
from app.platform.llm.gateway import CompletionResult, ContextRefs, LLMGateway
from app.platform.llm.limiter import RedisRateLimiter, get_rate_limiter
from app.platform.llm.models.prompt import (
    Backend,
    Priority,
    PromptKey,
    RenderedPrompt,
    SummaryFeature,
    Usage,
)
from app.platform.llm.models.summary import (
    BRIEF_SCHEMA_VERSION,
    DETAILED_SCHEMA_VERSION,
    BriefSummary,
    DetailedSummary,
)
from app.platform.llm.provider import (
    DeterministicTestProvider,
    K2ThinkProvider,
    LLMProvider,
    RawCompletion,
    get_provider,
)
from app.platform.llm.registry import PromptRegistry, get_prompt_registry
from app.platform.llm.validation import OutputValidator

__all__ = [
    "ContextBuilder",
    "estimate_tokens",
    "GatewayError",
    "GatewayFailed",
    "InvalidInput",
    "InvalidOutput",
    "ProviderTransient",
    "RateLimited",
    "CompletionResult",
    "ContextRefs",
    "LLMGateway",
    "RedisRateLimiter",
    "get_rate_limiter",
    "Backend",
    "Priority",
    "PromptKey",
    "RenderedPrompt",
    "SummaryFeature",
    "Usage",
    "BRIEF_SCHEMA_VERSION",
    "DETAILED_SCHEMA_VERSION",
    "BriefSummary",
    "DetailedSummary",
    "DeterministicTestProvider",
    "K2ThinkProvider",
    "LLMProvider",
    "RawCompletion",
    "get_provider",
    "PromptRegistry",
    "get_prompt_registry",
    "OutputValidator",
]
