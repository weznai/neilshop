"""客服域仓储 —— 纯查询/分页，不掺业务规则"""

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Query, Session

from app.models import ReplyTemplate, Ticket, TicketMessage, User

# 状态推进 CAS（同 trade 域 claim_* 风格：原子 UPDATE + rowcount 判定）：
# rowcount=0 = 状态已被并发流转/认领，调用方据此 409，消除读-判-写 TOCTOU
_CLAIM_TICKET_STATUS_SQL = text(
    "UPDATE tickets SET status = :new WHERE id = :tid AND status = :prev"
)
# 关单 CAS：任意未关(≠4)态可推进 4，并发重复关单后者 rowcount=0（护住 closed_at/close_reason 审计）
_CLAIM_TICKET_CLOSE_SQL = text(
    "UPDATE tickets SET status = 4 WHERE id = :tid AND status != 4"
)
# 认领 CAS：仅未指派（assignee IS NULL）可抢注，并发「指派给我」后者 rowcount=0
_CLAIM_TICKET_ASSIGN_SQL = text(
    "UPDATE tickets SET assignee_admin_id = :aid WHERE id = :tid AND assignee_admin_id IS NULL"
)


def claim_ticket_status(db: Session, ticket_id: int, prev: int, new: int) -> int:
    return db.execute(
        _CLAIM_TICKET_STATUS_SQL, {"tid": ticket_id, "prev": prev, "new": new}
    ).rowcount


def claim_ticket_close(db: Session, ticket_id: int) -> int:
    return db.execute(_CLAIM_TICKET_CLOSE_SQL, {"tid": ticket_id}).rowcount


def claim_ticket_assign(db: Session, ticket_id: int, admin_id: int) -> int:
    return db.execute(
        _CLAIM_TICKET_ASSIGN_SQL, {"tid": ticket_id, "aid": admin_id}
    ).rowcount


def page(q: Query, page: int, size: int):
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return rows, total


def ticket_by_no(db: Session, ticket_no: str) -> Ticket | None:
    return db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()


def tickets_by_email_desc(db: Session, email_norm: str) -> list[Ticket]:
    return (
        db.query(Ticket)
        .filter(func.lower(Ticket.email) == email_norm)
        .order_by(Ticket.id.desc())
        .all()
    )


def messages_asc(db: Session, ticket_id: int) -> list[TicketMessage]:
    return (
        db.query(TicketMessage)
        .filter(TicketMessage.ticket_id == ticket_id)
        .order_by(TicketMessage.created_at, TicketMessage.id)
        .all()
    )


def messages_asc_map(db: Session, ticket_ids: list[int]) -> dict[int, list[TicketMessage]]:
    """按工单集一次 IN 批查全部消息并按 (created_at, id) 升序分组：
    客户侧列表逐单 messages_asc 的 N+1 消除（响应结构不变，仍带全量消息）"""
    if not ticket_ids:
        return {}
    rows = (
        db.query(TicketMessage)
        .filter(TicketMessage.ticket_id.in_(ticket_ids))
        .order_by(TicketMessage.created_at, TicketMessage.id)
        .all()
    )
    out: dict[int, list[TicketMessage]] = {}
    for m in rows:
        out.setdefault(m.ticket_id, []).append(m)
    return out


def last_messages_map(db: Session, ticket_ids: list[int]) -> dict[int, TicketMessage]:
    """每工单最后一条消息（单条 IN 批查，列表页避免逐单 N+1）；
    按 (created_at, id) 升序遍历覆盖，留下每单最新一条；无消息的工单不在结果中。"""
    if not ticket_ids:
        return {}
    rows = (
        db.query(TicketMessage)
        .filter(TicketMessage.ticket_id.in_(ticket_ids))
        .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
        .all()
    )
    out: dict[int, TicketMessage] = {}
    for m in rows:
        out[m.ticket_id] = m
    return out


def admin_tickets_query(
    db: Session, statuses: list[int] | None, category: int | None, q: str | None,
    assignee: int | None = None, priority: int | None = None,
) -> Query:
    query = db.query(Ticket)
    if statuses:
        query = query.filter(Ticket.status.in_(statuses))
    if category is not None:
        query = query.filter(Ticket.category == category)
    if assignee is not None:
        query = query.filter(Ticket.assignee_admin_id == assignee)
    if priority is not None:
        query = query.filter(Ticket.priority == priority)
    if q:
        # 后台搜索：邮箱 / 工单号 / 主题 / 订单号 四字段模糊
        like = f"%{q}%"
        query = query.filter(or_(
            Ticket.email.ilike(like), Ticket.ticket_no.ilike(like),
            Ticket.subject.ilike(like), Ticket.order_no.ilike(like),
        ))
    return query.order_by(Ticket.priority.asc(), Ticket.created_at.desc(), Ticket.id.desc())


def admin_names_by_ids(db: Session, ids: set[int]) -> dict[int, str]:
    """工单指派人姓名回填用批量查询（避免逐行查用户；name 为空回退 email）"""
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: (u.name or u.email) for u in rows}


def active_templates(db: Session, category: int | None) -> list[ReplyTemplate]:
    q = db.query(ReplyTemplate).filter(ReplyTemplate.active == 1)
    if category is not None:
        q = q.filter(ReplyTemplate.category == category)
    return q.order_by(ReplyTemplate.id).all()


def all_templates(db: Session, category: int | None = None) -> list[ReplyTemplate]:
    """后台模板管理：全量（含停用），可按分类过滤"""
    q = db.query(ReplyTemplate)
    if category is not None:
        q = q.filter(ReplyTemplate.category == category)
    return q.order_by(ReplyTemplate.category, ReplyTemplate.id).all()


def template_by_id(db: Session, tpl_id: int) -> ReplyTemplate | None:
    return db.get(ReplyTemplate, tpl_id)
