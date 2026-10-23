
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.category import Category
from repositories import category_repository
from schemas.category import CategoryCreate, CategoryUpdate


def create_category(
    db: Session, data: CategoryCreate
) -> Category:
    name = data.name.strip()

    existing = category_repository.get_category_by_name(db, name)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A category with this name already exists",
        )

    category = Category(
        name=name,
        description=data.description,
        is_active=True,
    )

    try:
        return category_repository.create_category(db, category)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A category with this name already exists",
        ) from exc


def update_category(
    db: Session, category: Category, data: CategoryUpdate
) -> Category:
    changes = data.model_dump(exclude_unset=True)

    if "name" in changes and changes["name"] is not None:
        name = changes["name"].strip()

        existing = category_repository.get_category_by_name(
            db, name, exclude_id=category.id
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="A category with this name already exists",
            )

        changes["name"] = name

    try:
        return category_repository.update_category(
            db, category, changes
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A category with this name already exists",
        ) from exc
