"""客服域服务 —— 工单创建/查询/追加留言业务 + 后台工单工作台"""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import AdminLog, Ticket, TicketMessage, User
from app.domains.support import repository as repo
from app.domains.support.schemas import AssignIn, CloseIn, ReplyIn, TicketCreateIn, TicketMessageIn, TicketStatusIn


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


def create_ticket(db: Session, body: TicketCreateIn, user: User | None = None) -> dict:
    ticket = Ticket(
        ticket_no=_ticket_no(),
        user_id=user.id if user else None,
        email=body.email,
        order_no=body.order_no,
        category=body.category,
        subject=body.subject,
        status=0,
    )
    db.add(ticket)
    db.flush()
    db.add(TicketMessage(ticket_id=ticket.id, sender=1, content=body.content))
    # 关联订单侧落 ticket_linked 时间线（客服在订单时间线即可看到工单入口）
    if body.order_no:
        from app.domains.trade import repository as trade_repo

        order = trade_repo.order_by_no(db, body.order_no.strip().upper())
        if order:
            trade_repo.add_timeline(
                db, order.id, "ticket_linked", actor="user",
                detail={"ticket_no": ticket.ticket_no, "subject": body.subject},
            )
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
    if t.status == 2:
        # 等待客户(2) 下客户追加回复 → 自动回流处理中(1)，免客服手动捞单
        t.status = 1
    db.commit()
    return {"ok": True}


def list_templates(db: Session, category: int | None) -> list[dict]:
    rows = repo.active_templates(db, category)
    return [
        {"id": r.id, "category": r.category, "title": r.title, "content": r.content}
        for r in rows
    ]


# ===== 后台：工单工作台 =====


def _ticket_admin_dict(t: Ticket, admin_names: dict[int, str] | None = None) -> dict:
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
        "assignee_name": admin_names.get(t.assignee_admin_id) if (t.assignee_admin_id and admin_names) else None,
        "first_reply_at": t.first_reply_at,
        "closed_at": t.closed_at,
        "created_at": t.created_at,
    }


def _assignee_names(db: Session, tickets: list[Ticket]) -> dict[int, str]:
    """列表/详情共用：按页内 assignee 批量取姓名（未指派/查不到 → 空 dict，dict 取值 None）"""
    ids = {t.assignee_admin_id for t in tickets if t.assignee_admin_id}
    return repo.admin_names_by_ids(db, ids)


def _get_ticket(db: Session, ticket_no: str) -> Ticket:
    t = repo.ticket_by_no(db, ticket_no)
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")
    return t


def admin_tickets(
    db: Session, statuses: list[int] | None, category: int | None, q: str | None,
    page: int, size: int, assignee: int | None = None, priority: int | None = None,
) -> dict:
    query = repo.admin_tickets_query(db, statuses, category, q, assignee, priority)
    rows, total = repo.page(query, page, size)
    names = _assignee_names(db, rows)
    return {"items": [_ticket_admin_dict(t, names) for t in rows], "total": total, "page": page, "size": size}


def admin_reply(db: Session, admin: User, ticket_no: str, body: ReplyIn) -> dict:
    t = _get_ticket(db, ticket_no)
    if t.status == 4:
        # 已关闭工单不接受追加回复（防审计流被覆盖）；如需继续处理应先重开
        raise HTTPException(status_code=400, detail="ticket closed")
    db.add(TicketMessage(ticket_id=t.id, sender=2, content=body.content))
    if t.first_reply_at is None:
        t.first_reply_at = utcnow()
    if t.status == 0:
        t.status = 1
    log_admin(db, admin, "reply", "ticket", t.id, {"status": t.status})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t, _assignee_names(db, [t]))


def admin_close(db: Session, admin: User, ticket_no: str, body: CloseIn) -> dict:
    t = _get_ticket(db, ticket_no)
    if t.status == 4:
        # 重复关闭会覆盖 closed_at/close_reason 审计数据 → 409；
        # 3(已解决待关)→4 是正常确认流，0/1/2 主动关单均保留（前端既有行为不受影响）
        raise HTTPException(status_code=409, detail="ticket_already_closed")
    t.status = 4
    t.closed_at = utcnow()
    t.close_reason = _norm_close_reason(body.close_reason)
    log_admin(db, admin, "close", "ticket", t.id, {"status": 4, "close_reason": body.close_reason})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t, _assignee_names(db, [t]))


def admin_assign(db: Session, admin: User, ticket_no: str, body: AssignIn) -> dict:
    t = _get_ticket(db, ticket_no)
    t.assignee_admin_id = body.admin_id
    log_admin(db, admin, "assign", "ticket", t.id, {"admin_id": body.admin_id})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t, _assignee_names(db, [t]))


def _norm_close_reason(value) -> int | None:
    """关单原因归一化到 CloseReason 数字枚举（列为 SmallInteger）：
    数字/数字串直取，自由文本落 9（其他），空值保持 None"""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    return int(s) if s.lstrip("-").isdigit() else 9


# 状态机：1→2/3/4、2→3/4、3→4；4→1 为重开（0/1 态只能经回复进入）
_ALLOWED_TRANSITIONS = {(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4), (4, 1)}


def admin_set_status(db: Session, admin: User, ticket_no: str, body: TicketStatusIn) -> dict:
    t = _get_ticket(db, ticket_no)
    prev = t.status
    if (prev, body.status) not in _ALLOWED_TRANSITIONS:
        raise HTTPException(status_code=409, detail="invalid_status_transition")
    t.status = body.status
    if body.status == 4:
        t.closed_at = utcnow()
        t.close_reason = _norm_close_reason(body.close_reason)
    elif prev == 4 and body.status == 1:
        # 重开：清空关单时间与原因，避免残留误导后续报表/筛选
        t.closed_at = None
        t.close_reason = None
    log_admin(db, admin, "status", "ticket", t.id, {"status": body.status, "close_reason": t.close_reason})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t, _assignee_names(db, [t]))
