from datetime import date

from pydantic import BaseModel, ConfigDict


class SatisfactionMetrics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feedback_count: int
    rated_feedback_count: int
    average_rating: float | None
    positive_feedback_count: int
    neutral_feedback_count: int
    negative_feedback_count: int
    satisfaction_percentage: float


class CategoryRating(BaseModel):
    category: str
    feedback_count: int
    rated_feedback_count: int
    average_rating: float | None
    positive_feedback_count: int
    neutral_feedback_count: int
    negative_feedback_count: int
    satisfaction_percentage: float


class FeedbackTrendPoint(BaseModel):
    date: date
    feedback_count: int
    rated_feedback_count: int
    average_rating: float | None
    positive_feedback_count: int
    neutral_feedback_count: int
    negative_feedback_count: int
    satisfaction_percentage: float


class ResolvedComplaintSatisfaction(BaseModel):
    resolved_complaint_count: int
    feedback_count: int
    rated_feedback_count: int
    average_rating: float | None
    positive_feedback_count: int
    neutral_feedback_count: int
    negative_feedback_count: int
    satisfaction_percentage: float


class SatisfactionDashboard(BaseModel):
    overall: SatisfactionMetrics
    category_ratings: list[CategoryRating]
    resolved_complaints: ResolvedComplaintSatisfaction