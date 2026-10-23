from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from models.complaint import Complaint
from models.feedback import Feedback


UTC = timezone.utc
POSITIVE_MINIMUM = 4
NEGATIVE_MAXIMUM = 2
RESOLVED_STATUSES = {"RESOLVED", "CLOSED"}


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def feedback_day(feedback: Feedback) -> date:
    return as_utc(feedback.feedback_date).date()


def filter_by_date(
    feedback_items: list[Feedback],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Feedback]:
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date cannot be after end_date")

    result = []

    for item in feedback_items:
        item_date = feedback_day(item)

        if start_date and item_date < start_date:
            continue
        if end_date and item_date > end_date:
            continue

        result.append(item)

    return result


def summarize(feedback_items: list[Feedback]) -> dict:
    # Feedback.rating is constrained to 1..5 in the existing model.
    ratings = [
        item.rating
        for item in feedback_items
        if item.rating is not None
    ]

    positive = sum(rating >= POSITIVE_MINIMUM for rating in ratings)
    negative = sum(rating <= NEGATIVE_MAXIMUM for rating in ratings)
    neutral = sum(
        NEGATIVE_MAXIMUM < rating < POSITIVE_MINIMUM
        for rating in ratings
    )

    rated_count = len(ratings)

    return {
        "feedback_count": len(feedback_items),
        "rated_feedback_count": rated_count,
        "average_rating": (
            round(sum(ratings) / rated_count, 2)
            if rated_count else None
        ),
        "positive_feedback_count": positive,
        "neutral_feedback_count": neutral,
        "negative_feedback_count": negative,
        "satisfaction_percentage": (
            round(positive / rated_count * 100, 2)
            if rated_count else 0.0
        ),
    }


def get_all_feedback(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Feedback]:
    feedback_items = db.query(Feedback).all()
    return filter_by_date(feedback_items, start_date, end_date)


def get_overall_satisfaction(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    return summarize(get_all_feedback(db, start_date, end_date))


def get_category_ratings(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    feedback_items = get_all_feedback(db, start_date, end_date)
    grouped = defaultdict(list)

    for item in feedback_items:
        grouped[item.category].append(item)

    results = []

    for category in sorted(grouped):
        results.append({
            "category": category,
            **summarize(grouped[category]),
        })

    return results


def get_feedback_trends(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    feedback_items = get_all_feedback(db, start_date, end_date)
    grouped = defaultdict(list)

    for item in feedback_items:
        grouped[feedback_day(item)].append(item)

    # Include dates with zero feedback when both bounds are provided.
    if start_date and end_date:
        current = start_date
        while current <= end_date:
            grouped.setdefault(current, [])
            current += timedelta(days=1)

    return [
        {"date": day, **summarize(grouped[day])}
        for day in sorted(grouped)
    ]


def get_resolved_complaint_satisfaction(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    complaints = db.query(Complaint).all()

    resolved_ids = {
        item.id
        for item in complaints
        if item.status in RESOLVED_STATUSES
    }

    feedback_items = get_all_feedback(db, start_date, end_date)

    linked_feedback = [
        item for item in feedback_items
        if item.complaint_id in resolved_ids
    ]

    linked_complaint_ids = {
        item.complaint_id
        for item in linked_feedback
        if item.complaint_id is not None
    }

    return {
        "resolved_complaint_count": len(linked_complaint_ids),
        **summarize(linked_feedback),
    }


def get_satisfaction_dashboard(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    return {
        "overall": get_overall_satisfaction(db, start_date, end_date),
        "category_ratings": get_category_ratings(
            db, start_date, end_date
        ),
        "resolved_complaints": get_resolved_complaint_satisfaction(
            db, start_date, end_date
        ),
    }