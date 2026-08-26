"""账户服务：注册/登录/资料/地址簿/心愿单/邮件订阅/隐私/退订（HMAC）/密码重置。

业务与事务边界（commit/refresh 在此）；数据访问走 repository；
沿用原有 HTTPException 语义（状态码/detail 逐字保留）。
"""

import hashlib
import hmac
import os
import secrets
import time
from datetime import timedelta, timezone
from urllib.parse import quote

import jwt as pyjwt
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.permissions import BACKEND_ROLES, permissions_of
from app.core.security import create_token, hash_password, verify_password
from app.models import (
    Cart, CookieConsent, DataRequest, EmailPreference, Order, OrderItem,
    OutboxEvent, PointsLedger, Referral, Review, Setting, Subscription, Ticket,
    TicketMessage, User, UserAddress, WishlistItem,
)
from app.services.emails import deliver, render
from app.services import points as points_svc

from app.domains.member import repository as repo
from app.domains.member import service_referrals
from app.domains.member.schemas import (
    AddressIn, ConsentIn, EmailChangeIn, EmailChangeConfirmIn,
    EmailPreferencesUpdateIn, LoginIn, NewsletterIn, PasswordChangeIn,
    PasswordResetConfirmIn, PasswordResetRequestIn, ProfileUpdateIn,
    RegisterIn, UnsubscribeIn,
)

def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,  # 前端会话判定（后台守卫需 role≥2；role 本身非敏感）
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
        "out": sum(v.stock for v in variants) <= 0,
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
        "rating": round(p.rating_avg / 100, 2),  # 0-5 口径与 catalog 域卡片一致
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


# welcome_coupon 模板回落常量（折扣码表查不到 WELCOME20/非百分比型时使用）
_WELCOME_FALLBACK_CODE = "WELCOME20"
_WELCOME_FALLBACK_DISCOUNT = 20


def register(db: Session, body: RegisterIn) -> dict:
    email = body.email.strip().lower()
    if repo.user_email_taken(db, email):
        raise HTTPException(status_code=409, detail="email already registered")
    try:
        user = repo.add_user(
            db, email=email, password_hash=hash_password(body.password), name=body.name
        )
        db.flush()
        # 推荐绑定闭环：/register?ref= 落地页承诺的双方 1000 积分依赖此绑定记录
        # （首单支付发放逻辑在 trade 域 on_order_paid，此处只负责把邀请关系写对）
        service_referrals.bind_referral_on_register(db, body.ref_code, user)
        # 欢迎邮件走 outbox（worker 消费，营销偏好 sub_promo=0 时合规跳过并标记 published）
        # payload 供 welcome_coupon 模板渲染：discount/code 取折扣码表 WELCOME20 换算，
        # 查不到回落常量（20% / WELCOME20）
        code, discount = repo.welcome_coupon(db) or (
            _WELCOME_FALLBACK_CODE, _WELCOME_FALLBACK_DISCOUNT
        )
        db.add(OutboxEvent(
            aggregate_type="user", aggregate_id=user.id, event_type="user.welcome",
            payload={
                "user_id": user.id, "email": user.email,
                "code": code, "discount": discount,
            },
        ))
        db.commit()
    except IntegrityError:
        # 并发同 email 注册：先查后插的竞态窗口撞 users.email 唯一索引 → 统一 409 而非 500
        db.rollback()
        raise HTTPException(status_code=409, detail="email already registered")
    db.refresh(user)
    return {"token": create_token(user.id, user.role), "user": _user_out(user)}


def login(db: Session, body: LoginIn, admin: bool = False) -> dict:
    """登录（admin=True 为后台专用入口：仅后台角色（客服/运营/仓库/美甲师/超管，
    见 core/permissions.BACKEND_ROLES）可登录，签发短时效 token）。"""
    user = repo.get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    if user.status != 1:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if admin and user.role not in BACKEND_ROLES:
        raise HTTPException(status_code=403, detail="admin only")
    user.last_login_at = utcnow()
    db.commit()
    token = create_token(user.id, user.role, hours=settings.admin_token_hours) if admin \
        else create_token(user.id, user.role)
    out = _user_out(user)
    if admin:
        out["permissions"] = sorted(permissions_of(user.role))
    return {"token": token, "user": out}


