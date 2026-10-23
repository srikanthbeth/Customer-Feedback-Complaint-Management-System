
from datetime import date, datetime, time, timedelta, timezone
from math import ceil

from sqlalchemy.orm import Session

from models.complaint import Complaint


def create_complaint(db: Session, complaint: Complaint) -> Complaint:
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


def get_complaint(
    db: Session, complaint_id: int
) -> Complaint | None:
    return (
        db.query(Complaint)
        .filter(Complaint.id == complaint_id)
        .first()
    )


def list_complaints(
    db: Session,
    *,
    customer_id: int | None = None,
    category_id: int | None = None,
    assigned_to: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    severity: str | None = None,
    search: str | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    resolved_from: date | None = None,
    resolved_to: date | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")

    if created_from and created_to and created_from > created_to:
        raise ValueError("created_from cannot be after created_to")

    if resolved_from and resolved_to and resolved_from > resolved_to:
        raise ValueError("resolved_from cannot be after resolved_to")

    sort_fields = {
        "id": Complaint.id,
        "created_at": Complaint.created_at,
        "updated_at": Complaint.updated_at,
        "priority": Complaint.priority,
        "status": Complaint.status,
        "title": Complaint.title,
        "resolved_at": Complaint.resolved_at,
        "category_id": Complaint.category_id,
        "customer_id": Complaint.customer_id,
        "assigned_to": Complaint.assigned_to,
    }

    if sort_by not in sort_fields:
        raise ValueError("Invalid sort_by field")

    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be 'asc' or 'desc'")

    query = db.query(Complaint)

    # Exact-match filters
    if customer_id is not None:
        query = query.filter(Complaint.customer_id == customer_id)

    if category_id is not None:
        query = query.filter(Complaint.category_id == category_id)

    if assigned_to is not None:
        query = query.filter(Complaint.assigned_to == assigned_to)

    if status:
        query = query.filter(Complaint.status == status.upper())

    if priority:
        query = query.filter(Complaint.priority == priority.upper())

    if severity:
        query = query.filter(Complaint.severity == severity.upper())

    # Keyword search stays in the database.
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            Complaint.title.ilike(pattern)
            | Complaint.description.ilike(pattern)
            | Complaint.reference_number.ilike(pattern)
        )

    # Date filters use inclusive calendar days.
    # The upper boundary is exclusive, avoiding end-of-day precision issues.
    if created_from is not None:
        created_start = datetime.combine(
            created_from, time.min, tzinfo=timezone.utc
        )
        query = query.filter(Complaint.created_at >= created_start)

    if created_to is not None:
        created_end_exclusive = datetime.combine(
            created_to + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        query = query.filter(
            Complaint.created_at < created_end_exclusive
        )

    if resolved_from is not None:
        resolved_start = datetime.combine(
            resolved_from, time.min, tzinfo=timezone.utc
        )
        query = query.filter(Complaint.resolved_at >= resolved_start)

    if resolved_to is not None:
        resolved_end_exclusive = datetime.combine(
            resolved_to + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        query = query.filter(
            Complaint.resolved_at < resolved_end_exclusive
        )

    # Count only matching records, before pagination.
    total = query.order_by(None).count()

    column = sort_fields[sort_by]
    if sort_order == "desc":
        column = column.desc()
    else:
        column = column.asc()

    items = (
        query.order_by(column, Complaint.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    }


def update_complaint(
    db: Session,
    complaint: Complaint,
    updates: dict,
) -> Complaint:
    for field, value in updates.items():
        setattr(complaint, field, value)

    db.commit()
    db.refresh(complaint)
    return complaint
