"""聊天域仓储 —— 纯查询/分页，不掺业务规则"""

from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session

from app.core.enums import UserRole
from app.models import ChatConversation, ChatMessage, Faq, User


def page(q: Query, page: int, size: int):
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return rows, total


def artists_public(db: Session) -> list[dict]:
    """公开美甲师列表（role=4 且启用）：只暴露 id/姓名/简介，不漏邮箱等敏感列"""
    rows = (
        db.query(User.id, User.name, User.artist_intro)
        .filter(User.role == int(UserRole.ARTIST), User.status == 1)
        .order_by(User.id)
        .all()
    )
    return [{"id": r.id, "name": r.name or f"Artist #{r.id}", "intro": r.artist_intro or ""} for r in rows]


def artist_by_id(db: Session, artist_id: int) -> User | None:
    return (
        db.query(User)
        .filter(User.id == artist_id, User.role == int(UserRole.ARTIST), User.status == 1)
        .first()
    )


def open_conversation(
    db: Session, *, channel: int, token: str, user_id: int | None, artist_id: int | None,
) -> ChatConversation | None:
    """同 token/用户 + 渠道（美甲师再按人）唯一进行中会话：存在即复用，聊天记录续上"""
    q = db.query(ChatConversation).filter(
        ChatConversation.channel == channel,
        ChatConversation.status == 0,
        or_(ChatConversation.guest_token == token, *(
            [ChatConversation.user_id == user_id] if user_id else []
        )),
    )
    if channel == 2:
        q = q.filter(ChatConversation.artist_id == (artist_id or 0))
    return q.order_by(ChatConversation.id.desc()).first()


def conversation_by_no(db: Session, conv_no: str) -> ChatConversation | None:
    return db.query(ChatConversation).filter(ChatConversation.conv_no == conv_no).first()


def conversations_of(db: Session, token: str, user_id: int | None) -> list[ChatConversation]:
    q = db.query(ChatConversation).filter(ChatConversation.guest_token == token)
    if user_id:
        q = q.union(
            db.query(ChatConversation).filter(ChatConversation.user_id == user_id)
        )
    return q.order_by(ChatConversation.last_message_at.desc(), ChatConversation.id.desc()).all()


def messages_asc(db: Session, conversation_id: int, limit: int | None = None) -> list[ChatMessage]:
    q = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    if limit:
        rows = q.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit).all()
        rows.reverse()
        return rows
    return q.all()


def last_messages_map(db: Session, conv_ids: list[int]) -> dict[int, ChatMessage]:
    """每会话最后一条消息：SQL 聚合（group by conv_id 取 MAX(id)）后按主键 IN 批查
    目标行，避免全量拉取到 Python 过滤（4 秒轮询 _pending_total 放大）；
    id 自增与 (created_at, id) 排序口径一致，返回形状 {conv_id: 消息行} 不变"""
    if not conv_ids:
        return {}
    max_ids = (
        db.query(func.max(ChatMessage.id))
        .filter(ChatMessage.conversation_id.in_(conv_ids))
        .group_by(ChatMessage.conversation_id)
        .all()
    )
    ids = [r[0] for r in max_ids]
    if not ids:
        return {}
    rows = db.query(ChatMessage).filter(ChatMessage.id.in_(ids)).all()
    return {m.conversation_id: m for m in rows}


def user_names_by_ids(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {u.id: (u.name or u.email) for u in rows}


def admin_conversations_query(
    db: Session, channel: int | None, status: int | None, q: str | None, mine_admin_id: int | None,
) -> Query:
    query = db.query(ChatConversation)
    if channel is not None:
        query = query.filter(ChatConversation.channel == channel)
    if status is not None:
        query = query.filter(ChatConversation.status == status)
    if mine_admin_id is not None:
        # 我的会话：人工渠道=我接手；美甲师渠道=我是美甲师本人
        query = query.filter(or_(
            (ChatConversation.channel == 1) & (ChatConversation.agent_admin_id == mine_admin_id),
            (ChatConversation.channel == 2) & (ChatConversation.artist_id == mine_admin_id),
        ))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            ChatConversation.conv_no.ilike(like),
            func.lower(ChatConversation.email).like(like.lower()),
            ChatConversation.name.ilike(like),
        ))
    return query.order_by(
        ChatConversation.status.asc(), ChatConversation.last_message_at.desc(), ChatConversation.id.desc()
    )


def active_faqs(db: Session) -> list[Faq]:
    """AI 知识库源：全量启用 FAQ（内容管理维护，问答对注入 LLM system prompt）"""
    return db.query(Faq).filter(Faq.active == 1).order_by(Faq.category, Faq.sort_order).all()
