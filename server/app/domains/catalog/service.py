"""商品域服务：前台目录（列表/详情/分类树/集合/搜索/评价/到货通知）+ 后台管理（含操作日志）。

业务与事务边界；数据访问走 repository；沿用原有 HTTPException 语义。
"""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import (
    Category, Collection, CollectionProduct, Product, ProductTranslation,
    StockNotification, User, Variant,
)
from app.services.cache import _cache, cached

from app.domains.catalog import repository as repo
from app.domains.catalog.schemas import (
    CategoryCreateIn, CollectionCreateIn, CollectionProductsIn, CollectionUpdateIn,
    ProductBulkIn, ProductCreateIn, ProductUpdateIn, TranslationUpsertIn,
    VariantCreateIn, VariantUpdateIn,
)
_SORTS = ("new", "best", "price_asc", "price_desc")

_EMPTY_STOCK = {"total": 0, "low": 0, "out": 0}


def _invalidate_cache() -> None:
    _cache.clear("catalog")
    _cache.clear("ai")


def _stock_summary(variants: list) -> dict:
    return {
        "total": sum(v.stock for v in variants),
        "low": sum(1 for v in variants if v.stock <= v.safety_stock),
        "out": sum(v.stock for v in variants) <= 0,
    }


def _card(p: Product, stock: dict) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "subtitle": p.subtitle,
        "price_min": p.price_min,
        "price_max": p.price_max,
        "compare_at_price": p.compare_at_price,
        "hero_image": p.hero_image,
        "tags": p.tags or [],
        "is_new": p.is_new,
        "is_best_seller": p.is_best_seller,
        "sold_count": p.sold_count,
        "rating_count": p.rating_count,
        "rating": round(p.rating_avg / 100, 2),
        "stock_summary": {"total": int(stock["total"]), "low": int(stock["low"]),
                          "out": bool(stock["out"])},
    }


def _variant_out(v: Variant, images: list[str] | None = None) -> dict:
    if v.stock <= 0:
        status = "out"
    elif v.stock <= v.safety_stock:
        status = "low"
    else:
        status = "in"
    return {
        "id": v.id,
        "sku": v.sku,
        "price": v.price,
        "stock": v.stock,
        "safety_stock": v.safety_stock,
        "option1_value": v.option1_value,
        "option2_value": v.option2_value,
        "stock_status": status,
        "images": list(images or []),
    }


def _mask_name(user: User | None) -> str:
    name = ""
    if user:
        name = user.name or (user.email.split("@")[0] if user.email else "")
    if not name:
        name = "Glowmag Fan"
    if len(name) == 1:
        return name + "***"
    return name[0] + "***" + name[-1]


# ---------- 前台 ----------


@cached("catalog:products")
def list_products(
    db: Session, *, category: str | None, tag: str | None, q: str | None,
    sort: str, page: int, size: int, locale: str | None = None,
    min_price: int | None = None, max_price: int | None = None,
    on_sale: bool = False, shape: str | None = None,
) -> dict:
    if sort not in _SORTS:
        raise HTTPException(status_code=400, detail="invalid sort")
    shape = (shape or "").strip() or None
    cat_ids = repo.category_ids(db, category) if category else None
    if category and not cat_ids:
        return {"items": [], "total": 0, "page": page, "size": size}
    total, prods = repo.list_products(
        db, category_id_list=cat_ids, tag=tag, q=q, sort=sort,
        offset=(page - 1) * size, limit=size,
        min_price=min_price, max_price=max_price, on_sale=on_sale, shape=shape,
    )
    smap = repo.stock_map(db, [p.id for p in prods])
    tmap = repo.translations_map(db, [p.id for p in prods], locale) if locale else {}
    items = []
    for p in prods:
        card = _card(p, smap.get(p.id, _EMPTY_STOCK))
        t = tmap.get(p.id)
        if t is not None:
            card["title"] = t.title
            if t.subtitle is not None:
                card["subtitle"] = t.subtitle
        items.append(card)
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    }


