
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FeedbackCategory(str, Enum):
    PRODUCT = "PRODUCT"
    SERVICE = "SERVICE"
    SUPPORT = "SUPPORT"
    DELIVERY = "DELIVERY"
    OTHER = "OTHER"


class FeedbackStatus(str, Enum):
    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class FeedbackCreate(BaseModel):
    category: FeedbackCategory
    rating: int = Field(strict=True, ge=1, le=5)
    description: str = Field(min_length=1, max_length=5000)
    complaint_id: int | None = Field(default=None, gt=0)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Description cannot be empty")
        return value


class FeedbackUpdate(BaseModel):
    category: FeedbackCategory | None = None
    rating: int | None = Field(
        default=None, strict=True, ge=1, le=5
    )
    description: str | None = Field(
        default=None, min_length=1, max_length=5000
    )

    @field_validator("description")
    @classmethod
    def validate_description(
        cls, value: str | None
    ) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Description cannot be empty")
        return value

    @model_validator(mode="after")
    def require_update(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    category: str
    rating: int
    description: str
    status: str
    feedback_date: datetime
    created_at: datetime
    updated_at: datetime
    complaint_id: int | None


class FeedbackHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feedback_id: int
    changed_by: str
    action: str
    changes: dict[str, Any]
    changed_at: datetime
    note: str | None
