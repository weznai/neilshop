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


# ===== AI 客服大模型配置（settings key=llm_config，覆盖 GM_LLM_* 环境变量） =====
@router.get("/api/admin/ai/config")
def get_ai_config(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """当前生效配置（API Key 脱敏）+ 来源标记（db=后台配置 / env=环境变量 / 空=未配置）"""
    from app.services.llm import LLM_SETTING_KEY, mask_key, resolve_params
    from app.domains.chat.retrieval import rag_status

    p = resolve_params(db)
    row = db.get(Setting, LLM_SETTING_KEY)
    db_key = bool(row and isinstance(row.value, dict) and row.value.get("api_key"))
    from app.core.config import settings as _cfg
    source = "db" if db_key else ("env" if _cfg.llm_api_key else "")
    return {
        "api_key_set": bool(p.get("api_key")),
        "api_key_masked": mask_key(p.get("api_key") or ""),
        "base_url": p.get("base_url"),
        "model": p.get("model"),
        "timeout": p.get("timeout"),
        "max_tokens": p.get("max_tokens"),
        "temperature": p.get("temperature", 0.4),
        "persona": p.get("persona") or "",
        "prompt_extra": p.get("prompt_extra") or "",
        "embedding_model": p.get("embedding_model") or "",
        "rag": rag_status(db),
        "source": source,
        "updated_at": row.updated_at if row else None,
    }


@router.put("/api/admin/ai/config")
def save_ai_config(body: dict, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """保存 LLM 配置：字段存在才更新（api_key 传空串=清除）；立即生效（每次调用实时 resolve）"""
    from app.services.llm import LLM_SETTING_KEY

    clean: dict = {}
    row = db.get(Setting, LLM_SETTING_KEY)
    cur = dict(row.value) if (row and isinstance(row.value, dict)) else {}

    if "api_key" in body:
        k = str(body.get("api_key") or "").strip()
        if k and len(k) > 200:
            raise HTTPException(status_code=422, detail="api_key 过长")
        cur["api_key"] = k
    if "base_url" in body:
        u = str(body.get("base_url") or "").strip().rstrip("/")
        if u and not (u.startswith("http://") or u.startswith("https://")):
            raise HTTPException(status_code=422, detail="base_url 需以 http(s):// 开头")
        cur["base_url"] = u
    if "model" in body:
        m = str(body.get("model") or "").strip()
        if not m or len(m) > 100:
            raise HTTPException(status_code=422, detail="model 必填且 ≤100 字符")
        cur["model"] = m
    for k, lo, hi in (("timeout", 3, 60), ("max_tokens", 50, 2000)):
        if k in body:
            v = body.get(k)
            if not isinstance(v, int) or not (lo <= v <= hi):
                raise HTTPException(status_code=422, detail=f"{k} 需为 {lo}-{hi} 的整数")
            cur[k] = v
    if "temperature" in body:
        v = body.get("temperature")
        if not isinstance(v, (int, float)) or not (0 <= v <= 2):
            raise HTTPException(status_code=422, detail="temperature 需为 0-2 的数值")
        cur["temperature"] = round(float(v), 2)
    for k, hi in (("persona", 500), ("prompt_extra", 2000), ("embedding_model", 100)):
        if k in body:
            v = str(body.get(k) or "").strip()
            if len(v) > hi:
                raise HTTPException(status_code=422, detail=f"{k} 超长（≤{hi} 字符）")
            cur[k] = v

    clean = {k2: v2 for k2, v2 in cur.items() if v2 not in ("", None)}
    if row:
        row.value = clean
        row.updated_by = admin.id
    else:
        db.add(Setting(key=LLM_SETTING_KEY, value=clean,
                       description="AI 客服大模型配置（OpenAI 兼容）", updated_by=admin.id))
    from app.domains.support.service import log_admin
    log_admin(db, admin, "setting", "llm_config", 0, {})
    db.commit()
    return {"ok": True}


@router.get("/api/admin/ai/prompt-preview")
def ai_prompt_preview(q: str | None = Query(None, description="模拟客户问题：RAG 就绪时预览 top-k 片段注入效果"),
                      admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """最终系统提示词预览：人设 + 安全红线 + 补充指令 + 政策摘要 + FAQ 知识库（实际下发内容）"""
    from app.domains.chat.prompt import DEFAULT_PERSONA, SAFETY_RULES, build_system_prompt

    return {
        "prompt": build_system_prompt(db, q),
        "default_persona": DEFAULT_PERSONA,
        "safety_rules": SAFETY_RULES,
        "rag": q is not None,
    }


@router.post("/api/admin/ai/rag/reindex")
def rag_reindex(body: dict | None = None, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """（重建）FAQ 向量索引：默认只补缺失行，body.full=true 全量重建（换 embedding 模型后用）"""
    from app.domains.chat.retrieval import reindex, rag_status

    full = bool((body or {}).get("full")) if body else False
    out = reindex(db, only_missing=not full)
    if out.get("ok"):
        from app.domains.support.service import log_admin
        log_admin(db, admin, "setting", "llm_rag_reindex", 0, {"full": full, **{k: out[k] for k in ("indexed", "failed")}})
        db.commit()
    out["rag"] = rag_status(db)
    return out


@router.post("/api/admin/ai/test")
def test_ai_config(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """连通性测试：用当前生效配置发一条极小补全，返回延迟与回复（未配置/失败给原因）"""
    import time

    from app.services.llm import chat_completion, resolve_params

    p = resolve_params(db)
    if not p.get("api_key"):
        return {"ok": False, "reason": "未配置 API Key（当前 AI 客服走内置规则引擎）"}
    t0 = time.monotonic()
    reply = chat_completion(
        "You are a connectivity test. Reply with exactly: OK",
        [{"role": "user", "content": "ping"}], temperature=0, params=p)
    ms = int((time.monotonic() - t0) * 1000)
    if reply:
        return {"ok": True, "latency_ms": ms, "model": p.get("model"), "reply": reply[:80]}
    return {"ok": False, "latency_ms": ms, "model": p.get("model"),
            "reason": f"调用失败（{ms}ms）——检查 Key/网关地址/模型名，详见服务端日志"}
