"""聊天域服务 —— 三渠道会话编排：AI（LLM+知识库→规则引擎兜底）/ 人工（转接/接入）/ 美甲师

AI 回复策略（_ai_generate）：
- 订单类意图固定走 ai 域规则引擎 —— 查库 + 邮箱双因子脱敏，LLM 不碰数据查询
- 其余意图优先 LLM（OpenAI 兼容网关，FAQ 知识库注入 system prompt），失败/未配置回退规则引擎
- 「转人工」意图：有邮箱（会话或登录账户）直接升级会话渠道保留记录，无邮箱引导补邮箱
"""

import logging
import re
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import ChatSender, UserRole
from app.models import ChatConversation, ChatMessage, User
from app.domains.ai import repository as ai_repo
from app.domains.ai.schemas import ChatIn
from app.domains.ai.service import chat as ai_rules_chat
from app.domains.chat import repository as repo
from app.domains.chat.schemas import (
    CHANNEL_LABEL, ESCALATE_ASK_EMAIL, SENDER_LABEL, SYS_AGENT_JOINED, SYS_ARTIST_JOINED,
    SYS_BACK_TO_AI, SYS_CLOSED, SYS_ESCALATED, SYS_HUMAN_WAITING, WELCOME,
    ConversationStartIn, EscalateIn, MessageIn,
)
from app.domains.support.service import log_admin
from app.services import llm

log = logging.getLogger("glowmag.chat")

AI_CONTEXT_TURNS = 10  # LLM 携带的最近对话轮数（双向消息条数）


def _conv_no() -> str:
    return "CV" + utcnow().strftime("%y%m%d") + uuid.uuid4().hex[:4].upper()


def _lang_ok(v: str) -> str:
    return "zh" if (v or "").strip().lower() == "zh" else "en"


def _msg_dict(m: ChatMessage, sender_name: str | None = None) -> dict:
    label = None
    if m.sender == ChatSender.AGENT:
        label = sender_name or SENDER_LABEL[2]
    elif m.sender == ChatSender.BOT:
        label = "GlowBot"
    elif m.sender == ChatSender.ARTIST:
        label = sender_name or SENDER_LABEL[5]
    return {
        "id": m.id,
        "sender": m.sender,
        "sender_name": label,
        "content": m.content,
        "created_at": m.created_at,
    }


def _conv_dict(
    c: ChatConversation, *, names: dict[int, str] | None = None,
    last: ChatMessage | None = None,
) -> dict:
    names = names or {}
    out = {
        "conv_no": c.conv_no,
        "channel": c.channel,
        "channel_label": CHANNEL_LABEL.get(c.channel),
        "status": c.status,
        "email": c.email,
        "name": c.name,
        "lang": c.lang,
        "artist_id": c.artist_id,
        "artist_name": names.get(c.artist_id) if c.artist_id else None,
        "agent_admin_id": c.agent_admin_id,
        "agent_name": names.get(c.agent_admin_id) if c.agent_admin_id else None,
        "last_message_at": c.last_message_at or c.created_at,
        "created_at": c.created_at,
        "closed_at": c.closed_at,
    }
    if last is not None:
        out["last_message"] = {
            "sender": last.sender,
            "preview": (last.content or "")[:80],
            "created_at": last.created_at,
        }
        # 客户最后发言且会话进行中 → 待客服/美甲师处理（列表红点）
        out["pending_reply"] = c.status == 0 and last.sender == int(ChatSender.CUSTOMER)
    return out


def _names_for(db: Session, convs: list[ChatConversation]) -> dict[int, str]:
    ids = set()
    for c in convs:
        ids.update(x for x in (c.artist_id, c.agent_admin_id) if x)
    return repo.user_names_by_ids(db, ids)


def _get_authorized(db: Session, conv_no: str, token: str, user: User | None) -> ChatConversation:
    """会话归属核验：guest_token 匹配，或登录用户与会话 user_id 一致（防跨会话越权读取）"""
    conv = repo.conversation_by_no(db, conv_no)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if conv.guest_token != token:
        if not (user is not None and conv.user_id == user.id):
            raise HTTPException(status_code=403, detail="not conversation owner")
    return conv


def _add_msg(db: Session, conv: ChatConversation, sender: int, content: str) -> ChatMessage:
    m = ChatMessage(conversation_id=conv.id, sender=sender, content=content)
    conv.last_message_at = utcnow()
    db.add(m)
    return m


# ===== 用户侧 =====


