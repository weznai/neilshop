"""内容域服务 —— FAQ/博客/评价/UGC 业务（含后台审核与积分奖励）"""

from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import PointsReason
from app.models import (
    AdminLog, Article, Faq, PointsLedger, Product, Review, UgcSubmission, User,
)
from app.domains.content import repository as repo
from app.domains.content.schemas import (
    ArticleCreateIn, ArticleUpdateIn, FaqCreateIn, FaqUpdateIn, ReasonIn,
    ReviewIn, UgcIn, FAQ_CATEGORY, UGC_REWARD,
)


def log_admin(db: Session, admin: User, action: str, entity: str, entity_id: int, diff: dict | None = None):
    db.add(AdminLog(
        admin_id=admin.id,
        action=action,
        entity=entity,
        entity_id=int(entity_id or 0),
        diff_json=diff,
    ))


def _mask_name(name: str | None, email: str) -> str:
    src = (name or "").strip() or email
    if "@" in src:
        src = src.split("@", 1)[0]
    if len(src) <= 1:
        return src + "***"
    return src[0] + "***" + src[-1]


MAX_IMAGE_URL_LEN = 500
MAX_REVIEW_IMAGES = 6


def _check_image_url(url: str) -> None:
    """UGC/评价图片链接校验：仅 http/https 绝对地址且长度受限（防 javascript: 注入与超长垃圾）"""
    if not url or len(url) > MAX_IMAGE_URL_LEN:
        raise HTTPException(status_code=400, detail="invalid image_url")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="invalid image_url")


# ===== 用户侧：FAQ =====


def list_faqs(db: Session, category: int | None) -> list[dict]:
    rows = repo.active_faqs(db, category)
    return [
        {
            "id": f.id,
            "category": f.category,
            "question": f.question,
            "answer_md": f.answer_md,
            "sort_order": f.sort_order,
        }
        for f in rows
    ]


# ===== 用户侧：博客文章 =====


def list_articles(db: Session, page: int, size: int, tag: str | None) -> dict:
    q = repo.published_articles(db, tag)
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    items = [
        {
            "title": a.title,
            "slug": a.slug,
            "cover": a.cover,
            "author": a.author,
            "tags": a.tags,
            "published_at": a.published_at,
            "summary": (a.content_md or "")[:120],
        }
        for a in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


def article_detail(db: Session, slug: str) -> dict:
    a = repo.article_by_slug(db, slug)
    if not a:
        raise HTTPException(status_code=404, detail="article not found")
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "cover": a.cover,
        "content_md": a.content_md,
        "author": a.author,
        "tags": a.tags,
        "published_at": a.published_at,
    }


# ===== 用户侧：评价 =====


