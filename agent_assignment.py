
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentAssignmentCreate(BaseModel):
    agent_id: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=1000)


class SupportAgentResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AssignmentHistoryResponse(BaseModel):
    id: int
    complaint_id: int
    previous_agent_id: int | None
    new_agent_id: int
    assigned_by: int
    action: str
    note: str | None
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentWorkloadResponse(BaseModel):
    agent_id: int
    agent_name: str
    agent_email: str
    total_assigned: int
    active_complaints: int
    resolved_complaints: int


class AssignedComplaintResponse(BaseModel):
    id: int
    reference_number: str
    customer_id: int
    category_id: int
    assigned_to: int | None
    assigned_at: datetime | None
    title: str
    description: str
    priority: str
    severity: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
