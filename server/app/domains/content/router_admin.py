"""内容域后台路由 —— /api/admin/ops 下 articles/faqs/reviews/ugc（绝对路径，由 admin_ops shim 组装）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.content import service
from app.domains.content.schemas import (
    ArticleCreateIn, ArticleUpdateIn, FaqCreateIn, FaqUpdateIn, ReasonIn,
)
from app.models import User

router = APIRouter(tags=["admin-ops"])


@router.get("/api/admin/ops/articles")
def list_articles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.list_articles_admin(db, page, size)


@router.post("/api/admin/ops/articles")
def create_article(body: ArticleCreateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_article(db, admin, body)


@router.put("/api/admin/ops/articles/{article_id}")
def update_article(article_id: int, body: ArticleUpdateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.update_article(db, admin, article_id, body)


@router.delete("/api/admin/ops/articles/{article_id}")
def delete_article(article_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.delete_article(db, admin, article_id)


@router.get("/api/admin/ops/faqs")
def list_faqs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_faqs_admin(db)


@router.post("/api/admin/ops/faqs")
def create_faq(body: FaqCreateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_faq(db, admin, body)


@router.put("/api/admin/ops/faqs/{faq_id}")
def update_faq(faq_id: int, body: FaqUpdateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.update_faq(db, admin, faq_id, body)


@router.delete("/api/admin/ops/faqs/{faq_id}")
def delete_faq(faq_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.delete_faq(db, admin, faq_id)


@router.get("/api/admin/ops/reviews")
def admin_reviews(
    status: int | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.admin_reviews(db, status, page, size)


@router.post("/api/admin/ops/reviews/{review_id}/approve")
def approve_review(review_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.approve_review(db, admin, review_id)


@router.post("/api/admin/ops/reviews/{review_id}/reject")
def reject_review(review_id: int, body: ReasonIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.reject_review(db, admin, review_id, body)


@router.get("/api/admin/ops/ugc")
def admin_ugc(
    status: int | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.admin_ugc(db, status, page, size)


@router.post("/api/admin/ops/ugc/{ugc_id}/approve")
def approve_ugc(ugc_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.approve_ugc(db, admin, ugc_id)


@router.post("/api/admin/ops/ugc/{ugc_id}/reject")
def reject_ugc(ugc_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.reject_ugc(db, admin, ugc_id)
