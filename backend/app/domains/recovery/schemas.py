from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )


class ReapStuckRowsRequest(CamelModel):
    report_only: bool = False


class ReconcileStorageRequest(CamelModel):
    mode: str = "report_only"  # report_only | cleanup


class MaintenanceRunRead(CamelModel):
    id: UUID
    run_type: str
    mode: str
    status: str
    triggered_by_user_id: UUID | None
    started_at: datetime
    completed_at: datetime | None
    summary_json: dict | None
    error_message: str | None
    created_at: datetime
