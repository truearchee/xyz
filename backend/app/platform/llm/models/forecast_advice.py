"""Grade-forecast advice output schema (Stage 11.6).

The model produces a single student-facing advice paragraph that EXPLAINS Stage 9's deterministic
forecast. The numbers, the target grade, and the forecast state are decided deterministically; the
analytics domain validates numeric/fact consistency, state contradiction, and student-copy safety
before any AI text is persisted or returned.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

GRADE_FORECAST_ADVICE_SCHEMA_VERSION = "grade-forecast-advice-v1"

# The ``section_type`` the advice worker passes into ContextRefs and that the prompt renders as
# ``Section type: {{section_type}}``. The deterministic test provider splits on this exact marker to
# recover the payload, so the worker and the provider MUST agree on this one constant.
GRADE_FORECAST_ADVICE_SECTION_TYPE = "grade_forecast_advice"


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class GradeForecastAdvice(CamelModel):
    advice: str