def admin_profile(user: User) -> dict:
    """后台会话探测（/admin/me）：基本资料 + 实时权限集（前端路由/菜单/按钮权限判定）。"""
    out = _user_out(user)
    out["permissions"] = sorted(permissions_of(user.role))
    return out


def profile(user: User) -> dict:
    return _user_out(user)


def profile_with_delete_request(db: Session, user: User) -> dict:
    """前台 /me：附带回显进行中的注销申请（刷新后恢复冷静期状态，避免重复提交撞 409）。"""
    pending = (
        db.query(DataRequest)
        .filter(DataRequest.user_id == user.id, DataRequest.type == 2,
                DataRequest.status == 0)
        .first()
    )
    out = _user_out(user)
    out["delete_request"] = (
        {
            "request_id": pending.id,
            "effective_at": pending.created_at + timedelta(days=_gdpr_delay_days(db)),
        }
        if pending is not None else None
    )
    return out


def update_profile(db: Session, user: User, body: ProfileUpdateIn) -> dict:
    if body.name is not None:
        user.name = body.name
    if body.birthday is not None:
        user.birthday = body.birthday
    elif "birthday" in body.model_fields_set:
        # 显式传 null = 清空生日（修复前端清空后端静默忽略的假成功）
        user.birthday = None
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
    # 唯一默认防线：撤掉唯一默认地址会让地址簿无默认（下单默认收货地址失去兜底）
    if (
        addr.is_default == 1 and not body.is_default
        and not repo.has_other_default_address(db, user.id, addr.id)
    ):
        raise HTTPException(status_code=422, detail="last_default_required")
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


def wishlist_has(db: Session, user: User, product_id: int) -> dict:
    return {"in_wishlist": repo.get_wishlist_item(db, user.id, product_id) is not None}


def add_to_wishlist(db: Session, user: User, product_id: int) -> tuple[dict, bool]:
    if not repo.get_product(db, product_id):
        raise HTTPException(status_code=404, detail="product not found")
    if repo.get_wishlist_item(db, user.id, product_id):
        return {"ok": True, "product_id": product_id}, False
    repo.add_wishlist_item(db, user.id, product_id)
    try:
        db.commit()
    except IntegrityError:
        # 并发双加撞复合主键 → 幂等返回"已存在"（同 register 的 409 收敛思路，此处语义为幂等 200）
        db.rollback()
        return {"ok": True, "product_id": product_id}, False
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
    try:
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
    except IntegrityError:
        # 并发同邮箱首次订阅：check-then-insert 竞态撞唯一主键 → 回滚后重查走更新路径，
        # 幂等 200（register 同款捕获，只是此处语义为收敛而非 409）
        db.rollback()
        sub = repo.get_newsletter_subscriber(db, body.email)
        if sub:
            sub.source = body.source
        pref = repo.get_email_preference(db, body.email)
        if pref:
            pref.user_id = user.id if user else pref.user_id
            pref.source = body.source
            pref.sub_promo = 1
            pref.sub_new_arrival = 1
            pref.sub_cart_abandon = 1
            pref.unsubscribed_at = None
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
        try:
            db.commit()
        except IntegrityError:
            # 并发退订首插竞态：回滚重查走更新路径，幂等 200
            db.rollback()
            pref = repo.get_email_preference(db, body.email)
            if pref is None:
                raise
            pref.sub_promo = 0
            pref.sub_new_arrival = 0
            pref.sub_cart_abandon = 0
            pref.unsubscribed_at = now
            db.commit()
        return {"ok": True}
    db.commit()
    return {"ok": True}


# ---------- 密码重置 ----------

