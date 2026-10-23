
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models.user import User
from repositories import agent_assignment_repository as repository
from schemas.agent_assignment import (
    AgentAssignmentCreate,
    AgentWorkloadResponse,
    AssignmentHistoryResponse,
    AssignedComplaintResponse,
    SupportAgentResponse,
)
from services import agent_assignment_service as service


router = APIRouter(
    prefix="/agent-assignments",
    tags=["Agent Assignments"],
)

MANAGER_ROLES = ("ADMIN", "SUPPORT_MANAGER")


@router.get(
    "/agents",
    response_model=list[SupportAgentResponse],
)
def list_support_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    return repository.list_agents(db)


@router.post(
    "/complaints/{complaint_id}/assign",
    response_model=AssignedComplaintResponse,
)
def assign_complaint(
    complaint_id: int,
    data: AgentAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    complaint = repository.get_complaint(db, complaint_id)

    if complaint is None:
        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    try:
        return service.assign_complaint(
            db=db,
            complaint=complaint,
            agent_id=data.agent_id,
            manager_id=current_user.id,
            note=data.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/agents/{agent_id}/workload",
    response_model=AgentWorkloadResponse,
)
def agent_workload(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    try:
        return service.get_agent_workload(db, agent_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/agents/{agent_id}/complaints",
    response_model=list[AssignedComplaintResponse],
)
def agent_complaints(
    agent_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in MANAGER_ROLES:
        if (
            current_user.role != "SUPPORT_AGENT"
            or current_user.id != agent_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You can only view your own assigned complaints",
            )

    try:
        items, _ = service.list_assigned_complaints(
            db, agent_id, page, page_size
        )
        return items
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/complaints/{complaint_id}/history",
    response_model=list[AssignmentHistoryResponse],
)
def complaint_assignment_history(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    try:
        return service.get_assignment_history(db, complaint_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
