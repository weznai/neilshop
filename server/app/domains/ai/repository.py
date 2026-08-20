"""AI 域仓储 —— 纯查询（商品推荐来源/FAQ/订单物流/折扣码/settings 运营参数）"""

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models import DiscountCode, Faq, Order, Product, Setting, Shipment


def setting_value(db: Session, key: str, default):
    """settings 读值（客服话术用）：查不到/类型不符/DB 异常一律回默认值，不断供"""
    try:
        row = db.get(Setting, key)
        if row is None or row.value is None:
            return default
        return type(default)(row.value)
    except Exception:
        return default


def active_products(db: Session) -> Query:
    return db.query(Product).filter(Product.status == 1)


def product_by_id(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def same_category_bestsellers(db: Session, category_id: int, exclude_id: int) -> list[Product]:
    return (
        active_products(db)
        .filter(Product.category_id == category_id, Product.id != exclude_id)
        .order_by(Product.sold_count.desc(), Product.id.asc()).all()
    )


def active_by_ids(db: Session, ids: list[int]) -> list[Product]:
    return active_products(db).filter(Product.id.in_(ids)).all()


def all_active(db: Session) -> list[Product]:
    return active_products(db).all()


def category_bestsellers(db: Session, category_ids: set[int]) -> list[Product]:
    return (
        active_products(db)
        .filter(Product.category_id.in_(category_ids))
        .order_by(Product.sold_count.desc(), Product.id.asc()).all()
    )


def hot_all(db: Session) -> list[Product]:
    return (
        active_products(db)
        .order_by(Product.is_best_seller.desc(), Product.sold_count.desc(), Product.id.asc()).all()
    )


def new_all(db: Session) -> list[Product]:
    return (
        active_products(db)
        .order_by(Product.published_at.desc(), Product.id.desc()).all()
    )


def hot_top(db: Session, size: int) -> list[Product]:
    return (
        active_products(db)
        .order_by(Product.is_best_seller.desc(), Product.sold_count.desc(), Product.id.asc())
        .limit(size)
        .all()
    )


def faq_top3(db: Session, category: int) -> list[Faq]:
    return (
        db.query(Faq)
        .filter(Faq.category == category, Faq.active == 1)
        .order_by(Faq.sort_order.asc(), Faq.id.asc())
        .limit(3)
        .all()
    )


def order_by_no(db: Session, order_no: str) -> Order | None:
    return db.query(Order).filter(Order.order_no == order_no).first()


def shipments_asc(db: Session, order_id: int) -> list[Shipment]:
    return db.query(Shipment).filter(Shipment.order_id == order_id).order_by(Shipment.id.asc()).all()


def active_codes(db: Session, now) -> list[DiscountCode]:
    return (
        db.query(DiscountCode)
        .filter(
            DiscountCode.is_active == 1,
            DiscountCode.starts_at <= now,
            or_(DiscountCode.ends_at.is_(None), DiscountCode.ends_at > now),
        )
        .order_by(DiscountCode.id.asc())
        .all()
    )