def quick_replies(db: Session) -> dict:
    """客户聊天窗快捷问题：settings 可配置，未配置/坏数据回退默认（归一/钳制见 schemas.quick_norm）
    （不走 ai_repo.setting_value——其 type(default)(value) 钳制面向标量，dict 会恒返默认）"""
    from app.domains.chat.schemas import QUICK_SETTING_KEY, quick_norm
    from app.models import Setting

    try:
        row = db.get(Setting, QUICK_SETTING_KEY)
        raw = row.value if row else None
    except Exception:
        raw = None
    return quick_norm(raw)


def start_conversation(db: Session, body: ConversationStartIn, user: User | None) -> dict:
    artist = None
    if body.channel == 2:
        if not body.artist_id:
            raise HTTPException(status_code=422, detail="artist_id required")
        artist = repo.artist_by_id(db, body.artist_id)
        if not artist:
            raise HTTPException(status_code=404, detail="artist not found")
    if body.channel in (1, 2) and not (body.email or (user and user.email)):
        # 人工/美甲师渠道需要回联邮箱（登录用户自动带账户邮箱）
        raise HTTPException(status_code=422, detail="email required")

    # 合并客服语义：AI 与人工是同一会话的内部状态（channel 0↔1），不建平行会话
    if body.channel == 0:
        # 已有进行中人工会话 → 直接复用（转回 AI 前不再开新 AI 会话）
        existing = repo.open_conversation(
            db, channel=1, token=body.token, user_id=user.id if user else None, artist_id=None)
        if existing:
            return _conv_detail(db, existing)
    elif body.channel == 1:
        # 已有进行中 AI 会话 → 原地升级为人工（聊天记录完整保留）
        existing = repo.open_conversation(
            db, channel=0, token=body.token, user_id=user.id if user else None, artist_id=None)
        if existing:
            email = body.email or existing.email or (user.email if user else None)
            if not email:
                raise HTTPException(status_code=422, detail="email required")
            existing.channel = 1
            existing.email = email
            if body.name:
                existing.name = body.name
            lang = "zh" if existing.lang == "zh" else "en"
            _add_msg(db, existing, int(ChatSender.SYSTEM), SYS_ESCALATED[lang])
            _add_msg(db, existing, int(ChatSender.SYSTEM), SYS_HUMAN_WAITING[lang])
            db.commit()
            return _conv_detail(db, existing)

    conv = repo.open_conversation(
        db, channel=body.channel, token=body.token,
        user_id=user.id if user else None,
        artist_id=body.artist_id,
    )
    if conv:
        return _conv_detail(db, conv)

    conv = ChatConversation(
        conv_no=_conv_no(),
        channel=body.channel,
        user_id=user.id if user else None,
        guest_token=body.token,
        email=(body.email or (user.email if user else None) or ""),
        name=(body.name or (user.name if user else None) or ""),
        lang=_lang_ok(body.lang),
        artist_id=artist.id if artist else None,
        status=0,
    )
    db.add(conv)
    db.flush()
    zh = conv.lang == "zh"
    if body.channel == 0:
        _add_msg(db, conv, int(ChatSender.BOT), WELCOME["zh" if zh else "en"])
    elif body.channel == 1:
        _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_HUMAN_WAITING["zh" if zh else "en"])
    else:
        _add_msg(db, conv, int(ChatSender.SYSTEM),
                 (SYS_ARTIST_JOINED["zh" if zh else "en"]).format(name=artist.name or "Artist"))
    db.commit()
    return _conv_detail(db, conv)


def _conv_detail(db: Session, conv: ChatConversation) -> dict:
    out = _conv_dict(conv, names=_names_for(db, [conv]))
    out["messages"] = [_msg_dict(m, out.get("artist_name") if m.sender == 5 else out.get("agent_name"))
                       for m in repo.messages_asc(db, conv.id)]
    return out


def my_conversations(db: Session, token: str, user: User | None) -> dict:
    convs = repo.conversations_of(db, token, user.id if user else None)
    names = _names_for(db, convs)
    lmap = repo.last_messages_map(db, [c.id for c in convs])
    return {"items": [_conv_dict(c, names=names, last=lmap.get(c.id)) for c in convs]}


def get_messages(db: Session, conv_no: str, token: str, user: User | None) -> dict:
    conv = _get_authorized(db, conv_no, token, user)
    return _conv_detail(db, conv)


