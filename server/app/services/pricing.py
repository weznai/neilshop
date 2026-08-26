"""定价引擎 —— 结算分项计算（纯函数 + 只读查询，金额一律美分 int）；模块头部含 SQLite 兼容垫片（BigInteger 主键自增 / DATETIME 读回带时区），仅 sqlite 方言生效，MySQL 不受影响。"""

from __future__ import annotations

from datetime import timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.db import utcnow
from app.models import (
    Category, DiscountCode, GiftCard, Product, Setting, ShippingRate, Variant,
)
from app.services import points as points_svc
from app.services import promo_rules
from app.services.tax_rates import rate_for

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"


DEFAULT_FREE_SHIPPING_THRESHOLD = 3500
DEFAULT_TAX_RATE = 0.0735
DEFAULT_SHIPPING_STANDARD = 499
DEFAULT_SHIPPING_EXPRESS = 1499


def _setting(db: Session, key: str, default):
    row = db.get(Setting, key)
    if row is None or row.value is None:
        return default
    return row.value


def _shipping_rate(db: Session, country: str, method: str) -> Optional[dict]:
    """按 国家(精确→通配) + 方式 匹配启用中的运费模板；未命中返回 None（走 settings 回退）。

    seed: usps/standard 499 · ups/express 1499 · dhl/* 1299 —— 与 settings 默认一致，
    行为零变化；运营改表后即时生效（无缓存，逐单查询）。
    """
    country = (country or "US").strip().upper()[:2]
    method = (method or "standard").strip().lower() or "standard"
    row = (
        db.query(ShippingRate)
        .filter(
            ShippingRate.active == 1,
            ShippingRate.method == method,
            ShippingRate.dest_country.in_([country, "*"]),
        )
        .order_by(ShippingRate.price.asc(), ShippingRate.id.asc())
        .first()
    )
    if row is None:
        return None
    return {"id": row.id, "price": int(row.price), "free_over": row.free_over}


def shipping_methods(db: Session, country: str = "US") -> list[dict]:
    """前台可用配送方式（公开）：按方式聚合最低价。"""
    country = (country or "US").strip().upper()[:2]
    rows = (
        db.query(ShippingRate)
        .filter(ShippingRate.active == 1, ShippingRate.dest_country.in_([country, "*"]))
        .order_by(ShippingRate.method.asc(), ShippingRate.price.asc())
        .all()
    )
    out: dict[str, dict] = {}
    for r in rows:
        cur = out.get(r.method)
        if cur is None or r.price < cur["price"]:
            out[r.method] = {
                "method": r.method,
                "carrier": r.carrier,
                "price": int(r.price),
                "free_over": r.free_over,
                "eta_min_days": r.eta_min_days,
                "eta_max_days": r.eta_max_days,
            }
    return list(out.values())


def _resolve_items(db: Session, items: list[dict]) -> list[dict]:
    if not items:
        raise HTTPException(status_code=400, detail="empty_cart")
    merged: dict[int, int] = {}
    ordered: list[int] = []
    for row in items:
        vid = int(row.get("variant_id") or 0)
        qty = int(row.get("qty") or 1)
        if vid <= 0 or qty <= 0:
            raise HTTPException(status_code=400, detail="invalid_item")
        if vid in merged:
            merged[vid] += qty
        else:
            merged[vid] = qty
            ordered.append(vid)
    lines = []
    for vid in ordered:
        qty = merged[vid]
        variant = db.get(Variant, vid)
        if not variant:
            raise HTTPException(status_code=404, detail=f"variant_not_found:{vid}")
        if not variant.is_active:
            raise HTTPException(status_code=409, detail=f"variant_inactive:{vid}")
        product = db.get(Product, variant.product_id)
        # 下架/草稿商品拦截：商品归档(status!=1)后变体仍 is_active，只校验变体会
        # 把不可售商品加进购物车下单
        if product is not None and product.status != 1:
            raise HTTPException(status_code=409, detail=f"product_unavailable:{vid}")
        category = db.get(Category, product.category_id) if product else None
        lines.append({
            "variant_id": variant.id,
            "sku": variant.sku,
            "product_slug": product.slug if product else "",
            "title": f"{product.title} · {variant.option1_value}" if product else variant.sku,
            "image": (product.hero_image or "") if product else "",
            "category_slug": category.slug if category else "",
            "qty": qty,
            "unit_price": int(variant.price),
            "line_subtotal": int(variant.price) * qty,
            "stock": int(variant.stock),
            "version": int(variant.version),
        })
    return lines


