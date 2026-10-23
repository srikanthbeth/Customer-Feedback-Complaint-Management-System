
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.feedback import Feedback
from models.feedback_history import FeedbackHistory


def create_feedback(db: Session, feedback: Feedback) -> Feedback:
    db.add(feedback)
    db.flush()
    return feedback


def get_feedback(
    db: Session,
    feedback_id: int,
) -> Feedback | None:
    return db.get(Feedback, feedback_id)


def list_feedback(
    db: Session,
    customer_id: int | None = None,
) -> list[Feedback]:
    statement = select(Feedback).order_by(
        Feedback.created_at.desc(), Feedback.id.desc()
    )

    if customer_id is not None:
        statement = statement.where(
            Feedback.customer_id == customer_id
        )

    return list(db.scalars(statement).all())


def add_history(
    db: Session,
    history: FeedbackHistory,
) -> FeedbackHistory:
    db.add(history)
    db.flush()
    return history


def list_history(
    db: Session,
    feedback_id: int,
) -> list[FeedbackHistory]:
    statement = (
        select(FeedbackHistory)
        .where(FeedbackHistory.feedback_id == feedback_id)
        .order_by(
            FeedbackHistory.changed_at.asc(),
            FeedbackHistory.id.asc(),
        )
    )
    return list(db.scalars(statement).all())
