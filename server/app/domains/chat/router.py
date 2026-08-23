"""聊天域用户侧路由 —— /api/chat/*（HTTP 编排，业务在 service）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user_optional
from app.domains.chat import service
from app.domains.chat.schemas import ConversationStartIn, EscalateIn, MessageIn, TokenIn
from app.models import User

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _token(q: str) -> str:
    TokenIn(token=q)  # 复用校验（非法直接 422）
    return q


@router.get("/artists")
def list_artists(db: Session = Depends(get_db)):
    """公开美甲师列表（前台聊天窗选择美甲师用）"""
    return {"items": service.repo.artists_public(db)}


@router.get("/quicks")
def list_quicks(db: Session = Depends(get_db)):
    """客户聊天窗快捷问题（后台可配置，见 /chat ⚡ 客户快捷问题）"""
    return service.quick_replies(db)


@router.post("/conversations")
def start_conversation(
    body: ConversationStartIn,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service.start_conversation(db, body, user)


@router.get("/conversations")
def my_conversations(
    token: str = Query(...),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    _token(token)
    return service.my_conversations(db, token, user)


@router.get("/conversations/{conv_no}/messages")
def get_messages(
    conv_no: str,
    token: str = Query(...),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    _token(token)
    return service.get_messages(db, conv_no, token, user)


@router.post("/conversations/{conv_no}/messages")
def send_message(
    conv_no: str,
    body: MessageIn,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service.send_message(db, conv_no, body, user)


@router.post("/conversations/{conv_no}/escalate")
def escalate(
    conv_no: str,
    body: EscalateIn,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service.escalate(db, conv_no, body, user)


@router.post("/conversations/{conv_no}/close")
def close_conversation(
    conv_no: str,
    body: TokenIn,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service.close_conversation(db, conv_no, body.token, user)
