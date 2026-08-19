"""客服域（3 表）"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, SmallInteger, String, Text

from app.core.db import Base, utcnow


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("idx_status_priority", "status", "priority", "created_at"),
        Index("idx_assignee", "assignee_admin_id", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_no = Column(String(14), nullable=False, unique=True)  # TK260814xxxx
    user_id = Column(BigInteger)
    email = Column(String(191), nullable=False)
    order_no = Column(String(20))
    category = Column(SmallInteger, nullable=False)  # 1物流 2质量 3退换 4账户 5售前 6其他
    priority = Column(SmallInteger, nullable=False, default=1)  # 0紧急 1普通
    subject = Column(String(200), nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)
    # 0新 1处理中 2等待用户 3已解决待关 4已关闭
    assignee_admin_id = Column(BigInteger)
    first_reply_at = Column(DateTime)
    closed_at = Column(DateTime)
    close_reason = Column(SmallInteger)
    satisfaction = Column(SmallInteger)  # 1-5 评价
    created_at = Column(DateTime, nullable=False, default=utcnow)


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id = Column(BigInteger, nullable=False, index=True)
    sender = Column(SmallInteger, nullable=False)  # 1用户 2客服 3系统
    content = Column(Text, nullable=False)
    attachments = Column(JSON)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class ReplyTemplate(Base):
    __tablename__ = "reply_templates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    category = Column(SmallInteger, nullable=False)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    active = Column(SmallInteger, nullable=False, default=1)
