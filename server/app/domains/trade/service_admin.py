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
    NoteIn, OrderAddressUpdateIn, RefundRequest, RmaRejectRequest, RmaRefundRequest,
    ShipRequest, ShippingRateIn, ShippingRateUpdateIn, StockAdjustRequest,
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
        if gc.status == 4:
            # 作废卡不可复活：余额已清零且作废负流水已记账，跳过回填与流水，
            # 该笔退款资金走原路退回（卡支付部分）/人工处理，不复活卡余额
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

    # 原子累计退款（可退余守卫进 WHERE）：并发双退时输者 rowcount=0 → 409，防丢失更新
    if repo.claim_payment_refund(db, payment.id, refund_amount, full) == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="already_fully_refunded")
    # 原生 UPDATE 不经过身份映射：expire 后重读，payment.status 取到 CAS 写入的新值
    db.expire(payment)

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
    date_to: Optional[str] = None, sort: Optional[str] = None,
    status_in: Optional[list[int]] = None,
) -> dict:
    # 可选每页条数：缺省 10 兼容；显式传值时钳制到 10-100
    pp = PER_PAGE_ORDERS if per_page is None else min(max(per_page, 10), 100)
    # 时间范围闭区间：date_to 补到当日 23:59:59
    start = _parse_date(date_from, "date_from") if date_from else None
    end = None
    if date_to:
        end = _parse_date(date_to, "date_to").replace(hour=23, minute=59, second=59)
    orders, total = repo.paginate_orders(
        db, status=status, status_in=status_in, q=q, page=page, per_page=pp,
        date_from=start, date_to=end, sort=sort,
    )
    return {
        "items": [{
            "order_no": o.order_no, "email": o.email, "status": o.status,
            "grand_total": o.grand_total, "shipping_status": o.shipping_status,
            "note": o.note,
            "placed_at": o.placed_at.isoformat() if o.placed_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "shipped_at": o.shipped_at.isoformat() if o.shipped_at else None,
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
    prev_status = order.status
    if prev_status not in (1, 2):
        raise HTTPException(status_code=409, detail=f"not_shippable:{prev_status}")
    items = repo.order_items(db, order.id)
    now = utcnow()
    # 发货 CAS（WHERE status IN (1,2)）：并发重复发货/已付取消竞态时 rowcount=0 → 409
    if repo.claim_order_shipped(db, order.id, now, body.tracking_no) == 0:
        db.rollback()
        db.expire(order)
        raise HTTPException(status_code=409, detail=f"not_shippable:{order.status}")
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


def prepare_order(db: Session, admin: User, order_no: str) -> dict:
    """后台开始备货：CAS 1→2（与已付取消/发货/重复备货并发互斥，rowcount=0 → 409）"""
    order = _get_order(db, order_no)
    if order.status != 1:
        raise HTTPException(status_code=409, detail=f"not_prepable:{order.status}")
    if repo.claim_order_preparing(db, order.id) == 0:
        db.rollback()
        db.expire(order)
        raise HTTPException(status_code=409, detail=f"not_prepable:{order.status}")
    order.status = 2
    _timeline(db, order.id, "status_changed", actor="admin", detail={"from": 1, "to": 2})
    _admin_log(db, admin, "prepare", "order", order.id, {"from": 1, "to": 2})
    db.commit()
    return {"order_no": order.order_no, "order_status": order.status}


def mark_completed(db: Session, admin: User, order_no: str) -> dict:
    """后台代确认完成：与用户侧 confirm_received 共用 claim_order_completed CAS 原语
    （4→5 并发互斥）；completed_at 落库，积分解冻仍由 worker 按 paid_at+return_days 独立驱动。"""
    order = _get_order(db, order_no)
    if order.status != 4:
        raise HTTPException(status_code=409, detail=f"not_completable:{order.status}")
    now = utcnow()
    if repo.claim_order_completed(db, order.id, now) == 0:
        db.rollback()
        db.expire(order)
        raise HTTPException(status_code=409, detail=f"not_completable:{order.status}")
    # 原生 CAS UPDATE 不经过身份映射：expire 后重读，保证响应携带新状态
    db.expire(order)
    order.completed_at = now
    _timeline(db, order.id, "status_changed", actor="admin", detail={
        "from": 4, "to": 5, "reason": "admin_confirm",
    })
    _admin_log(db, admin, "mark_completed", "order", order.id, {"from": 4, "to": 5})
    db.commit()
    return {"order_no": order.order_no, "order_status": order.status}


def update_order_address(
    db: Session, admin: User, order_no: str, body: OrderAddressUpdateIn | None,
) -> dict:
    """后台订单改地址：仅未发货（status≤2）可改，全字段可选部分更新；
    timeline address_updated 存旧值摘要 + 审计日志。"""
    order = _get_order(db, order_no)
    if order.status > 2:
        raise HTTPException(status_code=409, detail="order already shipped")
    data = body.model_dump(exclude_unset=True) if body else {}
    addr = dict(order.shipping_address or {})
    diff: dict = {}
    for field, new in data.items():
        old = addr.get(field)
        if old != new:
            diff[field] = {"old": old, "new": new}
            addr[field] = new
    if not diff:
        return {"order_no": order.order_no, "shipping_address": addr}
    order.shipping_address = addr
    _timeline(db, order.id, "address_updated", actor="admin", detail={
        "old": {k: v["old"] for k, v in diff.items()},
        "new": {k: v["new"] for k, v in diff.items()},
    })
    _admin_log(db, admin, "update_address", "order", order.id, diff)
    db.commit()
    return {"order_no": order.order_no, "shipping_address": addr}


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
    status_in: Optional[list[int]] = None,
) -> dict:
    rows, total = repo.list_rmas(
        db, status, q=q, page=page, per_page=per_page, status_in=status_in,
    )
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
    # CAS 抢占（WHERE status=0）：并发双击/与 reject 互斥；成功后 expire 重读再补写其余字段
    if repo.claim_rma_approved(db, rma.id) == 0:
        db.rollback()
        db.expire(rma)
        raise HTTPException(status_code=409, detail=f"rma_not_approvable:{rma.status}")
    db.expire(rma)
    rma.label_url = f"https://mock.glowmag.com/label/{rma.rma_no}.pdf"
    rma.handled_by = admin.id
    _timeline(db, rma.order_id, "rma_label_sent", actor="admin", detail={"rma_no": rma.rma_no})
    _admin_log(db, admin, "rma_approve", "return", rma.id, {"rma_no": rma.rma_no, "to": 2})
    db.commit()
    return {"rma_no": rma.rma_no, "status": rma.status, "label_url": rma.label_url}


def reject_rma(db: Session, admin: User, rma_no: str, reason: str | None = None) -> dict:
    """拒绝退货申请（0→6）：不符合政策的申请走此闭环，落时间线与审计日志；
    CAS 抢占（WHERE status=0）与 approve 并发互斥。"""
    rma = _get_rma(db, rma_no)
    if rma.status != 0:
        raise HTTPException(status_code=409, detail=f"rma_not_rejectable:{rma.status}")
    if repo.claim_rma_rejected(db, rma.id) == 0:
        db.rollback()
        db.expire(rma)
        raise HTTPException(status_code=409, detail=f"rma_not_rejectable:{rma.status}")
    db.expire(rma)
    rma.handled_by = admin.id
    # 拒绝释放未决占用（守卫防负数），可退量回补
    repo.release_item_rma(db, rma.order_item_id, rma.qty)
    _timeline(db, rma.order_id, "rma_rejected", actor="admin", detail={
        "rma_no": rma.rma_no, "reason": reason or "",
    })
    _admin_log(db, admin, "rma_reject", "return", rma.id, {
        "rma_no": rma.rma_no, "reason": reason or "",
    })
    db.commit()
    return {"rma_no": rma.rma_no, "status": rma.status}


def receive_rma(db: Session, admin: User, rma_no: str) -> dict:
    rma = _get_rma(db, rma_no)
    if rma.status not in (1, 2, 3):
        raise HTTPException(status_code=409, detail=f"rma_not_receivable:{rma.status}")
    # CAS 抢占（WHERE status IN (1,2,3)）：并发重复收货互斥，成功后再回补库存/流水
    if repo.claim_rma_received(db, rma.id) == 0:
        db.rollback()
        db.expire(rma)
        raise HTTPException(status_code=409, detail=f"rma_not_receivable:{rma.status}")
    item = repo.get_order_item(db, rma.order_item_id)
    repo.release_stock(db, item.variant_id, rma.qty)
    repo.add_stock_movement(
        db, variant_id=item.variant_id, change=rma.qty,
        stock_after=repo.stock_of(db, item.variant_id),
        type=5, ref_type="rma", ref_id=rma.order_id,
    )
    db.expire(rma)
    rma.restock_qty = rma.qty
    rma.received_at = utcnow()
    rma.handled_by = admin.id
    _timeline(db, rma.order_id, "rma_received", actor="admin", detail={"rma_no": rma.rma_no, "restock_qty": rma.qty})
    _admin_log(db, admin, "rma_receive", "return", rma.id, {"rma_no": rma.rma_no, "restock_qty": rma.qty})
    db.commit()
    return {"rma_no": rma.rma_no, "status": rma.status, "restock_qty": rma.restock_qty}


def refund_rma(
    db: Session, admin: User, rma_no: str, body: RmaRefundRequest | None = None,
) -> dict:
    """RMA 退款：缺省按订单实付比例折算（单件全退恰为 grand_total，订单可达 REFUNDED）；
    可选 amount_cents 人工调整（>0 且 ≤ 折算可退额）：低于折算额 → RMA 部分退款(7)，
    等于 → 已退款(5)；订单侧沿用 apply_refund 语义（Payment 累计，全额才驱动订单状态）。"""
    rma = _get_rma(db, rma_no)
    if rma.status != 4:
        raise HTTPException(status_code=409, detail=f"rma_not_refundable:{rma.status}")
    # 退款占用 CAS（refunded_at NULL→非空 + status=4 守卫）：并发双退后者 rowcount=0 → 409；
    # 后续 apply_refund 失败抛异常时整体不提交，CAS 占位一并撤销
    if repo.claim_rma_refund(db, rma.id, utcnow()) == 0:
        db.rollback()
        db.expire(rma)
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
    full_amount = min(amount + refund_shipping, order.grand_total)
    # 多笔 RMA 按比例折算各摊运费可能累计超过剩余可退（apply_refund 会 409 拒绝，
    # RMA 将永远卡在 4 态无法结案）；缺省路径钳到剩余可退，恰好收尾为全额退
    payment = repo.refundable_payment_of_order(db, order.id)
    remaining = (
        payment.amount - payment.refunded_amount if payment is not None else None
    )
    cap = full_amount if remaining is None else min(full_amount, remaining)
    if body is not None and body.amount_cents is not None:
        if body.amount_cents > cap:
            raise HTTPException(status_code=409, detail="invalid refund amount")
        amount = body.amount_cents
    else:
        amount = cap
    partial = amount < full_amount

    # 占用结转 refunded_qty：单语句原子累计（防并发丢失更新），CASE 防负数；
    # 原生 UPDATE 不经过身份映射，expire 后 apply_refund 全额回补路径读到新值
    repo.convert_item_rma_refunded(db, item.id, rma.qty)
    db.expire(item)
    try:
        result = apply_refund(
            db, order, amount, reason=f"rma:{rma.rma_no}", actor="admin", admin=admin,
        )
    except HTTPException as exc:
        if exc.detail != "no_refundable_payment":
            raise
        # 纯礼品卡/积分抵扣单无 Payment 行（对齐换货 _refund_negative_diff 的 bypass 模式）：
        # 纯礼品卡单按整单回补礼品卡，不做 Payment 记账，timeline 手动补 refund_issued
        if order.giftcard_discount > 0:
            _refund_giftcard_debit(db, order)
        repo.add_timeline(db, order.id, "refund_issued", actor="admin", detail={
            "amount": amount, "reason": f"rma:{rma.rma_no}", "full": True,
        })
        result = {"amount": amount, "full": True, "payment_status": None}
    # 低于折算额 → 部分退款(7)；等于（含钳到剩余可退收尾的全额）→ 已退款(5)
    db.expire(rma)
    rma.status = 7 if partial else 5
    rma.refund_amount = amount
    rma.refund_shipping = refund_shipping
    rma.refunded_at = utcnow()
    rma.handled_by = admin.id
    _admin_log(db, admin, "rma_refund", "return", rma.id, {
        "rma_no": rma.rma_no, "amount": amount, "refund_shipping": refund_shipping,
        "partial": partial,
    })
    db.commit()
    return {
        "rma_no": rma.rma_no, "status": rma.status, "refund_amount": amount,
        "refund_shipping": refund_shipping, "partial": partial, **result,
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
    type: Optional[int] = None, date_from: Optional[str] = None,
    date_to: Optional[str] = None, per_page: Optional[int] = None,
) -> dict:
    # 可选每页条数：缺省 20 兼容；显式传值时钳制到 10-100（前端导出传 100）
    pp = PER_PAGE_MOVEMENTS if per_page is None else min(max(per_page, 10), 100)
    # 发生时间范围闭区间（与订单时间筛选同款解析）：date_to 补到当日 23:59:59
    start = _parse_date(date_from, "date_from") if date_from else None
    end = None
    if date_to:
        end = _parse_date(date_to, "date_to").replace(hour=23, minute=59, second=59)
    rows, total = repo.paginate_stock_movements(
        db, variant_id=variant_id, page=page, per_page=pp, type=type,
        date_from=start, date_to=end,
    )
    return {
        "items": [{
            "id": m.id, "variant_id": m.variant_id, "change": m.change,
            "stock_after": m.stock_after, "type": m.type,
            "ref_type": m.ref_type, "ref_id": m.ref_id, "operator": m.operator,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in rows],
        "page": page, "per_page": pp, "total": total,
        "pages": (total + pp - 1) // pp,
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
    data = body.model_dump(exclude_unset=True)
    # 目的地/承运商归一化与创建同口径（strip+upper / strip+lower）
    if data.get("dest_country") is not None:
        data["dest_country"] = data["dest_country"].strip().upper()
    if data.get("carrier") is not None:
        data["carrier"] = data["carrier"].strip().lower()
    # 改唯一键组合（目的地+承运商+方式）前查重，撞已有模板 409
    if any(k in data for k in ("dest_country", "carrier", "method")):
        dup = (
            db.query(ShippingRate)
            .filter(
                ShippingRate.dest_country == data.get("dest_country", r.dest_country),
                ShippingRate.carrier == data.get("carrier", r.carrier),
                ShippingRate.method == data.get("method", r.method),
                ShippingRate.id != r.id,
            )
            .first()
        )
        if dup:
            raise HTTPException(status_code=409, detail="rate_conflict")
    diff: dict = {}
    for field, new in data.items():
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
