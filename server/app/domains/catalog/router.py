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
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    on_sale: bool = False,
    shape: str | None = Query(
        None, min_length=1, max_length=50,
        description="甲型筛选：常用词 almond/square/stiletto/coffin；"
                    "其他任意词按变体 option1_value 模糊匹配（ilike，未知词空集不报错）",
    ),
    sort: str = "new",
    locale: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service.list_products(
        db, category=category, tag=tag, q=q, sort=sort, page=page, size=size,
        locale=locale, min_price=min_price, max_price=max_price, on_sale=on_sale,
        shape=shape,
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
def search(
    q: str = Query(..., max_length=100),
    db: Session = Depends(get_db),
):
    return service.search(db, q=q.strip())


@router.get("/reviews")
def list_reviews(
    product_id: int,
    rating: int | None = Query(None, ge=1, le=5),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return service.list_reviews(db, product_id, page, size, rating=rating)


@router.get("/variants/{variant_id}/siblings")
def variant_siblings(variant_id: int, db: Session = Depends(get_db)):
    return service.variant_siblings(db, variant_id=variant_id)


@router.get("/reviews/distribution")
def review_distribution(product_id: int, db: Session = Depends(get_db)):
    return service.review_distribution(db, product_id)


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
