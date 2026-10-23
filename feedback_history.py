
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FeedbackHistory(Base):
    __tablename__ = "feedback_history"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("feedback.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    changed_by: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    action: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    changes: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
