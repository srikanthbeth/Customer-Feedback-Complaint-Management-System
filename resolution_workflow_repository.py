from sqlalchemy.orm import Session

from models.complaint_comment import ComplaintComment
from models.complaint_status_history import ComplaintStatusHistory


def create_comment(
    db: Session,
    comment: ComplaintComment,
) -> ComplaintComment:
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_comments(
    db: Session,
    complaint_id: int,
    include_internal: bool,
) -> list[ComplaintComment]:
    query = db.query(ComplaintComment).filter(
        ComplaintComment.complaint_id == complaint_id
    )

    if not include_internal:
        query = query.filter(
            ComplaintComment.is_internal.is_(False)
        )

    return query.order_by(
        ComplaintComment.created_at.asc(),
        ComplaintComment.id.asc(),
    ).all()


def create_status_history(
    db: Session,
    history: ComplaintStatusHistory,
) -> ComplaintStatusHistory:
    db.add(history)
    db.flush()
    return history


def list_status_history(
    db: Session,
    complaint_id: int,
) -> list[ComplaintStatusHistory]:
    return (
        db.query(ComplaintStatusHistory)
        .filter(
            ComplaintStatusHistory.complaint_id == complaint_id
        )
        .order_by(
            ComplaintStatusHistory.changed_at.asc(),
            ComplaintStatusHistory.id.asc(),
        )
        .all()
    )