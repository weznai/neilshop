"""结算服务 —— preview 试算 / place 下单（乐观锁预扣库存 + 用分 + 礼品卡原子扣减 + 清车）。
place 含轻量防重：carts 行锁串行化同车并发 + 90 秒内同用户/同邮箱 items 完全相同的
PENDING 订单幂等返回（不重复建单扣库存）；黑名单（risk_flag=2）用户拒绝下单。"""

import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.domains.trade.schemas import PlaceRequest, PreviewRequest
from app.models import Cart, Order, OrderItem, User
from app.services import points as points_svc
from app.services.pricing import price_cart

# 同用户/同邮箱重复下单防重窗口
DEDUP_WINDOW = timedelta(seconds=90)
# 防重扫描的最近候选单数上限（status=0 且在窗口内，倒序取最近若干单做 items 精确比对）
DEDUP_SCAN_LIMIT = 20


def cart_items_of(cart: Cart) -> list[dict]:
    items = []
    for row in cart.items or []:
        vid = int(row.get("variantId") or row.get("variant_id") or 0)
        qty = int(row.get("qty") or 1)
        if vid > 0 and qty > 0:
            items.append({"variant_id": vid, "qty": qty})
    return items


def preview(
    db: Session, cart: Cart, body: PreviewRequest | None, user: User | None,
) -> dict:
    items = (
        [i.model_dump() for i in body.items] if body and body.items
        else cart_items_of(cart)
    )
    return price_cart(
        db,
        items=items,
        country=body.country if body else "US",
        state=body.state if body else None,
        code=body.code if body else None,
        points=body.points if body else 0,
        gift_card_code=body.gift_card_code if body else None,
        email=body.email if body else None,
        user_id=user.id if user else None,
        shipping_method=body.shipping_method if body else "standard",
    )


def _place_payload(order: Order) -> dict:
    return {
        "order_no": order.order_no,
        "status": order.status,
        "email": order.email,
        "subtotal": order.subtotal,
        "discount_total": order.discount_total,
        "points_discount": order.points_discount,
        "giftcard_discount": order.giftcard_discount,
        "shipping_fee": order.shipping_fee,
        "tax": order.tax,
        "grand_total": order.grand_total,
    }


def _dedup_pending_order(
    db: Session, *, user: User | None, email: str | None,
    items: list[dict] | None,
) -> Order | None:
    """90 秒内同用户（登录）/同邮箱（游客）的 PENDING 订单防重扫描。
    items 非空时做 (variant_id, qty) 集合精确比对（候选单条目 1 条 IN 批量取回，避免逐单 N+1）；
    items 为空（清车后的重放请求）时直接返回最近一笔 PENDING（即刚下的那单）。
    游客按 email 等值匹配：下单 email 已归一 strip().lower() 落库，MySQL ci collation
    下等值即不区分大小写且可走索引（SQLite 侧因写入同归一亦等价）。"""
    cutoff = utcnow() - DEDUP_WINDOW
    query = db.query(Order).filter(Order.status == 0, Order.placed_at >= cutoff)
    if user is not None:
        query = query.filter(Order.user_id == user.id)
    elif email and email.strip():
        query = query.filter(Order.email == email.strip().lower())
    else:
        return None
    candidates = query.order_by(Order.id.desc()).limit(DEDUP_SCAN_LIMIT).all()
    if not candidates:
        return None
    if items is None:
        return candidates[0]
    target = sorted((i["variant_id"], i["qty"]) for i in items)
    items_map = repo.order_items_map(db, [o.id for o in candidates])
    for order in candidates:
        existing = sorted(
            (i.variant_id, i.qty) for i in items_map.get(order.id, [])
        )
        if existing == target:
            return order
    return None


