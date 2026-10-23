from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.complaint import Complaint
from models.complaint_comment import ComplaintComment
from models.complaint_status_history import ComplaintStatusHistory
from repositories import resolution_workflow_repository as repository


ALLOWED_TRANSITIONS = {
    "OPEN": {"ASSIGNED", "IN_PROGRESS"},
    "ASSIGNED": {"IN_PROGRESS", "WAITING_FOR_CUSTOMER"},
    "IN_PROGRESS": {"WAITING_FOR_CUSTOMER", "RESOLVED"},
    "WAITING_FOR_CUSTOMER": {"IN_PROGRESS"},
    "RESOLVED": {"CLOSED", "REOPENED"},
    "CLOSED": {"REOPENED"},
    "REOPENED": {"IN_PROGRESS", "WAITING_FOR_CUSTOMER"},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def add_comment(
    db: Session,
    complaint: Complaint,
    author_id: int,
    content: str,
    is_internal: bool,
) -> ComplaintComment:
    comment = ComplaintComment(
        complaint_id=complaint.id,
        author_id=author_id,
        content=content.strip(),
        is_internal=is_internal,
    )
    return repository.create_comment(db, comment)


def get_comments(
    db: Session,
    complaint_id: int,
    include_internal: bool,
) -> list[ComplaintComment]:
    return repository.list_comments(
        db,
        complaint_id=complaint_id,
        include_internal=include_internal,
    )


def transition_status(
    db: Session,
    complaint: Complaint,
    new_status: str,
    actor_id: int,
    reason: str | None = None,
    resolution_details: str | None = None,
) -> Complaint:
    old_status = complaint.status
    new_status = new_status.upper()

    allowed = ALLOWED_TRANSITIONS.get(old_status, set())

    if new_status not in allowed:
        raise ValueError(
            f"Invalid status transition: {old_status} -> {new_status}"
        )

    if new_status == "RESOLVED":
        details = (
            resolution_details.strip()
            if resolution_details
            else ""
        )
        if len(details) < 5:
            raise ValueError(
                "Resolution details are required and must contain "
                "at least 5 characters"
            )
        complaint.resolution_details = details
        complaint.resolved_at = utc_now()

    if new_status == "CLOSED":
        if old_status != "RESOLVED":
            raise ValueError(
                "A complaint must be resolved before it can be closed"
            )
        complaint.closed_at = utc_now()

    if new_status == "REOPENED":
        complaint.resolved_at = None
        complaint.closed_at = None

    complaint.status = new_status
    complaint.updated_at = utc_now()

    history = ComplaintStatusHistory(
        complaint_id=complaint.id,
        previous_status=old_status,
        new_status=new_status,
        changed_by=actor_id,
        reason=reason.strip() if reason else None,
    )

    try:
        repository.create_status_history(db, history)
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
        return complaint
    except Exception:
        db.rollback()
        raise


def resolve_complaint(
    db: Session,
    complaint: Complaint,
    actor_id: int,
    resolution_details: str,
    reason: str | None = None,
) -> Complaint:
    return transition_status(
        db=db,
        complaint=complaint,
        new_status="RESOLVED",
        actor_id=actor_id,
        reason=reason,
        resolution_details=resolution_details,
    )


def close_complaint(
    db: Session,
    complaint: Complaint,
    actor_id: int,
    reason: str | None = None,
) -> Complaint:
    return transition_status(
        db=db,
        complaint=complaint,
        new_status="CLOSED",
        actor_id=actor_id,
        reason=reason,
    )


def reopen_complaint(
    db: Session,
    complaint: Complaint,
    actor_id: int,
    reason: str | None = None,
) -> Complaint:
    if complaint.status not in {"RESOLVED", "CLOSED"}:
        raise ValueError(
            "Only resolved or closed complaints can be reopened"
        )

    return transition_status(
        db=db,
        complaint=complaint,
        new_status="REOPENED",
        actor_id=actor_id,
        reason=reason,
    )


def get_status_history(
    db: Session,
    complaint_id: int,
) -> list[ComplaintStatusHistory]:
    return repository.list_status_history(db, complaint_id)