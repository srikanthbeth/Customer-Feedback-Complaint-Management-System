from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.audit_log import AuditLog


def create_audit_log(
    db: Session,
    *,
    actor_id: int | None,
    actor_email: str | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details or {},
    )

    db.add(audit_log)
    db.flush()
    return audit_log


def list_audit_logs(
    db: Session,
    *,
    actor_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AuditLog], int]:
    filters = []

    if actor_id is not None:
        filters.append(AuditLog.actor_id == actor_id)

    if action:
        filters.append(AuditLog.action == action)

    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)

    if entity_id:
        filters.append(AuditLog.entity_id == entity_id)

    total = db.scalar(
        select(func.count(AuditLog.id)).where(*filters)
    ) or 0

    statement = (
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = list(db.scalars(statement).all())
    return items, total