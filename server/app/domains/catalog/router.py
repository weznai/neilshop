"""商品目录路由（薄层，前台 /api/catalog）：列表/详情/分类树/集合/搜索/评价/到货通知。"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db

from app.domains.catalog import service
from app.domains.catalog.schemas import StockNotifyIn

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/products")
def list_products(
    category: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str = "new",
    locale: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service.list_products(
        db, category=category, tag=tag, q=q, sort=sort, page=page, size=size,
        locale=locale,
    )


@router.get("/products/{slug}")
def product_detail(slug: str, locale: str | None = None, db: Session = Depends(get_db)):
    return service.product_detail(db, slug=slug, locale=locale)


@router.get("/products-by-id/{product_id}")
def product_detail_by_id(product_id: int, locale: str | None = None, db: Session = Depends(get_db)):
    return service.product_detail_by_id(db, product_id=product_id, locale=locale)


@router.get("/categories")
def category_tree(db: Session = Depends(get_db)):
    return service.category_tree(db)


@router.get("/collections")
def list_collections(db: Session = Depends(get_db)):
    return service.list_collections(db)


@router.get("/collections/{slug}")
def collection_detail(slug: str, db: Session = Depends(get_db)):
    return service.collection_detail(db, slug=slug)


@router.get("/search")
def search(q: str, db: Session = Depends(get_db)):
    return service.search(db, q=q)


@router.get("/reviews")
def list_reviews(
    product_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return service.list_reviews(db, product_id, page, size)


@router.post("/stock-notify")
def stock_notify_subscribe(body: StockNotifyIn, db: Session = Depends(get_db)):
    code, payload = service.stock_notify_subscribe(db, body.variant_id, body.email)
    return JSONResponse(status_code=code, content=payload)


@router.get("/stock-notify")
def stock_notify_status(
    variant_id: int,
    email: str,
    db: Session = Depends(get_db),
):
    return service.stock_notify_status(db, variant_id, email)


@router.delete("/stock-notify")
def stock_notify_cancel(
    variant_id: int,
    email: str,
    db: Session = Depends(get_db),
):
    return service.stock_notify_cancel(db, variant_id, email)