def price_cart(
    db: Session,
    *,
    items: list[dict],
    country: str = "US",
    state: Optional[str] = None,
    code: Optional[str] = None,
    points: int = 0,
    gift_card_code: Optional[str] = None,
    email: Optional[str] = None,
    user_id: Optional[int] = None,
    shipping_method: str = "standard",
) -> dict:
    lines = _resolve_items(db, items)
    subtotal = sum(l["line_subtotal"] for l in lines)

    code_id = None
    code_valid, code_discount, free_shipping, code_reason = False, 0, False, "no_code"
    normalized_code = (code or "").strip().upper()
    if normalized_code:
        valid, disc, fship, reason = promo_rules.validate_code(
            db, normalized_code, subtotal, email=email, user_id=user_id,
        )
        dc = db.query(DiscountCode).filter(DiscountCode.code == normalized_code).first()
        if valid:
            if dc is not None and dc.type == 1:
                rounded = (subtotal * int(dc.value) + 50) // 100
                if dc.max_discount:
                    rounded = min(rounded, int(dc.max_discount))
                disc = min(rounded, subtotal)
            code_id = dc.id if dc else None
            code_valid, code_discount, free_shipping, code_reason = True, int(disc), bool(fship), "ok"
        else:
            code_valid, code_discount, free_shipping, code_reason = False, 0, False, reason

    press_lines = [l for l in lines if l["category_slug"] == "press-on-nails"]
    press_qty = sum(l["qty"] for l in press_lines)
    off3 = int(_setting(db, "bundle_3_off", 20))
    off2 = int(_setting(db, "bundle_2_off", 15))
    bundle_off = off3 if (press_qty >= 3 and off3) else (off2 if press_qty == 2 else 0)
    press_subtotal = sum(l["line_subtotal"] for l in press_lines)
    bundle_discount = press_subtotal * bundle_off // 100 if bundle_off else 0

    discount_total = min(code_discount + bundle_discount, subtotal)

    points_applied = 0
    if points and int(points) > 0:
        if not user_id:
            raise HTTPException(status_code=401, detail="login_required_for_points")
        if int(points) > points_svc.usable_balance(db, user_id):
            raise HTTPException(status_code=409, detail="insufficient_points")
        points_applied = max(0, min(int(points), subtotal - discount_total))
    points_discount = points_applied

    gift_card: Optional[dict] = None
    giftcard_discount = 0
    gift_card_error: Optional[str] = None
    if gift_card_code:
        gc = db.query(GiftCard).filter(
            GiftCard.code == str(gift_card_code).strip().upper()
        ).first()
        now = utcnow()
        if not gc or gc.status != 1:
            gift_card_error = "gift_card_not_available"
        elif gc.expires_at and gc.expires_at < now:
            gift_card_error = "gift_card_expired"
        else:
            remaining = max(0, subtotal - discount_total - points_discount)
            giftcard_discount = min(int(gc.balance), remaining)
            gift_card = {"id": gc.id, "code": gc.code, "balance": int(gc.balance)}

    after_discount = max(0, subtotal - discount_total - points_discount - giftcard_discount)
    rate_row = _shipping_rate(db, country, shipping_method)
    threshold = int(
        rate_row["free_over"] if rate_row and rate_row["free_over"] is not None
        else _setting(db, "free_shipping_threshold", DEFAULT_FREE_SHIPPING_THRESHOLD)
    )
    if free_shipping or after_discount >= threshold:
        shipping_fee = 0
    elif rate_row is not None:
        shipping_fee = int(rate_row["price"])
    elif shipping_method == "express":
        shipping_fee = int(_setting(db, "shipping_express", DEFAULT_SHIPPING_EXPRESS))
    else:
        shipping_fee = int(_setting(db, "shipping_standard", DEFAULT_SHIPPING_STANDARD))

    tax_rate = rate_for(state, float(_setting(db, "tax_rate", DEFAULT_TAX_RATE)))
    taxable_base = subtotal - discount_total - points_discount - giftcard_discount + shipping_fee
    tax = int(taxable_base * tax_rate + 0.5)
    grand_total = max(0, taxable_base + tax)
    tax_state = (state or "").strip().upper() or None

    return {
        "items": lines,
        "subtotal": subtotal,
        "code": normalized_code or None,
        "code_id": code_id,
        "code_valid": code_valid,
        "code_reason": code_reason,
        "code_discount": code_discount,
        "free_shipping": free_shipping,
        "bundle_qty": press_qty,
        "bundle_discount": bundle_discount,
        "discount_total": discount_total,
        "points_applied": points_applied,
        "points_discount": points_discount,
        "gift_card": gift_card,
        "gift_card_error": gift_card_error,
        "giftcard_discount": giftcard_discount,
        "shipping_method": shipping_method,
        "shipping_fee": shipping_fee,
        # 免邮门槛回传（前端进度条/文案统一消费，替代三处硬编码 3500）
        "free_shipping_threshold": threshold,
        "tax_rate": tax_rate,
        "tax_state": tax_state,
        "tax": tax,
        "grand_total": grand_total,
    }
