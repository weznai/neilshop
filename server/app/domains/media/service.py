"""媒体域服务 —— 上传校验与落盘 + 媒体库列表/删除（路径拼接收敛在本模块，路由层不碰文件系统）"""

import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import cast, String
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import (
    AdminLog, Article, Collection, Product, Review, UgcSubmission, User, VariantImage,
)

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

# 魔数白名单：按扩展名匹配文件头（JPEG/PNG/GIF/WEBP），杜绝改扩展名/改 Content-Type 的伪装载荷
_IMAGE_MAGICS: dict[str, tuple[bytes, ...]] = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
}


def _magic_ok(ext: str, data: bytes) -> bool:
    """文件头魔数校验：WEBP 需 RIFF + 偏移 8..12 为 WEBP 双段判定，其余按前缀白名单"""
    if ext == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return any(data.startswith(m) for m in _IMAGE_MAGICS.get(ext, ()))

# 文件名/目录段白名单：字母数字加点划线（拒绝路径穿越 ../..、盘符、反斜杠、空白与控制符）
_NAME_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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
    if not _magic_ok(ext, data):
        # 扩展名/Content-Type 合法但文件头不是图片 → 415（防伪装成图片的非图片载荷）
        raise HTTPException(status_code=415, detail="invalid image content")
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


# ===== 媒体库列表 / 删除 =====


def _safe_relpath(filename: str) -> Path:
    """路径安全校验：仅允许「白名单字符段/白名单字符段」形式的相对路径
    （如 202608/ab12cd34ef.png）；拒绝穿越（../）、绝对路径、盘符、反斜杠等"""
    name = (filename or "").strip().replace("\\", "/")
    if not name or name.startswith("/") or len(name) > 255:
        raise HTTPException(status_code=400, detail="invalid filename")
    segments = name.split("/")
    if len(segments) > 4 or not all(
        _NAME_SEGMENT_RE.match(s) and s not in (".", "..") for s in segments
    ):
        raise HTTPException(status_code=400, detail="invalid filename")
    candidate = _UPLOAD_ROOT.joinpath(*segments)
    # 纵深防御：解析后必须仍落在 uploads 根内
    try:
        candidate.resolve().relative_to(_UPLOAD_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid filename")
    return candidate


def _scan_files() -> list[Path]:
    """全量扫描上传目录（不存在返回空），后续内存过滤/分页（本地目录规模可控）"""
    if not _UPLOAD_ROOT.exists():
        return []
    return [p for p in _UPLOAD_ROOT.rglob("*") if p.is_file()]


def list_media(page: int, size: int, q: str | None = None) -> dict:
    """媒体库列表：文件名/字节/修改时间/完整 URL；q 对相对路径子串过滤；
    按修改时间倒序（新上传在前），目录不存在返回空列表"""
    files = _scan_files()
    if q:
        needle = q.strip().lower()
        files = [p for p in files if needle in p.relative_to(_UPLOAD_ROOT)
                 .as_posix().lower()]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    total = len(files)
    chunk = files[(page - 1) * size: (page - 1) * size + size]
    items = [
        {
            "name": p.relative_to(_UPLOAD_ROOT).as_posix(),
            "bytes": p.stat().st_size,
            "modified_at": datetime.fromtimestamp(
                p.stat().st_mtime, tz=timezone.utc
            ).isoformat(timespec="seconds"),
            "url": f"/static/uploads/{p.relative_to(_UPLOAD_ROOT).as_posix()}",
        }
        for p in chunk
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


def _media_in_use(db: Session, basename: str) -> bool:
    """基础引用检查：商品主图/图集、变体图、集合 banner、文章封面、UGC/评价图
    任一 URL 字段 LIKE 命中即视为占用（JSON 列 cast 成字符串再匹配，双库兼容；
    autoescape 防 "_" 通配误伤）"""
    def _like(col):
        return col.contains(basename, autoescape=True)

    checks = (
        db.query(Product.id).filter(_like(Product.hero_image)),
        db.query(Product.id).filter(_like(cast(Product.images, String))),
        db.query(VariantImage.id).filter(_like(VariantImage.image_url)),
        db.query(Collection.id).filter(_like(Collection.banner_image)),
        db.query(Article.id).filter(_like(Article.cover)),
        db.query(UgcSubmission.id).filter(_like(UgcSubmission.image_url)),
        db.query(Review.id).filter(_like(cast(Review.images, String))),
    )
    return any(q.first() is not None for q in checks)


def delete_media(db: Session, admin: User, filename: str) -> dict:
    """删除媒体文件：路径安全校验 → 引用检查（命中 409 media in use）→ 删文件 + 审计"""
    target = _safe_relpath(filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    rel = target.relative_to(_UPLOAD_ROOT).as_posix()
    if _media_in_use(db, target.name):
        raise HTTPException(status_code=409, detail="media in use")
    target.unlink()
    db.add(AdminLog(
        admin_id=admin.id, action="delete", entity="media", entity_id=0,
        diff_json={"url": f"/static/uploads/{rel}"},
    ))
    db.commit()
    return {"ok": True, "deleted": rel}
