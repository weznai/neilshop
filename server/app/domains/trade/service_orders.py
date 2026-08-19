"""订单服务 —— 用户列表/详情/游客物流查询/待付取消（释放库存 + type=4 流水）"""

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.models import Order, User

PER_PAGE = 10


def _brief(order: Order) -> dict:
    return {
        "order_no": order.order_no,
        "email": order.email,
        "status": order.status,
        "shipping_status": order.shipping_status,
        "grand_total": order.grand_total,
        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


def _get_order(db: Session, order_no: str) -> Order:
    order = repo.order_by_no(db, order_no)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    return order


def _detail(db: Session, order: Order) -> dict:
    items = repo.order_items(db, order.id)
    timeline = repo.order_timeline_desc(db, order.id)
    shipments = repo.order_shipments(db, order.id)
    payments = repo.order_payments(db, order.id)
    return {
        **_brief(order),
        "subtotal": order.subtotal,
        "discount_total": order.discount_total,
        "points_discount": order.points_discount,
        "points_used": order.points_used,
        "points_earned": order.points_earned,
        "giftcard_discount": order.giftcard_discount,
        "shipping_fee": order.shipping_fee,
        "tax": order.tax,
        "shipping_address": order.shipping_address,
        "shipping_method": order.shipping_method,
        "tracking_no": order.tracking_no,
        "items": [{
            "id": i.id, "variant_id": i.variant_id, "title": i.title_snapshot,
            "image": i.image, "qty": i.qty, "unit_price": i.unit_price,
            "subtotal": i.subtotal, "refunded_qty": i.refunded_qty,
            "exchanged_qty": i.exchanged_qty,
        } for i in items],
        "timeline": [{
            "event": t.event, "actor": t.actor, "detail": t.detail,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in timeline],
        "shipments": [{
            "shipment_no": s.shipment_no, "carrier": s.carrier,
            "tracking_no": s.tracking_no, "status": s.status,
        } for s in shipments],
        "payments": [{
            "id": p.id, "status": p.status, "amount": p.amount,
            "refunded_amount": p.refunded_amount,
            "payment_intent": p.stripe_payment_intent,
        } for p in payments],
    }


def list_orders(
    db: Session, user: User, status: Optional[int], page: int,
) -> dict:
    orders, total = repo.paginate_orders(
        db, user_id=user.id, status=status, page=page, per_page=PER_PAGE,
    )
    return {
        "items": [_brief(o) for o in orders],
        "page": page,
        "per_page": PER_PAGE,
        "total": total,
        "pages": (total + PER_PAGE - 1) // PER_PAGE,
    }


def track(db: Session, no: str, email: str) -> dict:
    order = _get_order(db, no.strip().upper())
    if order.email.lower() != email.strip().lower():
        raise HTTPException(status_code=404, detail="order_not_found")
    shipments = repo.order_shipments(db, order.id)
    timeline = repo.order_timeline_desc(db, order.id)
    return {
        "order_no": order.order_no,
        "status": order.status,
        "grand_total": order.grand_total,
        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        "shipments": [{
            "shipment_no": s.shipment_no, "carrier": s.carrier,
            "tracking_no": s.tracking_no, "status": s.status,
            "shipped_at": s.shipped_at.isoformat() if s.shipped_at else None,
            "delivered_at": s.delivered_at.isoformat() if s.delivered_at else None,
        } for s in shipments],
        "timeline": [{
            "event": t.event, "actor": t.actor, "detail": t.detail,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in timeline],
    }


def order_detail(
    db: Session, order_no: str, email: Optional[str], user: Optional[User],
) -> dict:
    order = _get_order(db, order_no.strip().upper())
    is_owner = user is not None and order.user_id == user.id
    is_email = email is not None and email.strip().lower() == order.email.lower()
    if not (is_owner or is_email):
        raise HTTPException(status_code=404, detail="order_not_found")
    return _detail(db, order)


def cancel_order(db: Session, order_no: str, user: User) -> dict:
    order = _get_order(db, order_no.strip().upper())
    if order.user_id != user.id:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.status != 0:
        raise HTTPException(status_code=409, detail=f"not_cancellable:{order.status}")
    items = repo.order_items(db, order.id)
    for item in items:
        repo.release_stock(db, item.variant_id, item.qty)
        stock_after = repo.stock_of(db, item.variant_id)
        repo.add_stock_movement(
            db, variant_id=item.variant_id, change=item.qty,
            stock_after=stock_after, type=4, ref_type="order", ref_id=order.id,
        )
    order.status = 8
    order.cancel_reason = "user"
    order.canceled_at = utcnow()
    repo.add_timeline(db, order.id, "status_changed", actor="user", detail={
        "from": 0, "to": 8, "reason": "user",
    })
    db.commit()
    return {"order_no": order.order_no, "status": order.status}
