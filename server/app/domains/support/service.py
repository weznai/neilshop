"""客服域服务 —— 工单创建/查询/追加留言业务 + 后台工单工作台"""

import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.permissions import ADMIN_ACCOUNT_ROLES
from app.models import AdminLog, ReplyTemplate, Ticket, TicketMessage, User
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
    # 6 位随机熵（24bit）：4 位撞唯一索引概率偏高；再长会超 ticket_no String(14) 列宽
    return "TK" + utcnow().strftime("%y%m%d") + uuid.uuid4().hex[:6].upper()


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
    # 关联订单归属校验：携带 order_no 时订单 email 须与提交 email 一致，
    # 不一致 403（防冒用他人邮箱向他人订单注入 ticket_linked 时间线）；
    # 订单号查不到维持既有宽松行为（不关联时间线也不报错）
    order = None
    if body.order_no:
        from app.domains.trade import repository as trade_repo

        order = trade_repo.order_by_no(db, body.order_no.strip().upper())
        if order and order.email.strip().lower() != body.email.strip().lower():
            raise HTTPException(status_code=403, detail="order_email_mismatch")
    # ticket_no 撞唯一索引（极小概率）→ 换号重建一次（同 deps._create_cart 重试风格）
    for _attempt in range(2):
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
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue
        db.add(TicketMessage(ticket_id=ticket.id, sender=1, content=body.content))
        # 关联订单侧落 ticket_linked 时间线（客服在订单时间线即可看到工单入口）
        if order is not None:
            trade_repo.add_timeline(
                db, order.id, "ticket_linked", actor="user",
                detail={"ticket_no": ticket.ticket_no, "subject": body.subject},
            )
        db.commit()
        return {"ticket_no": ticket.ticket_no, "status": ticket.status}
    raise HTTPException(status_code=503, detail="ticket no conflict, retry")


def list_tickets_for_request(db: Session, user: User | None, email: str, ticket_no: str | None) -> dict:
    email_norm = email.strip().lower()
    if user is not None:
        if user.email.strip().lower() != email_norm:
            raise HTTPException(status_code=403, detail="not ticket owner")
        tickets = repo.tickets_by_email_desc(db, email_norm)
        # 消息一次 IN 批查分组（替代逐单查消息的 N+1；响应结构不变，仍带全量消息）
        mmap = repo.messages_asc_map(db, [t.id for t in tickets])
        return {"items": [_ticket_dict(t, mmap.get(t.id, [])) for t in tickets]}
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
    if t.status in (2, 3):
        # 等待客户(2)/已解决待关(3) 下客户追加回复 → 自动回流处理中(1)，免客服手动捞单
        t.status = 1
    db.commit()
    return {"ok": True}


def list_templates(db: Session, category: int | None) -> list[dict]:
    rows = repo.active_templates(db, category)
    return [
        {"id": r.id, "category": r.category, "title": r.title, "content": r.content}
        for r in rows
    ]


# ===== 后台：快捷回复模板管理 =====


def _tpl_dict(r) -> dict:
    return {"id": r.id, "category": r.category, "title": r.title, "content": r.content, "active": r.active}


def admin_templates(db: Session, category: int | None) -> dict:
    return {"items": [_tpl_dict(r) for r in repo.all_templates(db, category)]}


def admin_template_save(db: Session, admin: User, body, tpl_id: int | None) -> dict:
    if tpl_id is None:
        row = ReplyTemplate(
            category=body.category, title=body.title, content=body.content, active=body.active)
        db.add(row)
    else:
        row = repo.template_by_id(db, tpl_id)
        if not row:
            raise HTTPException(status_code=404, detail="template not found")
        row.category = body.category
        row.title = body.title
        row.content = body.content
        row.active = body.active
    log_admin(db, admin, "template_save", "reply_template", tpl_id or 0, {"title": body.title})
    db.commit()
    return _tpl_dict(row)


def admin_template_delete(db: Session, admin: User, tpl_id: int) -> dict:
    row = repo.template_by_id(db, tpl_id)
    if not row:
        raise HTTPException(status_code=404, detail="template not found")
    db.delete(row)
    log_admin(db, admin, "template_delete", "reply_template", tpl_id, {})
    db.commit()
    return {"ok": True}


# ===== 后台：工单工作台 =====


def _ticket_admin_dict(
    t: Ticket, admin_names: dict[int, str] | None = None,
    last_message: TicketMessage | None = None,
) -> dict:
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
        # 最后一条消息信息（列表页排序/预览用；sender 1=客户 2=客服 3=系统，无消息为 None）
        "last_message_at": last_message.created_at if last_message else None,
        "last_sender": last_message.sender if last_message else None,
    }


def _assignee_names(db: Session, tickets: list[Ticket]) -> dict[int, str]:
    """列表/详情共用：按页内 assignee 批量取姓名（未指派/查不到 → 空 dict，dict 取值 None）"""
    ids = {t.assignee_admin_id for t in tickets if t.assignee_admin_id}
    return repo.admin_names_by_ids(db, ids)


def _last_message(db: Session, t: Ticket) -> TicketMessage | None:
    """单工单最后一条消息（回复/关单等单票响应回填用）"""
    return repo.last_messages_map(db, [t.id]).get(t.id)


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
    # 每单最后一条消息：单条 IN 批查（避免逐单查消息的 N+1）
    lmap = repo.last_messages_map(db, [t.id for t in rows])
    return {
        "items": [_ticket_admin_dict(t, names, lmap.get(t.id)) for t in rows],
        "total": total, "page": page, "size": size,
    }


