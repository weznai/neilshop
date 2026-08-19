"""营销域服务 —— 折扣码校验/礼品卡/弹窗业务 + 后台折扣码/弹窗/站点设置管理"""

import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import (
    AdminLog, DiscountCode, GiftCard, Order, OrderItem, OrderTimeline,
    PopupConfig, Setting, User,
)
from app.domains.promo import repository as repo
from app.domains.promo.schemas import (
    DiscountCreateIn, DiscountUpdateIn, GiftcardIn, GiftcardPurchaseIn,
    PopupCreateIn, PopupUpdateIn, SettingIn, ValidateIn, REASON_TEXT,
)
from app.services import promo_rules

_GIFT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def log_admin(db: Session, admin: User, action: str, entity: str, entity_id: int, diff: dict | None = None):
    db.add(AdminLog(
        admin_id=admin.id,
        action=action,
        entity=entity,
        entity_id=int(entity_id or 0),
        diff_json=diff,
    ))


# ===== 用户侧 =====


def validate_code(db: Session, body: ValidateIn) -> dict:
    valid, discount_cents, free_shipping, reason = promo_rules.validate_code(
        db, body.code, body.subtotal_cents, email=body.email
    )
    return {
        "valid": valid,
        "discount_cents": discount_cents,
        "free_shipping": free_shipping,
        "reason": REASON_TEXT.get(reason, reason),
    }


def check_giftcard(db: Session, body: GiftcardIn) -> dict:
    code = (body.code or "").strip().upper()
    card = repo.giftcard_by_code(db, code)
    if not card or card.status != 1:
        raise HTTPException(status_code=404, detail="invalid_card")
    return {"balance_cents": card.balance, "status": card.status, "expires_at": card.expires_at}


def active_popup(db: Session, scene: str) -> PopupConfig | None:
    return repo.active_popup_for_scene(db, scene, utcnow())


def popup_payload(popup: PopupConfig) -> dict:
    return {
        "id": popup.id,
        "scene": popup.scene,
        "title": popup.title,
        "content_md": popup.content_md,
        "coupon_code": popup.coupon_code,
        "trigger_rules": popup.trigger_rules,
        "start_at": popup.start_at,
        "end_at": popup.end_at,
    }


def purchase_giftcard(db: Session, body: GiftcardPurchaseIn) -> dict:
    for _ in range(5):
        code = "GC-" + "-".join(
            "".join(secrets.choice(_GIFT_ALPHABET) for _ in range(4))
            for _ in range(3)
        )
        if not repo.giftcard_id_by_code(db, code):
            break
    else:
        raise HTTPException(status_code=500, detail="code collision")

    now = utcnow()
    order = Order(
        order_no="NS" + now.strftime("%y%m%d") + uuid.uuid4().hex[:6].upper(),
        email=body.purchaser_email, status=0, subtotal=body.amount_cents,
        grand_total=body.amount_cents,
        shipping_address={"full_name": "Gift Card", "line1": "-",
                          "city": "-", "zip": "-", "country": "US"},
        note=f"giftcard:{code}", source="web",
    )
    db.add(order)
    db.flush()
    db.add(OrderItem(
        order_id=order.id, variant_id=0, product_slug="gift-card",
        title_snapshot=f"Gift Card ${body.amount_cents / 100:.2f}",
        image="", qty=1, unit_price=body.amount_cents, subtotal=body.amount_cents,
    ))
    card = GiftCard(
        code=code, initial_amount=body.amount_cents, balance=body.amount_cents,
        status=0, purchaser_email=body.purchaser_email,
        purchaser_order_id=order.id, recipient_email=body.recipient_email,
    )
    db.add(card)
    db.flush()
    db.add(OrderTimeline(
        order_id=order.id, event="giftcard_created", actor="user",
        detail={"code": code, "amount": body.amount_cents,
                "recipient": body.recipient_email, "message": body.message},
    ))
    db.commit()
    return {
        "code": card.code, "order_no": order.order_no,
        "amount_cents": body.amount_cents, "status": card.status,
    }


# ===== 后台：折扣码 =====