@cached("catalog:detail")
def product_detail(db: Session, *, slug: str, locale: str | None = None) -> dict:
    p = repo.get_product_by_slug(db, slug)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    return _detail_out(db, p, locale)


def product_detail_by_id(db: Session, *, product_id: int, locale: str | None = None) -> dict:
    """按 id 查详情（前端 ?id=N 直链用，替代客户端硬编码 id→slug 映射表）。"""
    p = repo.get_product(db, product_id)
    if not p or p.status != 1:
        raise HTTPException(status_code=404, detail="product not found")
    return _detail_out(db, p, locale)


def _detail_out(db: Session, p: Product, locale: str | None = None) -> dict:
    variants = repo.active_variants(db, p.id)
    vimgs = repo.variant_images_map(db, [v.id for v in variants])
    related_prods = repo.related_products(db, p)
    related_smap = repo.stock_map(db, [r.id for r in related_prods])
    data = _card(p, _stock_summary(variants))
    data.update({
        "description_md": p.description_md,
        "video_url": p.video_url,
        "images": p.images or [],
        "category_id": p.category_id,
        "variants": [_variant_out(v, vimgs.get(v.id)) for v in variants],
        "related": [_card(r, related_smap.get(r.id, _EMPTY_STOCK)) for r in related_prods],
    })
    if locale:
        t = repo.get_translation(db, p.id, locale)
        if t is not None:
            data["title"] = t.title
            if t.subtitle is not None:
                data["subtitle"] = t.subtitle
            if t.description_md is not None:
                data["description_md"] = t.description_md
            data["locale"] = locale
        else:
            data["locale"] = "en-US"
    return data


@cached("catalog:categories")
def category_tree(db: Session) -> list:
    rows = repo.active_categories(db)
    nodes = {
        c.id: {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "sort_order": c.sort_order,
            "children": [],
        }
        for c in rows
    }
    roots = []
    for c in rows:
        if c.parent_id is None:
            roots.append(nodes[c.id])
        elif c.parent_id in nodes:
            nodes[c.parent_id]["children"].append(nodes[c.id])
    return roots


@cached("catalog:collections")
def list_collections(db: Session) -> dict:
    rows = repo.list_collections(db)
    return {
        "items": [
            {
                "id": c.id,
                "slug": c.slug,
                "title": c.title,
                "banner_image": c.banner_image,
            }
            for c in rows
        ]
    }


@cached("catalog:collection_detail")
def collection_detail(db: Session, *, slug: str) -> dict:
    c = repo.get_collection_by_slug(db, slug)
    if not c:
        raise HTTPException(status_code=404, detail="collection not found")
    materialized = repo.collection_product_count(db, c.id) > 0
    if materialized:
        prods = repo.collection_products(db, c.id)
    else:
        prods = repo.rule_products(db, c.rule_json or {})
    smap = repo.stock_map(db, [p.id for p in prods])
    return {
        "id": c.id,
        "slug": c.slug,
        "title": c.title,
        "banner_image": c.banner_image,
        "products": [_card(p, smap.get(p.id, _EMPTY_STOCK)) for p in prods],
    }


@cached("catalog:search")
def search(db: Session, *, q: str) -> dict:
    like = f"%{q}%"
    prods = repo.search_products(db, like)
    cats = repo.search_categories(db, like)
    smap = repo.stock_map(db, [p.id for p in prods])
    return {
        "products": [_card(p, smap.get(p.id, _EMPTY_STOCK)) for p in prods],
        "categories": [{"id": c.id, "slug": c.slug, "name": c.name} for c in cats],
    }


