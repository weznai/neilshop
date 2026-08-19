"""客服域用户侧路由 —— /api/support/*（HTTP 编排，业务在 service）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user_optional
from app.domains.support import service
from app.domains.support.schemas import TicketCreateIn, TicketMessageIn
from app.models import User

router = APIRouter(prefix="/api/support", tags=["support"])


@router.post("/tickets")
def create_ticket(body: TicketCreateIn, db: Session = Depends(get_db)):
    return service.create_ticket(db, body)


@router.get("/tickets")
def list_tickets(
    email: str = Query(...),
    ticket_no: str | None = Query(None),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service.list_tickets_for_request(db, user, email, ticket_no)


@router.post("/tickets/{ticket_no}/messages")
def append_message(ticket_no: str, body: TicketMessageIn, db: Session = Depends(get_db)):
    return service.append_message(db, ticket_no, body)


@router.get("/templates")
def list_templates(category: int | None = Query(None), db: Session = Depends(get_db)):
    return service.list_templates(db, category)
