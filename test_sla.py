
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import sla_service


UTC = timezone.utc


def make_complaint(
    priority="HIGH",
    status="OPEN",
    created_at=None,
    resolved_at=None,
    complaint_id=1,
):
    """Create a lightweight complaint for unit tests."""
    return SimpleNamespace(
        id=complaint_id,
        reference_number=f"CMP-{complaint_id:04d}",
        priority=priority,
        status=status,
        created_at=created_at or datetime(
            2026, 10, 20, 8, 0, tzinfo=UTC
        ),
        resolved_at=resolved_at,
    )


# ---------------------------------------------------------
# 1. Priority-based SLA targets
# ---------------------------------------------------------

@pytest.mark.parametrize(
    ("priority", "expected_hours"),
    [
        ("CRITICAL", 1),
        ("HIGH", 4),
        ("MEDIUM", 12),
        ("LOW", 24),
        ("high", 4),
        ("Medium", 12),
    ],
)
def test_get_sla_hours(priority, expected_hours):
    assert sla_service.get_sla_hours(priority) == expected_hours


def test_get_sla_hours_rejects_unknown_priority():
    with pytest.raises(ValueError, match="Unsupported complaint priority"):
        sla_service.get_sla_hours("URGENT")


# ---------------------------------------------------------
# 2. SLA deadline calculation
# ---------------------------------------------------------

@pytest.mark.parametrize(
    ("priority", "expected_hours"),
    [
        ("CRITICAL", 1),
        ("HIGH", 4),
        ("MEDIUM", 12),
        ("LOW", 24),
    ],
)
def test_calculate_sla_deadline(priority, expected_hours):
    created_at = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    complaint = make_complaint(
        priority=priority,
        created_at=created_at,
    )

    result = sla_service.calculate_sla(
        complaint,
        now=created_at,
    )

    assert result["sla_hours"] == expected_hours
    assert result["sla_deadline"] == (
        created_at + timedelta(hours=expected_hours)
    )
    assert result["complaint_id"] == complaint.id
    assert result["reference_number"] == complaint.reference_number


# ---------------------------------------------------------
# 3. Time remaining
# ---------------------------------------------------------

def test_calculate_sla_time_remaining():
    created_at = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    now = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)

    complaint = make_complaint(
        priority="HIGH",
        created_at=created_at,
    )

    result = sla_service.calculate_sla(complaint, now=now)

    # High priority has a four-hour SLA.
    # Two hours remain after two hours have elapsed.
    assert result["time_remaining_seconds"] == 2 * 60 * 60
    assert result["is_overdue"] is False
    assert result["sla_breached"] is False
    assert result["overdue_seconds"] == 0


def test_calculate_sla_at_deadline_has_no_time_remaining():
    created_at = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    deadline = created_at + timedelta(hours=4)

    complaint = make_complaint(
        priority="HIGH",
        created_at=created_at,
    )

    result = sla_service.calculate_sla(
        complaint,
        now=deadline,
    )

    assert result["time_remaining_seconds"] == 0
    assert result["is_overdue"] is False
    assert result["sla_breached"] is False


# ---------------------------------------------------------
# 4. Overdue complaints
# ---------------------------------------------------------

def test_unresolved_complaint_is_overdue_after_deadline():
    created_at = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    now = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)

    complaint = make_complaint(
        priority="HIGH",
        status="IN_PROGRESS",
        created_at=created_at,
    )

    result = sla_service.calculate_sla(complaint, now=now)

    assert result["is_overdue"] is True
    assert result["sla_breached"] is True
    assert result["overdue_seconds"] == 60 * 60
    assert result["time_remaining_seconds"] == 0


def test_get_overdue_complaints_returns_only_overdue_items(monkeypatch):
    now = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)

    overdue = make_complaint(
        priority="HIGH",
        status="OPEN",
        created_at=datetime(2026, 10, 20, 8, 0, tzinfo=UTC),
        complaint_id=1,
    )

    not_overdue = make_complaint(
        priority="HIGH",
        status="OPEN",
        created_at=datetime(2026, 10, 20, 11, 0, tzinfo=UTC),
        complaint_id=2,
    )

    # Freeze the service clock so this test is deterministic.
    monkeypatch.setattr(sla_service, "utc_now", lambda: now)

    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.all.return_value = [
        not_overdue,
        overdue,
    ]

    results = sla_service.get_overdue_complaints(db)

    assert len(results) == 1
    assert results[0]["complaint_id"] == 1
    assert results[0]["is_overdue"] is True


