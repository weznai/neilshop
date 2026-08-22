"""客服域后台路由 —— /api/admin/ops 下 tickets 工作台（绝对路径，由 admin_ops shim 组装）"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.support import service
from app.domains.support.schemas import AssignIn, CloseIn, ReplyIn, TicketStatusIn
from app.models import User

router = APIRouter(tags=["admin-ops"])


def _parse_statuses(raw: str | None) -> list[int] | None:
    """组合状态查询：'3,4' → [3,4]；单值 '3' → [3]（与旧单值行为一致）；None/空串 → 不过滤"""
    if raw is None or not raw.strip():
        return None
    try:
        values = [int(x) for x in raw.split(",") if x.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_status")
    return values or None


@router.get("/api/admin/ops/tickets")
def admin_tickets(
    status: str | None = Query(None, description="单值或逗号分隔多值，如 3,4"),
    category: int | None = Query(None),
    q: str | None = Query(None),
    assignee: int | None = Query(None, description="按指派人 admin_id 过滤"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.admin_tickets(db, _parse_statuses(status), category, q, page, size, assignee)


@router.post("/api/admin/ops/tickets/{ticket_no}/reply")
def admin_reply(ticket_no: str, body: ReplyIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_reply(db, admin, ticket_no, body)


@router.post("/api/admin/ops/tickets/{ticket_no}/close")
def admin_close(ticket_no: str, body: CloseIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_close(db, admin, ticket_no, body)


@router.post("/api/admin/ops/tickets/{ticket_no}/assign")
def admin_assign(ticket_no: str, body: AssignIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_assign(db, admin, ticket_no, body)


@router.put("/api/admin/support/tickets/{ticket_no}/status")
def admin_set_status(
    ticket_no: str, body: TicketStatusIn,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service.admin_set_status(db, admin, ticket_no, body)
