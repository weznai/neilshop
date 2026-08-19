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


def admin_tickets_query(db: Session, status: int | None, category: int | None, q: str | None) -> Query:
    query = db.query(Ticket)
    if status is not None:
        query = query.filter(Ticket.status == status)
    if category is not None:
        query = query.filter(Ticket.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Ticket.email.ilike(like), Ticket.ticket_no.ilike(like)))
    return query.order_by(Ticket.priority.asc(), Ticket.created_at.desc(), Ticket.id.desc())


def active_templates(db: Session, category: int | None) -> list[ReplyTemplate]:
    q = db.query(ReplyTemplate).filter(ReplyTemplate.active == 1)
    if category is not None:
        q = q.filter(ReplyTemplate.category == category)
    return q.order_by(ReplyTemplate.id).all()
