"""聊天域后台路由 —— /api/admin/chat/*（绝对路径，由 main 的 admin 聚合组装）"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.chat import service
from app.domains.chat.schemas import (
    QUICK_SETTING_KEY, ReplyIn, quick_defaults, quick_norm, quick_norm_item,
)
from app.models import Setting, User

router = APIRouter(tags=["admin-chat"])


def _parse_channel(raw: int | None) -> int | None:
    if raw is None:
        return None
    if raw not in (0, 1, 2):
        raise HTTPException(status_code=422, detail="invalid channel")
    return raw


def _parse_status(raw: int | None) -> int | None:
    if raw is None:
        return None
    if raw not in (0, 1):
        raise HTTPException(status_code=422, detail="invalid status")
    return raw


@router.get("/api/admin/chat/conversations")
def admin_conversations(
    channel: int | None = Query(None, description="0 AI 1 人工 2 美甲师"),
    status: int | None = Query(None, description="0 进行中 1 已关闭"),
    q: str | None = Query(None),
    mine: int | None = Query(None, description="1=我的会话（人工=我接手 / 美甲师=本人）"),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.admin_list(
        db, _parse_channel(channel), _parse_status(status), q,
        admin.id if mine == 1 else None, page, size,
    )


@router.get("/api/admin/chat/conversations/{conv_no}")
def admin_conversation(conv_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_conversation(db, conv_no)


@router.post("/api/admin/chat/conversations/{conv_no}/reply")
def admin_reply(
    conv_no: str, body: ReplyIn,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service.admin_reply(db, admin, conv_no, body.content)


@router.post("/api/admin/chat/conversations/{conv_no}/take")
def admin_take(conv_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_take(db, admin, conv_no)


@router.post("/api/admin/chat/conversations/{conv_no}/resume-ai")
def admin_resume_ai(conv_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """人工 → AI 内部切换（同一会话交还 GlowBot 自动应答）"""
    return service.admin_resume_ai(db, admin, conv_no)


@router.post("/api/admin/chat/conversations/{conv_no}/close")
def admin_close(conv_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.admin_close(db, admin, conv_no)


@router.put("/api/admin/chat/quicks")
def save_quicks(
    body: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """客户快捷问题配置：{"zh": [item], "en": [item]}（结构化校验 + 钳制见 schemas.quick_norm_item）"""
    clean = {}
    for lang in ("zh", "en"):
        items = body.get(lang)
        if not isinstance(items, list):
            raise HTTPException(status_code=422, detail=f"{lang} must be a list")
        normed = [x for x in (quick_norm_item(i) for i in items) if x]
        if not normed:
            raise HTTPException(status_code=422, detail=f"{lang} has no valid items")
        clean[lang] = normed
    row = db.query(Setting).filter(Setting.key == QUICK_SETTING_KEY).first()
    if row:
        row.value = clean
        row.updated_by = admin.id
    else:
        db.add(Setting(key=QUICK_SETTING_KEY, value=clean,
                       description="客户聊天窗快捷问题（中/英，含动作类型）", updated_by=admin.id))
    from app.domains.support.service import log_admin
    log_admin(db, admin, "setting", "chat_quick_replies", 0, {})
    db.commit()
    return clean


@router.get("/api/admin/chat/quicks")
def get_quicks(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """配置态读取：当前生效项（归一后）+ 原始是否自定义标记 + 审计（最后修改人/时间）"""
    row = db.query(Setting).filter(Setting.key == QUICK_SETTING_KEY).first()
    out = {"items": quick_norm(row.value if row else None), "customized": row is not None}
    if row is not None:
        from app.domains.chat import repository as chat_repo
        names = chat_repo.user_names_by_ids(db, {row.updated_by} if row.updated_by else set())
        out["updated_by"] = names.get(row.updated_by) if row.updated_by else None
        out["updated_at"] = row.updated_at
    return out


@router.post("/api/admin/chat/quicks/reset")
def reset_quicks(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """恢复出厂默认（删除自定义配置行）"""
    row = db.query(Setting).filter(Setting.key == QUICK_SETTING_KEY).first()
    if row:
        db.delete(row)
        from app.domains.support.service import log_admin
        log_admin(db, admin, "setting", "chat_quick_replies", 0, {"action": "reset"})
        db.commit()
    return quick_defaults()
