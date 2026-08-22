"""后台交易/履约服务 —— 订单列表详情/发货/送达/退款、RMA 队列推进、库存调整与流水。
退款公共路径 apply_refund（admin 全额/部分、RMA 退款、webhook charge.refunded 共用）。"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.domains.trade.schemas import (
    NoteIn, RefundRequest, ShipRequest, ShippingRateIn, ShippingRateUpdateIn,
    StockAdjustRequest,
)
from app.models import Order, Rma, Shipment, ShippingRate, User
from app.services import points as points_svc

PER_PAGE_ORDERS = 10
PER_PAGE_MOVEMENTS = 20
PER_PAGE_RMAS = 20


def _timeline(
    db: Session, order_id: int, event: str,
    actor: str = "admin", detail: dict | None = None,
) -> None:
    repo.add_timeline(db, order_id, event, actor=actor, detail=detail)


def _admin_log(
    db: Session, admin: User, action: str, entity: str, entity_id: int,
    diff: dict | None = None,
) -> None:
    repo.add_admin_log(
        db, admin_id=admin.id, action=action, entity=entity,
        entity_id=entity_id, diff_json=diff or {},
    )


def _get_order(db: Session, order_no: str) -> Order:
    order = repo.order_by_no(db, order_no.strip().upper())
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    return order


def _get_rma(db: Session, rma_no: str) -> Rma:
    rma = repo.rma_by_no(db, rma_no.strip().upper())
    if not rma:
        raise HTTPException(status_code=404, detail="rma_not_found")
    return rma


def _restock_items(db: Session, order: Order, *, ref_type: str) -> None:
    items = repo.order_items(db, order.id)
    eligible = [i for i in items if i.qty - i.refunded_qty > 0]
    for item in eligible:
        repo.release_stock(db, item.variant_id, item.qty - item.refunded_qty)
    stocks: dict[int, int] = {}
    if eligible:
        vids = list({i.variant_id for i in eligible})
        stocks = repo.variant_stock_map(db, vids)
    for item in eligible:
        repo.add_stock_movement(
            db, variant_id=item.variant_id, change=item.qty - item.refunded_qty,
            stock_after=stocks[item.variant_id],
            type=5, ref_type=ref_type, ref_id=order.id,
        )


def _refund_giftcard_debit(db: Session, order: Order) -> None:
    """礼品卡扣款回补：按该单 ledger change_type=3（消费确认）流水反查逐卡返还
    （余额加回 + 用尽卡复活 + change_type=5 流水）；无礼品卡扣款时为空操作。
    礼品卡 MVP 下单即扣且不建 payment 行，取消/超时/退款共用此回补。"""
    for row in repo.giftcard_debit_ledgers(db, order.id):
        gc = repo.get_gift_card(db, row.gift_card_id)
        if not gc:
            continue
        gc.balance += row.amount
        if gc.status == 3 and gc.balance > 0:
            gc.status = 1
        repo.add_giftcard_ledger(
            db, gift_card_id=gc.id, order_id=order.id, change_type=5,
            amount=row.amount, balance_after=gc.balance,
        )


def apply_refund(
    db: Session,
    order: Order,
    amount: Optional[int],
    *,
    reason: str,
    actor: str,
    admin: Optional[User] = None,
) -> dict:
    """退款公共路径（admin 全额/部分、RMA 退款、webhook charge.refunded 共用；调用方 commit）"""
    payment = repo.refundable_payment_of_order(db, order.id)
    if not payment:
        raise HTTPException(status_code=409, detail="no_refundable_payment")
    remaining = payment.amount - payment.refunded_amount
    if remaining <= 0:
        raise HTTPException(status_code=409, detail="already_fully_refunded")
    refund_amount = int(amount) if amount is not None else remaining
    if refund_amount <= 0 or refund_amount > remaining:
        raise HTTPException(status_code=409, detail=f"invalid_refund_amount:{remaining}")
    full = refund_amount == remaining

    payment.refunded_amount += refund_amount
    payment.status = 3 if full else 4

    if full:
        _restock_items(db, order, ref_type="order")
        order.status = 9
        points_svc.refund_void(db, order)
        # 累计退满：该单已用积分返还（points_used=0 跳过，同单幂等）
        points_svc.refund_return(db, order, order.user_id, order.points_used)
        if order.giftcard_discount > 0:
            _refund_giftcard_debit(db, order)
        repo.add_outbox_event(
            db, aggregate_type="order", aggregate_id=order.id,
            event_type="order.refunded",
            payload={
                "order_no": order.order_no, "amount": refund_amount,
                "full": True, "reason": reason,
            },
        )

    _timeline(db, order.id, "refund_issued", actor=actor, detail={
        "amount": refund_amount, "reason": reason, "full": full,
    })
    if admin:
        _admin_log(db, admin, "refund", "order", order.id, {
            "amount": refund_amount, "reason": reason, "full": full,
        })
    return {"amount": refund_amount, "full": full, "payment_status": payment.status}


def _parse_date(value: str, name: str) -> datetime:
    """YYYY-MM-DD 解析为 naive UTC 日期零点（placed_at 存储口径），非法格式 400"""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid_{name}")


def list_orders(
    db: Session, status: Optional[int], q: Optional[str], page: int,
    per_page: Optional[int] = None, date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    # 可选每页条数：缺省 10 兼容；显式传值时钳制到 10-100
    pp = PER_PAGE_ORDERS if per_page is None else min(max(per_page, 10), 100)
    # 时间范围闭区间：date_to 补到当日 23:59:59
    start = _parse_date(date_from, "date_from") if date_from else None
    end = None
    if date_to:
        end = _parse_date(date_to, "date_to").replace(hour=23, minute=59, second=59)
    orders, total = repo.paginate_orders(
        db, status=status, q=q, page=page, per_page=pp,
        date_from=start, date_to=end,
    )
    return {
        "items": [{
            "order_no": o.order_no, "email": o.email, "status": o.status,
            "grand_total": o.grand_total, "shipping_status": o.shipping_status,
            "note": o.note,
            "placed_at": o.placed_at.isoformat() if o.placed_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        } for o in orders],
        "page": page, "per_page": pp, "total": total,
        "pages": (total + pp - 1) // pp,
    }


def order_detail(db: Session, order_no: str) -> dict:
    order = _get_order(db, order_no)
    items = repo.order_items(db, order.id)
    payments = repo.order_payments(db, order.id)
    shipments = repo.order_shipments(db, order.id)
    timeline = repo.order_timeline_desc(db, order.id)
    redemptions = repo.order_redemptions(db, order.id)
    return {
        "order_no": order.order_no,
        "email": order.email,
        "user_id": order.user_id,
        "status": order.status,
        "shipping_status": order.shipping_status,
        "subtotal": order.subtotal,
        "discount_total": order.discount_total,
        "points_discount": order.points_discount,
        "points_used": order.points_used,
        "points_earned": order.points_earned,
        "giftcard_discount": order.giftcard_discount,
        "shipping_fee": order.shipping_fee,
        "tax": order.tax,
        "grand_total": order.grand_total,
        "shipping_address": order.shipping_address,
        "tracking_no": order.tracking_no,
        "note": order.note,
        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "items": [{
            "id": i.id, "variant_id": i.variant_id, "title": i.title_snapshot,
            "qty": i.qty, "unit_price": i.unit_price, "subtotal": i.subtotal,
            "refunded_qty": i.refunded_qty,
        } for i in items],
        "payments": [{
            "id": p.id, "status": p.status, "amount": p.amount,
            "refunded_amount": p.refunded_amount,
            "payment_intent": p.stripe_payment_intent,
        } for p in payments],
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
        "redemptions": [{
            "code_id": r.code_id, "discount_amount": r.discount_amount, "email": r.email,
        } for r in redemptions],
    }


def ship_order(db: Session, admin: User, order_no: str, body: ShipRequest) -> dict:
    order = _get_order(db, order_no)
    if order.status not in (1, 2):
        raise HTTPException(status_code=409, detail=f"not_shippable:{order.status}")
    items = repo.order_items(db, order.id)
    now = utcnow()
    shipment = Shipment(
        shipment_no="SP" + now.strftime("%y%m%d") + uuid.uuid4().hex[:4].upper(),
        order_id=order.id,
        carrier=body.carrier,
        tracking_no=body.tracking_no,
        status=3,
        item_json=[{"order_item_id": i.id, "qty": i.qty} for i in items],
        shipped_at=now,
    )
    db.add(shipment)
    prev_status = order.status
    order.status = 3
    order.shipped_at = now
    order.shipping_status = 2
    order.tracking_no = body.tracking_no
    _timeline(db, order.id, "shipment_created", actor="admin", detail={
        "shipment_no": shipment.shipment_no, "carrier": body.carrier,
        "tracking_no": body.tracking_no,
    })
    _timeline(db, order.id, "status_changed", actor="admin", detail={"from": prev_status, "to": 3})
    # 发货通知邮件（worker _EVENT_EMAILS 消费 order.shipped → order_shipped 模板）
    repo.add_outbox_event(
        db, aggregate_type="order", aggregate_id=order.id, event_type="order.shipped",
        payload={
            "order_no": order.order_no, "email": order.email,
            "carrier": body.carrier, "tracking_no": body.tracking_no,
        },
    )
    _admin_log(db, admin, "ship", "order", order.id, {
        "shipment_no": shipment.shipment_no, "carrier": body.carrier, "tracking_no": body.tracking_no,
    })
    db.commit()
    return {"shipment_no": shipment.shipment_no, "order_status": order.status}


def mark_delivered(db: Session, admin: User, order_no: str) -> dict:
    order = _get_order(db, order_no)
    if order.status != 3:
        raise HTTPException(status_code=409, detail=f"not_in_transit:{order.status}")
    now = utcnow()
    order.status = 4
    order.delivered_at = now
    shipments = repo.order_shipments(db, order.id)
    for s in shipments:
        if s.status == 3:
            s.status = 4
            s.delivered_at = now
    _timeline(db, order.id, "status_changed", actor="admin", detail={"from": 3, "to": 4})
    _admin_log(db, admin, "mark_delivered", "order", order.id, {})
    db.commit()
    return {"order_no": order.order_no, "order_status": order.status}


def refund_order(
    db: Session, admin: User, order_no: str, body: RefundRequest | None,
) -> dict:
    order = _get_order(db, order_no)
    amount = body.amount_cents if body else None
    reason = (body.reason if body else None) or "admin_refund"
    result = apply_refund(db, order, amount, reason=reason, actor="admin", admin=admin)
    db.commit()
    return {"order_no": order.order_no, "order_status": order.status, **result}


def cancel_order(db: Session, admin: User, order_no: str) -> dict:
    """后台取消待支付订单：CAS 抢占（WHERE status=0，与支付回调/超时关单互斥）
    + 库存/积分/礼品卡回补，回补路径与用户侧取消一致。"""
    order = _get_order(db, order_no)
    if order.status != 0:
        raise HTTPException(status_code=409, detail="only_pending_can_cancel")
    now = utcnow()
    if repo.claim_order_canceled(db, order.id, now, "admin") == 0:
        db.rollback()
        db.expire(order)
        raise HTTPException(status_code=409, detail="only_pending_can_cancel")
    order.status = 8
    order.cancel_reason = "admin"
    order.canceled_at = now
    for item in repo.order_items(db, order.id):
        repo.release_stock(db, item.variant_id, item.qty)
        repo.add_stock_movement(
            db, variant_id=item.variant_id, change=item.qty,
            stock_after=repo.stock_of(db, item.variant_id),
            type=4, ref_type="order", ref_id=order.id,
        )
    # 已用积分返还（points_used=0 自动跳过，同单幂等）
    points_svc.refund_return(db, order, order.user_id, order.points_used)
    # 礼品卡扣款回补（MVP 下单即扣；无 change_type=3 流水时为空操作）
    _refund_giftcard_debit(db, order)
    _timeline(db, order.id, "status_changed", actor="admin", detail={
        "from": 0, "to": 8, "reason": "admin",
    })
    _admin_log(db, admin, "cancel", "order", order.id, {"from": 0, "to": 8})
    db.commit()
    return {"ok": True}


def add_order_note(db: Session, admin: User, order_no: str, body: NoteIn) -> dict:
    """后台订单备注：仅落 order_timeline（note_added），不改下单备注列"""
    order = _get_order(db, order_no)
    _timeline(db, order.id, "note_added", actor="admin", detail={"text": body.text})
    _admin_log(db, admin, "note", "order", order.id, {"text": body.text})
    db.commit()
    return {"ok": True}


def list_rmas(
    db: Session, status: Optional[int],
    page: int = 1, per_page: int = PER_PAGE_RMAS, q: Optional[str] = None,
) -> dict:
    rows, total = repo.list_rmas(db, status, q=q, page=page, per_page=per_page)
    return {
        "items": [{
            "rma_no": rma.rma_no,
            "order_no": order.order_no,
            "email": order.email,
            "status": rma.status,
            "qty": rma.qty,
            "reason": rma.reason,
            "item_title": item.title_snapshot,
            "unit_price": item.unit_price,
            "refund_amount": rma.refund_amount,
            "created_at": rma.created_at.isoformat() if rma.created_at else None,
        } for rma, item, order in rows],
        "page": page, "per_page": per_page, "total": total,
        "pages": (total + per_page - 1) // per_page,
    }


def approve_rma(db: Session, admin: User, rma_no: str) -> dict:
    rma = _get_rma(db, rma_no)
    if rma.status != 0:
        raise HTTPException(status_code=409, detail=f"rma_not_approvable:{rma.status}")
    rma.status = 2
    rma.label_url = f"https://mock.glowmag.com/label/{rma.rma_no}.pdf"
    rma.handled_by = admin.id
    _timeline(db, rma.order_id, "rma_label_sent", actor="admin", detail={"rma_no": rma.rma_no})
    _admin_log(db, admin, "rma_approve", "return", rma.id, {"rma_no": rma.rma_no, "to": 2})
    db.commit()
    return {"rma_no": rma.rma_no, "status": rma.status, "label_url": rma.label_url}


def receive_rma(db: Session, admin: User, rma_no: str) -> dict:
    rma = _get_rma(db, rma_no)
    if rma.status not in (1, 2, 3):
        raise HTTPException(status_code=409, detail=f"rma_not_receivable:{rma.status}")
    item = repo.get_order_item(db, rma.order_item_id)
    repo.release_stock(db, item.variant_id, rma.qty)
    repo.add_stock_movement(
        db, variant_id=item.variant_id, change=rma.qty,
        stock_after=repo.stock_of(db, item.variant_id),
        type=5, ref_type="rma", ref_id=rma.order_id,
    )
    rma.status = 4
    rma.restock_qty = rma.qty
    rma.received_at = utcnow()
    rma.handled_by = admin.id
    _timeline(db, rma.order_id, "rma_received", actor="admin", detail={"rma_no": rma.rma_no, "restock_qty": rma.qty})
    _admin_log(db, admin, "rma_receive", "return", rma.id, {"rma_no": rma.rma_no, "restock_qty": rma.qty})
    db.commit()
    return {"rma_no": rma.rma_no, "status": rma.status, "restock_qty": rma.restock_qty}


def refund_rma(db: Session, admin: User, rma_no: str) -> dict:
    rma = _get_rma(db, rma_no)
    if rma.status != 4:
        raise HTTPException(status_code=409, detail=f"rma_not_refundable:{rma.status}")
    order = repo.get_order(db, rma.order_id)
    item = repo.get_order_item(db, rma.order_item_id)
    # 按订单实付比例折算（含税/运费/折扣分摊），单件全退时恰为 grand_total，订单可达 REFUNDED
    base = rma.qty * item.unit_price
    if order.subtotal > 0:
        amount = int(base * order.grand_total / order.subtotal + 0.5)
    else:
        amount = base
    # 退运费（reason 2/4/5）：按订单实付 shipping_fee 按件数比例折算（最低 0），
    # 不再固定补 499 —— 免邮单/多件部分退不应虚增退款
    refund_shipping = 0
    if rma.reason in (2, 4, 5) and order.shipping_fee > 0:
        total_qty = sum(i.qty for i in repo.order_items(db, order.id))
        if total_qty > 0:
            refund_shipping = max(0, min(
                int(order.shipping_fee * rma.qty / total_qty + 0.5),
                order.shipping_fee,
            ))
    amount = min(amount + refund_shipping, order.grand_total)
    payment = repo.refundable_payment_of_order(db, order.id)
    if payment is not None and amount > payment.amount - payment.refunded_amount:
        # 多笔 RMA 按比例折算各摊运费可能累计超过剩余可退（apply_refund 会 409 拒绝，
        # RMA 将永远卡在 4 态无法结案）；钳到剩余可退，恰好收尾为全额退
        amount = payment.amount - payment.refunded_amount

    item.refunded_qty += rma.qty
    result = apply_refund(
        db, order, amount, reason=f"rma:{rma.rma_no}", actor="admin", admin=admin,
    )
    rma.status = 5
    rma.refund_amount = amount
    rma.refund_shipping = refund_shipping
    rma.refunded_at = utcnow()
    rma.handled_by = admin.id
    _admin_log(db, admin, "rma_refund", "return", rma.id, {
        "rma_no": rma.rma_no, "amount": amount, "refund_shipping": refund_shipping,
    })
    db.commit()
    return {
        "rma_no": rma.rma_no, "status": rma.status, "refund_amount": amount,
        "refund_shipping": refund_shipping, **result,
    }


def adjust_stock(db: Session, admin: User, body: StockAdjustRequest) -> dict:
    variant = repo.get_variant(db, body.variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="variant_not_found")
    if body.change == 0:
        raise HTTPException(status_code=400, detail="zero_change")
    result = repo.adjust_stock_locked(db, body.variant_id, body.change, variant.version)
    if result == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="stock_adjust_conflict")
    stock_after = repo.stock_of(db, body.variant_id)
    repo.add_stock_movement(
        db, variant_id=body.variant_id, change=body.change,
        stock_after=stock_after, type=7, ref_type="manual", operator=admin.email,
    )
    _admin_log(db, admin, "stock_adjust", "product", body.variant_id, {
        "change": body.change, "reason": body.reason, "stock_after": stock_after,
    })
    db.commit()
    return {"variant_id": body.variant_id, "change": body.change, "stock": stock_after}


def stock_movements(
    db: Session, variant_id: Optional[int], page: int,
    type: Optional[int] = None,
) -> dict:
    rows, total = repo.paginate_stock_movements(
        db, variant_id=variant_id, page=page, per_page=PER_PAGE_MOVEMENTS, type=type,
    )
    return {
        "items": [{
            "id": m.id, "variant_id": m.variant_id, "change": m.change,
            "stock_after": m.stock_after, "type": m.type,
            "ref_type": m.ref_type, "ref_id": m.ref_id, "operator": m.operator,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in rows],
        "page": page, "per_page": PER_PAGE_MOVEMENTS, "total": total,
        "pages": (total + PER_PAGE_MOVEMENTS - 1) // PER_PAGE_MOVEMENTS,
    }


def low_stock(db: Session, threshold: int) -> dict:
    rows = repo.low_stock_variants(db, threshold)
    return {"threshold": threshold, "items": [{
        "variant_id": v.id, "sku": v.sku, "product_title": p.title,
        "stock": v.stock, "safety_stock": v.safety_stock,
    } for v, p in rows]}


# ---------- 运费模板管理（ShippingRate 激活，pricing 实时读取） ----------

def _rate_out(r: ShippingRate) -> dict:
    return {
        "id": r.id, "dest_country": r.dest_country, "carrier": r.carrier,
        "method": r.method, "price": int(r.price), "free_over": r.free_over,
        "eta_min_days": r.eta_min_days, "eta_max_days": r.eta_max_days,
        "max_weight_g": r.max_weight_g, "active": bool(r.active),
    }


def list_shipping_rates(db: Session) -> dict:
    rows = (
        db.query(ShippingRate)
        .order_by(ShippingRate.dest_country.asc(), ShippingRate.method.asc(), ShippingRate.id.asc())
        .all()
    )
    return {"items": [_rate_out(r) for r in rows]}


def create_shipping_rate(db: Session, admin: User, body: ShippingRateIn) -> dict:
    r = ShippingRate(
        dest_country=body.dest_country.strip().upper(),
        carrier=body.carrier.strip().lower(),
        method=body.method,
        max_weight_g=body.max_weight_g,
        price=body.price,
        free_over=body.free_over,
        eta_min_days=body.eta_min_days,
        eta_max_days=body.eta_max_days,
        active=1,
    )
    if r.eta_max_days < r.eta_min_days:
        raise HTTPException(status_code=422, detail="eta_max_below_min")
    db.add(r)
    db.flush()
    _admin_log(db, admin, "create", "shipping_rate", r.id, {"price": r.price, "method": r.method})
    db.commit()
    db.refresh(r)
    return _rate_out(r)


def update_shipping_rate(
    db: Session, admin: User, rate_id: int, body: ShippingRateUpdateIn,
) -> dict:
    r = db.get(ShippingRate, rate_id)
    if not r:
        raise HTTPException(status_code=404, detail="shipping_rate_not_found")
    diff: dict = {}
    for field, new in body.model_dump(exclude_unset=True).items():
        if field == "active":
            new = int(new)
        old = getattr(r, field)
        if old != new:
            setattr(r, field, new)
            diff[field] = {"before": old, "after": new}
    if r.eta_max_days < r.eta_min_days:
        raise HTTPException(status_code=422, detail="eta_max_below_min")
    if diff:
        _admin_log(db, admin, "update", "shipping_rate", r.id, diff)
        db.commit()
        db.refresh(r)
    return _rate_out(r)


def delete_shipping_rate(db: Session, admin: User, rate_id: int) -> dict:
    """删除运费模板：订单仅快照 shipping_fee/method 无 FK 引用，可直接删；
    若未来引入引用约束导致删除失败，统一回落 409 rate_referenced。"""
    r = db.get(ShippingRate, rate_id)
    if not r:
        raise HTTPException(status_code=404, detail="shipping_rate_not_found")
    _admin_log(db, admin, "delete", "shipping_rate", r.id, {
        "dest_country": r.dest_country, "carrier": r.carrier, "method": r.method,
    })
    try:
        db.delete(r)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="rate_referenced")
    return {"ok": True}
