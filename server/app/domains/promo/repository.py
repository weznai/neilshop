"""营销域仓储 —— 纯查询/分页，不掺业务规则"""

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models import (
    DiscountCode, DiscountRedemption, GiftCard, GiftCardLedger, Order,
    PopupConfig, Setting,
)


def page(q: Query, page: int, size: int):
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return rows, total


def discounts_newest_first(db: Session) -> Query:
    return db.query(DiscountCode).order_by(DiscountCode.id.desc())


def discount_id_by_code(db: Session, code: str):
    return db.query(DiscountCode.id).filter(DiscountCode.code == code).first()


def discount_id_by_code_excluding(db: Session, code: str, exclude_id: int):
    return (
        db.query(DiscountCode.id)
        .filter(DiscountCode.code == code, DiscountCode.id != exclude_id)
        .first()
    )


def popups_newest_first(db: Session) -> list[PopupConfig]:
    return db.query(PopupConfig).order_by(PopupConfig.id.desc()).all()


def active_popup_for_scene(db: Session, scene: str, now):
    return (
        db.query(PopupConfig)
        .filter(
            PopupConfig.scene == scene,
            PopupConfig.active == 1,
            or_(PopupConfig.start_at.is_(None), PopupConfig.start_at <= now),
            or_(PopupConfig.end_at.is_(None), PopupConfig.end_at >= now),
        )
        .order_by(PopupConfig.id.desc())
        .first()
    )


def giftcard_by_code(db: Session, code: str) -> GiftCard | None:
    return db.query(GiftCard).filter(GiftCard.code == code).first()


def giftcard_id_by_code(db: Session, code: str):
    return db.query(GiftCard.id).filter(GiftCard.code == code).first()


def giftcards_filtered(db: Session, q: str | None, status: int | None) -> Query:
    """后台礼品卡列表：q 匹配 code/邮箱（ilike），status 按模型枚举直传"""
    query = db.query(GiftCard)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            GiftCard.code.ilike(like),
            GiftCard.purchaser_email.ilike(like),
            GiftCard.recipient_email.ilike(like),
        ))
    if status is not None:
        query = query.filter(GiftCard.status == status)
    return query.order_by(GiftCard.id.desc())


def giftcard_ledgers(db: Session, gift_card_id: int) -> Query:
    """礼品卡流水（outerjoin 订单号，无关联订单的行为空）"""
    return (
        db.query(GiftCardLedger, Order.order_no)
        .outerjoin(Order, Order.id == GiftCardLedger.order_id)
        .filter(GiftCardLedger.gift_card_id == gift_card_id)
        .order_by(GiftCardLedger.id.desc())
    )


def discount_usages(db: Session, code_id: int) -> Query:
    """折扣码核销记录（join 订单号，时间倒序）"""
    return (
        db.query(DiscountRedemption, Order.order_no)
        .outerjoin(Order, Order.id == DiscountRedemption.order_id)
        .filter(DiscountRedemption.code_id == code_id)
        .order_by(DiscountRedemption.created_at.desc(), DiscountRedemption.id.desc())
    )


def discount_redemption_exists(db: Session, code_id: int) -> bool:
    return (
        db.query(DiscountRedemption.id)
        .filter(DiscountRedemption.code_id == code_id)
        .first()
        is not None
    )


def settings_by_key(db: Session) -> list[Setting]:
    return db.query(Setting).order_by(Setting.key).all()