def _site_url(db: Session) -> str:
    """站点根地址（重置链接等外链前缀）：ops settings 表 site_url/base_url 优先，
    其次环境变量 GM_SITE_URL，最后 dev 友好默认 http://localhost:5173。"""
    for key in ("site_url", "base_url"):
        row = db.get(Setting, key)
        if row is not None and row.value:
            val = str(row.value).strip().rstrip("/")
            if val.startswith(("http://", "https://")):
                return val
    val = (os.getenv("GM_SITE_URL") or "").strip().rstrip("/")
    return val or "http://localhost:5173"


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
                   reset_link=(
                       f"{_site_url(db)}/reset-password"
                       f"?token={token}&email={quote(user.email)}"
                   )),
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
    # token 一次性：签发（iat）不晚于最近改密秒 → 视为已用/过期作废（含上次重置/改密），
    # 封死 15 分钟内重复改密窗口。取保守侧（<=）：同秒签发同秒改密的 token 一并作废，
    # 新 token 最迟下一秒即可用；不依赖"已用"标记位
    if user.pwd_changed_at is not None and int(payload.get("iat", 0)) <= int(
        user.pwd_changed_at.replace(tzinfo=timezone.utc).timestamp()
    ):
        raise HTTPException(status_code=400, detail="invalid_token")
    user.password_hash = hash_password(body.new_password)
    user.pwd_changed_at = utcnow()
    db.commit()
    return {"ok": True}


def change_password(db: Session, user: User, body: PasswordChangeIn) -> dict:
    """登录态改密：旧密校验失败 401；password_hash 为 None（GDPR 匿名/OAuth-only 用户）
    无旧密可验 → 401（走邮件重置流）。不做 token_version 主动失效旧会话 ——
    与邮件重置 password_reset_confirm 同口径（既有 token 自然过期）；
    但同样落 pwd_changed_at，使改密前签发的 pwreset token 全部作废。"""
    if user.password_hash is None or not verify_password(
        body.old_password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="invalid credentials")
    user.password_hash = hash_password(body.new_password)
    user.pwd_changed_at = utcnow()
    db.commit()
    return {"ok": True}


# ---------- 邮箱修改（双步验证） ----------

# 验证码有效期（分钟）与 dev 判定（与全站 dev 口径一致：GM_ENV=dev，见 core/config）
EMAIL_CHANGE_CODE_MINUTES = 10


def _is_dev() -> bool:
    return settings.env == "dev"


def email_change_request(db: Session, user: User, body: EmailChangeIn) -> dict:
    """第 1 步：密码二次验证 → 6 位数字码落库（旧码作废）并发往新邮箱。
    dev 环境（GM_ENV=dev）响应附 dev_code 便于联调（邮件投递为日志 MVP）。"""
    if user.password_hash is None or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="invalid_password")
    new_email = body.new_email.strip().lower()
    if new_email == user.email.strip().lower():
        raise HTTPException(status_code=400, detail="same_email")
    if repo.user_email_taken(db, new_email):
        raise HTTPException(status_code=409, detail="email_taken")
    code = f"{secrets.randbelow(1000000):06d}"
    repo.replace_email_change_request(
        db, user_id=user.id, new_email=new_email, code=code,
        expires_at=utcnow() + timedelta(minutes=EMAIL_CHANGE_CODE_MINUTES),
    )
    deliver(
        new_email, "Your GLOWMAG email change code",
        "<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:560px;"
        "margin:0 auto\"><h2 style=\"letter-spacing:3px\">GLOWMAG</h2>"
        f"<p>Hi {user.email},</p>"
        "<p>You asked to change your GLOWMAG account email to this address. "
        "Enter this code to confirm (valid for "
        f"{EMAIL_CHANGE_CODE_MINUTES} minutes):</p>"
        "<p style=\"font-size:24px;letter-spacing:4px;font-weight:bold;"
        "background:#f7f7f7;padding:14px;text-align:center\">"
        f"{code}</p>"
        "<p>Didn't ask for this? Just ignore this email &mdash; your email "
        "stays unchanged.</p>"
        "<p>Stay glowing,<br>The GLOWMAG Team</p></div>",
    )
    db.commit()
    out = {"ok": True}
    if _is_dev():
        out["dev_code"] = code
    return out


