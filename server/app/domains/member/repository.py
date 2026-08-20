"""会员域 repository —— 纯数据访问（用户/地址/心愿单/邮件偏好/积分流水/推荐/订阅）。

纪律：不引入 HTTP 框架、不抛 HTTP 异常；只做查询与 ORM 写入原语，事务提交由 service 负责。
"""

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    CookieConsent, EmailPreference, NewsletterSubscriber, OrderTimeline,
    PointsLedger, Product, Referral, Subscription, User, UserAddress, Variant,
    WishlistItem,
)


# ---------- 用户 ----------

def user_email_taken(db: Session, email: str) -> bool:
    return db.query(User.id).filter(User.email == email).first() is not None


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def add_user(db: Session, *, email: str, password_hash: str, name: str) -> User:
    user = User(email=email, password_hash=password_hash, name=name)
    db.add(user)
    return user


# ---------- 地址簿 ----------

def list_addresses(db: Session, user_id: int) -> list[UserAddress]:
    return (
        db.query(UserAddress)
        .filter(UserAddress.user_id == user_id)
        .order_by(UserAddress.is_default.desc(), UserAddress.id.asc())
        .all()
    )


def get_address(db: Session, user_id: int, address_id: int) -> UserAddress | None:
    return (
        db.query(UserAddress)
        .filter(UserAddress.id == address_id, UserAddress.user_id == user_id)
        .first()
    )


def clear_other_default_addresses(db: Session, user_id: int, keep_id: int) -> None:
    db.query(UserAddress).filter(
        UserAddress.user_id == user_id,
        UserAddress.is_default == 1,
        UserAddress.id != keep_id,
    ).update({"is_default": 0})


# ---------- 心愿单 ----------

def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def wishlist_products(db: Session, user_id: int) -> list[Product]:
    return (
        db.query(Product)
        .join(WishlistItem, WishlistItem.product_id == Product.id)
        .filter(WishlistItem.user_id == user_id)
        .order_by(WishlistItem.created_at.desc(), Product.id.desc())
        .all()
    )


def active_variants_by_product(db: Session, pids: list[int]) -> dict[int, list]:
    vmap: dict[int, list] = {}
    if not pids:
        return vmap
    for v in db.query(Variant).filter(
        Variant.product_id.in_(pids), Variant.is_active == 1
    ).all():
        vmap.setdefault(v.product_id, []).append(v)
    return vmap


def get_wishlist_item(db: Session, user_id: int, product_id: int) -> WishlistItem | None:
    return db.get(WishlistItem, (user_id, product_id))


def add_wishlist_item(db: Session, user_id: int, product_id: int) -> None:
    db.add(WishlistItem(user_id=user_id, product_id=product_id))


# ---------- 邮件订阅 / 隐私 ----------

def get_newsletter_subscriber(db: Session, email: str) -> NewsletterSubscriber | None:
    return db.get(NewsletterSubscriber, email)


def add_newsletter_subscriber(db: Session, *, email: str, source: str) -> None:
    db.add(NewsletterSubscriber(email=email, source=source))


def get_email_preference(db: Session, email: str) -> EmailPreference | None:
    return db.get(EmailPreference, email)


def add_email_preference(db: Session, pref: EmailPreference) -> None:
    db.add(pref)


def add_cookie_consent(db: Session, consent: CookieConsent) -> None:
    db.add(consent)


# ---------- 积分流水 ----------

def ledger_page(db: Session, user_id: int, offset: int, limit: int) -> tuple[int, list]:
    q = (
        db.query(PointsLedger)
        .filter(PointsLedger.user_id == user_id)
        .order_by(PointsLedger.id.desc())
    )
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return total, rows


def expiring_ledger_rows(db: Session, user_id: int, now) -> list:
    return (
        db.query(PointsLedger)
        .filter(
            PointsLedger.user_id == user_id,
            PointsLedger.change > 0,
            PointsLedger.frozen == 0,
            PointsLedger.expires_at.isnot(None),
            PointsLedger.expires_at > now,
            PointsLedger.expires_at <= now + timedelta(days=30),
        )
        .order_by(PointsLedger.expires_at.asc())
        .all()
    )


def referral_points_earned(db: Session, user_id: int, reason: int) -> int:
    earned = (
        db.query(func.coalesce(func.sum(PointsLedger.change), 0))
        .filter(
            PointsLedger.user_id == user_id,
            PointsLedger.reason == reason,
        )
        .scalar()
    )
    return int(earned or 0)


def add_points_ledger(db: Session, entry: PointsLedger) -> None:
    db.add(entry)


# ---------- 推荐 ----------

def referrals_by_referrer(db: Session, user_id: int) -> list[Referral]:
    return (
        db.query(Referral)
        .filter(Referral.referrer_user_id == user_id)
        .order_by(Referral.id.desc())
        .all()
    )


def find_referral(db: Session, code: str, invited_email: str) -> Referral | None:
    return (
        db.query(Referral)
        .filter(Referral.code == code, Referral.invited_email == invited_email)
        .first()
    )


def user_id_by_email(db: Session, email: str) -> int | None:
    row = db.query(User.id).filter(User.email == email).first()
    return row[0] if row else None


def all_user_ids(db: Session) -> list[int]:
    """推荐码反查用：derive_code 为 user_id 确定性派生（无存储列），
    单查全量 id 后内存匹配（注册低频端点，MVP 规模可接受）。"""
    return [r[0] for r in db.query(User.id).all()]


def add_referral(db: Session, referral: Referral) -> None:
    db.add(referral)


def pending_referrals_for_email(db: Session, email: str) -> list[Referral]:
    return (
        db.query(Referral)
        .filter(Referral.invited_email == email, Referral.status < 3)
        .all()
    )


def add_order_timeline(db: Session, entry: OrderTimeline) -> None:
    db.add(entry)


# ---------- 订阅 ----------

def list_subscriptions(db: Session, user_id: int) -> list[Subscription]:
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.id.desc())
        .all()
    )


def get_subscription(db: Session, user_id: int, sub_id: int) -> Subscription | None:
    return (
        db.query(Subscription)
        .filter(Subscription.id == sub_id, Subscription.user_id == user_id)
        .first()
    )


def add_subscription(db: Session, sub: Subscription) -> None:
    db.add(sub)


__all__ = [
    "user_email_taken", "get_user_by_email", "add_user",
    "list_addresses", "get_address", "clear_other_default_addresses",
    "get_product", "wishlist_products", "active_variants_by_product",
    "get_wishlist_item", "add_wishlist_item",
    "get_newsletter_subscriber", "add_newsletter_subscriber",
    "get_email_preference", "add_email_preference", "add_cookie_consent",
    "ledger_page", "expiring_ledger_rows", "referral_points_earned",
    "add_points_ledger", "referrals_by_referrer", "find_referral",
    "user_id_by_email", "all_user_ids", "add_referral",
    "pending_referrals_for_email",
    "add_order_timeline", "list_subscriptions", "get_subscription",
    "add_subscription",
]