def escalate(db: Session, conv_no: str, body: EscalateIn, user: User | None) -> dict:
    """AI/美甲师会话 → 人工：保留全部记录，客户无感切换"""
    conv = _get_authorized(db, conv_no, body.token, user)
    if conv.status == 1:
        raise HTTPException(status_code=409, detail="conversation closed")
    if conv.channel == 1:
        return _conv_detail(db, conv)
    email = body.email or conv.email or (user.email if user else None)
    if not email:
        raise HTTPException(status_code=422, detail="email required")
    conv.channel = 1
    conv.email = email
    if body.name:
        conv.name = body.name
    zh = conv.lang == "zh"
    _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_ESCALATED["zh" if zh else "en"])
    _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_HUMAN_WAITING["zh" if zh else "en"])
    db.commit()
    return _conv_detail(db, conv)


def close_conversation(db: Session, conv_no: str, token: str, user: User | None) -> dict:
    conv = _get_authorized(db, conv_no, token, user)
    if conv.status == 1:
        return _conv_detail(db, conv)
    conv.status = 1
    conv.closed_at = utcnow()
    zh = conv.lang == "zh"
    _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_CLOSED["zh" if zh else "en"])
    db.commit()
    return _conv_detail(db, conv)


def _system_prompt(db: Session, query: str | None = None) -> str:
    """LLM 系统提示词（组装见 chat/prompt.py：人设可配 + 安全红线 + FAQ/政策注入；
    query 非空且 RAG 就绪时仅注入相关 FAQ 片段，否则全量）"""
    from app.domains.chat.prompt import build_system_prompt

    return build_system_prompt(db, query)


def _llm_history(history: list[ChatMessage]) -> list[dict]:
    out: list[dict] = []
    for m in history[-AI_CONTEXT_TURNS:]:
        if m.sender == int(ChatSender.CUSTOMER):
            out.append({"role": "user", "content": m.content})
        elif m.sender == int(ChatSender.BOT):
            out.append({"role": "assistant", "content": m.content})
    return out


def send_message(db: Session, conv_no: str, body: MessageIn, user: User | None) -> dict:
    conv = _get_authorized(db, conv_no, body.token, user)
    if conv.status == 1:
        raise HTTPException(status_code=409, detail="conversation closed")
    user_msg = _add_msg(db, conv, int(ChatSender.CUSTOMER), body.content)
    db.flush()

    new_msgs = [user_msg]
    suggestions: list[str] = []
    source = ""
    escalated = False

    if conv.channel == 0:
        zh = bool(re.search(r"[\u4e00-\u9fff]", body.content)) or conv.lang == "zh"
        lang = "zh" if zh else "en"
        # 规则引擎意图判定（订单查询双因子：会话邮箱即下单邮箱时直接放行）
        rules = ai_rules_chat(db, ChatIn(message=body.content, email=conv.email or None), user)
        suggestions = rules.get("suggestions") or []
        if rules["intent"] == "human":
            email = conv.email or (user.email if user else None)
            if email:
                # 直接升级转人工（保留记录），前端据 escalated 切换人工视图
                conv.channel = 1
                _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_ESCALATED[lang])
                _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_HUMAN_WAITING[lang])
                escalated = True
                source = "escalated"
            else:
                bot = _add_msg(db, conv, int(ChatSender.BOT), ESCALATE_ASK_EMAIL[lang])
                new_msgs.append(bot)
                escalated = True  # 前端同时高亮「人工客服」入口（先补邮箱）
                source = "rules"
        elif rules["intent"] == "order":
            # 订单查询固定走规则引擎：查库 + 双因子脱敏，LLM 不碰数据类问题
            bot = _add_msg(db, conv, int(ChatSender.BOT), rules["reply"])
            new_msgs.append(bot)
            source = "rules"
        else:
            p = llm.resolve_params(db)
            reply = llm.chat_completion(_system_prompt(db, body.content), _llm_history(
                repo.messages_asc(db, conv.id)), params=p)
            if reply:
                bot = _add_msg(db, conv, int(ChatSender.BOT), reply)
                new_msgs.append(bot)
                source = "llm"
            else:
                bot = _add_msg(db, conv, int(ChatSender.BOT), rules["reply"])
                new_msgs.append(bot)
                source = "rules"
    db.commit()

    detail = _conv_detail(db, conv)
    detail["new_messages"] = [
        _msg_dict(m, detail.get("artist_name") if m.sender == 5 else detail.get("agent_name"))
        for m in new_msgs
    ]
    detail["suggestions"] = suggestions
    detail["source"] = source
    detail["escalated"] = escalated
    return detail


