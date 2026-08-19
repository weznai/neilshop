"""账户服务：注册/登录/资料/地址簿/心愿单/邮件订阅/隐私/退订（HMAC）/密码重置。

业务与事务边界（commit/refresh 在此）；数据访问走 repository；
沿用原有 HTTPException 语义（状态码/detail 逐字保留）。
"""

import hashlib
import hmac
import time
from datetime import timedelta

import jwt as pyjwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.security import create_token, hash_password, verify_password
from app.models import (
    CookieConsent, DataRequest, EmailPreference, Order, OrderItem, PointsLedger,
    Referral, Review, Setting, Subscription, Ticket, TicketMessage, User,
    UserAddress,
)
from app.services.emails import deliver, render

from app.domains.member import repository as repo
from app.domains.member.schemas import (
    AddressIn, ConsentIn, EmailPreferencesUpdateIn, LoginIn, NewsletterIn,
    PasswordResetConfirmIn, PasswordResetRequestIn, ProfileUpdateIn, RegisterIn,
    UnsubscribeIn,
)

def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "points": u.points,
        "tier": u.tier,
        "total_spent": u.total_spent,
        "birthday": u.birthday,
        "created_at": u.created_at,
    }


def _stock_summary(variants: list) -> dict:
    return {
        "total": sum(v.stock for v in variants),
        "low": sum(1 for v in variants if v.stock <= v.safety_stock),
        "out": any(v.stock <= 0 for v in variants),
    }


def _wish_card(p, variants: list) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "price_min": p.price_min,
        "price_max": p.price_max,
        "compare_at_price": p.compare_at_price,
        "hero_image": p.hero_image,
        "rating": p.rating_avg,
        "stock_summary": _stock_summary(variants),
    }


def _addr_out(a) -> dict:
    return {
        "id": a.id,
        "full_name": a.full_name,
        "line1": a.line1,
        "line2": a.line2,
        "city": a.city,
        "state": a.state,
        "zip": a.zip,
        "country": a.country,
        "phone": a.phone,
        "is_default": bool(a.is_default),
    }


def register(db: Session, body: RegisterIn) -> dict:
    if repo.user_email_taken(db, body.email):
        raise HTTPException(status_code=409, detail="email already registered")
    user = repo.add_user(
        db, email=body.email, password_hash=hash_password(body.password), name=body.name
    )
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id, user.role), "user": _user_out(user)}


def login(db: Session, body: LoginIn, admin: bool = False) -> dict:
    """登录（admin=True 为后台专用入口：仅 role>=2 可登录，签发短时效 token）。"""
    user = repo.get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if user.status != 1:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if admin and user.role < 2:
        raise HTTPException(status_code=403, detail="admin only")
    user.last_login_at = utcnow()
    db.commit()
    token = create_token(user.id, user.role, hours=settings.admin_token_hours) if admin \
        else create_token(user.id, user.role)
    return {"token": token, "user": _user_out(user)}


def profile(user: User) -> dict:
    return _user_out(user)


def update_profile(db: Session, user: User, body: ProfileUpdateIn) -> dict:
    if body.name is not None:
        user.name = body.name
    if body.birthday is not None:
        user.birthday = body.birthday
    db.commit()
    return _user_out(user)


# ---------- 地址簿 ----------

def list_addresses(db: Session, user: User) -> list[dict]:
    return [_addr_out(a) for a in repo.list_addresses(db, user.id)]


def create_address(db: Session, user: User, body: AddressIn) -> dict:
    addr = UserAddress(
        user_id=user.id,
        full_name=body.full_name,
        line1=body.line1,
        line2=body.line2,
        city=body.city,
        state=body.state,
        zip=body.zip,
        country=body.country,
        phone=body.phone,
        is_default=1 if body.is_default else 0,
    )
    db.add(addr)
    db.flush()
    if body.is_default:
        repo.clear_other_default_addresses(db, user.id, addr.id)
    db.commit()
    db.refresh(addr)
    return _addr_out(addr)