def admin_reply(db: Session, admin: User, ticket_no: str, body: ReplyIn) -> dict:
    t = _get_ticket(db, ticket_no)
    if t.status == 4:
        # 已关闭工单不接受追加回复（防审计流被覆盖）；如需继续处理应先重开
        raise HTTPException(status_code=400, detail="ticket closed")
    db.add(TicketMessage(ticket_id=t.id, sender=2, content=body.content))
    if t.first_reply_at is None:
        t.first_reply_at = utcnow()
    if t.status in (0, 2):
        # 待处理(0)/等待客户(2) 下客服回复 → 处理中(1)（等待客户时回复自动回流，免手动切状态）
        t.status = 1
    diff = {"status": t.status}
    if body.priority is not None:
        # 顺带更新优先级（0紧急 1普通，见 models/support.py），激活原本死掉的 priority 字段
        t.priority = body.priority
        diff["priority"] = body.priority
    log_admin(db, admin, "reply", "ticket", t.id, diff)
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t, _assignee_names(db, [t]), _last_message(db, t))


def admin_close(db: Session, admin: User, ticket_no: str, body: CloseIn) -> dict:
    t = _get_ticket(db, ticket_no)
    if t.status == 4:
        # 重复关闭会覆盖 closed_at/close_reason 审计数据 → 409；
        # 3(已解决待关)→4 是正常确认流，0/1/2 主动关单均保留（前端既有行为不受影响）
        raise HTTPException(status_code=409, detail="ticket_already_closed")
    # 关单 CAS：与并发关单/状态流转互斥（rowcount=0 = 已被并发推进），护住 close 审计字段
    if repo.claim_ticket_close(db, t.id) == 0:
        raise HTTPException(status_code=409, detail="ticket_already_closed")
    t.status = 4
    t.closed_at = utcnow()
    t.close_reason = _norm_close_reason(body.close_reason)
    diff = {"status": 4, "close_reason": body.close_reason}
    if body.priority is not None:
        t.priority = body.priority
        diff["priority"] = body.priority
    log_admin(db, admin, "close", "ticket", t.id, diff)
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t, _assignee_names(db, [t]), _last_message(db, t))


def admin_assign(db: Session, admin: User, ticket_no: str, body: AssignIn) -> dict:
    t = _get_ticket(db, ticket_no)
    # 指派对象必须是在编后台账号（客服/运营/仓库/超管且启用中，与 ops.list_admins 候选同口径），
    # 防误指普通用户/美甲师/停用账号
    assignee = db.get(User, body.admin_id)
    if (assignee is None or assignee.role not in ADMIN_ACCOUNT_ROLES
            or assignee.status != 1):
        raise HTTPException(status_code=400, detail="invalid_admin_id")
    prev_assignee = t.assignee_admin_id
    if body.admin_id == admin.id and prev_assignee != admin.id:
        # 「指派给我」：未指派走 CAS 抢注（并发互斥），已被他人指派 → 409
        if prev_assignee is not None:
            raise HTTPException(status_code=409, detail="already_assigned")
        if repo.claim_ticket_assign(db, t.id, admin.id) == 0:
            raise HTTPException(status_code=409, detail="already_assigned")
        t.assignee_admin_id = body.admin_id  # 同步 ORM 快照（CAS 已落库）
    else:
        # 显式改派（指定他人/重复指派给自己）：保留覆盖语义，审计记录原指派人
        t.assignee_admin_id = body.admin_id
    log_admin(db, admin, "assign", "ticket", t.id,
              {"admin_id": body.admin_id, "from": prev_assignee})
    db.commit()
    db.refresh(t)
    return _ticket_admin_dict(t, _assignee_names(db, [t]), _last_message(db, t))


# 关单原因白名单（CloseIn 数字枚举语义）：1已解决 2重复 3无效 9其他
_CLOSE_REASON_VALUES = {1, 2, 3, 9}


def _norm_close_reason(value) -> int | None:
    """关单原因归一化到白名单枚举（列为 SmallInteger）：
    白名单内数字/数字串直取，自由文本与越界数字（如 5/-1）落 9（其他），空值保持 None"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 9
    if isinstance(value, int):
        return value if value in _CLOSE_REASON_VALUES else 9
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        n = int(s)
        return n if n in _CLOSE_REASON_VALUES else 9
    return 9


# 状态机：1→2/3/4、2→1/3/4、3→1/4；4→1 为重开（清空关单审计）；3→1 仅切状态不清 close 字段
_ALLOWED_TRANSITIONS = {
    (1, 2), (1, 3), (1, 4), (2, 1), (2, 3), (2, 4), (3, 1), (3, 4), (4, 1),
}


def admin_set_status(db: Session, admin: User, ticket_no: str, body: TicketStatusIn) -> dict:
    t = _get_ticket(db, ticket_no)
    prev = t.status
    if (prev, body.status) not in _ALLOWED_TRANSITIONS:
        raise HTTPException(status_code=409, detail="invalid_status_transition")
    # 每条边原子化：CAS 抢占（WHERE status=:prev），并发同边/异边流转后者 rowcount=0 → 409
    if repo.claim_ticket_status(db, t.id, prev, body.status) == 0:
        raise HTTPException(status_code=409, detail="status_conflict")
    t.status = body.status  # 同步 ORM 快照（CAS 已落库）
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
    return _ticket_admin_dict(t, _assignee_names(db, [t]), _last_message(db, t))
