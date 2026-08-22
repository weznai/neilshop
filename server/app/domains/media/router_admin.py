"""媒体域后台路由 —— POST /api/admin/media/upload（multipart 字段 file）"""

from fastapi import APIRouter, Depends, File, UploadFile
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