def email_change_confirm(db: Session, user: User, body: EmailChangeConfirmIn) -> dict:
    """第 2 步：校验验证码（错/过期/已用 409）→ 更新 user.email（strip+lower）。
    会话 token 基于 user id 签发（deps 只取 sub），邮箱变更无需重签 token。"""
    row = repo.latest_active_email_change_request(db, user.id)
    if row is None or not secrets.compare_digest(row.code, body.code.strip()):
        raise HTTPException(status_code=409, detail="invalid_code")
    if row.expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="expired")
    new_email = row.new_email.strip().lower()
    # 请求与确认窗口之间新邮箱可能被他人注册：占位复查（含自身已改完的重放）
    other = repo.get_user_by_email(db, new_email)
    if other is not None and other.id != user.id:
        raise HTTPException(status_code=409, detail="email_taken")
    user.email = new_email
    row.used_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="email_taken")
    db.refresh(user)
    return {"ok": True, "user": profile_with_delete_request(db, user)}


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
    # N+1 修复：订单 items / 工单 messages 先收集 id 后 IN 批查内存分组（批查范式同 repository.active_variants_by_product）
    order_rows = (
        db.query(Order).filter(Order.user_id == user.id).order_by(Order.id.asc()).all()
    )
    items_by_order: dict[int, list] = {}
    if order_rows:
        for it in (
            db.query(OrderItem)
            .filter(OrderItem.order_id.in_([o.id for o in order_rows]))
            .order_by(OrderItem.id.asc()).all()
        ):
            items_by_order.setdefault(it.order_id, []).append(it)
    orders = [
        {
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
                for i in items_by_order.get(o.id, [])
            ],
        }
        for o in order_rows
    ]
    ticket_rows = (
        db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.id.asc()).all()
    )
    msgs_by_ticket: dict[int, list] = {}
    if ticket_rows:
        for m in (
            db.query(TicketMessage)
            .filter(TicketMessage.ticket_id.in_([t.id for t in ticket_rows]))
            .order_by(TicketMessage.id.asc()).all()
        ):
            msgs_by_ticket.setdefault(m.ticket_id, []).append(m)
    tickets = [
        {
            "ticket_no": t.ticket_no,
            "subject": t.subject,
            "category": t.category,
            "status": t.status,
            "order_no": t.order_no,
            "created_at": t.created_at,
            "messages": [
                {"sender": m.sender, "content": m.content, "created_at": m.created_at}
                for m in msgs_by_ticket.get(t.id, [])
            ],
        }
        for t in ticket_rows
    ]
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


def anonymize_user(db: Session, user_id: int) -> bool:
    """GDPR 删除执行核心（单一实现，两方共用）：
    worker 到期批处理（scripts/worker.py process_data_requests）与
    后台立即执行（ops 域 data-requests execute）都调本函数。

    匿化用户主体 + 删除地址/购物车/心愿单 + 历史订单脱敏保留（金额/状态不动）；
    事务边界归调用方（不 commit）；返回用户是否存在（不存在时无操作，幂等）。
    """
    user = db.get(User, user_id)
    if user is None:
        return False
    old_email = user.email
    anon_email = f"deleted+{user.id}@anonymized.local"
    user.email = anon_email
    user.password_hash = None
    user.name = ""
    user.status = -1
    user.birthday = None
    # 积分清零走 points.py 原子原语并补流水（reason=ADMIN_ADJUST/ref=gdpr，balance_after=0），
    # 保证对账 diff_points=0；不再 ORM 赋 user.points=0（无流水且 flush 可能覆盖 raw 结果）
    points_svc.clear_points(db, user_id, ref_type="gdpr", ref_id=user_id)
    db.query(UserAddress).filter(UserAddress.user_id == user.id).delete(
        synchronize_session=False)
    db.query(Cart).filter(Cart.user_id == user.id).delete(
        synchronize_session=False)
    db.query(WishlistItem).filter(WishlistItem.user_id == user.id).delete(
        synchronize_session=False)
    # PII 残留清理：推荐行 invited_email 脱敏（deleted+行id，与订单匿名化同风格且唯一索引安全）；
    # 邮件偏好按 GDPR 删除语义直接删行（邮箱或 user_id 关联的都清）
    for ref in db.query(Referral).filter(Referral.invited_email == old_email).all():
        ref.invited_email = f"deleted+{ref.id}@anonymized.local"
    db.query(EmailPreference).filter(
        or_(EmailPreference.email == old_email, EmailPreference.user_id == user_id)
    ).delete(synchronize_session=False)
    for order in db.query(Order).filter(Order.user_id == user.id).all():
        order.email = anon_email
        addr = dict(order.shipping_address or {})
        addr["full_name"] = "Deleted User"
        addr["phone"] = ""
        order.shipping_address = addr
    return True


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
