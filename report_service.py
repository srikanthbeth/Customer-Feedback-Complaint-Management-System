
from datetime import date, datetime, time, timedelta, timezone
from math import ceil

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models.customer import Customer
from models.feedback import Feedback
from models.complaint import Complaint
from models.user import User
from services.sla_service import calculate_sla


UTC = timezone.utc

RESOLVED_STATUSES = {"RESOLVED", "CLOSED"}
OPEN_STATUSES = {
    "OPEN",
    "ASSIGNED",
    "IN_PROGRESS",
    "WAITING_FOR_CUSTOMER",
    "REOPENED",
}

SORTABLE_COMPLAINT_FIELDS = {
    "id": Complaint.id,
    "reference_number": Complaint.reference_number,
    "title": Complaint.title,
    "priority": Complaint.priority,
    "severity": Complaint.severity,
    "status": Complaint.status,
    "created_at": Complaint.created_at,
    "resolved_at": Complaint.resolved_at,
}


def utc_start(value: date):
    return datetime.combine(value, time.min, tzinfo=UTC)


def utc_end_exclusive(value: date):
    return datetime.combine(
        value + timedelta(days=1),
        time.min,
        tzinfo=UTC,
    )


def validate_dates(start_date: date | None, end_date: date | None):
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date cannot be after end_date")


def apply_date_filter(query, model, start_date=None, end_date=None):
    if start_date:
        query = query.filter(model.created_at >= utc_start(start_date))

    if end_date:
        query = query.filter(
            model.created_at < utc_end_exclusive(end_date)
        )

    return query


def get_dashboard_summary(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    validate_dates(start_date, end_date)

    customer_query = db.query(func.count(Customer.id))
    feedback_query = db.query(func.count(Feedback.id))
    complaint_query = db.query(Complaint)

    customer_query = apply_date_filter(
        customer_query, Customer, start_date, end_date
    )
    feedback_query = apply_date_filter(
        feedback_query, Feedback, start_date, end_date
    )
    complaint_query = apply_date_filter(
        complaint_query, Complaint, start_date, end_date
    )

    total_customers = customer_query.scalar() or 0
    total_feedback = feedback_query.scalar() or 0
    complaints = complaint_query.all()

    open_complaints = sum(
        complaint.status in OPEN_STATUSES
        for complaint in complaints
    )

    resolved_complaints = sum(
        complaint.status in RESOLVED_STATUSES
        for complaint in complaints
    )

    now = datetime.now(UTC)
    overdue_complaints = sum(
        calculate_sla(complaint, now=now)["is_overdue"]
        for complaint in complaints
    )

    # Average resolution time uses complaints resolved during the
    # selected period, measured from creation to resolved_at.
    resolution_query = db.query(
        func.avg(
            func.extract(
                "epoch",
                Complaint.resolved_at - Complaint.created_at,
            )
        )
    ).filter(Complaint.resolved_at.isnot(None))

    if start_date:
        resolution_query = resolution_query.filter(
            Complaint.resolved_at >= utc_start(start_date)
        )

    if end_date:
        resolution_query = resolution_query.filter(
            Complaint.resolved_at < utc_end_exclusive(end_date)
        )

    average_seconds = resolution_query.scalar()
    average_resolution_hours = (
        round(float(average_seconds) / 3600, 2)
        if average_seconds is not None
        else None
    )

    rating_query = db.query(func.avg(Feedback.rating))
    rating_query = apply_date_filter(
        rating_query, Feedback, start_date, end_date
    )
    average_rating = rating_query.scalar()

    return {
        "total_customers": total_customers,
        "total_feedback_submissions": total_feedback,
        "total_complaints": len(complaints),
        "open_complaints": open_complaints,
        "resolved_complaints": resolved_complaints,
        "overdue_complaints": overdue_complaints,
        "average_resolution_time_hours": average_resolution_hours,
        "average_customer_rating": (
            round(float(average_rating), 2)
            if average_rating is not None
            else None
        ),
    }


def get_complaints_by_priority(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    validate_dates(start_date, end_date)

    query = db.query(
        Complaint.priority,
        func.count(Complaint.id).label("complaint_count"),
    )
    query = apply_date_filter(
        query, Complaint, start_date, end_date
    )

    rows = (
        query.group_by(Complaint.priority)
        .order_by(Complaint.priority)
        .all()
    )

    return [
        {
            "priority": row.priority,
            "complaint_count": row.complaint_count,
        }
        for row in rows
    ]


def get_agent_performance(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    validate_dates(start_date, end_date)

    query = (
        db.query(
            User.id.label("agent_id"),
            User.email.label("agent_email"),
            func.count(Complaint.id).label("total_assigned"),
            func.sum(
                func.cast(
                    Complaint.status.in_(list(OPEN_STATUSES)),
                    type_=__import__("sqlalchemy").Integer,
                )
            ).label("open_complaints"),
            func.sum(
                func.cast(
                    Complaint.status.in_(list(RESOLVED_STATUSES)),
                    type_=__import__("sqlalchemy").Integer,
                )
            ).label("resolved_complaints"),
        )
        .join(Complaint, Complaint.assigned_to == User.id)
        .filter(User.role == "SUPPORT_AGENT")
    )

    query = apply_date_filter(
        query, Complaint, start_date, end_date
    )

    rows = (
        query.group_by(User.id, User.email)
        .order_by(User.email)
        .all()
    )

    return [
        {
            "agent_id": row.agent_id,
            "agent_email": row.agent_email,
            "total_assigned": row.total_assigned,
            "open_complaints": row.open_complaints or 0,
            "resolved_complaints": row.resolved_complaints or 0,
        }
        for row in rows
    ]


def get_complaint_report(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    priority: str | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict:
    validate_dates(start_date, end_date)

    if sort_by not in SORTABLE_COMPLAINT_FIELDS:
        raise ValueError("Invalid sort_by field")

    if sort_order.lower() not in {"asc", "desc"}:
        raise ValueError("sort_order must be 'asc' or 'desc'")

    query = apply_date_filter(
        db.query(Complaint),
        Complaint,
        start_date,
        end_date,
    )

    if status:
        query = query.filter(Complaint.status == status.upper())

    if priority:
        query = query.filter(Complaint.priority == priority.upper())

    total = query.count()
    sort_column = SORTABLE_COMPLAINT_FIELDS[sort_by]

    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc(), Complaint.id.asc())
    else:
        query = query.order_by(sort_column.desc(), Complaint.id.desc())

    items = (
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
        "items": items,
    }