def _discount_dict(d: DiscountCode) -> dict:
    return {
        "id": d.id,
        "code": d.code,
        "name": d.name,
        "type": d.type,
        "value": d.value,
        "min_subtotal": d.min_subtotal,
        "max_discount": d.max_discount,
        "usage_limit": d.usage_limit,
        "per_user_limit": d.per_user_limit,
        "first_order_only": d.first_order_only,
        "used_count": d.used_count,
        "starts_at": d.starts_at,
        "ends_at": d.ends_at,
        "is_active": d.is_active,
    }


def list_discounts(db: Session, page: int, size: int) -> dict:
    rows, total = repo.page(repo.discounts_newest_first(db), page, size)
    return {"items": [_discount_dict(d) for d in rows], "total": total, "page": page, "size": size}


def create_discount(db: Session, admin: User, body: DiscountCreateIn) -> dict:
    code = body.code.strip().upper()
    if repo.discount_id_by_code(db, code):
        raise HTTPException(status_code=409, detail="code exists")
    dc = DiscountCode(
        code=code,
        type=body.type,
        value=body.value,
        min_subtotal=body.min_subtotal,
        max_discount=body.max_discount,
        usage_limit=body.usage_limit,
        per_user_limit=body.per_user_limit,
        first_order_only=body.first_order_only,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        is_active=1,
    )
    db.add(dc)
    db.flush()
    log_admin(db, admin, "create", "discount", dc.id, {"code": code, "type": body.type, "value": body.value})
    db.commit()
    db.refresh(dc)
    return _discount_dict(dc)


def update_discount(db: Session, admin: User, discount_id: int, body: DiscountUpdateIn) -> dict:
    dc = db.get(DiscountCode, discount_id)
    if not dc:
        raise HTTPException(status_code=404, detail="discount not found")
    data = body.model_dump(exclude_unset=True)
    if "code" in data:
        data["code"] = data["code"].strip().upper()
        if repo.discount_id_by_code_excluding(db, data["code"], dc.id):
            raise HTTPException(status_code=409, detail="code exists")
    for k, v in data.items():
        setattr(dc, k, v)
    log_admin(db, admin, "update", "discount", dc.id, data)
    db.commit()
    db.refresh(dc)
    return _discount_dict(dc)


def toggle_discount(db: Session, admin: User, discount_id: int) -> dict:
    dc = db.get(DiscountCode, discount_id)
    if not dc:
        raise HTTPException(status_code=404, detail="discount not found")
    dc.is_active = 0 if dc.is_active else 1
    log_admin(db, admin, "toggle", "discount", dc.id, {"is_active": dc.is_active})
    db.commit()
    db.refresh(dc)
    return _discount_dict(dc)


# ===== 后台：弹窗 =====


def _popup_dict(p: PopupConfig) -> dict:
    return {
        "id": p.id,
        "scene": p.scene,
        "title": p.title,
        "content_md": p.content_md,
        "coupon_code": p.coupon_code,
        "trigger_rules": p.trigger_rules,
        "start_at": p.start_at,
        "end_at": p.end_at,
        "active": p.active,
        "stats_shown": p.stats_shown,
        "stats_converted": p.stats_converted,
    }


def list_popups(db: Session) -> dict:
    rows = repo.popups_newest_first(db)
    return {"items": [_popup_dict(p) for p in rows]}


def create_popup(db: Session, admin: User, body: PopupCreateIn) -> dict:
    p = PopupConfig(
        scene=body.scene,
        title=body.title,
        content_md=body.content_md,
        coupon_code=body.coupon_code,
        trigger_rules=body.trigger_rules,
        start_at=body.start_at,
        end_at=body.end_at,
        active=body.active,
    )
    db.add(p)
    db.flush()
    log_admin(db, admin, "create", "popup", p.id, {"scene": body.scene, "active": body.active})
    db.commit()
    db.refresh(p)
    return _popup_dict(p)


