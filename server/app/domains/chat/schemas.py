"""聊天域 Pydantic 输入模型与静态文案（就近存放）"""

import re

from pydantic import BaseModel, field_validator

MAX_CHAT_CHARS = 2000     # 单条消息上限（超长截断）
TOKEN_RX = re.compile(r"^[0-9a-zA-Z_-]{8,64}$")  # 游客会话 token（前端 localStorage uuid）
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

WELCOME = {
    "en": "Hi, glam! 💅 I'm GlowBot — ask me about orders, sizing, shipping, returns or promo codes.",
    "zh": "嗨，宝贝！💅 我是 GlowBot——订单、尺码、运费、退换、折扣码都可以问我～",
}
SYS_HUMAN_WAITING = {
    "en": "Connecting you to a human agent 💜 Average first reply is under 4 hours; you can keep typing.",
    "zh": "正在为你转接人工客服 💜 平均 4 小时内首次回复，你可以先继续留言～",
}
SYS_ESCALATED = {
    "en": "Switched to a human agent — your chat history stays with you.",
    "zh": "已转接人工客服，聊天记录会完整保留～",
}
SYS_AGENT_JOINED = {
    "en": "Agent {name} joined the chat.",
    "zh": "客服 {name} 已接入～",
}
SYS_BACK_TO_AI = {
    "en": "Switched back to GlowBot — AI will answer from here.",
    "zh": "已转回 AI 客服（GlowBot），继续为你服务～",
}
SYS_ARTIST_JOINED = {
    "en": "Nail artist {name} joined the chat.",
    "zh": "美甲师 {name} 已接入～",
}
SYS_CLOSED = {
    "en": "Conversation closed. Tap any channel to start a new one.",
    "zh": "会话已结束，随时可以重新发起聊天～",
}
ESCALATE_ASK_EMAIL = {
    "en": "Sure — connecting you to a human 💜 Please leave your email first so we can reach you, then tap \"Human\" to continue.",
    "zh": "好的，正在为你转人工 💜 请先在「人工客服」页留下邮箱方便联系你，再继续对话～",
}

CHANNEL_LABEL = {0: "AI", 1: "Human", 2: "Artist"}
SENDER_LABEL = {1: "Customer", 2: "Agent", 3: "System", 4: "GlowBot", 5: "Artist"}


def _clean(v: str | None) -> str:
    return re.sub(r"\s+", " ", (v or "").strip())


class ConversationStartIn(BaseModel):
    channel: int          # 0 AI 1 人工 2 美甲师
    token: str            # 游客会话 token（登录用户也带，绑会话续聊）
    lang: str = "en"      # 欢迎语/系统消息语言（zh/en）
    email: str | None = None
    name: str | None = None
    artist_id: int | None = None

    @field_validator("channel")
    @classmethod
    def _v_channel(cls, v: int) -> int:
        if v not in (0, 1, 2):
            raise ValueError("invalid channel")
        return v

    @field_validator("token")
    @classmethod
    def _v_token(cls, v: str) -> str:
        if not TOKEN_RX.match(v or ""):
            raise ValueError("invalid token")
        return v

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str | None) -> str | None:
        v = _clean(v)
        if v and not EMAIL_RX.match(v):
            raise ValueError("invalid email")
        return v or None


class MessageIn(BaseModel):
    content: str
    token: str

    @field_validator("content")
    @classmethod
    def _v_content(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty content")
        return v[:MAX_CHAT_CHARS]

    @field_validator("token")
    @classmethod
    def _v_token(cls, v: str) -> str:
        if not TOKEN_RX.match(v or ""):
            raise ValueError("invalid token")
        return v


class EscalateIn(BaseModel):
    token: str
    email: str | None = None
    name: str | None = None

    @field_validator("token")
    @classmethod
    def _v_token(cls, v: str) -> str:
        if not TOKEN_RX.match(v or ""):
            raise ValueError("invalid token")
        return v

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str | None) -> str | None:
        v = _clean(v)
        if v and not EMAIL_RX.match(v):
            raise ValueError("invalid email")
        return v or None


class TokenIn(BaseModel):
    token: str

    @field_validator("token")
    @classmethod
    def _v_token(cls, v: str) -> str:
        if not TOKEN_RX.match(v or ""):
            raise ValueError("invalid token")
        return v


class ReplyIn(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def _v_content(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("empty content")
        return v[:MAX_CHAT_CHARS]
