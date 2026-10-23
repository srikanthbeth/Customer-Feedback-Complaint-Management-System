
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.complaint import Complaint


# SLA targets are measured in elapsed hours, using UTC timestamps.
# CRITICAL = 1 hour is a configurable default.
SLA_HOURS = {
    "CRITICAL": 1,
    "HIGH": 4,
    "MEDIUM": 12,
    "LOW": 24,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Treat naive database timestamps as UTC and normalize aware values."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def get_sla_hours(priority: str) -> int:
    """Return the configured SLA duration for a complaint priority."""
    normalized_priority = priority.upper()

    if normalized_priority not in SLA_HOURS:
        raise ValueError(
            f"Unsupported complaint priority: {priority}"
        )

    return SLA_HOURS[normalized_priority]


def calculate_sla(
    complaint: Complaint,
    now: datetime | None = None,
) -> dict:
    """Calculate the SLA deadline, remaining time, and breach status."""
    current_time = as_utc(now) if now is not None else utc_now()
    created_at = as_utc(complaint.created_at)

    if created_at is None:
        raise ValueError("Complaint creation time is missing")

    resolved_at = as_utc(complaint.resolved_at)
    sla_hours = get_sla_hours(complaint.priority)
    deadline = created_at + timedelta(hours=sla_hours)

    is_resolved = resolved_at is not None
    is_terminal = complaint.status in {"RESOLVED", "CLOSED"}

    # Resolution duration is measured from creation until resolution.
    resolution_duration_seconds = None
    if resolved_at is not None:
        resolution_duration_seconds = max(
            0,
            int((resolved_at - created_at).total_seconds()),
        )

    # A resolved complaint breaches its SLA if it was resolved late.
    # An unresolved complaint breaches its SLA after its deadline passes.
    if resolved_at is not None:
        sla_breached = resolved_at > deadline
        is_overdue = False
        time_remaining_seconds = None
        overdue_seconds = max(
            0,
            int((resolved_at - deadline).total_seconds()),
        )
    else:
        is_overdue = current_time > deadline and not is_terminal
        sla_breached = is_overdue
        time_remaining_seconds = max(
            0,
            int((deadline - current_time).total_seconds()),
        )
        overdue_seconds = max(
            0,
            int((current_time - deadline).total_seconds()),
        ) if is_overdue else 0

    return {
        "complaint_id": complaint.id,
        "reference_number": complaint.reference_number,
        "priority": complaint.priority,
        "status": complaint.status,
        "sla_hours": sla_hours,
        "created_at": created_at,
        "sla_deadline": deadline,
        "resolved_at": resolved_at,
        "time_remaining_seconds": time_remaining_seconds,
        "overdue_seconds": overdue_seconds,
        "resolution_duration_seconds": resolution_duration_seconds,
        "is_overdue": is_overdue,
        "sla_breached": sla_breached,
    }


def get_complaint_sla(
    db: Session,
    complaint_id: int,
) -> dict:
    complaint = (
        db.query(Complaint)
        .filter(Complaint.id == complaint_id)
        .first()
    )

    if complaint is None:
        raise LookupError("Complaint not found")

    return calculate_sla(complaint)


def get_overdue_complaints(db: Session) -> list[dict]:
    """Return unresolved complaints that have exceeded their SLA."""
    complaints = (
        db.query(Complaint)
        .filter(
            Complaint.status.notin_(["RESOLVED", "CLOSED"]),
        )
        .all()
    )

    results = []

    for complaint in complaints:
        sla = calculate_sla(complaint)

        if sla["is_overdue"]:
            results.append(sla)

    return sorted(
        results,
        key=lambda item: item["sla_deadline"],
    )
