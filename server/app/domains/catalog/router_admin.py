"""后台目录管理路由（薄层，/api/admin/catalog）：商品/变体/分类/集合 + 操作日志。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_perm
from app.models import User

from app.domains.catalog import service
from app.domains.catalog.schemas import (
    BatchStatusIn, CategoryCreateIn, CategoryUpdateIn, CollectionCreateIn,
    CollectionProductsIn, CollectionUpdateIn, ProductBulkIn, ProductCreateIn,
    ProductUpdateIn, TranslationUpsertIn, VariantCreateIn, VariantUpdateIn,
)

router = APIRouter(prefix="/api/admin/catalog", tags=["admin-catalog"])


@router.get("/stock-notifies")
def admin_stock_notifies(
    product_id: int | None = Query(None),
    variant_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_perm("stock:read")),
    db: Session = Depends(get_db),
):
    """到货通知名单（StockNotification 模型在本 catalog 域，端点落位 catalog）"""
    return service.admin_stock_notifies(
        db, product_id=product_id, variant_id=variant_id, page=page, size=size,
    )

@router.get("/products")
def admin_list_products(
    status: int | None = None,
    category_id: int | None = None,
    q: str | None = None,
    sort: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_perm("catalog:read")),
    db: Session = Depends(get_db),
):
    return service.admin_list_products(
        db, status=status, category_id=category_id, q=q, page=page, size=size, sort=sort
    )


@router.get("/variants")
def admin_list_variants(
    product_id: int | None = None,
    q: str | None = None,
    sort: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    admin: User = Depends(require_perm("catalog:read")),
    db: Session = Depends(get_db),
):
    return service.admin_list_variants(
        db, product_id=product_id, q=q, page=page, size=size, sort=sort
    )


@router.get("/products/{product_id}")
def admin_get_product(
    product_id: int,
    admin: User = Depends(require_perm("catalog:read")),
    db: Session = Depends(get_db),
):
    return service.admin_get_product(db, product_id)


@router.post("/products", status_code=201)
def admin_create_product(
    body: ProductCreateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_create_product(db, admin, body)


@router.post("/products/bulk", status_code=201)
def admin_bulk_products(
    body: ProductBulkIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_bulk_products(db, admin, body)


@router.post("/products/batch-status")
def admin_batch_status(
    body: BatchStatusIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    """批量上下架：1 发布 / 2 归档 / 0 恢复草稿（逐条部分成功，失败返回明细）"""
    return service.admin_batch_status(db, admin, body)


@router.put("/products/{product_id}")
def admin_update_product(
    product_id: int,
    body: ProductUpdateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_update_product(db, admin, product_id, body)


@router.post("/products/{product_id}/publish")
def admin_publish_product(
    product_id: int,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_publish_product(db, admin, product_id)


@router.post("/products/{product_id}/unpublish")
def admin_unpublish_product(
    product_id: int,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_unpublish_product(db, admin, product_id)


@router.post("/products/{product_id}/variants", status_code=201)
def admin_create_variant(
    product_id: int,
    body: VariantCreateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_create_variant(db, admin, product_id, body)


@router.put("/variants/{variant_id}")
def admin_update_variant(
    variant_id: int,
    body: VariantUpdateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_update_variant(db, admin, variant_id, body)


@router.delete("/variants/{variant_id}")
def admin_delete_variant(
    variant_id: int,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_delete_variant(db, admin, variant_id)


@router.get("/categories")
def admin_list_categories(
    admin: User = Depends(require_perm("catalog:read")),
    db: Session = Depends(get_db),
):
    return service.admin_list_categories(db)


@router.post("/categories", status_code=201)
def admin_create_category(
    body: CategoryCreateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_create_category(db, admin, body)


@router.put("/categories/{category_id}")
def admin_update_category(
    category_id: int,
    body: CategoryUpdateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_update_category(db, admin, category_id, body)


@router.delete("/categories/{category_id}")
def admin_delete_category(
    category_id: int,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_delete_category(db, admin, category_id)


@router.get("/collections")
def admin_list_collections(
    admin: User = Depends(require_perm("catalog:read")),
    db: Session = Depends(get_db),
):
    return service.admin_list_collections(db)


@router.post("/collections", status_code=201)
def admin_create_collection(
    body: CollectionCreateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_create_collection(db, admin, body)


@router.put("/collections/{collection_id}")
def admin_update_collection(
    collection_id: int,
    body: CollectionUpdateIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_update_collection(db, admin, collection_id, body)


@router.delete("/collections/{collection_id}")
def admin_delete_collection(
    collection_id: int,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_delete_collection(db, admin, collection_id)


@router.put("/collections/{collection_id}/products")
def admin_set_collection_products(
    collection_id: int,
    body: CollectionProductsIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_set_collection_products(db, admin, collection_id, body)


@router.get("/collections/{collection_id}/products")
def admin_collection_products(
    collection_id: int,
    admin: User = Depends(require_perm("catalog:read")),
    db: Session = Depends(get_db),
):
    return service.admin_collection_products(db, collection_id)


@router.get("/products/{product_id}/translations")
def admin_list_translations(
    product_id: int,
    admin: User = Depends(require_perm("catalog:read")),
    db: Session = Depends(get_db),
):
    return service.admin_list_translations(db, product_id)


@router.put("/products/{product_id}/translations")
def admin_upsert_translation(
    product_id: int,
    body: TranslationUpsertIn,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_upsert_translation(db, admin, product_id, body)


@router.delete("/products/{product_id}/translations/{locale}")
def admin_delete_translation(
    product_id: int,
    locale: str,
    admin: User = Depends(require_perm("catalog:manage")),
    db: Session = Depends(get_db),
):
    return service.admin_delete_translation(db, admin, product_id, locale)