def test_get_overdue_complaints_sorts_by_deadline(monkeypatch):
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

    later_deadline = make_complaint(
        priority="HIGH",
        created_at=datetime(2026, 10, 22, 6, 0, tzinfo=UTC),
        complaint_id=1,
    )

    earlier_deadline = make_complaint(
        priority="HIGH",
        created_at=datetime(2026, 10, 22, 5, 0, tzinfo=UTC),
        complaint_id=2,
    )

    monkeypatch.setattr(sla_service, "utc_now", lambda: now)

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        later_deadline,
        earlier_deadline,
    ]

    results = sla_service.get_overdue_complaints(db)

    assert [item["complaint_id"] for item in results] == [2, 1]


# ---------------------------------------------------------
# 5. Resolution duration and SLA breach
# ---------------------------------------------------------

def test_on_time_resolution_does_not_breach_sla():
    created_at = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    resolved_at = datetime(2026, 10, 20, 11, 0, tzinfo=UTC)

    complaint = make_complaint(
        priority="HIGH",
        status="RESOLVED",
        created_at=created_at,
        resolved_at=resolved_at,
    )

    result = sla_service.calculate_sla(
        complaint,
        now=resolved_at,
    )

    assert result["resolution_duration_seconds"] == 3 * 60 * 60
    assert result["sla_breached"] is False
    assert result["is_overdue"] is False
    assert result["overdue_seconds"] == 0
    assert result["time_remaining_seconds"] is None


def test_late_resolution_breaches_sla():
    created_at = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    resolved_at = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)

    complaint = make_complaint(
        priority="HIGH",
        status="RESOLVED",
        created_at=created_at,
        resolved_at=resolved_at,
    )

    result = sla_service.calculate_sla(
        complaint,
        now=resolved_at,
    )

    assert result["resolution_duration_seconds"] == 5 * 60 * 60
    assert result["sla_breached"] is True
    assert result["is_overdue"] is False
    assert result["overdue_seconds"] == 60 * 60


def test_unresolved_complaint_has_no_resolution_duration():
    complaint = make_complaint(status="IN_PROGRESS")

    result = sla_service.calculate_sla(
        complaint,
        now=complaint.created_at,
    )

    assert result["resolution_duration_seconds"] is None
    assert result["resolved_at"] is None


# ---------------------------------------------------------
# 6. UTC timezone handling
# ---------------------------------------------------------

def test_naive_timestamps_are_treated_as_utc():
    created_at = datetime(2026, 10, 20, 8, 0)
    now = datetime(2026, 10, 20, 10, 0)

    complaint = make_complaint(
        priority="HIGH",
        created_at=created_at,
    )

    result = sla_service.calculate_sla(complaint, now=now)

    assert result["created_at"].tzinfo == UTC
    assert result["sla_deadline"].tzinfo == UTC
    assert result["time_remaining_seconds"] == 2 * 60 * 60


def test_timezone_aware_timestamps_are_normalized_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))

    created_at = datetime(2026, 10, 20, 13, 30, tzinfo=ist)
    now = datetime(2026, 10, 20, 15, 30, tzinfo=ist)

    complaint = make_complaint(
        priority="HIGH",
        created_at=created_at,
    )

    result = sla_service.calculate_sla(complaint, now=now)

    expected_created_at = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)

    assert result["created_at"] == expected_created_at
    assert result["created_at"].tzinfo == UTC
    assert result["sla_deadline"] == (
        expected_created_at + timedelta(hours=4)
    )


def test_missing_creation_time_raises_error():
    complaint = make_complaint(created_at=None)
    complaint.created_at = None

    with pytest.raises(ValueError, match="creation time is missing"):
        sla_service.calculate_sla(
            complaint,
            now=datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
        )
