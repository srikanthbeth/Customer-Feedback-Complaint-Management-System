
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SLAResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    complaint_id: int
    reference_number: str
    priority: str
    status: str
    sla_hours: int
    created_at: datetime
    sla_deadline: datetime
    resolved_at: datetime | None
    time_remaining_seconds: int | None
    overdue_seconds: int
    resolution_duration_seconds: int | None
    is_overdue: bool
    sla_breached: bool


class SLAOverdueResponse(BaseModel):
    items: list[SLAResponse]
    total: int