def update_address(db: Session, user: User, address_id: int, body: AddressIn) -> dict:
    addr = repo.get_address(db, user.id, address_id)
    if not addr:
        raise HTTPException(status_code=404, detail="address not found")
    addr.full_name = body.full_name
    addr.line1 = body.line1
    addr.line2 = body.line2
    addr.city = body.city
    addr.state = body.state
    addr.zip = body.zip
    addr.country = body.country
    addr.phone = body.phone
    addr.is_default = 1 if body.is_default else 0
    if body.is_default:
        repo.clear_other_default_addresses(db, user.id, addr.id)
    db.commit()
    return _addr_out(addr)


def delete_address(db: Session, user: User, address_id: int) -> dict:
    addr = repo.get_address(db, user.id, address_id)
    if not addr:
        raise HTTPException(status_code=404, detail="address not found")
    db.delete(addr)
    db.commit()
    return {"ok": True}


# ---------- 心愿单 ----------

def wishlist(db: Session, user: User) -> list[dict]:
    prods = repo.wishlist_products(db, user.id)
    vmap = repo.active_variants_by_product(db, [p.id for p in prods])
    return [_wish_card(p, vmap.get(p.id, [])) for p in prods]


def add_to_wishlist(db: Session, user: User, product_id: int) -> tuple[dict, bool]:
    if not repo.get_product(db, product_id):
        raise HTTPException(status_code=404, detail="product not found")
    if repo.get_wishlist_item(db, user.id, product_id):
        return {"ok": True, "product_id": product_id}, False
    repo.add_wishlist_item(db, user.id, product_id)
    db.commit()
    return {"ok": True, "product_id": product_id}, True


