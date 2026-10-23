
from sqlalchemy.orm import Session

from models.category import Category
from models.complaint import Complaint
from models.customer import Customer
from schemas.complaint import ComplaintCreate
from repositories import complaint_repository


def create_complaint(
    db: Session,
    customer: Customer,
    data: ComplaintCreate,
) -> Complaint:
    if not customer.is_active:
        raise ValueError("Inactive customers cannot create complaints")

    category = db.query(Category).filter(
        Category.id == data.category_id
    ).first()

    if category is None:
        raise LookupError("Category not found")

    if not category.is_active:
        raise ValueError("Cannot create a complaint in an inactive category")

    complaint = Complaint(
        customer_id=customer.id,
        category_id=data.category_id,
        title=data.title,
        description=data.description,
        priority=data.priority.value,
        severity=data.severity.value,
        status="OPEN",
        attachment_urls=data.attachment_urls,
    )

    try:
        return complaint_repository.create_complaint(db, complaint)
    except Exception:
        db.rollback()
        raise


def update_complaint(
    db: Session,
    complaint: Complaint,
    data,
) -> Complaint:
    updates = data.model_dump(exclude_unset=True)

    if not updates:
        raise ValueError("Provide at least one field to update")

    if "category_id" in updates:
        category = db.query(Category).filter(
            Category.id == updates["category_id"]
        ).first()

        if category is None:
            raise LookupError("Category not found")
        if not category.is_active:
            raise ValueError(
                "Cannot use an inactive complaint category"
            )

    for field in ("priority", "severity"):
        if field in updates and updates[field] is not None:
            updates[field] = updates[field].value

    try:
        return complaint_repository.update_complaint(
            db, complaint, updates
        )
    except Exception:
        db.rollback()
        raise

def update_complaint_status(
    db: Session,
    complaint: Complaint,
    new_status: str,
    actor_id: int,
    reason: str | None = None,
    resolution_details: str | None = None,
) -> Complaint:
    from services.resolution_workflow_service import (
        transition_status,
    )

    return transition_status(
        db=db,
        complaint=complaint,
        new_status=new_status,
        actor_id=actor_id,
        reason=reason,
        resolution_details=resolution_details,
    )