"""内容域用户侧路由 —— /api/content/*（HTTP 编排，业务在 service）"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_current_user_optional
from app.domains.content import service
from app.domains.content.schemas import ReviewIn, UgcIn
from app.models import User

router = APIRouter(prefix="/api/content", tags=["content"])


@router.post("/reviews/upload")
async def upload_review_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """评价图片上传（登录，multipart）：png/jpeg/webp/gif ≤5MB，
    返回 {url}（/static/uploads/reviews/{yyyymm}/{uuid}.{ext}，静态挂载公开可访问）。
    多读 1 字节判定超限，不把超大文件整载内存。"""
    data = await file.read(service.REVIEW_UPLOAD_MAX_BYTES + 1)
    return service.save_review_upload(
        user, filename=file.filename,
        content_type=file.content_type, data=data,
    )


@router.get("/faqs")
def list_faqs(category: int | None = Query(None), db: Session = Depends(get_db)):
    return service.list_faqs(db, category)


@router.get("/articles")
def list_articles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return service.list_articles(db, page, size, tag)


@router.get("/articles/{slug}")
def article_detail(slug: str, db: Session = Depends(get_db)):
    return service.article_detail(db, slug)


@router.post("/reviews")
def create_review(body: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.create_review(db, user, body)


@router.get("/reviews")
def list_reviews(
    product_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service.list_reviews(db, product_id, page, size)


@router.post("/ugc")
def submit_ugc(
    body: UgcIn,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service.submit_ugc(db, user, body)


@router.get("/ugc")
def list_ugc_wall(
    page: int = Query(1, ge=1),
    size: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service.list_ugc_wall(db, page, size)