def remove_from_wishlist(db: Session, user: User, product_id: int) -> dict:
    row = repo.get_wishlist_item(db, user.id, product_id)
    if not row:
        raise HTTPException(status_code=404, detail="wishlist item not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------- 邮件订阅 / 隐私 ----------

def newsletter(db: Session, user: User | None, body: NewsletterIn) -> dict:
    sub = repo.get_newsletter_subscriber(db, body.email)
    if sub:
        sub.source = body.source
    else:
        repo.add_newsletter_subscriber(db, email=body.email, source=body.source)
    pref = repo.get_email_preference(db, body.email)
    if pref:
        pref.user_id = user.id if user else pref.user_id
        pref.source = body.source
        pref.sub_promo = 1
        pref.sub_new_arrival = 1
        pref.sub_cart_abandon = 1
        pref.unsubscribed_at = None
    else:
        repo.add_email_preference(db, EmailPreference(
            email=body.email,
            user_id=user.id if user else None,
            source=body.source,
            sub_promo=1,
            sub_new_arrival=1,
            sub_cart_abandon=1,
        ))
    db.commit()
    return {"ok": True, "email": body.email}


def consent(db: Session, user: User | None, body: ConsentIn) -> dict:
    repo.add_cookie_consent(db, CookieConsent(
        session_id=body.session_id,
        user_id=user.id if user else None,
        necessary=1 if body.necessary else 0,
        analytics=1 if body.analytics else 0,
        marketing=1 if body.marketing else 0,
        region=body.region,
    ))
    db.commit()
    return {"ok": True}


# ---------- 退订（HMAC token） ----------

def _unsubscribe_token(email: str) -> str:
    digest = hmac.new(
        settings.jwt_secret.encode(), email.lower().encode(), hashlib.sha256
    ).hexdigest()
    return "us_" + digest[:16]


def unsubscribe(db: Session, user: User | None, body: UnsubscribeIn) -> dict:
    expected = _unsubscribe_token(body.email)
    if body.token is not None:
        if not hmac.compare_digest(body.token, expected):
            raise HTTPException(status_code=400, detail="invalid_token")
    elif not (user and user.email.lower() == body.email.lower()):
        raise HTTPException(status_code=400, detail="token_required")
    now = utcnow()
    pref = repo.get_email_preference(db, body.email)
    if pref:
        pref.sub_promo = 0
        pref.sub_new_arrival = 0
        pref.sub_cart_abandon = 0
        pref.unsubscribed_at = now
    else:
        repo.add_email_preference(db, EmailPreference(
            email=body.email,
            sub_promo=0, sub_new_arrival=0, sub_cart_abandon=0,
            unsubscribed_at=now, source="unsubscribe",
        ))
    db.commit()
    return {"ok": True}


# ---------- 密码重置 ----------

def password_reset_request(db: Session, body: PasswordResetRequestIn) -> dict:
    user = repo.get_user_by_email(db, body.email)
    if user:
        now = int(time.time())
        token = pyjwt.encode(
            {"sub": str(user.id), "purpose": "pwreset", "iat": now, "exp": now + 900},
            settings.jwt_secret, algorithm="HS256",
        )
        deliver(
            body.email, "Reset your GLOWMAG password",
            render("password_reset", email=body.email,
                   reset_link=f"https://glowmag.example/reset-password?token={token}"),
        )
    return {"ok": True}


def password_reset_confirm(db: Session, body: PasswordResetConfirmIn) -> dict:
    try:
        payload = pyjwt.decode(body.token, settings.jwt_secret, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=400, detail="invalid_token")
    if payload.get("purpose") != "pwreset":
        raise HTTPException(status_code=400, detail="invalid_token")
    user = repo.get_user_by_email(db, body.email)
    if not user or payload.get("sub") != str(user.id):
        raise HTTPException(status_code=400, detail="invalid_token")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


# ---------- GDPR：数据导出 / 删除请求 ----------

def _gdpr_delay_days(db: Session) -> int:
    row = db.get(Setting, "gdpr_delete_delay_days")
    if row is not None and row.value is not None:
        try:
            return int(row.value)
        except (TypeError, ValueError):
            pass
    return 7


def export_my_data(db: Session, user: User) -> dict:
    orders = []
    for o in (
        db.query(Order).filter(Order.user_id == user.id).order_by(Order.id.asc()).all()
    ):
        orders.append({
            "order_no": o.order_no,
            "status": o.status,
            "currency": o.currency,
            "subtotal": o.subtotal,
            "discount_total": o.discount_total,
            "points_discount": o.points_discount,
            "giftcard_discount": o.giftcard_discount,
            "shipping_fee": o.shipping_fee,
            "tax": o.tax,
            "grand_total": o.grand_total,
            "shipping_address": o.shipping_address,
            "placed_at": o.placed_at,
            "paid_at": o.paid_at,
            "items": [
                {
                    "variant_id": i.variant_id,
                    "product_slug": i.product_slug,
                    "title": i.title_snapshot,
                    "qty": i.qty,
                    "unit_price": i.unit_price,
                    "subtotal": i.subtotal,
                }
                for i in db.query(OrderItem)
                .filter(OrderItem.order_id == o.id).order_by(OrderItem.id.asc()).all()
            ],
        })
    tickets = []
    for t in db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.id.asc()).all():
        tickets.append({
            "ticket_no": t.ticket_no,
            "subject": t.subject,
            "category": t.category,
            "status": t.status,
            "order_no": t.order_no,
            "created_at": t.created_at,
            "messages": [
                {"sender": m.sender, "content": m.content, "created_at": m.created_at}
                for m in db.query(TicketMessage)
                .filter(TicketMessage.ticket_id == t.id).order_by(TicketMessage.id.asc()).all()
            ],
        })
    data = {
        "profile": _user_out(user),
        "addresses": [_addr_out(a) for a in repo.list_addresses(db, user.id)],
        "orders": orders,
        "points_ledger": [
            {
                "id": r.id, "change": r.change, "balance_after": r.balance_after,
                "reason": r.reason, "ref_type": r.ref_type, "ref_id": r.ref_id,
                "frozen": r.frozen, "expires_at": r.expires_at, "created_at": r.created_at,
            }
            for r in db.query(PointsLedger).filter(PointsLedger.user_id == user.id)
            .order_by(PointsLedger.id.asc()).all()
        ],
        "reviews": [
            {
                "id": r.id, "product_id": r.product_id, "rating": r.rating,
                "content": r.content, "status": r.status, "created_at": r.created_at,
            }
            for r in db.query(Review).filter(Review.user_id == user.id)
            .order_by(Review.id.asc()).all()
        ],
        "tickets": tickets,
        "subscriptions": [
            {
                "id": sub.id, "plan": sub.plan, "style_mode": sub.style_mode,
                "status": sub.status, "next_billing_at": sub.next_billing_at,
                "created_at": sub.created_at,
            }
            for sub in repo.list_subscriptions(db, user.id)
        ],
        "referrals": {
            "referrer": [
                {
                    "id": r.id, "code": r.code, "invited_email": r.invited_email,
                    "status": r.status, "reward_referrer": r.reward_referrer,
                    "created_at": r.created_at,
                }
                for r in repo.referrals_by_referrer(db, user.id)
            ],
            "invited": [
                {
                    "id": r.id, "code": r.code, "status": r.status,
                    "reward_invitee": r.reward_invitee, "created_at": r.created_at,
                }
                for r in db.query(Referral).filter(Referral.invited_email == user.email)
                .order_by(Referral.id.asc()).all()
            ],
        },
        "cookie_consents": [
            {
                "id": c.id, "session_id": c.session_id, "necessary": c.necessary,
                "analytics": c.analytics, "marketing": c.marketing,
                "region": c.region, "created_at": c.created_at,
            }
            for c in db.query(CookieConsent).filter(CookieConsent.user_id == user.id)
            .order_by(CookieConsent.id.asc()).all()
        ],
    }
    db.add(DataRequest(user_id=user.id, type=1, status=1, fulfilled_at=utcnow()))
    db.commit()
    return data


