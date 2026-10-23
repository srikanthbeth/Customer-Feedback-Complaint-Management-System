
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from models.complaint import Complaint
from models.complaint_assignment_history import (
    ComplaintAssignmentHistory,
)
from models.user import User
from repositories import agent_assignment_repository as repository


def assign_complaint(
    db: Session,
    complaint: Complaint,
    agent_id: int,
    manager_id: int,
    note: str | None = None,
) -> Complaint:
    agent = repository.get_agent(db, agent_id)

    if agent is None or agent.role != "SUPPORT_AGENT":
        raise LookupError("Support agent not found")

    if not agent.is_active:
        raise ValueError("Cannot assign complaints to inactive agents")

    previous_agent_id = complaint.assigned_to

    if previous_agent_id == agent.id:
        raise ValueError("Complaint is already assigned to this agent")

    action = (
        "REASSIGNED"
        if previous_agent_id is not None
        else "ASSIGNED"
    )

    complaint.assigned_to = agent.id
    complaint.assigned_at = repository.utc_now() if hasattr(
        repository, "utc_now"
    ) else None

    if complaint.status == "OPEN":
        complaint.status = "ASSIGNED"

    history = ComplaintAssignmentHistory(
        complaint_id=complaint.id,
        previous_agent_id=previous_agent_id,
        new_agent_id=agent.id,
        assigned_by=manager_id,
        action=action,
        note=note.strip() if note else None,
    )

    try:
        repository.save_assignment(db, complaint, history)
    except Exception:
        db.rollback()
        raise

    return complaint


def get_agent_or_raise(
    db: Session,
    agent_id: int,
) -> User:
    agent = repository.get_agent(db, agent_id)

    if agent is None or agent.role != "SUPPORT_AGENT":
        raise LookupError("Support agent not found")

    return agent


def get_assignment_history(
    db: Session,
    complaint_id: int,
) -> list[ComplaintAssignmentHistory]:
    complaint = repository.get_complaint(db, complaint_id)

    if complaint is None:
        raise LookupError("Complaint not found")

    return repository.get_assignment_history(db, complaint_id)


def get_agent_workload(
    db: Session,
    agent_id: int,
) -> dict:
    agent = get_agent_or_raise(db, agent_id)

    workload = repository.get_agent_workload(db, agent.id)

    return {
        "agent_id": agent.id,
        "agent_name": agent.full_name,
        "agent_email": agent.email,
        **workload,
    }


def list_assigned_complaints(
    db: Session,
    agent_id: int,
    page: int = 1,
    page_size: int = 10,
):
    get_agent_or_raise(db, agent_id)

    return repository.list_assigned_complaints(
        db, agent_id, page, page_size
    )