def list_reviews(
    db: Session, product_id: int, page: int, size: int,
    rating: int | None = None,
) -> dict:
    total, rows = repo.reviews_page(
        db, product_id, (page - 1) * size, size, rating=rating
    )
    users = {}
    uids = {r.user_id for r in rows}
    if uids:
        users = {u.id: u for u in repo.users_by_ids(db, uids)}
    items = [
        {
            "id": r.id,
            "rating": r.rating,
            "content": r.content,
            "images": r.images or [],
            "created_at": r.created_at,
            "user": _mask_name(users.get(r.user_id)),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


def review_distribution(db: Session, product_id: int) -> dict:
    """评价星级分布（仅 status=1）：rating_avg ×100 口径与 Product.rating_avg 一致；无评价返回全 0（与 list_reviews 不 404 同口径）"""
    rows = repo.review_rating_distribution(db, product_id)
    dist = {str(r): 0 for r in range(1, 6)}
    total = rating_sum = 0
    for rating, n in rows:
        dist[str(rating)] = n
        total += n
        rating_sum += rating * n
    return {
        "product_id": product_id,
        "rating_avg": round(rating_sum * 100 / total) if total else 0,
        "rating_count": total,
        "distribution": dist,
    }


def variant_siblings(db: Session, *, variant_id: int) -> dict:
    """变体兄弟（同商品全部启用变体，公开）：换甲型/换规格选择器数据源。
    复用详情页 active_variants + variant_images_map 组装（_variant_out 同口径）。"""
    v = repo.get_variant(db, variant_id)
    if not v:
        raise HTTPException(status_code=404, detail="variant not found")
    p = repo.get_product(db, v.product_id)
    if not p or p.status != 1:
        raise HTTPException(status_code=404, detail="product not found")
    variants = repo.active_variants(db, p.id)
    vimgs = repo.variant_images_map(db, [x.id for x in variants])
    return {
        "variant_id": v.id,
        "product_id": p.id,
        "slug": p.slug,
        "title": p.title,
        "variants": [_variant_out(x, vimgs.get(x.id)) for x in variants],
    }


# ---------- 到货通知（stock_notifications 影子表） ----------

def _notify_email(email: str) -> str:
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="invalid email")
    return email


def stock_notify_subscribe(db: Session, variant_id: int, email: str) -> tuple[int, dict]:
    """仅允许售罄变体订阅；uk(variant,email) 语义幂等（重复 200）"""
    email = _notify_email(email)
    v = repo.get_variant(db, variant_id)
    if not v:
        raise HTTPException(status_code=404, detail="variant not found")
    if v.stock > 0:
        raise HTTPException(status_code=409, detail="in_stock")
    if repo.stock_notification_by(db, variant_id, email) is not None:
        return 200, {"watching": True}
    repo.add_stock_notification(db, StockNotification(variant_id=variant_id, email=email))
    db.commit()
    return 201, {"watching": True}


def stock_notify_status(db: Session, variant_id: int, email: str) -> dict:
    email = _notify_email(email)
    return {"watching": repo.stock_notification_by(db, variant_id, email) is not None}


def stock_notify_cancel(db: Session, variant_id: int, email: str) -> dict:
    email = _notify_email(email)
    if repo.delete_stock_notification(db, variant_id, email):
        db.commit()
    return {"watching": False}


# ---------- 后台 ----------

def _sync_price_range(db: Session, product_id: int) -> None:
    """变体价格变更后回写商品冗余价格区间（前台卡片价与价格筛选依赖该列）；
    仅统计在售变体；无在售变体时保留原值不动"""
    row = (
        db.query(func.min(Variant.price), func.max(Variant.price))
        .filter(Variant.product_id == product_id, Variant.is_active == 1)
        .one()
    )
    pmin, pmax = row
    if pmin is None:
        return
    p = repo.get_product(db, product_id)
    if p:
        p.price_min, p.price_max = int(pmin), int(pmax)


def _admin_variant_out(v: Variant, images: list[str] | None = None) -> dict:
    return {
        "id": v.id,
        "product_id": v.product_id,
        "sku": v.sku,
        "option1_name": v.option1_name,
        "option1_value": v.option1_value,
        "option2_name": v.option2_name,
        "option2_value": v.option2_value,
        "price": v.price,
        "stock": v.stock,
        "safety_stock": v.safety_stock,
        "weight_gram": v.weight_gram,
        "is_active": v.is_active,
        "images": list(images or []),
    }


def _admin_product_out(p: Product, agg: dict) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "subtitle": p.subtitle,
        "description_md": p.description_md,
        "status": p.status,
        "category_id": p.category_id,
        "compare_at_price": p.compare_at_price,
        "price_min": p.price_min,
        "price_max": p.price_max,
        "hero_image": p.hero_image,
        "images": p.images or [],
        "video_url": p.video_url,
        "tags": p.tags or [],
        "is_new": p.is_new,
        "is_best_seller": p.is_best_seller,
        "rating_avg": p.rating_avg,
        "rating_count": p.rating_count,
        "sold_count": p.sold_count,
        "published_at": p.published_at,
        "scheduled": bool(p.published_at and p.published_at > utcnow()),
        "created_at": p.created_at,
        **agg,
    }


