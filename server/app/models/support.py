"""客服域（5 表）"""

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


class ChatConversation(Base):
    """在线客服会话 —— 一个客户 × 一个渠道（0 AI / 1 人工 / 2 美甲师）一条进行中会话；
    游客凭 guest_token（localStorage）标识，登录后绑 user_id（token 仍保留可续聊）"""

    __tablename__ = "chat_conversations"
    __table_args__ = (
        Index("idx_chatconv_token", "guest_token"),
        Index("idx_chatconv_channel_status", "channel", "status", "last_message_at"),
        Index("idx_chatconv_user", "user_id"),
        Index("idx_chatconv_artist", "artist_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conv_no = Column(String(16), nullable=False, unique=True)  # CV260814xxxx
    channel = Column(SmallInteger, nullable=False, default=0)  # 0 AI 1 人工 2 美甲师
    user_id = Column(BigInteger)
    guest_token = Column(String(64), nullable=False, default="")
    email = Column(String(191))
    name = Column(String(100))
    lang = Column(String(2), nullable=False, default="en")  # 欢迎语/AI 回复语言
    artist_id = Column(BigInteger)                          # channel=2 时的美甲师 user_id
    agent_admin_id = Column(BigInteger)                     # channel=1 接手客服 user_id
    status = Column(SmallInteger, nullable=False, default=0)  # 0 进行中 1 已关闭
    last_message_at = Column(DateTime)
    closed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("idx_chatmsg_conv", "conversation_id", "id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(BigInteger, nullable=False, index=True)
    # 1 客户 2 客服 3 系统 4 AI 机器人 5 美甲师
    sender = Column(SmallInteger, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
