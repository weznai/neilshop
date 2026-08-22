"""媒体域服务 —— 上传校验与落盘（路径拼接收敛在本模块，路由层不碰文件系统）"""

import secrets
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import AdminLog, User

# 上传根目录（相对 server/ 的 static/uploads，与 main.py 的 /static 挂载对应）
_UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "static" / "uploads"

# 白名单：扩展名 → content-type（双校验且须一致，杜绝只改扩展名/只改头伪装）
_EXT_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB 上限（超出 413）


def _ext_of(filename: str | None) -> str:
    """仅取原始文件名扩展并小写化（不信任原名其余部分，落盘名完全服务端生成）"""
    name = filename or ""
    return name.rsplit(".", 1)[-1].strip().lower() if "." in name else ""


def save_upload(
    db: Session, admin: User, *, filename: str | None,
    content_type: str | None, data: bytes,
) -> dict:
    """校验（白名单双校验 + 大小上限）后落盘 static/uploads/{YYYYMM}/{随机名}.{ext}"""
    ext = _ext_of(filename)
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ext not in _EXT_CONTENT_TYPES or ctype != _EXT_CONTENT_TYPES[ext]:
        raise HTTPException(status_code=400, detail="unsupported image type")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    month_dir = _UPLOAD_ROOT / utcnow().strftime("%Y%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    target = None
    for _ in range(5):
        candidate = month_dir / f"{secrets.token_hex(5)}.{ext}"  # 10 位十六进制，落在 8-12 位区间
        if not candidate.exists():
            target = candidate
            break
    if target is None:
        raise HTTPException(status_code=500, detail="file name collision")
    target.write_bytes(data)
    url = f"/static/uploads/{month_dir.name}/{target.name}"
    db.add(AdminLog(
        admin_id=admin.id, action="upload", entity="media", entity_id=0,
        diff_json={"url": url, "bytes": len(data)},
    ))
    db.commit()
    return {"url": url}
