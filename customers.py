
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models.user import User
from schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerStatusUpdate,
    CustomerUpdate,
)
from services import customer_service

router = APIRouter(prefix="/customers", tags=["Customers"])


def get_owned_customer_or_403(
    customer_id: int,
    current_user: User,
    db: Session,
):
    try:
        customer = customer_service.get_customer(db, customer_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if current_user.role == "CUSTOMER":
        if customer.email.lower() != current_user.email.lower():
            raise HTTPException(
                status_code=403,
                detail="You can only access your own customer profile",
            )

        if not customer.is_active:
            raise HTTPException(
                status_code=403,
                detail="This customer profile is inactive",
            )

    return customer


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("ADMIN", "SUPPORT_MANAGER")
    ),
):
    try:
        return customer_service.create_customer(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "",
    response_model=CustomerListResponse,
)
def get_customers(
    search: str | None = Query(default=None, max_length=150),
    is_active: bool | None = None,
    city: str | None = Query(default=None, max_length=100),
    country: str | None = Query(default=None, max_length=100),
    company_name: str | None = Query(default=None, max_length=150),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    sort_by: Literal[
        "id", "full_name", "email", "city", "created_at"
    ] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("ADMIN", "SUPPORT_MANAGER")
    ),
):
    return customer_service.list_customers(
        db,
        search=search,
        is_active=is_active,
        city=city,
        country=country,
        company_name=company_name,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/me", response_model=CustomerResponse)
def get_my_customer_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "CUSTOMER":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for customer accounts only",
        )

    customer = customer_service.get_customer_by_email(
        db, current_user.email
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer profile not found",
        )

    if not customer.is_active:
        raise HTTPException(
            status_code=403,
            detail="This customer profile is inactive",
        )

    return customer


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer_profile(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (
        "ADMIN", "SUPPORT_MANAGER", "CUSTOMER"
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view customer profiles",
        )

    return get_owned_customer_or_403(
        customer_id, current_user, db
    )


@router.patch(
    "/{customer_id}",
    response_model=CustomerResponse,
)
def update_customer_profile(
    customer_id: int,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (
        "ADMIN", "SUPPORT_MANAGER", "CUSTOMER"
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to update customer profiles",
        )

    customer = get_owned_customer_or_403(
        customer_id, current_user, db
    )

    if current_user.role == "CUSTOMER":
        updates = data.model_dump(exclude_unset=True)

        if "email" in updates:
            raise HTTPException(
                status_code=403,
                detail="Customers cannot change their profile email",
            )

        if "is_active" in updates:
            raise HTTPException(
                status_code=403,
                detail="Customers cannot change account status",
            )

    try:
        return customer_service.update_customer(db, customer, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch(
    "/{customer_id}/status",
    response_model=CustomerResponse,
)
def update_customer_status(
    customer_id: int,
    data: CustomerStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        customer = customer_service.get_customer(db, customer_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return customer_service.set_customer_status(
        db, customer, data.is_active
    )
