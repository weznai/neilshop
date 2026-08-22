"""商品域 repository —— 纯数据访问（前台目录 + 后台管理）。

纪律：不引入 HTTP 框架、不抛 HTTP 异常。
性能红线（test_perf 断言对象，保持原样、禁止退化为逐商品查询）：
- stock_map：单条 GROUP BY 聚合批量求 stock_summary；
- category_ids：分类表单查询 + 内存 BFS 求子树。
"""

from sqlalchemy import String, case, cast, exists, func, or_
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import (
    AdminLog, Category, Collection, CollectionProduct, Product, ProductTranslation,
    Review, User, StockNotification, Variant, VariantImage,
)

_SORT_ORDERS = {
    "new": Product.published_at.desc(),
    "best": Product.sold_count.desc(),
    "price_asc": Product.price_min.asc(),
    "price_desc": Product.price_min.desc(),
}


def _tag_filter(query, tag: str):
    return query.filter(cast(Product.tags, String).like(f'%"{tag}"%'))


def _visible():
    """前台可见性（查询时生效）：已上架且 published_at 未到未来（NULL 视为立即可见）。

    仅作为附加条件并进既有 WHERE，不新增 SQL 条数；seed 现有商品 published_at
    均为过去/None，行为零变化。admin 查询不套此条件（运营可见未来商品）。
    """
    return or_(Product.published_at.is_(None), Product.published_at <= utcnow())


# ---------- 批量库存聚合（性能红线，勿改） ----------

def stock_map(db: Session, pids: list[int]) -> dict[int, dict]:
    """out 语义：全部变体售罄（总可售库存 <= 0）才整品 SOLD OUT；
    任一变体售罄仅该变体不可购，不再连坐整品。"""
    smap: dict[int, dict] = {}
    if not pids:
        return smap
    rows = (
        db.query(
            Variant.product_id,
            func.coalesce(func.sum(Variant.stock), 0),
            func.coalesce(func.sum(case((Variant.stock <= Variant.safety_stock, 1), else_=0)), 0),
            case((func.coalesce(func.sum(Variant.stock), 0) <= 0, 1), else_=0),
        )
        .filter(Variant.product_id.in_(pids), Variant.is_active == 1)
        .group_by(Variant.product_id)
        .all()
    )
    for pid, total, low, out in rows:
        smap[pid] = {"total": total, "low": low, "out": out}
    return smap


# ---------- 分类子树（性能红线：单查询 + 内存 BFS，勿改） ----------

def category_ids(db: Session, slug: str) -> list[int] | None:
    rows = db.query(Category.id, Category.parent_id, Category.slug).all()
    root = next((r[0] for r in rows if r[2] == slug), None)
    if root is None:
        return None
    children: dict[int, list[int]] = {}
    for cid, pid, _ in rows:
        children.setdefault(pid, []).append(cid)
    ids = [root]
    frontier = [root]
    while frontier:
        nxt: list[int] = []
        for c in frontier:
            nxt.extend(children.get(c, []))
        frontier = nxt
        ids.extend(frontier)
    return ids


# ---------- 前台目录 ----------

