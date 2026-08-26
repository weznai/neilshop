"""内容域服务 —— FAQ/博客/评价/UGC 业务（含后台审核与积分奖励）"""

from collections import Counter
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import PointsReason
from app.models import (
    AdminLog, Article, Faq, OrderItem, PointsLedger, Product, Review,
    UgcSubmission, User,
)
from app.domains.content import repository as repo
from app.domains.content.schemas import (
    ArticleCreateIn, ArticleUpdateIn, FaqCreateIn, FaqUpdateIn, ReasonIn,
    ReviewIn, UgcIn, FAQ_CATEGORY, REVIEW_REWARD, UGC_REWARD,
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


def _article_summary(content_md: str | None) -> str:
    """列表摘要：剥首个 '# ' 标题行与空行后截 120 字符；剥完为空回落原文截断"""
    raw = content_md or ""
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return body[:120] if body else raw[:120]


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
            "summary": _article_summary(a.content_md),
        }
        for a in rows
    ]
    # 标签云：全量已发布文章 tags（JSON 列表）Counter 聚合，count 降序（并列按首次出现）
    counter: Counter = Counter()
    for tags in repo.published_article_tags(db):
        for t in tags or []:
            counter[str(t)] += 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "tags": [{"name": name, "count": n} for name, n in counter.most_common()],
    }


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
    # CAS 抢占 reviewed 0→1：并发双提交只有一个赢家，输家 rowcount=0 → 409
    # （替代双查后插入的 check-then-set，杜绝同 item 并发双评撞唯一索引 500）
    claimed = db.execute(
        update(OrderItem)
        .where(OrderItem.id == item.id, OrderItem.reviewed == 0)
        .values(reviewed=1)
    )
    if claimed.rowcount == 0:
        raise HTTPException(status_code=409, detail="already reviewed")
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
    db.commit()
    db.refresh(review)
    out = {"id": review.id, "status": review.status}
    if review.status == 0:
        out["pending_review"] = True  # 前端提示「提交成功，审核通过后展示」
    return out


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


# 评价奖励积分发放用原子 UPDATE（与 services/points.py 同通道：先原子加分再读余额记流水，
# 避免与同事务内其他 ORM 脏快照互相覆盖）
_ADD_POINTS_SQL = text("UPDATE users SET points = points + :amt WHERE id = :uid")
_POINTS_OF_SQL = text("SELECT points FROM users WHERE id = :uid")


def _grant_review_reward(db: Session, review: Review) -> None:
    """评价过审发放奖励积分（REVIEW_REWARD=10，不冻结，即时可用）。
    幂等：同 review 只发一次（ledger 查 ref_type='review' + ref_id 命中即跳过），
    双保险 approve_review 本身已有 status!=0 → 409 挡重复过审。"""
    if not review.user_id:
        return
    dup = (
        db.query(PointsLedger.id)
        .filter(PointsLedger.user_id == review.user_id,
                PointsLedger.reason == int(PointsReason.REVIEW_REWARD),
                PointsLedger.ref_type == "review",
                PointsLedger.ref_id == review.id)
        .first()
    )
    if dup:
        return
    db.execute(_ADD_POINTS_SQL, {"uid": review.user_id, "amt": REVIEW_REWARD})
    balance = int(db.execute(_POINTS_OF_SQL, {"uid": review.user_id}).scalar())
    db.add(PointsLedger(
        user_id=review.user_id,
        change=REVIEW_REWARD,
        reason=int(PointsReason.REVIEW_REWARD),
        balance_after=balance,
        ref_type="review",
        ref_id=review.id,
        frozen=0,
        created_at=utcnow(),
    ))


def approve_review(db: Session, admin: User, review_id: int) -> dict:
    r = repo.review_by_id(db, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="review not found")
    if r.status != 0:
        raise HTTPException(status_code=409, detail="review not pending")
    r.status = 1
    db.flush()
    _grant_review_reward(db, r)
    _recalc_rating(db, r.product_id)
    log_admin(db, admin, "approve", "review", r.id, {"status": 1, "points": REVIEW_REWARD})
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
        "pages": (total + size - 1) // size,
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


_ARTICLE_STATUS_FILTER = {"published": 1, "draft": 0}


def list_articles_admin(db: Session, status: str | None, page: int, size: int) -> dict:
    """status 语义参数映射模型 SmallInteger 列（1发布/0草稿），非法值 400"""
    status_val = None
    if status is not None:
        status_val = _ARTICLE_STATUS_FILTER.get(status.strip().lower())
        if status_val is None:
            raise HTTPException(status_code=400, detail="invalid status, expect published/draft")
    rows, total = repo.page(repo.admin_articles_desc(db, status_val), page, size)
    return {
        "items": [_article_dict(a) for a in rows], "total": total,
        "page": page, "size": size, "pages": (total + size - 1) // size,
    }


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
        cover=body.cover,
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


def _faq_category_filter(category: str | None) -> int | None:
    """分类筛选参数 → 模型 SmallInteger 列：数字串直转，否则按中文名反查，非法 400"""
    if category is None:
        return None
    val = category.strip()
    if not val:
        return None
    if val.isdigit():
        return int(val)
    by_name = {name: cid for cid, name in FAQ_CATEGORY.items()}
    if val not in by_name:
        raise HTTPException(status_code=400, detail="invalid faq category")
    return by_name[val]


def list_faqs_admin(db: Session, category: str | None, page: int, size: int) -> dict:
    """后台 FAQ 列表：分类过滤 + 标准分页（默认 size=100 兼容原全量消费方）"""
    rows, total = repo.page(
        repo.admin_faqs_ordered(db, _faq_category_filter(category)), page, size
    )
    return {
        "items": [_faq_dict(f) for f in rows], "total": total,
        "page": page, "size": size, "pages": (total + size - 1) // size,
    }


def _embed_faq(db: Session, f) -> None:
    """best-effort 向量化（RAG 索引）：网关未配/失败静默跳过，后续可「重建索引」补齐；
    成功后失效检索缓存。异常绝不上抛——FAQ 保存不能因 embedding 故障失败。"""
    try:
        from app.services.embedding import embed_texts, faq_text
        from app.services.llm import resolve_params

        p = resolve_params(db)
        if not p.get("api_key"):
            return
        vec = embed_texts([faq_text(f.question, f.answer_md)], p)
        if vec:
            f.embedding = vec[0]
            from app.domains.chat.retrieval import invalidate
            invalidate()
    except Exception:
        pass


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
    _embed_faq(db, f)
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
    if "question" in data or "answer_md" in data:
        f.embedding = None  # 内容变了旧向量失效，重嵌（失败留空走全量回退）
        _embed_faq(db, f)
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
