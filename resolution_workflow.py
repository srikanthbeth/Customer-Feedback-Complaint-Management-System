from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Comment cannot be empty")
        return value


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    complaint_id: int
    author_id: int
    content: str
    is_internal: bool
    created_at: datetime


class ResolutionCreate(BaseModel):
    resolution_details: str = Field(
        min_length=5, max_length=10000
    )
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("resolution_details")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError(
                "Resolution details must contain at least 5 characters"
            )
        return value


class WorkflowReason(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class StatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    complaint_id: int
    previous_status: str
    new_status: str
    changed_by: int
    reason: str | None
    changed_at: datetime