def create_review(db: Session, user: User, body: ReviewIn) -> dict:
    order = repo.order_for_review(db, body.order_no, user.id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    if order.status not in (3, 4, 5):
        raise HTTPException(status_code=409, detail="order not reviewable")
    item = repo.order_item_in_order(db, body.order_item_id, order.id)
    if not item:
        raise HTTPException(status_code=404, detail="order item not found")
    if item.reviewed or repo.review_id_for_item(db, item.id):
        raise HTTPException(status_code=409, detail="already reviewed")
    product = repo.product_by_slug(db, item.product_slug)
    if not product:
        raise HTTPException(status_code=404, detail="product not found")
    images = body.images or []
    if len(images) > MAX_REVIEW_IMAGES:
        raise HTTPException(status_code=400, detail="too many images")
    for u in images:
        _check_image_url(u)
    review = Review(
        product_id=product.id,
        user_id=user.id,
        order_item_id=item.id,
        rating=body.rating,
        content=body.content,
        images=images,
        status=0,
    )
    db.add(review)
    item.reviewed = 1
    db.commit()
    db.refresh(review)
    return {"id": review.id, "status": review.status}


def list_reviews(db: Session, product_id: int, page: int, size: int) -> dict:
    q = repo.product_reviews_desc(db, product_id)
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    user_ids = {r.user_id for r in rows}
    users = repo.users_by_ids(db, user_ids)
    name_map = {u.id: _mask_name(u.name, u.email) for u in users}
    items = [
        {
            "id": r.id,
            "product_id": r.product_id,
            "user_name": name_map.get(r.user_id, "匿名用户"),
            "rating": r.rating,
            "content": r.content,
            "images": r.images,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


# ===== 用户侧：UGC =====


def submit_ugc(db: Session, user: User | None, body: UgcIn) -> dict:
    _check_image_url(body.image_url)
    ugc = UgcSubmission(
        user_id=user.id if user else None,
        instagram_handle=body.instagram_handle,
        image_url=body.image_url,
        caption=body.caption,
        related_product_id=body.related_product_id,
        status=0,
    )
    db.add(ugc)
    db.commit()
    db.refresh(ugc)
    return {"id": ugc.id, "status": ugc.status}


def list_ugc_wall(db: Session, page: int, size: int) -> dict:
    total, rows = repo.wall_ugc(db, (page - 1) * size, size)
    pids = {u.related_product_id for u in rows if u.related_product_id}
    pmap = {p.id: p for p in repo.products_by_ids(db, pids)}
    items = []
    for u in rows:
        p = pmap.get(u.related_product_id) if u.related_product_id else None
        items.append({
            "id": u.id,
            "image_url": u.image_url,
            "caption": u.caption,
            "instagram_handle": u.instagram_handle,
            "product": (
                {"slug": p.slug, "title": p.title, "hero_image": p.hero_image}
                if p else None
            ),
        })
    return {"items": items, "total": total, "page": page, "size": size}


# ===== 后台：评价审核 =====


def _recalc_rating(db: Session, product_id: int):
    rows = repo.approved_ratings(db, product_id)
    cnt = len(rows)
    avg = round(sum(r[0] for r in rows) * 100 / cnt) if cnt else 0
    product = repo.product_by_id(db, product_id)
    if product:
        product.rating_avg = avg
        product.rating_count = cnt


def admin_reviews(db: Session, status: int | None, page: int, size: int) -> dict:
    rows, total = repo.page(repo.admin_reviews_desc(db, status), page, size)
    return {
        "items": [
            {
                "id": r.id,
                "product_id": r.product_id,
                "user_id": r.user_id,
                "order_item_id": r.order_item_id,
                "rating": r.rating,
                "content": r.content,
                "images": r.images,
                "status": r.status,
                "reject_reason": r.reject_reason,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def approve_review(db: Session, admin: User, review_id: int) -> dict:
    r = repo.review_by_id(db, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="review not found")
    if r.status != 0:
        raise HTTPException(status_code=409, detail="review not pending")
    r.status = 1
    db.flush()
    _recalc_rating(db, r.product_id)
    log_admin(db, admin, "approve", "review", r.id, {"status": 1})
    db.commit()
    return {"id": r.id, "status": r.status}


def reject_review(db: Session, admin: User, review_id: int, body: ReasonIn) -> dict:
    r = repo.review_by_id(db, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="review not found")
    if r.status != 0:
        raise HTTPException(status_code=409, detail="review not pending")
    r.status = 2
    r.reject_reason = body.reason
    log_admin(db, admin, "reject", "review", r.id, {"status": 2, "reason": body.reason})
    db.commit()
    return {"id": r.id, "status": r.status, "reject_reason": r.reject_reason}


# ===== 后台：UGC 审核 =====


def admin_ugc(db: Session, status: int | None, page: int = 1, size: int = 20) -> dict:
    """后台 UGC 队列：与 reviews 分页形态对齐（items/total/page/size）。
    响应原先即为 {"items": [...]} 对象，新增 total/page/size 键为纯增量，向后兼容。"""
    rows, total = repo.page(repo.admin_ugc_desc(db, status), page, size)
    return {
        "items": [
            {
                "id": u.id,
                "user_id": u.user_id,
                "instagram_handle": u.instagram_handle,
                "image_url": u.image_url,
                "caption": u.caption,
                "related_product_id": u.related_product_id,
                "status": u.status,
                "points_rewarded": u.points_rewarded,
                "created_at": u.created_at,
            }
            for u in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def _grant_ugc_reward(db: Session, ugc: UgcSubmission):
    if not ugc.user_id:
        return
    user = repo.user_by_id(db, ugc.user_id)
    if not user:
        return
    user.points += UGC_REWARD
    db.add(PointsLedger(
        user_id=user.id,
        change=UGC_REWARD,
        reason=int(PointsReason.UGC_REWARD),
        balance_after=user.points,
        ref_type="ugc",
        ref_id=ugc.id,
        frozen=0,
        created_at=utcnow(),
    ))
    ugc.points_rewarded = UGC_REWARD


def approve_ugc(db: Session, admin: User, ugc_id: int) -> dict:
    u = repo.ugc_by_id(db, ugc_id)
    if not u:
        raise HTTPException(status_code=404, detail="ugc not found")
    if u.status != 0:
        raise HTTPException(status_code=409, detail="ugc not pending")
    u.status = 1
    _grant_ugc_reward(db, u)
    log_admin(db, admin, "approve", "ugc", u.id, {"status": 1, "points": u.points_rewarded})
    db.commit()
    return {"id": u.id, "status": u.status, "points_rewarded": u.points_rewarded}


def reject_ugc(db: Session, admin: User, ugc_id: int) -> dict:
    u = repo.ugc_by_id(db, ugc_id)
    if not u:
        raise HTTPException(status_code=404, detail="ugc not found")
    if u.status != 0:
        raise HTTPException(status_code=409, detail="ugc not pending")
    u.status = 2
    log_admin(db, admin, "reject", "ugc", u.id, {"status": 2})
    db.commit()
    return {"id": u.id, "status": u.status}


# ===== 后台：博客文章 =====


def _article_dict(a: Article) -> dict:
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "cover": a.cover,
        "content_md": a.content_md,
        "author": a.author,
        "tags": a.tags,
        "status": a.status,
        "published_at": a.published_at,
        "created_at": a.created_at,
    }


def list_articles_admin(db: Session, page: int, size: int) -> dict:
    rows, total = repo.page(repo.admin_articles_desc(db), page, size)
    return {"items": [_article_dict(a) for a in rows], "total": total, "page": page, "size": size}


def create_article(db: Session, admin: User, body: ArticleCreateIn) -> dict:
    slug = body.slug.strip().lower()
    if not slug:
        raise HTTPException(status_code=422, detail="slug required")
    if repo.article_id_by_slug(db, slug):
        raise HTTPException(status_code=409, detail="slug exists")
    a = Article(
        slug=slug,
        title=body.title.strip(),
        author=body.author.strip(),
        content_md=body.content_md,
        tags=body.tags or [],
        status=body.status,
        published_at=utcnow() if body.status == 1 else None,
    )
    db.add(a)
    db.flush()
    log_admin(db, admin, "create", "article", a.id, {"slug": slug, "title": a.title, "status": a.status})
    db.commit()
    db.refresh(a)
    return _article_dict(a)


def update_article(db: Session, admin: User, article_id: int, body: ArticleUpdateIn) -> dict:
    a = repo.article_by_id(db, article_id)
    if not a:
        raise HTTPException(status_code=404, detail="article not found")
    data = body.model_dump(exclude_unset=True)
    if "slug" in data:
        data["slug"] = data["slug"].strip().lower()
        if not data["slug"]:
            raise HTTPException(status_code=422, detail="slug required")
        if repo.article_id_by_slug(db, data["slug"], exclude_id=a.id):
            raise HTTPException(status_code=409, detail="slug exists")
    if data.get("status") == 1 and a.published_at is None:
        a.published_at = utcnow()
    for k, v in data.items():
        setattr(a, k, v)
    log_admin(db, admin, "update", "article", a.id, data)
    db.commit()
    db.refresh(a)
    return _article_dict(a)


def delete_article(db: Session, admin: User, article_id: int) -> dict:
    a = repo.article_by_id(db, article_id)
    if not a:
        raise HTTPException(status_code=404, detail="article not found")
    log_admin(db, admin, "delete", "article", a.id, {"slug": a.slug, "title": a.title})
    db.delete(a)
    db.commit()
    return {"id": article_id, "deleted": True}


# ===== 后台：FAQ =====


def _faq_dict(f: Faq) -> dict:
    return {
        "id": f.id,
        "category": f.category,
        "category_name": FAQ_CATEGORY.get(f.category, str(f.category)),
        "question": f.question,
        "answer_md": f.answer_md,
        "sort_order": f.sort_order,
        "active": f.active,
    }


def list_faqs_admin(db: Session) -> dict:
    rows = repo.admin_faqs_ordered(db)
    return {"items": [_faq_dict(f) for f in rows]}


def create_faq(db: Session, admin: User, body: FaqCreateIn) -> dict:
    f = Faq(
        category=body.category,
        question=body.question.strip(),
        answer_md=body.answer_md,
        sort_order=body.sort_order,
        active=1,
    )
    db.add(f)
    db.flush()
    log_admin(db, admin, "create", "faq", f.id, {"category": f.category, "question": f.question})
    db.commit()
    db.refresh(f)
    return _faq_dict(f)


def update_faq(db: Session, admin: User, faq_id: int, body: FaqUpdateIn) -> dict:
    f = repo.faq_by_id(db, faq_id)
    if not f:
        raise HTTPException(status_code=404, detail="faq not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(f, k, v)
    log_admin(db, admin, "update", "faq", f.id, data)
    db.commit()
    db.refresh(f)
    return _faq_dict(f)


def delete_faq(db: Session, admin: User, faq_id: int) -> dict:
    f = repo.faq_by_id(db, faq_id)
    if not f:
        raise HTTPException(status_code=404, detail="faq not found")
    log_admin(db, admin, "delete", "faq", f.id, {"question": f.question})
    db.delete(f)
    db.commit()
    return {"id": faq_id, "deleted": True}
