
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.category import Category


def create_category(db: Session, category: Category) -> Category:
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def get_category(db: Session, category_id: int) -> Category | None:
    return db.get(Category, category_id)


def get_category_by_name(
    db: Session, name: str, exclude_id: int | None = None
) -> Category | None:
    query = select(Category).where(
        func.lower(Category.name) == name.strip().lower()
    )

    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)

    return db.scalar(query)


def list_categories(
    db: Session,
    is_active: bool | None = None,
    search: str | None = None,
) -> list[Category]:
    query = select(Category)

    if is_active is not None:
        query = query.where(Category.is_active == is_active)

    if search and search.strip():
        query = query.where(
            Category.name.ilike(f"%{search.strip()}%")
        )

    query = query.order_by(Category.name.asc())
    return list(db.scalars(query).all())


def update_category(
    db: Session, category: Category, changes: dict
) -> Category:
    for field, value in changes.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


def update_category_status(
    db: Session, category: Category, is_active: bool
) -> Category:
    category.is_active = is_active
    db.commit()
    db.refresh(category)
    return category