def update_popup(db: Session, admin: User, popup_id: int, body: PopupUpdateIn) -> dict:
    p = db.get(PopupConfig, popup_id)
    if not p:
        raise HTTPException(status_code=404, detail="popup not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    log_admin(db, admin, "update", "popup", p.id, data)
    db.commit()
    db.refresh(p)
    return _popup_dict(p)


def toggle_popup(db: Session, admin: User, popup_id: int) -> dict:
    p = db.get(PopupConfig, popup_id)
    if not p:
        raise HTTPException(status_code=404, detail="popup not found")
    p.active = 0 if p.active else 1
    log_admin(db, admin, "toggle", "popup", p.id, {"active": p.active, "stats_kept": True})
    db.commit()
    db.refresh(p)
    return _popup_dict(p)


# ===== 后台：站点设置 =====


def list_settings(db: Session) -> dict:
    rows = repo.settings_by_key(db)
    return {
        "items": [
            {
                "key": s.key,
                "value": s.value,
                "description": s.description,
                "updated_by": s.updated_by,
                "updated_at": s.updated_at,
            }
            for s in rows
        ]
    }


def upsert_setting(db: Session, admin: User, body: SettingIn) -> dict:
    s = db.get(Setting, body.key)
    if s:
        old = s.value
        s.value = body.value
        s.updated_by = admin.id
    else:
        s = Setting(key=body.key, value=body.value, updated_by=admin.id)
        db.add(s)
        old = None
    log_admin(db, admin, "upsert", "setting", 0, {"key": body.key, "old": old, "new": body.value})
    db.commit()
    return {"key": s.key, "value": s.value, "updated_by": s.updated_by}


# ===== 后台：邮件模板运营预览（emails.py 只读渲染 · 固定示例数据）=====

# 每模板固定示例数据（运营预览用，与真实发送无关；subject 文案取自
# worker._EVENT_EMAILS/_ABANDON_SUBJECTS、service_account.password_reset_request、worker.daily_digest）
_EMAIL_COMMON = {
    "email": "emma@glowmag.com",
    "order_no": "NS260728D4E5F6",
}

_EMAIL_SAMPLES = (
    (
        "daily_digest",
        "GLOWMAG Daily Digest — 2026-07-27",
        {
            **_EMAIL_COMMON,
            "date": "2026-07-27",
            "gmv": 266900, "orders": 18, "paid_count": 14,
            "refund_count": 1, "refund_amount": 3110,
            "new_users": 9, "abandoned_new": 6,
            "todos": [
                {"name": "Pending orders", "count": 2},
                {"name": "RMA to review", "count": 1},
                {"name": "Open tickets", "count": 3},
            ],
            "top_products": [
                {"title": "Bare Gems", "qty": 6},
                {"title": "Winter Storm", "qty": 4},
                {"title": "Venus Cat-Eye Lashes", "qty": 3},
            ],
            "low_stock_count": 3,
        },
    ),
    (
        "order_paid",
        "Order NS260728D4E5F6 confirmed - thank you!",
        {**_EMAIL_COMMON, "grand_total": 3110},
    ),
    (
        "order_shipped",
        "Your order NS260728D4E5F6 has shipped!",
        {**_EMAIL_COMMON, "carrier": "usps", "tracking_no": "9400111899223197428490"},
    ),
    (
        "order_refunded",
        "Refund confirmed for order NS260728D4E5F6",
        {**_EMAIL_COMMON, "amount": 3110, "reason": "size not right"},
    ),
    (
        "abandoned_cart",
        "15% off your favorites",
        {
            **_EMAIL_COMMON,
            "stage": 2,
            "items": [{"title": "Bare Gems · Short Almond", "qty": 1, "stock": 120}],
            "coupon_code": "ABANDON15",
            "recovery_link": "https://glowmag.example/cart?recover=rt-demo-token",
        },
    ),
    (
        "welcome_coupon",
        "Welcome to GLOWMAG - 10% off inside",
        {**_EMAIL_COMMON, "discount": 10, "code": "WELCOME20"},
    ),
    (
        "restock_notify",
        "Back in stock: Bare Gems",
        {**_EMAIL_COMMON, "product_title": "Bare Gems", "variant": "Short Almond"},
    ),
    (
        "password_reset",
        "Reset your GLOWMAG password",
        {**_EMAIL_COMMON,
         "reset_link": "https://glowmag.example/reset-password?token=demo-reset-token"},
    ),
)


def email_template_previews() -> dict:
    """8 个自动化邮件模板逐个用固定示例数据渲染（只读 emails.py，不落库不发送）"""
    from app.services import emails

    return {
        "items": [
            {"name": name, "subject": subject, "html": emails.render(name, **ctx)}
            for name, subject, ctx in _EMAIL_SAMPLES
        ]
    }
