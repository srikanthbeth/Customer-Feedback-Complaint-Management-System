
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ComplaintPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComplaintSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComplaintStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class ComplaintCreate(BaseModel):
    category_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    priority: ComplaintPriority = ComplaintPriority.MEDIUM
    severity: ComplaintSeverity = ComplaintSeverity.MEDIUM
    attachment_urls: list[str] = Field(
        default_factory=list, max_length=10
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Title must contain at least 3 characters")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Description cannot be empty")
        return value

    @field_validator("attachment_urls")
    @classmethod
    def validate_attachment_urls(
        cls, values: list[str]
    ) -> list[str]:
        cleaned = []
        for value in values:
            value = value.strip()
            parsed = urlparse(value)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.netloc
            ):
                raise ValueError(
                    "Each attachment must be a valid HTTP or HTTPS URL"
                )
            cleaned.append(value)
        return cleaned


class ComplaintUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(
        default=None, min_length=1, max_length=10000
    )
    priority: ComplaintPriority | None = None
    severity: ComplaintSeverity | None = None
    attachment_urls: list[str] | None = Field(
        default=None, max_length=10
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if len(value) < 3:
                raise ValueError("Title must contain at least 3 characters")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Description cannot be empty")
        return value

    @field_validator("attachment_urls")
    @classmethod
    def validate_attachment_urls(
        cls, values: list[str] | None
    ) -> list[str] | None:
        if values is None:
            return values
        cleaned = []
        for value in values:
            value = value.strip()
            parsed = urlparse(value)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.netloc
            ):
                raise ValueError(
                    "Each attachment must be a valid HTTP or HTTPS URL"
                )
            cleaned.append(value)
        return cleaned

    @model_validator(mode="after")
    def require_update(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        if any(
            value is None for value in self.model_dump().values()
            if False
        ):
            raise ValueError("Invalid update")
        return self



class ComplaintStatusUpdate(BaseModel):
    status: ComplaintStatus
    resolution_details: str | None = Field(
        default=None,
        min_length=5,
        max_length=10000,
    )
    reason: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator("resolution_details")
    @classmethod
    def validate_resolution_details(
        cls, value: str | None
    ) -> str | None:
        if value is not None:
            value = value.strip()
            if len(value) < 5:
                raise ValueError(
                    "Resolution details must contain at least 5 characters"
                )
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(
        cls, value: str | None
    ) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                return None
        return value


class ComplaintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference_number: str
    customer_id: int
    category_id: int
    title: str
    description: str
    priority: str
    severity: str
    status: str
    attachment_urls: list[str]
    created_at: datetime
    updated_at: datetime


class ComplaintListResponse(BaseModel):
    items: list[ComplaintResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