def request_delete(db: Session, user: User) -> dict:
    pending = (
        db.query(DataRequest)
        .filter(DataRequest.user_id == user.id, DataRequest.type == 2,
                DataRequest.status == 0)
        .first()
    )
    if pending:
        raise HTTPException(status_code=409, detail="delete request already pending")
    req = DataRequest(user_id=user.id, type=2, status=0)
    db.add(req)
    db.flush()
    effective_at = req.created_at + timedelta(days=_gdpr_delay_days(db))
    db.commit()
    return {"request_id": req.id, "effective_at": effective_at}


def cancel_delete(db: Session, user: User) -> dict:
    db.query(DataRequest).filter(
        DataRequest.user_id == user.id, DataRequest.type == 2, DataRequest.status == 0
    ).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}


# ---------- 邮件偏好中心（细粒度退订 / 复订） ----------

def _pref_out(email: str, pref: EmailPreference | None) -> dict:
    if pref is None:
        return {
            "email": email,
            "sub_promo": 1,
            "sub_new_arrival": 1,
            "sub_cart_abandon": 1,
            "unsubscribed_at": None,
        }
    return {
        "email": pref.email,
        "sub_promo": pref.sub_promo,
        "sub_new_arrival": pref.sub_new_arrival,
        "sub_cart_abandon": pref.sub_cart_abandon,
        "unsubscribed_at": (
            pref.unsubscribed_at.isoformat() if pref.unsubscribed_at else None
        ),
    }


def _pref_target_email(user: User | None, email: str | None, token: str | None) -> str:
    """鉴权与目标邮箱解析：登录用户 → 自身邮箱；否则 ?email=&token=（us_ HMAC）。
    未登录且无 email → 401；email 给出但 token 缺失/错误 → 400。"""
    if user is not None:
        return user.email
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not token or not hmac.compare_digest(token, _unsubscribe_token(email)):
        raise HTTPException(status_code=400, detail="invalid_token")
    return email


def get_email_preferences(
    db: Session, user: User | None, email: str | None, token: str | None
) -> dict:
    target = _pref_target_email(user, email, token)
    return _pref_out(target, repo.get_email_preference(db, target))


def update_email_preferences(
    db: Session, user: User | None, body: EmailPreferencesUpdateIn,
    email: str | None, token: str | None,
) -> dict:
    target = _pref_target_email(user, email, token)
    pref = repo.get_email_preference(db, target)
    if pref is None:
        pref = EmailPreference(
            email=target,
            user_id=user.id if user else None,
            source="preference_center",
        )
        repo.add_email_preference(db, pref)
    if body.sub_promo is not None:
        pref.sub_promo = 1 if body.sub_promo else 0
    if body.sub_new_arrival is not None:
        pref.sub_new_arrival = 1 if body.sub_new_arrival else 0
    if body.sub_cart_abandon is not None:
        pref.sub_cart_abandon = 1 if body.sub_cart_abandon else 0
    # 任一开关为 1 → 清 unsubscribed_at（复订）；三开关全 0 → 置 now（等价全退）
    switches = [v if v is not None else 1 for v in
                (pref.sub_promo, pref.sub_new_arrival, pref.sub_cart_abandon)]
    pref.unsubscribed_at = None if any(switches) else utcnow()
    db.commit()
    db.refresh(pref)
    return _pref_out(target, pref)
