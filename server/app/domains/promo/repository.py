"""营销域仓储 —— 纯查询/分页，不掺业务规则"""

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models import DiscountCode, GiftCard, PopupConfig, Setting


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


def settings_by_key(db: Session) -> list[Setting]:
    return db.query(Setting).order_by(Setting.key).all()
