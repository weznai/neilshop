"""客服域后台路由 —— /api/admin/ops 下 tickets 工作台（绝对路径，由 admin_ops shim 组装）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.support import service
from app.domains.support.schemas import AssignIn, CloseIn, ReplyIn
from app.models import User

router = APIRouter(tags=["admin-ops"])


@router.get("/api/admin/ops/tickets")
def admin_tickets(
    status: int | None = Query(None),
    category: int | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.admin_tickets(db, status, category, q, page, size)


@router.post("/api/admin/ops/tickets/{ticket_no}/reply")
def admin_reply(ticket_no: str, body: ReplyIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_reply(db, admin, ticket_no, body)


@router.post("/api/admin/ops/tickets/{ticket_no}/close")
def admin_close(ticket_no: str, body: CloseIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_close(db, admin, ticket_no, body)


@router.post("/api/admin/ops/tickets/{ticket_no}/assign")
def admin_assign(ticket_no: str, body: AssignIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_assign(db, admin, ticket_no, body)