def place(db: Session, cart: Cart, body: PlaceRequest, user: User | None) -> dict:
    # 下单 email 归一（strip+lower）落库：游客防重/弃购召回/ Redemption 查询统一大小写口径
    email_norm = body.email.strip().lower()
    # 风控：黑名单用户拒绝下单；登出后用同 email 游客下单同拦（单次查询）
    if user is not None:
        if user.risk_flag == 2:
            raise HTTPException(status_code=403, detail="account_blocked")
    elif repo.blacklisted_email(db, email_norm):
        raise HTTPException(status_code=403, detail="account_blocked")
    cart_items = cart_items_of(cart)
    if not cart_items:
        # 清车后的重复提交（双击重放）：窗口内已有该用户/邮箱的 PENDING 单则幂等返回
        db.query(Cart.id).filter(Cart.id == cart.id).with_for_update().first()
        replay = _dedup_pending_order(db, user=user, email=email_norm, items=None)
        if replay is not None:
            cart.items = []
            cart.email = email_norm or cart.email
            db.commit()
            return _place_payload(replay)
        raise HTTPException(status_code=400, detail="empty_cart")
    if body.points and body.points > 0 and not user:
        raise HTTPException(status_code=401, detail="login_required_for_points")

    # carts 行锁串行化同车并发下单（不同车互不阻塞），锁内做防重判定
    db.query(Cart.id).filter(Cart.id == cart.id).with_for_update().first()
    existing = _dedup_pending_order(db, user=user, email=email_norm, items=cart_items)
    if existing is not None:
        cart.items = []
        cart.email = email_norm or cart.email
        db.commit()
        return _place_payload(existing)

    pricing = price_cart(
        db,
        items=cart_items,
        country=body.address.country or "US",
        state=getattr(body.address, "state", None),
        code=body.code,
        points=body.points,
        gift_card_code=body.gift_card_code,
        email=email_norm,
        user_id=user.id if user else None,
        shipping_method=body.shipping_method,
    )
    if pricing["code"] and not pricing["code_valid"]:
        raise HTTPException(status_code=409, detail=f"invalid_code:{pricing['code_reason']}")
    if pricing["gift_card_error"]:
        raise HTTPException(status_code=409, detail=pricing["gift_card_error"])

    now = utcnow()
    order = Order(
        order_no="NS" + now.strftime("%y%m%d") + uuid.uuid4().hex[:6].upper(),
        user_id=user.id if user else None,
        email=email_norm,
        status=0,
        currency="USD",
        subtotal=pricing["subtotal"],
        discount_total=pricing["discount_total"],
        points_discount=pricing["points_discount"],
        giftcard_discount=pricing["giftcard_discount"],
        shipping_fee=pricing["shipping_fee"],
        tax=pricing["tax"],
        grand_total=pricing["grand_total"],
        shipping_address=body.address.model_dump(),
        discount_code_id=pricing["code_id"],
        points_used=pricing["points_applied"],
        gift_flag=1 if body.gift_flag else 0,
        gift_message=body.gift_message,
        source="web",
        utm_json=body.utm,
        shipping_method=body.shipping_method,
        note=body.note,
        placed_at=now,
    )
    db.add(order)
    db.flush()

    for line in pricing["items"]:
        db.add(OrderItem(
            order_id=order.id,
            variant_id=line["variant_id"],
            product_slug=line["product_slug"],
            title_snapshot=line["title"],
            image=line["image"],
            qty=line["qty"],
            unit_price=line["unit_price"],
            subtotal=line["line_subtotal"],
        ))
        updated = repo.reserve_stock(db, line["variant_id"], line["qty"])
        if updated == 0:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"insufficient_stock:{line['variant_id']}")
        stock_after = repo.stock_of(db, line["variant_id"])
        repo.add_stock_movement(
            db, variant_id=line["variant_id"], change=-line["qty"],
            stock_after=stock_after, type=2, ref_type="order", ref_id=order.id,
        )

    if user and pricing["points_applied"] > 0:
        try:
            points_svc.spend(db, user.id, pricing["points_applied"], order.id)
        except ValueError:
            db.rollback()
            raise HTTPException(status_code=409, detail="insufficient_points")
    order.points_used = pricing["points_applied"]

    if pricing["gift_card"] and pricing["giftcard_discount"] > 0:
        gc = repo.get_gift_card(db, pricing["gift_card"]["id"])
        # 原子扣减：余额守卫进 WHERE，并发/余额变动时 rowcount=0 → 余额不足
        if repo.debit_gift_card(db, gc.id, pricing["giftcard_discount"]) == 0:
            db.rollback()
            raise HTTPException(status_code=409, detail="gift_card_insufficient")
        db.refresh(gc)
        if gc.balance <= 0:
            gc.status = 3
        repo.add_giftcard_ledger(
            db, gift_card_id=gc.id, order_id=order.id, change_type=3,
            amount=pricing["giftcard_discount"], balance_after=gc.balance,
        )

    cart.items = []
    # 弃购召回链路依赖：下单 email 回填购物车行（worker scan_abandoned_carts 过滤 email 非空）
    cart.email = email_norm or cart.email
    repo.add_timeline(db, order.id, "checkout_created", actor="user", detail={
        "order_no": order.order_no,
        "code_discount": pricing["code_discount"],
        "bundle_discount": pricing["bundle_discount"],
        "points_used": pricing["points_applied"],
        "giftcard_discount": pricing["giftcard_discount"],
    })
    db.commit()

    return _place_payload(order)