def list_products(
    db: Session, *, category_id_list: list[int] | None, tag: str | None,
    q: str | None, sort: str, offset: int, limit: int,
    min_price: int | None = None, max_price: int | None = None,
    on_sale: bool = False, shape: str | None = None,
) -> tuple[int, list[Product]]:
    query = db.query(Product).filter(Product.status == 1, _visible())
    if category_id_list:
        query = query.filter(Product.category_id.in_(category_id_list))
    if tag:
        query = _tag_filter(query, tag)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Product.title.like(like), Product.subtitle.like(like)))
    # 甲型筛选：任一启用变体 option1_value 包含 shape 词即命中（ilike 大小写不敏感，
    # 前端传 almond/square 等短词可匹配 "Short Almond"/"Medium Square" 复合值；未知词自然空集）
    if shape:
        query = query.filter(exists().where(
            Variant.product_id == Product.id,
            Variant.is_active == 1,
            Variant.option1_value.ilike(f"%{shape}%"),
        ))
    # 价格区间交集：[min_price, max_price] 与商品 [price_min, price_max] 有交集即命中（闭区间，单侧给半开）
    if min_price is not None:
        query = query.filter(Product.price_max >= min_price)
    if max_price is not None:
        query = query.filter(Product.price_min <= max_price)
    if on_sale:
        query = query.filter(
            Product.compare_at_price.isnot(None),
            Product.compare_at_price > Product.price_min,
        )
    total = query.count()
    prods = (
        query.order_by(_SORT_ORDERS[sort], Product.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, prods


def get_product_by_slug(db: Session, slug: str) -> Product | None:
    return db.query(Product).filter(
        Product.slug == slug, Product.status == 1, _visible()
    ).first()


def active_variants(db: Session, product_id: int) -> list[Variant]:
    return (
        db.query(Variant)
        .filter(Variant.product_id == product_id, Variant.is_active == 1)
        .order_by(Variant.id.asc())
        .all()
    )


def variant_images_map(db: Session, vids: list[int]) -> dict[int, list[str]]:
    imap: dict[int, list[str]] = {}
    if not vids:
        return imap
    rows = (
        db.query(VariantImage)
        .filter(VariantImage.variant_id.in_(vids))
        .order_by(
            VariantImage.variant_id.asc(),
            VariantImage.sort_order.asc(),
            VariantImage.id.asc(),
        )
        .all()
    )
    for r in rows:
        imap.setdefault(r.variant_id, []).append(r.image_url)
    return imap


def related_products(db: Session, product: Product, limit: int = 4) -> list[Product]:
    return (
        db.query(Product)
        .filter(
            Product.category_id == product.category_id,
            Product.status == 1,
            _visible(),
            Product.id != product.id,
        )
        .order_by(Product.sold_count.desc(), Product.id.asc())
        .limit(limit)
        .all()
    )


def active_categories(db: Session) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.is_active == 1)
        .order_by(Category.sort_order.asc(), Category.id.asc())
        .all()
    )


def rule_products(db: Session, rule: dict) -> list[Product]:
    query = db.query(Product).filter(Product.status == 1, _visible())
    for tag in rule.get("tags") or []:
        query = _tag_filter(query, str(tag))
    if rule.get("price_lt") is not None:
        query = query.filter(Product.price_min < int(rule["price_lt"]))
    if rule.get("category"):
        ids = category_ids(db, str(rule["category"]))
        if not ids:
            return []
        query = query.filter(Product.category_id.in_(ids))
    if rule.get("is_best"):
        query = query.filter(Product.is_best_seller == 1)
    return (
        query.order_by(Product.published_at.desc(), Product.id.asc())
        .limit(100)
        .all()
    )


def list_collections(db: Session) -> list[Collection]:
    return (
        db.query(Collection)
        .filter(Collection.is_active == 1)
        .order_by(Collection.sort_order.asc(), Collection.id.asc())
        .all()
    )


def get_collection_by_slug(db: Session, slug: str) -> Collection | None:
    return db.query(Collection).filter(
        Collection.slug == slug, Collection.is_active == 1
    ).first()


def collection_product_count(db: Session, collection_id: int) -> int:
    return (
        db.query(CollectionProduct)
        .filter(CollectionProduct.collection_id == collection_id)
        .count()
    )


def collection_products(db: Session, collection_id: int) -> list[Product]:
    return [
        p for _, p in (
            db.query(CollectionProduct, Product)
            .join(Product, Product.id == CollectionProduct.product_id)
            .filter(
                CollectionProduct.collection_id == collection_id,
                Product.status == 1,
                _visible(),
            )
            .order_by(
                CollectionProduct.sort_order.asc(),
                CollectionProduct.product_id.asc(),
            )
            .all()
        )
    ]


def search_products(db: Session, like: str, limit: int = 8) -> list[Product]:
    return (
        db.query(Product)
        .filter(
            Product.status == 1,
            _visible(),
            or_(
                Product.title.like(like),
                Product.subtitle.like(like),
                cast(Product.tags, String).like(like),
            ),
        )
        .order_by(Product.sold_count.desc(), Product.id.asc())
        .limit(limit)
        .all()
    )


def search_categories(db: Session, like: str) -> list[Category]:
    return (
        db.query(Category)
        .filter(
            Category.is_active == 1,
            or_(Category.name.like(like), Category.slug.like(like)),
        )
        .order_by(Category.id.asc())
        .all()
    )


