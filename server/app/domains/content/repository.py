"""内容域仓储 —— 纯查询/分页，不掺业务规则"""

from sqlalchemy.orm import Query, Session

from app.models import Article, Faq, Order, OrderItem, Product, Review, UgcSubmission, User


def page(q: Query, page: int, size: int):
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return rows, total


# ===== FAQ =====


def active_faqs(db: Session, category: int | None) -> list[Faq]:
    q = db.query(Faq).filter(Faq.active == 1)
    if category is not None:
        q = q.filter(Faq.category == category)
    return q.order_by(Faq.sort_order, Faq.id).all()


def admin_faqs_ordered(db: Session, category: int | None = None) -> Query:
    q = db.query(Faq)
    if category is not None:
        q = q.filter(Faq.category == category)
    return q.order_by(Faq.category.asc(), Faq.sort_order.asc(), Faq.id.asc())


def faq_by_id(db: Session, faq_id: int) -> Faq | None:
    return db.get(Faq, faq_id)


# ===== 博客文章 =====


def published_articles(db: Session, tag: str | None) -> Query:
    q = db.query(Article).filter(Article.status == 1)
    if tag:
        q = q.filter(Article.tags.like(f'%"{tag}"%'))
    return q.order_by(Article.published_at.desc(), Article.id.desc())


def article_by_slug(db: Session, slug: str) -> Article | None:
    return db.query(Article).filter(Article.slug == slug, Article.status == 1).first()


def published_article_tags(db: Session) -> list:
    """已发布文章全量 tags 列（JSON 列表），供前台标签云 Counter 聚合"""
    return [r[0] for r in db.query(Article.tags).filter(Article.status == 1).all()]


def admin_articles_desc(db: Session, status: int | None = None) -> Query:
    q = db.query(Article)
    if status is not None:
        q = q.filter(Article.status == status)
    return q.order_by(Article.id.desc())


def article_id_by_slug(db: Session, slug: str, exclude_id: int | None = None):
    q = db.query(Article.id).filter(Article.slug == slug)
    if exclude_id is not None:
        q = q.filter(Article.id != exclude_id)
    return q.first()


def article_by_id(db: Session, article_id: int) -> Article | None:
    return db.get(Article, article_id)


# ===== 评价 =====


def admin_reviews_desc(db: Session, status: int | None) -> Query:
    q = db.query(Review).order_by(Review.id.desc())
    if status is not None:
        q = q.filter(Review.status == status)
    return q


def review_by_id(db: Session, review_id: int) -> Review | None:
    return db.get(Review, review_id)


def product_reviews_desc(db: Session, product_id: int) -> Query:
    return (
        db.query(Review)
        .filter(Review.product_id == product_id, Review.status == 1)
        .order_by(Review.id.desc())
    )


def approved_ratings(db: Session, product_id: int) -> list[tuple[int]]:
    return (
        db.query(Review.rating)
        .filter(Review.product_id == product_id, Review.status == 1)
        .all()
    )


def order_for_review(db: Session, order_no: str, user_id: int) -> Order | None:
    return (
        db.query(Order)
        .filter(Order.order_no == order_no, Order.user_id == user_id)
        .first()
    )


def order_item_in_order(db: Session, item_id: int, order_id: int) -> OrderItem | None:
    return (
        db.query(OrderItem)
        .filter(OrderItem.id == item_id, OrderItem.order_id == order_id)
        .first()
    )


def review_id_for_item(db: Session, item_id: int):
    return db.query(Review.id).filter(Review.order_item_id == item_id).first()


def product_by_slug(db: Session, slug: str) -> Product | None:
    return db.query(Product).filter(Product.slug == slug).first()


def product_by_id(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def users_by_ids(db: Session, user_ids: set[int]) -> list[User]:
    return db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []


# ===== UGC =====


def admin_ugc_desc(db: Session, status: int | None) -> Query:
    q = db.query(UgcSubmission).order_by(UgcSubmission.id.desc())
    if status is not None:
        q = q.filter(UgcSubmission.status == status)
    return q


def wall_ugc(db: Session, offset: int, limit: int) -> tuple[int, list[UgcSubmission]]:
    q = (
        db.query(UgcSubmission)
        .filter(UgcSubmission.status == 1)
        .order_by(UgcSubmission.id.desc())
    )
    total = q.count()
    return total, q.offset(offset).limit(limit).all()


def ugc_by_id(db: Session, ugc_id: int) -> UgcSubmission | None:
    return db.get(UgcSubmission, ugc_id)


def user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def products_by_ids(db: Session, ids: set[int]) -> list[Product]:
    return (
        db.query(Product).filter(Product.id.in_(ids), Product.status == 1).all()
        if ids else []
    )
