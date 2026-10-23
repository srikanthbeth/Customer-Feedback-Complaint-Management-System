
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_roles
from models.user import User
from schemas.audit_log import AuditLogListResponse
from services.audit_log_service import get_audit_logs


router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

AUDIT_ROLES = ("ADMIN", "SUPPORT_MANAGER", "SUPPORT_AGENT")


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs_endpoint(
    actor_id: int | None = Query(default=None, gt=0),
    action: str | None = Query(default=None, min_length=1, max_length=100),
    entity_type: str | None = Query(
        default=None, min_length=1, max_length=100
    ),
    entity_id: str | None = Query(
        default=None, min_length=1, max_length=100
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*AUDIT_ROLES)),
):
    """List audit records. Accessible to authorized staff only."""
    return get_audit_logs(
        db,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
