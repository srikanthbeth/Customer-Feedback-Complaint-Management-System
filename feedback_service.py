
from sqlalchemy.orm import Session

from models.feedback import Feedback
from models.feedback_history import FeedbackHistory
from repositories import feedback_repository
from schemas.feedback import FeedbackCreate, FeedbackUpdate
from services.audit_log_service import record_audit_event

def record_history(
    db: Session,
    feedback_id: int,
    changed_by: str,
    action: str,
    changes: dict,
    note: str | None = None,
) -> None:
    feedback_repository.add_history(
        db,
        FeedbackHistory(
            feedback_id=feedback_id,
            changed_by=changed_by,
            action=action,
            changes=changes,
            note=note,
        ),
    )


def create_feedback(
    db: Session,
    customer_id: int,
    data: FeedbackCreate,
    changed_by: str,
) -> Feedback:
    feedback = Feedback(
        customer_id=customer_id,
        category=data.category.value,
        rating=data.rating,
        description=data.description,
        status="NEW",
    )

    feedback_repository.create_feedback(db, feedback)
    record_history(
        db,
        feedback.id,
        changed_by,
        "CREATED",
        {
            "category": feedback.category,
            "rating": feedback.rating,
            "description": feedback.description,
            "status": feedback.status,
        },
    )
    db.commit()
    db.refresh(feedback)
    return feedback



def update_feedback(
    db: Session,
    feedback: Feedback,
    data: FeedbackUpdate,
    changed_by: str,
    actor_id: int | None = None,
) -> Feedback:
    updates = data.model_dump(
        exclude_unset=True,
        exclude_none=True,
    )

    if not updates:
        raise ValueError("Provide at least one valid field to update")

    changes = {}

    for field, new_value in updates.items():
        if field == "category":
            new_value = new_value.value

        old_value = getattr(feedback, field)

        if old_value != new_value:
            changes[field] = {
                "old": old_value,
                "new": new_value,
            }
            setattr(feedback, field, new_value)

    if not changes:
        raise ValueError("No changes detected")

    record_history(
        db,
        feedback.id,
        changed_by,
        "UPDATED",
        changes,
    )

    record_audit_event(
        db,
        actor_id=actor_id,
        actor_email=changed_by,
        action="FEEDBACK_UPDATED",
        entity_type="FEEDBACK",
        entity_id=feedback.id,
        details={"changes": changes},
    )

    db.commit()
    db.refresh(feedback)
    return feedback



def update_feedback_status(
    db: Session,
    feedback: Feedback,
    new_status: str,
    changed_by: str,
    actor_id: int | None = None,
) -> Feedback:
    old_status = feedback.status

    if old_status == new_status:
        raise ValueError("Feedback already has this status")

    feedback.status = new_status

    changes = {
        "status": {
            "old": old_status,
            "new": new_status,
        }
    }

    record_history(
        db,
        feedback.id,
        changed_by,
        "STATUS_CHANGED",
        changes,
    )

    record_audit_event(
        db,
        actor_id=actor_id,
        actor_email=changed_by,
        action="FEEDBACK_STATUS_CHANGED",
        entity_type="FEEDBACK",
        entity_id=feedback.id,
        details={"changes": changes},
    )

    db.commit()
    db.refresh(feedback)
    return feedback