# ===== 后台：聊天工作台 =====


def _admin_names(db: Session, convs: list[ChatConversation]) -> dict[int, str]:
    return _names_for(db, convs)


def admin_list(
    db: Session, channel: int | None, status: int | None, q: str | None,
    mine_admin_id: int | None, page: int, size: int,
) -> dict:
    query = repo.admin_conversations_query(db, channel, status, q, mine_admin_id)
    rows, total = repo.page(query, page, size)
    names = _admin_names(db, rows)
    lmap = repo.last_messages_map(db, [c.id for c in rows])
    return {
        "items": [_conv_dict(c, names=names, last=lmap.get(c.id)) for c in rows],
        "total": total, "page": page, "size": size,
    }


def admin_conversation(db: Session, conv_no: str) -> dict:
    conv = repo.conversation_by_no(db, conv_no)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _conv_detail(db, conv)


def admin_reply(db: Session, admin: User, conv_no: str, content: str) -> dict:
    conv = repo.conversation_by_no(db, conv_no)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if conv.status == 1:
        raise HTTPException(status_code=400, detail="conversation closed")
    # 美甲师本人回复美甲师渠道 → sender=5；其余（运营/超管代答）→ sender=2 客服
    sender = int(ChatSender.ARTIST) if (
        conv.channel == 2 and admin.role == int(UserRole.ARTIST)
    ) else int(ChatSender.AGENT)
    lang = "zh" if conv.lang == "zh" else "en"
    joined = False
    if conv.channel == 0:
        # 客服在 AI 会话中直接回复 → 内部切换为人工（记录保留，客户侧见接入提示）
        conv.channel = 1
        joined = True
    if conv.channel == 1 and conv.agent_admin_id is None:
        conv.agent_admin_id = admin.id
        joined = True
    if joined:
        _add_msg(db, conv, int(ChatSender.SYSTEM),
                 SYS_AGENT_JOINED[lang].format(name=admin.name or "Agent"))
    if conv.channel == 2 and sender == int(ChatSender.ARTIST):
        _add_msg(db, conv, int(ChatSender.SYSTEM),
                 SYS_ARTIST_JOINED[lang].format(name=admin.name or "Artist"))
    _add_msg(db, conv, sender, content)
    log_admin(db, admin, "reply", "chat_conversation", conv.id, {"channel": conv.channel})
    db.commit()
    return _conv_detail(db, conv)


def admin_resume_ai(db: Session, admin: User, conv_no: str) -> dict:
    """人工 → AI 内部切换：交还 GlowBot 自动应答（会话/记录不变，客户侧系统提示可见）"""
    conv = repo.conversation_by_no(db, conv_no)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if conv.channel != 1:
        raise HTTPException(status_code=400, detail="not a human conversation")
    if conv.status == 1:
        raise HTTPException(status_code=400, detail="conversation closed")
    conv.channel = 0
    lang = "zh" if conv.lang == "zh" else "en"
    _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_BACK_TO_AI[lang])
    log_admin(db, admin, "resume_ai", "chat_conversation", conv.id, {})
    db.commit()
    return _conv_detail(db, conv)


def admin_take(db: Session, admin: User, conv_no: str) -> dict:
    conv = repo.conversation_by_no(db, conv_no)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if conv.channel != 1:
        raise HTTPException(status_code=400, detail="not a human conversation")
    if conv.status == 1:
        raise HTTPException(status_code=400, detail="conversation closed")
    first = conv.agent_admin_id is None
    conv.agent_admin_id = admin.id
    if first:
        lang = "zh" if conv.lang == "zh" else "en"
        _add_msg(db, conv, int(ChatSender.SYSTEM),
                 SYS_AGENT_JOINED[lang].format(name=admin.name or "Agent"))
    log_admin(db, admin, "take", "chat_conversation", conv.id, {})
    db.commit()
    return _conv_detail(db, conv)


def admin_close(db: Session, admin: User, conv_no: str) -> dict:
    conv = repo.conversation_by_no(db, conv_no)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if conv.status == 1:
        raise HTTPException(status_code=409, detail="conversation already closed")
    conv.status = 1
    conv.closed_at = utcnow()
    zh = conv.lang == "zh"
    _add_msg(db, conv, int(ChatSender.SYSTEM), SYS_CLOSED["zh" if zh else "en"])
    log_admin(db, admin, "close", "chat_conversation", conv.id, {})
    db.commit()
    return _conv_detail(db, conv)
