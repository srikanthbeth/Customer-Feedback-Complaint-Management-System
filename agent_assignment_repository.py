
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)

from models.complaint import Complaint
from models.complaint_assignment_history import (
    ComplaintAssignmentHistory,
)
from models.user import User


ACTIVE_STATUSES = (
    "ASSIGNED",
    "IN_PROGRESS",
    "WAITING_FOR_CUSTOMER",
    "REOPENED",
)


def get_agent(db: Session, agent_id: int) -> User | None:
    return (
        db.query(User)
        .filter(User.id == agent_id)
        .first()
    )


def list_agents(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.role == "SUPPORT_AGENT")
        .order_by(User.full_name.asc(), User.id.asc())
        .all()
    )


def get_complaint(
    db: Session, complaint_id: int
) -> Complaint | None:
    return (
        db.query(Complaint)
        .filter(Complaint.id == complaint_id)
        .first()
    )


def save_assignment(
    db: Session,
    complaint: Complaint,
    history: ComplaintAssignmentHistory,
) -> Complaint:
    try:
        db.add(history)
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
        db.refresh(history)
        return complaint
    except Exception:
        db.rollback()
        raise


def list_assigned_complaints(
    db: Session,
    agent_id: int,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[Complaint], int]:
    query = db.query(Complaint).filter(
        Complaint.assigned_to == agent_id
    )

    total = query.count()

    items = (
        query.order_by(
            Complaint.assigned_at.desc(),
            Complaint.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return items, total


def get_assignment_history(
    db: Session,
    complaint_id: int,
) -> list[ComplaintAssignmentHistory]:
    return (
        db.query(ComplaintAssignmentHistory)
        .filter(
            ComplaintAssignmentHistory.complaint_id
            == complaint_id
        )
        .order_by(
            ComplaintAssignmentHistory.assigned_at.desc(),
            ComplaintAssignmentHistory.id.desc(),
        )
        .all()
    )


def get_agent_workload(
    db: Session,
    agent_id: int,
) -> dict:
    total = (
        db.query(func.count(Complaint.id))
        .filter(Complaint.assigned_to == agent_id)
        .scalar()
        or 0
    )

    active = (
        db.query(func.count(Complaint.id))
        .filter(
            Complaint.assigned_to == agent_id,
            Complaint.status.in_(ACTIVE_STATUSES),
        )
        .scalar()
        or 0
    )

    resolved = (
        db.query(func.count(Complaint.id))
        .filter(
            Complaint.assigned_to == agent_id,
            Complaint.status.in_(("RESOLVED", "CLOSED")),
        )
        .scalar()
        or 0
    )

    return {
        "total_assigned": total,
        "active_complaints": active,
        "resolved_complaints": resolved,
    }
