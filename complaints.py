
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from datetime import date
from database import get_db
from dependencies import get_current_user, require_roles
from models.complaint import Complaint
from models.user import User
from repositories import complaint_repository
from schemas.complaint import (
    ComplaintCreate,
    ComplaintListResponse,
    ComplaintResponse,
    ComplaintStatusUpdate,
    ComplaintUpdate,
)
from services import complaint_service, customer_service


router = APIRouter(prefix="/complaints", tags=["Complaints"])

MANAGER_ROLES = ("ADMIN", "SUPPORT_MANAGER")
STAFF_ROLES = ("ADMIN", "SUPPORT_MANAGER", "SUPPORT_AGENT")


def get_customer_for_user(db: Session, user: User):
    customer = customer_service.get_customer_by_email(db, user.email)

    if customer is None:
        raise HTTPException(
            status_code=404, detail="Customer profile not found"
        )

    if not customer.is_active:
        raise HTTPException(
            status_code=403, detail="Customer profile is inactive"
        )

    return customer


def get_accessible_complaint(
    db: Session, complaint_id: int, user: User
) -> Complaint:
    complaint = complaint_repository.get_complaint(db, complaint_id)

    if complaint is None:
        raise HTTPException(
            status_code=404, detail="Complaint not found"
        )

    if user.role == "CUSTOMER":
        customer = get_customer_for_user(db, user)

        if complaint.customer_id != customer.id:
            raise HTTPException(
                status_code=403,
                detail="You can only access your own complaints",
            )

    elif user.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access complaints",
        )

    return complaint


@router.post(
    "",
    response_model=ComplaintResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_complaint(
    data: ComplaintCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CUSTOMER")),
):
    customer = get_customer_for_user(db, current_user)

    try:
        return complaint_service.create_complaint(db, customer, data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=ComplaintListResponse)
def list_complaints(
    category_id: int | None = Query(default=None, gt=0),
    complaint_status: str | None = Query(
        default=None, alias="status", max_length=30
    ),
    priority: str | None = Query(default=None, max_length=20),
    severity: str | None = Query(default=None, max_length=20),
    search: str | None = Query(default=None, max_length=200),
    assigned_to: int | None = Query(default=None, gt=0),
    customer_id: int | None = Query(default=None, gt=0),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    resolved_from: date | None = Query(default=None),
    resolved_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(
        default="desc", pattern="^(asc|desc)$"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "CUSTOMER":
        customer = get_customer_for_user(db, current_user)

        # Never allow customers to list another customer's complaints.
        if customer_id is not None and customer_id != customer.id:
            raise HTTPException(
                status_code=403,
                detail="You can only access your own complaints",
            )

        effective_customer_id = customer.id

    elif current_user.role in STAFF_ROLES:
        effective_customer_id = customer_id

    else:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to list complaints",
        )

    allowed_sorts = {
        "id",
        "created_at",
        "updated_at",
        "priority",
        "status",
        "title",
        "resolved_at",
        "category_id",
        "customer_id",
        "assigned_to",
    }

    if sort_by not in allowed_sorts:
        raise HTTPException(
            status_code=422,
            detail="Invalid sort_by field",
        )

    if created_from and created_to and created_from > created_to:
        raise HTTPException(
            status_code=422,
            detail="created_from cannot be after created_to",
        )

    if resolved_from and resolved_to and resolved_from > resolved_to:
        raise HTTPException(
            status_code=422,
            detail="resolved_from cannot be after resolved_to",
        )

    return complaint_repository.list_complaints(
        db,
        customer_id=effective_customer_id,
        category_id=category_id,
        assigned_to=assigned_to,
        status=complaint_status.upper() if complaint_status else None,
        priority=priority.upper() if priority else None,
        severity=severity.upper() if severity else None,
        search=search,
        created_from=created_from,
        created_to=created_to,
        resolved_from=resolved_from,
        resolved_to=resolved_to,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/{complaint_id}", response_model=ComplaintResponse)
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_accessible_complaint(db, complaint_id, current_user)


@router.patch("/{complaint_id}", response_model=ComplaintResponse)
def edit_complaint(
    complaint_id: int,
    data: ComplaintUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    complaint = get_accessible_complaint(db, complaint_id, current_user)

    if current_user.role == "CUSTOMER":
        if complaint.status != "OPEN":
            raise HTTPException(
                status_code=409,
                detail="Customers can only edit OPEN complaints",
            )

    elif current_user.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only managers can edit other customers' complaints",
        )

    try:
        return complaint_service.update_complaint(db, complaint, data)

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{complaint_id}/status",
    response_model=ComplaintResponse,
)
def edit_complaint_status(
    complaint_id: int,
    data: ComplaintStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    complaint = complaint_repository.get_complaint(db, complaint_id)

    if complaint is None:
        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    try:
        return complaint_service.update_complaint_status(
            db=db,
            complaint=complaint,
            new_status=data.status.value,
            actor_id=current_user.id,
            reason=data.reason,
            resolution_details=data.resolution_details,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
