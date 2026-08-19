"""客服域服务 —— 工单创建/查询/追加留言业务 + 后台工单工作台"""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import AdminLog, Ticket, TicketMessage, User
from app.domains.support import repository as repo
from app.domains.support.schemas import AssignIn, CloseIn, ReplyIn, TicketCreateIn, TicketMessageIn


def log_admin(db: Session, admin: User, action: str, entity: str, entity_id: int, diff: dict | None = None):
    db.add(AdminLog(
        admin_id=admin.id,
        action=action,
        entity=entity,
        entity_id=int(entity_id or 0),
        diff_json=diff,
    ))


def _ticket_no() -> str:
    return "TK" + utcnow().strftime("%y%m%d") + uuid.uuid4().hex[:4].upper()


def _ticket_dict(t: Ticket, messages: list[TicketMessage]) -> dict:
    return {
        "ticket_no": t.ticket_no,
        "email": t.email,
        "order_no": t.order_no,
        "category": t.category,
        "priority": t.priority,
        "subject": t.subject,
        "status": t.status,
        "assignee_admin_id": t.assignee_admin_id,
        "first_reply_at": t.first_reply_at,
        "closed_at": t.closed_at,
        "created_at": t.created_at,
        "messages": [
            {
                "id": m.id,
                "sender": m.sender,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


# ===== 用户侧 =====


def create_ticket(db: Session, body: TicketCreateIn) -> dict:
    ticket = Ticket(
        ticket_no=_ticket_no(),
        email=body.email,
        order_no=body.order_no,
        category=body.category,
        subject=body.subject,
        status=0,
    )
    db.add(ticket)
    db.flush()
    db.add(TicketMessage(ticket_id=ticket.id, sender=1, content=body.content))
    db.commit()
    return {"ticket_no": ticket.ticket_no, "status": ticket.status}


def list_tickets_for_request(db: Session, user: User | None, email: str, ticket_no: str | None) -> dict:
    email_norm = email.strip().lower()
    if user is not None:
        if user.email.strip().lower() != email_norm:
            raise HTTPException(status_code=403, detail="not ticket owner")
        tickets = repo.tickets_by_email_desc(db, email_norm)
        return {"items": [_ticket_dict(t, repo.messages_asc(db, t.id)) for t in tickets]}
    if not ticket_no:
        raise HTTPException(status_code=403, detail="ticket_no required")
    t = repo.ticket_by_no(db, ticket_no.strip())
    if not t or t.email.strip().lower() != email_norm:
        raise HTTPException(status_code=404, detail="ticket not found")
    return {"items": [_ticket_dict(t, repo.messages_asc(db, t.id))]}


def append_message(db: Session, ticket_no: str, body: TicketMessageIn) -> dict:
    t = repo.ticket_by_no(db, ticket_no)
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")
    if t.email.strip().lower() != body.email.strip().lower():
        raise HTTPException(status_code=403, detail="not ticket owner")
    if t.status == 4:
        raise HTTPException(status_code=409, detail="ticket closed")
    db.add(TicketMessage(ticket_id=t.id, sender=1, content=body.content))
    db.commit()
    return {"ok": True}


def list_templates(db: Session, category: int | None) -> list[dict]:
    rows = repo.active_templates(db, category)
    return [
        {"id": r.id, "category": r.category, "title": r.title, "content": r.content}
        for r in rows
    ]


# ===== 后台：工单工作台 =====


def _ticket_admin_dict(t: Ticket) -> dict:
    return {
        "id": t.id,
        "ticket_no": t.ticket_no,
        "email": t.email,
        "order_no": t.order_no,
        "category": t.category,
        "priority": t.priority,
        "subject": t.subject,
        "status": t.status,
        "assignee_admin_id": t.assignee_admin_id,
        "first_reply_at": t.first_reply_at,
        "closed_at": t.closed_at,
        "created_at": t.created_at,
    }


def _get_ticket(db: Session, ticket_no: str) -> Ticket:
    t = repo.ticket_by_no(db, ticket_no)
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")
    return t


def admin_tickets(db: Session, status: int | None, category: int | None, q: str | None, page: int, size: int) -> dict:
    query = repo.admin_tickets_query(db, status, category, q)
    rows, total = repo.page(query, page, size)
    return {"items": [_ticket_admin_dict(t) for t in rows], "total": total, "page": page, "size": size}


def admin_reply(db: Session, admin: User, ticket_no: str, body: ReplyIn) -> dict:
    t = _get_ticket(db, ticket_no)
    db.add(TicketMessage(ticket_id=t.id, sender=2, content=body.content))
    if t.first_reply_at is None:
        t.first_reply_at = utcnow()
    if t.status == 0:
        t.status = 1
    log_admin(db, admin, "reply", "ticket", t.id, {"status": t.status})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t)


def admin_close(db: Session, admin: User, ticket_no: str, body: CloseIn) -> dict:
    t = _get_ticket(db, ticket_no)
    t.status = 4
    t.closed_at = utcnow()
    t.close_reason = body.close_reason
    log_admin(db, admin, "close", "ticket", t.id, {"status": 4, "close_reason": body.close_reason})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t)


def admin_assign(db: Session, admin: User, ticket_no: str, body: AssignIn) -> dict:
    t = _get_ticket(db, ticket_no)
    t.assignee_admin_id = body.admin_id
    log_admin(db, admin, "assign", "ticket", t.id, {"admin_id": body.admin_id})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t)
