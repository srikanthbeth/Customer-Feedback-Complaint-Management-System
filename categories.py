
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models.category import Category
from models.user import User
from repositories import category_repository
from schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryStatusUpdate,
    CategoryUpdate,
)
from services import category_service


router = APIRouter(prefix="/categories", tags=["Categories"])

MANAGER_ROLES = ("ADMIN", "SUPPORT_MANAGER")


def get_category_or_404(db: Session, category_id: int) -> Category:
    category = category_repository.get_category(db, category_id)

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    return category


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    return category_service.create_category(db, data)


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return category_repository.list_categories(
        db,
        is_active=is_active,
        search=search,
    )


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_category_or_404(db, category_id)


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
)
def edit_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    category = get_category_or_404(db, category_id)
    return category_service.update_category(db, category, data)


@router.patch(
    "/{category_id}/status",
    response_model=CategoryResponse,
)
def edit_category_status(
    category_id: int,
    data: CategoryStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGER_ROLES)),
):
    category = get_category_or_404(db, category_id)

    return category_repository.update_category_status(
        db, category, data.is_active
    )