def reviews_page(
    db: Session, product_id: int, offset: int, limit: int,
    rating: int | None = None,
) -> tuple[int, list[Review]]:
    base = db.query(Review).filter(
        Review.product_id == product_id, Review.status == 1
    )
    if rating is not None:
        base = base.filter(Review.rating == rating)
    total = base.count()
    rows = (
        base.order_by(Review.created_at.desc(), Review.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, rows


def review_rating_distribution(db: Session, product_id: int) -> list[tuple[int, int]]:
    """评价星级分布（仅已发布 status=1，单条 GROUP BY 聚合）"""
    return (
        db.query(Review.rating, func.count())
        .filter(Review.product_id == product_id, Review.status == 1)
        .group_by(Review.rating)
        .all()
    )


def users_by_ids(db: Session, uids: set[int]) -> list[User]:
    return db.query(User).filter(User.id.in_(uids)).all()


# ---------- 到货通知（stock_notifications 影子表） ----------

def stock_notification_by(db: Session, variant_id: int, email: str) -> StockNotification | None:
    return db.query(StockNotification).filter(
        StockNotification.variant_id == variant_id, StockNotification.email == email
    ).first()


def add_stock_notification(db: Session, sn: StockNotification) -> None:
    db.add(sn)


def delete_stock_notification(db: Session, variant_id: int, email: str) -> bool:
    sn = stock_notification_by(db, variant_id, email)
    if sn is None:
        return False
    db.delete(sn)
    return True


def pending_restock(db: Session) -> list[tuple]:
    """待通知订阅 join 当前已回补（stock>0）的变体与商品（单条 JOIN 批量，避免逐行查询）"""
    return (
        db.query(StockNotification, Variant, Product)
        .join(Variant, Variant.id == StockNotification.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .filter(StockNotification.notified_at.is_(None), Variant.stock > 0)
        .order_by(StockNotification.id)
        .all()
    )


def scheduled_products_count(db: Session, now) -> int:
    """定时上架巡检：已上架但 published_at 在未来的商品数（供运营统计）"""
    return (
        db.query(func.count())
        .select_from(Product)
        .filter(Product.status == 1, Product.published_at.isnot(None),
                Product.published_at > now)
        .scalar()
    ) or 0


# ---------- 后台管理 ----------

def admin_products(
    db: Session, *, status: int | None, q: str | None, offset: int, limit: int,
) -> tuple[int, list[Product]]:
    query = db.query(Product)
    if status is not None:
        query = query.filter(Product.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Product.title.like(like), Product.slug.like(like)))
    total = query.count()
    prods = (
        query.order_by(Product.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, prods


def admin_variants(
    db: Session, *, product_id: int | None, q: str | None,
    offset: int, limit: int, active_only: bool = False,
) -> tuple[int, list[tuple[Variant, str]]]:
    """后台变体列表（join 商品标题，供库存中心/变体管理）。"""
    query = db.query(Variant, Product.title).join(
        Product, Variant.product_id == Product.id
    )
    if product_id is not None:
        query = query.filter(Variant.product_id == product_id)
    if active_only:
        query = query.filter(Variant.is_active == 1)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Variant.sku.like(like), Product.title.like(like)))
    total = query.count()
    rows = (
        query.order_by(Variant.product_id.asc(), Variant.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, rows


def variant_counts(db: Session, pids: list[int]) -> dict[int, dict]:
    """后台商品列表聚合（variant_count/total_stock/low_stock_count）：
    单条 GROUP BY 条件聚合批量求值（与 stock_map 同纪律，不整行载入 Variant）。"""
    agg: dict[int, dict] = {}
    if not pids:
        return agg
    rows = (
        db.query(
            Variant.product_id,
            func.count(),
            func.coalesce(func.sum(Variant.stock), 0),
            func.coalesce(func.sum(case((Variant.stock <= Variant.safety_stock, 1), else_=0)), 0),
        )
        .filter(Variant.product_id.in_(pids), Variant.is_active == 1)
        .group_by(Variant.product_id)
        .all()
    )
    for pid, cnt, total_stock, low in rows:
        agg[pid] = {"variant_count": cnt, "total_stock": total_stock, "low_stock_count": low}
    return agg


def product_slug_taken(db: Session, slug: str) -> bool:
    return db.query(Product.id).filter(Product.slug == slug).first() is not None


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def get_category(db: Session, category_id: int) -> Category | None:
    return db.get(Category, category_id)


def add_product(db: Session, p: Product) -> None:
    db.add(p)


def get_variant(db: Session, variant_id: int) -> Variant | None:
    return db.get(Variant, variant_id)


def variant_sku_taken(db: Session, sku: str) -> bool:
    return db.query(Variant.id).filter(Variant.sku == sku).first() is not None


def add_variant(db: Session, v: Variant) -> None:
    db.add(v)


def variant_images(db: Session, variant_id: int) -> list[str]:
    return [
        r[0] for r in db.query(VariantImage.image_url)
        .filter(VariantImage.variant_id == variant_id)
        .order_by(VariantImage.sort_order.asc(), VariantImage.id.asc())
        .all()
    ]


def add_variant_images(db: Session, variant_id: int, urls: list[str]) -> None:
    for sort_order, url in enumerate(urls):
        db.add(VariantImage(variant_id=variant_id, image_url=url, sort_order=sort_order))


def replace_variant_images(db: Session, variant_id: int, urls: list[str]) -> None:
    db.query(VariantImage).filter(
        VariantImage.variant_id == variant_id
    ).delete(synchronize_session=False)
    add_variant_images(db, variant_id, urls)


def all_categories(db: Session) -> list[Category]:
    return (
        db.query(Category)
        .order_by(Category.sort_order.asc(), Category.id.asc())
        .all()
    )


def category_slug_taken(db: Session, slug: str) -> bool:
    return db.query(Category.id).filter(Category.slug == slug).first() is not None


def add_category(db: Session, c: Category) -> None:
    db.add(c)


def all_collections(db: Session) -> list[Collection]:
    return (
        db.query(Collection)
        .order_by(Collection.sort_order.asc(), Collection.id.asc())
        .all()
    )


def collection_product_counts(db: Session, cids: list[int]) -> dict[int, int]:
    """后台集合列表商品数：单条 GROUP BY 批量计数（避免逐集合 count 的 N+1）"""
    counts = {cid: 0 for cid in cids}
    if not cids:
        return counts
    rows = (
        db.query(CollectionProduct.collection_id, func.count())
        .filter(CollectionProduct.collection_id.in_(cids))
        .group_by(CollectionProduct.collection_id)
        .all()
    )
    counts.update(dict(rows))
    return counts


def collection_slug_taken(db: Session, slug: str) -> bool:
    return db.query(Collection.id).filter(Collection.slug == slug).first() is not None


def add_collection(db: Session, c: Collection) -> None:
    db.add(c)


def get_collection(db: Session, collection_id: int) -> Collection | None:
    return db.get(Collection, collection_id)


def existing_product_ids(db: Session, ids: set[int]) -> set[int]:
    return {
        r[0] for r in db.query(Product.id).filter(Product.id.in_(ids)).all()
    }


def replace_collection_products(
    db: Session, collection_id: int, products: list[CollectionProduct],
) -> None:
    db.query(CollectionProduct).filter(
        CollectionProduct.collection_id == collection_id
    ).delete(synchronize_session=False)
    for cp in products:
        db.add(cp)


def delete_collection_products(db: Session, collection_id: int) -> None:
    """删除集合时级联清掉物化商品行（collection_products 无 ORM 级联配置）"""
    db.query(CollectionProduct).filter(
        CollectionProduct.collection_id == collection_id
    ).delete(synchronize_session=False)


def collection_product_pairs(
    db: Session, collection_id: int,
) -> list[tuple[CollectionProduct, Product]]:
    """后台集合商品清单：保留 sort_order 的 (关联行, 商品) 对（admin 视角不过滤上架状态）"""
    return (
        db.query(CollectionProduct, Product)
        .join(Product, Product.id == CollectionProduct.product_id)
        .filter(CollectionProduct.collection_id == collection_id)
        .order_by(
            CollectionProduct.sort_order.asc(),
            CollectionProduct.product_id.asc(),
        )
        .all()
    )


def add_admin_log(
    db: Session, *, admin_id: int, action: str, entity: str, entity_id: int,
    diff_json: dict | None = None,
) -> None:
    db.add(AdminLog(
        admin_id=admin_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        diff_json=diff_json,
    ))


# ---------- 商品多语言（product_translations 影子表） ----------

def translations_map(db: Session, pids: list[int], locale: str) -> dict[int, ProductTranslation]:
    tmap: dict[int, ProductTranslation] = {}
    if not pids:
        return tmap
    rows = db.query(ProductTranslation).filter(
        ProductTranslation.product_id.in_(pids),
        ProductTranslation.locale == locale,
    ).all()
    for t in rows:
        tmap[t.product_id] = t
    return tmap


def get_translation(db: Session, product_id: int, locale: str) -> ProductTranslation | None:
    return db.get(ProductTranslation, (product_id, locale))


def product_translations_all(db: Session, product_id: int) -> list[ProductTranslation]:
    return (
        db.query(ProductTranslation)
        .filter(ProductTranslation.product_id == product_id)
        .order_by(ProductTranslation.locale.asc())
        .all()
    )


def add_translation(db: Session, t: ProductTranslation) -> None:
    db.add(t)


def delete_translation(db: Session, product_id: int, locale: str) -> bool:
    t = get_translation(db, product_id, locale)
    if t is None:
        return False
    db.delete(t)
    return True
