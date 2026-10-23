from typing import Any

from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from repositories.audit_log_repository import (
    create_audit_log,
    list_audit_logs,
)


def record_audit_event(
    db: Session,
    *,
    actor_id: int | None,
    actor_email: str | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    return create_audit_log(
        db,
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )


def get_audit_logs(
    db: Session,
    *,
    actor_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    items, total = list_audit_logs(
        db,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }