"""运营域仓储 —— 纯查询/聚合（dashboard 聚合实现保持原样，SQL 条数是 test_perf 断言对象）"""

from datetime import datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session

from app.models import (
    AdminLog, Cart, CookieConsent, NewsletterSubscriber, Order, PointsLedger,
    Product, ReconciliationDaily, Review, Ticket, User, Variant,
)


def page(q: Query, page: int, size: int):
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return rows, total


# ===== 看板聚合（与原 admin_ops.dashboard 同构：COUNT/SUM 聚合下推数据库）=====


def orders_placed_since(db: Session, start: datetime) -> int:
    return db.query(func.count(Order.id)).filter(Order.placed_at >= start).scalar() or 0


def paid_gmv_since(db: Session, start: datetime) -> int:
    return (
        db.query(func.coalesce(func.sum(Order.grand_total), 0))
        .filter(Order.paid_at.isnot(None), Order.paid_at >= start)
        .scalar()
    )


def paid_orders_since(db: Session, start: datetime) -> int:
    return (
        db.query(func.count(Order.id))
        .filter(Order.paid_at.isnot(None), Order.paid_at >= start)
        .scalar()
        or 0
    )


def newsletter_count(db: Session) -> int:
    return db.query(func.count(NewsletterSubscriber.email)).scalar() or 0


def cookie_consent_count(db: Session) -> int:
    return db.query(func.count(CookieConsent.id)).scalar() or 0


def _has_items():
    return func.coalesce(func.json_length(Cart.items), 0) > 0


def carts_with_items_count(db: Session) -> int:
    return db.query(func.count(Cart.id)).filter(_has_items()).scalar() or 0


def abandoned_carts_count(db: Session, cutoff: datetime) -> int:
    return db.query(func.count(Cart.id)).filter(
        _has_items(), Cart.updated_at <= cutoff).scalar() or 0


def pending_orders_count(db: Session) -> int:
    return db.query(func.count(Order.id)).filter(Order.status == 0).scalar() or 0


def low_stock_count(db: Session) -> int:
    return db.query(func.count(Variant.id)).filter(Variant.stock <= 8).scalar() or 0


def pending_reviews_count(db: Session) -> int:
    return db.query(func.count(Review.id)).filter(Review.status == 0).scalar() or 0


def open_tickets_count(db: Session) -> int:
    return db.query(func.count(Ticket.id)).filter(Ticket.status.in_([0, 1, 2])).scalar() or 0


def top_products(db: Session, limit: int = 5) -> list[Product]:
    return (
        db.query(Product)
        .order_by(Product.sold_count.desc(), Product.id.desc())
        .limit(limit)
        .all()
    )


def daily_paid_rows(db: Session, d_start: datetime) -> list:
    return (
        db.query(
            func.date(Order.paid_at),
            func.coalesce(func.sum(Order.grand_total), 0),
            func.count(Order.id),
        )
        .filter(Order.status >= 1, Order.paid_at.isnot(None), Order.paid_at >= d_start)
        .group_by(func.date(Order.paid_at))
        .all()
    )


def latest_reconciliation(db: Session) -> ReconciliationDaily | None:
    return (
        db.query(ReconciliationDaily)
        .order_by(ReconciliationDaily.reconcile_date.desc(), ReconciliationDaily.id.desc())
        .first()
    )


def low_stock_top_rows(db: Session, limit: int = 5) -> list:
    return (
        db.query(Variant.sku, Product.title, Variant.stock)
        .join(Product, Product.id == Variant.product_id)
        .filter(Variant.stock <= 8)
        .order_by(Variant.stock.asc(), Variant.id.asc())
        .limit(limit)
        .all()
    )


# ===== 会员管理 =====


def members_query(db: Session, q: str | None, tier: int | None) -> Query:
    query = db.query(User).filter(User.role == 0)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.email.ilike(like), User.name.ilike(like)))
    if tier is not None:
        query = query.filter(User.tier == tier)
    return query.order_by(User.id.desc())


def member_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def member_ledger_recent(db: Session, user_id: int, limit: int = 10) -> list[PointsLedger]:
    return (
        db.query(PointsLedger)
        .filter(PointsLedger.user_id == user_id)
        .order_by(PointsLedger.id.desc())
        .limit(limit)
        .all()
    )


# ===== 审计日志 =====


def admin_logs_query(db: Session, entity: str | None) -> Query:
    q = db.query(AdminLog).order_by(AdminLog.id.desc())
    if entity:
        q = q.filter(AdminLog.entity == entity)
    return q
