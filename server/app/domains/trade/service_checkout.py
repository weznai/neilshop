"""结算服务 —— preview 试算 / place 下单（乐观锁预扣库存 + 用分 + 礼品卡扣减 + 清车）"""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.domains.trade.schemas import PlaceRequest, PreviewRequest
from app.models import Cart, Order, OrderItem, User
from app.services import points as points_svc
from app.services.pricing import price_cart


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


def place(db: Session, cart: Cart, body: PlaceRequest, user: User | None) -> dict:
    cart_items = cart_items_of(cart)
    if not cart_items:
        raise HTTPException(status_code=400, detail="empty_cart")
    if body.points and body.points > 0 and not user:
        raise HTTPException(status_code=401, detail="login_required_for_points")

    pricing = price_cart(
        db,
        items=cart_items,
        country=body.address.country or "US",
        state=getattr(body.address, "state", None),
        code=body.code,
        points=body.points,
        gift_card_code=body.gift_card_code,
        email=body.email,
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
        email=body.email,
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
        gc.balance -= pricing["giftcard_discount"]
        if gc.balance <= 0:
            gc.balance = 0
            gc.status = 3
        repo.add_giftcard_ledger(
            db, gift_card_id=gc.id, order_id=order.id, change_type=3,
            amount=pricing["giftcard_discount"], balance_after=gc.balance,
        )

    cart.items = []
    repo.add_timeline(db, order.id, "checkout_created", actor="user", detail={
        "order_no": order.order_no,
        "code_discount": pricing["code_discount"],
        "bundle_discount": pricing["bundle_discount"],
        "points_used": pricing["points_applied"],
        "giftcard_discount": pricing["giftcard_discount"],
    })
    db.commit()

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