def _log(db: Session, admin: User, action: str, entity: str, entity_id: int,
         diff: dict | None = None) -> None:
    repo.add_admin_log(
        db, admin_id=admin.id, action=action, entity=entity,
        entity_id=entity_id, diff_json=diff,
    )


def admin_list_products(
    db: Session, *, status: int | None, q: str | None, page: int, size: int,
    category_id: int | None = None, sort: str | None = None,
) -> dict:
    total, prods = repo.admin_products(
        db, status=status, category_id=category_id, q=q,
        offset=(page - 1) * size, limit=size, sort=sort,
    )
    agg = repo.variant_counts(db, [p.id for p in prods])
    empty = {"variant_count": 0, "total_stock": 0, "low_stock_count": 0}
    return {
        "items": [_admin_product_out(p, agg.get(p.id, empty)) for p in prods],
        "total": total,
        "page": page,
        "size": size,
    }


def admin_list_variants(
    db: Session, *, product_id: int | None, q: str | None, page: int, size: int,
    sort: str | None = None,
) -> dict:
    total, rows = repo.admin_variants(
        db, product_id=product_id, q=q,
        offset=(page - 1) * size, limit=size, sort=sort,
    )
    # 变体图片批量直出（一次 in_ 查全页 variant_id 再映射，避免 N+1；每变体按序 ≤6）
    vimgs = repo.variant_images_map(db, [v.id for v, _ in rows])
    return {
        "items": [
            {
                "id": v.id,
                "product_id": v.product_id,
                "product_title": title,
                "sku": v.sku,
                "option1_value": v.option1_value,
                "option2_value": v.option2_value,
                "price": v.price,
                "stock": v.stock,
                "safety_stock": v.safety_stock,
                "is_active": bool(v.is_active),
                "images": vimgs.get(v.id, [])[:6],
            }
            for v, title in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def admin_get_product(db: Session, product_id: int) -> dict:
    p = repo.get_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    agg = repo.variant_counts(db, [p.id]).get(
        p.id, {"variant_count": 0, "total_stock": 0, "low_stock_count": 0}
    )
    return _admin_product_out(p, agg)


def admin_bulk_products(db: Session, admin: User, body: ProductBulkIn) -> dict:
    """批量导入：逐条校验创建，部分成功模式（失败行返回原因，不回滚已成功行）。"""
    results: list[dict] = []
    created = failed = 0
    for i, item in enumerate(body.items):
        try:
            if repo.product_slug_taken(db, item.slug):
                raise HTTPException(status_code=409, detail="slug already exists")
            if not repo.get_category(db, item.category_id):
                raise HTTPException(status_code=400, detail="category not found")
            p = Product(
                slug=item.slug,
                title=item.title,
                subtitle=item.subtitle,
                description_md=item.description_md,
                category_id=item.category_id,
                price_min=item.price_min,
                price_max=item.price_max,
                compare_at_price=item.compare_at_price,
                hero_image=item.hero_image,
                images=item.images or [],
                video_url=item.video_url,
                tags=item.tags or [],
                is_new=int(item.is_new),
                is_best_seller=int(item.is_best_seller),
            )
            repo.add_product(db, p)
            db.flush()
            _log(db, admin, "create", "product", p.id)
            db.commit()
            created += 1
            results.append({"index": i, "ok": True, "id": p.id, "slug": p.slug})
        except HTTPException as exc:
            db.rollback()
            failed += 1
            results.append({"index": i, "ok": False, "slug": item.slug,
                            "error": exc.detail})
    if created:
        _invalidate_cache()
    return {"created": created, "failed": failed, "results": results}


def admin_create_product(db: Session, admin: User, body: ProductCreateIn) -> dict:
    if repo.product_slug_taken(db, body.slug):
        raise HTTPException(status_code=409, detail="slug already exists")
    if not repo.get_category(db, body.category_id):
        raise HTTPException(status_code=400, detail="category not found")
    p = Product(
        slug=body.slug,
        title=body.title,
        subtitle=body.subtitle,
        description_md=body.description_md,
        category_id=body.category_id,
        price_min=body.price_min,
        price_max=body.price_max,
        compare_at_price=body.compare_at_price,
        hero_image=body.hero_image,
        images=body.images or [],
        video_url=body.video_url,
        tags=body.tags or [],
        is_new=int(body.is_new),
        is_best_seller=int(body.is_best_seller),
    )
    repo.add_product(db, p)
    db.flush()
    _log(db, admin, "create", "product", p.id)
    db.commit()
    _invalidate_cache()
    db.refresh(p)
    return _admin_product_out(p, {"variant_count": 0, "total_stock": 0, "low_stock_count": 0})


def _diff_value(v):
    return v.isoformat() if isinstance(v, datetime) else v


def admin_update_product(
    db: Session, admin: User, product_id: int, body: ProductUpdateIn,
) -> dict:
    p = repo.get_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    payload = body.model_dump(exclude_unset=True)
    if payload.get("category_id") is not None and not repo.get_category(
        db, payload["category_id"]
    ):
        raise HTTPException(status_code=400, detail="category not found")
    if payload.get("is_new") is not None:
        payload["is_new"] = int(payload["is_new"])
    if payload.get("is_best_seller") is not None:
        payload["is_best_seller"] = int(payload["is_best_seller"])
    diff: dict = {}
    for field, new in payload.items():
        old = getattr(p, field)
        if old != new:
            setattr(p, field, new)
            diff[field] = {"before": _diff_value(old), "after": _diff_value(new)}
    if diff:
        _log(db, admin, "update", "product", p.id, diff)
        db.commit()
        _invalidate_cache()
        db.refresh(p)
    agg = repo.variant_counts(db, [p.id]).get(p.id, {})
    return _admin_product_out(p, agg)


def admin_publish_product(db: Session, admin: User, product_id: int) -> dict:
    p = repo.get_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    p.status = 1
    # 定时上架不被覆盖：已有未来 published_at（定时计划）则保留生效；为空或已过才落当前时间
    if not (p.published_at and p.published_at > utcnow()):
        p.published_at = utcnow()
    _log(db, admin, "publish", "product", p.id)
    db.commit()
    _invalidate_cache()
    db.refresh(p)
    return _admin_product_out(p, repo.variant_counts(db, [p.id]).get(p.id, {}))


def admin_unpublish_product(db: Session, admin: User, product_id: int) -> dict:
    p = repo.get_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product not found")
    p.status = 2
    _log(db, admin, "unpublish", "product", p.id)
    db.commit()
    _invalidate_cache()
    db.refresh(p)
    return _admin_product_out(p, repo.variant_counts(db, [p.id]).get(p.id, {}))


def admin_create_variant(
    db: Session, admin: User, product_id: int, body: VariantCreateIn,
) -> dict:
    if not repo.get_product(db, product_id):
        raise HTTPException(status_code=404, detail="product not found")
    if repo.variant_sku_taken(db, body.sku):
        raise HTTPException(status_code=409, detail="sku already exists")
    v = Variant(
        product_id=product_id,
        sku=body.sku,
        option1_value=body.option1_value,
        option2_value=body.option2_value,
        price=body.price,
        stock=body.stock,
        weight_gram=body.weight_gram,
    )
    repo.add_variant(db, v)
    db.flush()
    if body.images is not None:
        repo.add_variant_images(db, v.id, body.images)
    _sync_price_range(db, product_id)
    _log(db, admin, "create", "variant", v.id)
    db.commit()
    _invalidate_cache()
    db.refresh(v)
    return _admin_variant_out(v, body.images)


def admin_update_variant(
    db: Session, admin: User, variant_id: int, body: VariantUpdateIn,
) -> dict:
    v = repo.get_variant(db, variant_id)
    if not v:
        raise HTTPException(status_code=404, detail="variant not found")
    data = body.model_dump(exclude_unset=True)
    images = data.pop("images", None)
    diff: dict = {}
    for field, new in data.items():
        old = getattr(v, field)
        if old != new:
            setattr(v, field, new)
            diff[field] = {"before": old, "after": new}
    if images is not None:
        diff["images"] = {"before": repo.variant_images(db, v.id), "after": images}
        repo.replace_variant_images(db, v.id, images)
    if diff:
        _sync_price_range(db, v.product_id)
        _log(db, admin, "update", "variant", v.id, diff)
        db.commit()
        _invalidate_cache()
        db.refresh(v)
    return _admin_variant_out(v, repo.variant_images(db, v.id))


def admin_list_categories(db: Session) -> list[dict]:
    rows = repo.all_categories(db)
    return [
        {
            "id": c.id,
            "parent_id": c.parent_id,
            "slug": c.slug,
            "name": c.name,
            "sort_order": c.sort_order,
            "is_active": c.is_active,
        }
        for c in rows
    ]


def admin_create_category(db: Session, admin: User, body: CategoryCreateIn) -> dict:
    if repo.category_slug_taken(db, body.slug):
        raise HTTPException(status_code=409, detail="slug already exists")
    if body.parent_id is not None and not repo.get_category(db, body.parent_id):
        raise HTTPException(status_code=400, detail="parent category not found")
    c = Category(slug=body.slug, name=body.name, parent_id=body.parent_id)
    repo.add_category(db, c)
    db.commit()
    _invalidate_cache()
    db.refresh(c)
    return {
        "id": c.id,
        "parent_id": c.parent_id,
        "slug": c.slug,
        "name": c.name,
        "sort_order": c.sort_order,
        "is_active": c.is_active,
    }


def admin_list_collections(db: Session) -> dict:
    rows = repo.all_collections(db)
    counts = repo.collection_product_counts(db, [c.id for c in rows])
    return {
        "items": [
            {
                "id": c.id,
                "slug": c.slug,
                "title": c.title,
                "rule_json": c.rule_json or {},
                "banner_image": c.banner_image,
                "sort_order": c.sort_order,
                "is_active": c.is_active,
                "product_count": counts.get(c.id, 0),
            }
            for c in rows
        ]
    }


def admin_create_collection(db: Session, admin: User, body: CollectionCreateIn) -> dict:
    if repo.collection_slug_taken(db, body.slug):
        raise HTTPException(status_code=409, detail="slug already exists")
    c = Collection(slug=body.slug, title=body.title, rule_json=body.rule_json,
                   banner_image=body.banner_image)
    repo.add_collection(db, c)
    db.commit()
    _invalidate_cache()
    db.refresh(c)
    return {
        "id": c.id,
        "slug": c.slug,
        "title": c.title,
        "rule_json": c.rule_json,
        "banner_image": c.banner_image,
        "is_active": c.is_active,
    }


def admin_set_collection_products(
    db: Session, admin: User, collection_id: int, body: CollectionProductsIn,
) -> dict:
    c = repo.get_collection(db, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="collection not found")
    ids = {cp.product_id for cp in body.products}
    if ids:
        found = repo.existing_product_ids(db, ids)
        missing = ids - found
        if missing:
            raise HTTPException(status_code=400, detail=f"unknown products: {sorted(missing)}")
    repo.replace_collection_products(db, collection_id, [
        CollectionProduct(
            collection_id=collection_id,
            product_id=cp.product_id,
            sort_order=cp.sort_order,
        )
        for cp in body.products
    ])
    _log(db, admin, "update", "collection", collection_id,
         {"products": [cp.model_dump() for cp in body.products]})
    db.commit()
    _invalidate_cache()
    return {"ok": True, "count": len(body.products)}


def admin_update_collection(
    db: Session, admin: User, collection_id: int, body: CollectionUpdateIn,
) -> dict:
    c = repo.get_collection(db, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="collection not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_active") is not None:
        data["is_active"] = int(data["is_active"])
    diff: dict = {}
    for field, new in data.items():
        old = getattr(c, field)
        if old != new:
            setattr(c, field, new)
            diff[field] = {"before": old, "after": new}
    if diff:
        _log(db, admin, "update", "collection", c.id, diff)
        db.commit()
        _invalidate_cache()
        db.refresh(c)
    return {
        "id": c.id,
        "slug": c.slug,
        "title": c.title,
        "rule_json": c.rule_json or {},
        "banner_image": c.banner_image,
        "sort_order": c.sort_order,
        "is_active": c.is_active,
    }


def admin_delete_collection(db: Session, admin: User, collection_id: int) -> dict:
    c = repo.get_collection(db, collection_id)
    if not c:
        raise HTTPException(status_code=404, detail="collection not found")
    repo.delete_collection_products(db, collection_id)
    _log(db, admin, "delete", "collection", c.id, {"slug": c.slug, "title": c.title})
    db.delete(c)
    db.commit()
    _invalidate_cache()
    return {"ok": True}


def admin_collection_products(db: Session, collection_id: int) -> dict:
    if not repo.get_collection(db, collection_id):
        raise HTTPException(status_code=404, detail="collection not found")
    rows = repo.collection_product_pairs(db, collection_id)
    return {
        "items": [
            {
                "product_id": cp.product_id,
                "sort_order": cp.sort_order,
                "product": {"id": p.id, "title": p.title, "slug": p.slug},
            }
            for cp, p in rows
        ]
    }


# ---------- 后台：商品多语言（product_translations 影子表） ----------

def _translation_out(t) -> dict:
    return {
        "product_id": t.product_id,
        "locale": t.locale,
        "title": t.title,
        "subtitle": t.subtitle,
        "description_md": t.description_md,
    }


def admin_list_translations(db: Session, product_id: int) -> list[dict]:
    if not repo.get_product(db, product_id):
        raise HTTPException(status_code=404, detail="product not found")
    return [_translation_out(t) for t in repo.product_translations_all(db, product_id)]


def admin_upsert_translation(
    db: Session, admin: User, product_id: int, body: TranslationUpsertIn,
) -> dict:
    if not repo.get_product(db, product_id):
        raise HTTPException(status_code=404, detail="product not found")
    t = repo.get_translation(db, product_id, body.locale)
    created = t is None
    if created:
        t = ProductTranslation(product_id=product_id, locale=body.locale, title=body.title)
    data = body.model_dump(exclude_unset=True)
    data.pop("locale", None)
    for field, new in data.items():
        setattr(t, field, new)
    repo.add_translation(db, t)
    db.flush()
    _log(db, admin, "create" if created else "update", "product_translation",
         product_id, {"locale": body.locale, **data})
    db.commit()
    _invalidate_cache()
    db.refresh(t)
    return _translation_out(t)


def admin_delete_translation(
    db: Session, admin: User, product_id: int, locale: str,
) -> dict:
    if not repo.get_product(db, product_id):
        raise HTTPException(status_code=404, detail="product not found")
    deleted = repo.delete_translation(db, product_id, locale)
    if deleted:
        _log(db, admin, "delete", "product_translation", product_id, {"locale": locale})
        db.commit()
        _invalidate_cache()
    return {"ok": True, "deleted": int(deleted)}
