"""媒体域后台路由 —— POST /api/admin/media/upload（multipart 字段 file）
+ GET /api/admin/media 媒体库列表 / DELETE /api/admin/media/{filename} 删除"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.media import service
from app.models import User

router = APIRouter(tags=["admin-media"])


@router.post("/api/admin/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 多读 1 字节即可判定超限（413 交给 service），不把超大文件整载内存
    data = await file.read(service.MAX_UPLOAD_BYTES + 1)
    return service.save_upload(
        db, admin, filename=file.filename,
        content_type=file.content_type, data=data,
    )


@router.get("/api/admin/media")
def list_media(
    q: str | None = Query(None, description="文件名子串过滤"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.list_media(page, size, q)


@router.delete("/api/admin/media/{filename:path}")
def delete_media(
    filename: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除媒体：路径安全校验（防穿越，:path 兼容 YYYYMM/xxx.png 相对名）
    + 基础引用检查（在用 409）"""
    return service.delete_media(db, admin, filename)
