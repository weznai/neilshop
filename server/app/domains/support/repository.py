"""客服域仓储 —— 纯查询/分页，不掺业务规则"""

from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session

from app.models import ReplyTemplate, Ticket, TicketMessage, User


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
