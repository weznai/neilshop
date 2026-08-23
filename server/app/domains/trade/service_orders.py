"""订单服务 —— 用户列表/详情/游客物流查询/取消（待付 CAS + 释放库存 + type=4 流水 +
积分返还 + 礼品卡回补；已付未发货 CAS + 全额退款公共路径）"""

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.domains.trade import service_admin
from app.models import Order, User
from app.services import points as points_svc

log = logging.getLogger("glowmag.orders")

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
            "exchanged_qty": i.exchanged_qty, "reviewed": bool(i.reviewed),
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


def _cancel_pending(db: Session, order: Order, user: User) -> dict:
    # CAS 抢占（WHERE status=0）：与支付回调/超时关单并发互斥，防 paid 后被覆盖取消
    now = utcnow()
    if repo.claim_order_canceled(db, order.id, now, "user") == 0:
        db.rollback()
        db.expire(order)
        raise HTTPException(status_code=409, detail=f"not_cancellable:{order.status}")
    order.status = 8
    order.cancel_reason = "user"
    order.canceled_at = now
    items = repo.order_items(db, order.id)
    for item in items:
        repo.release_stock(db, item.variant_id, item.qty)
        stock_after = repo.stock_of(db, item.variant_id)
        repo.add_stock_movement(
            db, variant_id=item.variant_id, change=item.qty,
            stock_after=stock_after, type=4, ref_type="order", ref_id=order.id,
        )
    # 已用积分返还（points_used=0 自动跳过，同单幂等）
    points_svc.refund_return(db, order, order.user_id, order.points_used)
    # 礼品卡扣款回补（MVP 下单即扣；无 change_type=3 流水时为空操作）
    service_admin._refund_giftcard_debit(db, order)
    repo.add_timeline(db, order.id, "status_changed", actor="user", detail={
        "from": 0, "to": 8, "reason": "user",
    })
    db.commit()
    return {"order_no": order.order_no, "status": order.status}


def _cancel_paid_unshipped(db: Session, order: Order, user: User) -> dict:
    """已支付未发货取消：CAS（status=1 且 shipping_status=0，与发货互斥）→ 全额退款
    公共路径（库存回补/积分双向/礼品卡回补/outbox，订单终态 9）；
    无可退 payment 时降级为仅 CAS + timeline，不阻断取消。"""
    now = utcnow()
    if repo.claim_order_paid_canceled(db, order.id, now, "user") == 0:
        db.rollback()
        db.expire(order)
        raise HTTPException(status_code=409, detail=f"not_cancellable:{order.status}")
    order.status = 8
    order.cancel_reason = "user"
    order.canceled_at = now
    refund = None
    try:
        refund = service_admin.apply_refund(
            db, order, None, reason="user_cancel_paid", actor="user",
        )
    except HTTPException as exc:
        if exc.detail != "no_refundable_payment":
            raise
        log.warning("paid-cancel order %s degraded: no refundable payment, "
                    "order kept CANCELED without refund", order.order_no)
    repo.add_timeline(db, order.id, "status_changed", actor="user", detail={
        "from": 1, "to": order.status, "reason": "user_cancel_paid",
    })
    db.commit()
    return {"order_no": order.order_no, "status": order.status, "refund": refund}


def cancel_order(
    db: Session, order_no: str, user: Optional[User],
    email: Optional[str] = None,
) -> dict:
    order = _get_order(db, order_no.strip().upper())
    # 归属判定与 order_detail 同口径：登录属主 或 email 双因子（游客待付单自助取消）
    is_owner = user is not None and order.user_id == user.id
    is_email = email is not None and email.strip().lower() == order.email.lower()
    if not (is_owner or is_email):
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.status == 0:
        return _cancel_pending(db, order, user)
    if order.status == 1 and order.shipping_status == 0:
        return _cancel_paid_unshipped(db, order, user)
    raise HTTPException(status_code=409, detail=f"not_cancellable:{order.status}")


def confirm_received(db: Session, order_no: str, user: User) -> dict:
    """用户确认收货：CAS（WHERE status=4，与后台 mark-completed 并发互斥）4→5 已完成；
    积分解冻仍由 worker 按 paid_at+return_days 独立驱动，此处无积分副作用。"""
    order = _get_order(db, order_no.strip().upper())
    if order.user_id != user.id:
        raise HTTPException(status_code=404, detail="order_not_found")
    now = utcnow()
    if repo.claim_order_completed(db, order.id, now) == 0:
        db.rollback()
        db.expire(order)
        raise HTTPException(status_code=409, detail=f"not_confirmable:{order.status}")
    # 原生 CAS UPDATE 不经过身份映射：expire 后重读，保证响应携带新状态
    db.expire(order)
    order.completed_at = now
    repo.add_timeline(db, order.id, "status_changed", actor="user", detail={
        "from": 4, "to": 5, "reason": "user_confirm_received",
    })
    db.commit()
    return {"order_no": order.order_no, "status": order.status}
