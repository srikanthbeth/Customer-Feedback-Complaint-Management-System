from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import satisfaction_analytics_service as analytics
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc


def make_feedback(
    rating,
    category="SERVICE",
    day=date(2026, 10, 20),
    complaint_id=None,
):
    return SimpleNamespace(
        id=rating,
        rating=rating,
        category=category,
        complaint_id=complaint_id,
        feedback_date=datetime(
            day.year, day.month, day.day, 10, 0, tzinfo=UTC
        ),
    )


def test_overall_satisfaction_metrics():
    feedback = [
        make_feedback(5),
        make_feedback(4),
        make_feedback(3),
        make_feedback(2),
        make_feedback(1),
    ]

    result = analytics.summarize(feedback)

    assert result["feedback_count"] == 5
    assert result["rated_feedback_count"] == 5
    assert result["average_rating"] == 3.0
    assert result["positive_feedback_count"] == 2
    assert result["neutral_feedback_count"] == 1
    assert result["negative_feedback_count"] == 2
    assert result["satisfaction_percentage"] == 40.0


def test_empty_feedback_returns_zero_satisfaction():
    result = analytics.summarize([])

    assert result["feedback_count"] == 0
    assert result["rated_feedback_count"] == 0
    assert result["average_rating"] is None
    assert result["positive_feedback_count"] == 0
    assert result["neutral_feedback_count"] == 0
    assert result["negative_feedback_count"] == 0
    assert result["satisfaction_percentage"] == 0.0


def test_category_wise_ratings():
    feedback = [
        make_feedback(5, category="SERVICE"),
        make_feedback(4, category="SERVICE"),
        make_feedback(2, category="DELIVERY"),
    ]

    query = MagicMock()
    query.all.return_value = feedback

    db = MagicMock()
    db.query.return_value = query

    result = analytics.get_category_ratings(db)

    by_category = {item["category"]: item for item in result}

    assert by_category["SERVICE"]["feedback_count"] == 2
    assert by_category["SERVICE"]["average_rating"] == 4.5
    assert by_category["SERVICE"]["satisfaction_percentage"] == 100.0

    assert by_category["DELIVERY"]["feedback_count"] == 1
    assert by_category["DELIVERY"]["average_rating"] == 2.0
    assert by_category["DELIVERY"]["satisfaction_percentage"] == 0.0


def test_feedback_trends_by_date():
    feedback = [
        make_feedback(5, day=date(2026, 10, 20)),
        make_feedback(3, day=date(2026, 10, 20)),
        make_feedback(2, day=date(2026, 10, 21)),
    ]

    query = MagicMock()
    query.all.return_value = feedback

    db = MagicMock()
    db.query.return_value = query

    result = analytics.get_feedback_trends(
        db,
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 22),
    )

    assert len(result) == 3

    assert result[0]["date"] == date(2026, 10, 20)
    assert result[0]["feedback_count"] == 2
    assert result[0]["average_rating"] == 4.0

    assert result[1]["date"] == date(2026, 10, 21)
    assert result[1]["feedback_count"] == 1
    assert result[1]["negative_feedback_count"] == 1

    assert result[2]["date"] == date(2026, 10, 22)
    assert result[2]["feedback_count"] == 0
    assert result[2]["average_rating"] is None


def test_date_filter_excludes_feedback_outside_range():
    feedback = [
        make_feedback(5, day=date(2026, 10, 19)),
        make_feedback(4, day=date(2026, 10, 20)),
        make_feedback(2, day=date(2026, 10, 21)),
    ]

    result = analytics.filter_by_date(
        feedback,
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 20),
    )

    assert len(result) == 1
    assert result[0].rating == 4


def test_invalid_date_range_is_rejected():
    feedback = [make_feedback(5)]

    with pytest.raises(
        ValueError,
        match="start_date cannot be after end_date",
    ):
        analytics.filter_by_date(
            feedback,
            start_date=date(2026, 10, 22),
            end_date=date(2026, 10, 20),
        )


def test_resolved_complaint_satisfaction():
    complaints = [
        SimpleNamespace(id=1, status="RESOLVED"),
        SimpleNamespace(id=2, status="CLOSED"),
        SimpleNamespace(id=3, status="IN_PROGRESS"),
    ]

    feedback = [
        make_feedback(5, complaint_id=1),
        make_feedback(4, complaint_id=1),
        make_feedback(2, complaint_id=2),
        make_feedback(1, complaint_id=3),
        make_feedback(5, complaint_id=None),
    ]

    complaint_query = MagicMock()
    complaint_query.all.return_value = complaints

    feedback_query = MagicMock()
    feedback_query.all.return_value = feedback

    db = MagicMock()
    db.query.side_effect = [
        complaint_query,
        feedback_query,
    ]

    result = analytics.get_resolved_complaint_satisfaction(db)

    assert result["resolved_complaint_count"] == 2
    assert result["feedback_count"] == 3
    assert result["rated_feedback_count"] == 3
    assert result["average_rating"] == pytest.approx(11 / 3, abs=0.01)
    assert result["positive_feedback_count"] == 2
    assert result["negative_feedback_count"] == 1
    assert result["satisfaction_percentage"] == pytest.approx(66.67, abs=0.01)


def test_naive_feedback_timestamp_is_treated_as_utc():
    feedback = SimpleNamespace(
        feedback_date=datetime(2026, 10, 20, 23, 30)
    )

    assert analytics.feedback_day(feedback) == date(2026, 10, 20)


def test_aware_feedback_timestamp_is_converted_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))

    feedback = SimpleNamespace(
        feedback_date=datetime(2026, 10, 21, 2, 0, tzinfo=ist)
    )

    # 02:00 IST is 20:30 UTC on the previous calendar day.
    assert analytics.feedback_day(feedback) == date(2026, 10, 20)