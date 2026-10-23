
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DashboardSummary(BaseModel):
    total_customers: int
    total_feedback_submissions: int
    total_complaints: int
    open_complaints: int
    resolved_complaints: int
    overdue_complaints: int
    average_resolution_time_hours: float | None
    average_customer_rating: float | None


class PriorityCount(BaseModel):
    priority: str
    complaint_count: int


class AgentComplaintCount(BaseModel):
    agent_id: int
    agent_email: str
    total_assigned: int
    open_complaints: int
    resolved_complaints: int


class ComplaintReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference_number: str
    customer_id: int
    assigned_to: int | None
    title: str
    priority: str
    severity: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class ComplaintReportPage(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[ComplaintReportItem]
