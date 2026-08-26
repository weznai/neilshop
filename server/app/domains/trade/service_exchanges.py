"""换货 Exchange 服务 —— 用户侧申请/列表/详情（登录本人或 email 双因子）+ 后台队列与状态机
（0→approve 分流 2 待差价/1 直批 · 2→mark-paid→1 · 1→ship→3 新变体原子扣库存+shipment ·
3→complete→4 旧变体回补+exchanged_qty+负差价退款 · 0→reject→5）；用户侧撤销（0→CAS 删除）与
差价支付（diff_payment_id 挂 Payment 行，mock-pay/webhook 双通道核销）；金额美分，naive UTC。"""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.domains.trade import service_admin
from app.domains.trade.schemas import ExchangeCreateRequest, ShipRequest
from app.models import Exchange, Order, OrderItem, Payment, Shipment, User
from app.services.payment_provider import get_provider, mock_pay_enabled
from app.services.pricing import _setting

EXCHANGEABLE_STATUSES = {1, 2, 3, 4, 5}
STATUS_LABELS = {0: "申请", 1: "批准", 2: "待差价支付", 3: "已发货", 4: "完成", 5: "拒绝"}
PER_PAGE = 10


def _variant_view(v, pmap: dict) -> Optional[dict]:
    if not v:
        return None
    p = pmap.get(v.product_id)
    base = p.title if p else ""
    spec = " ".join(x for x in (v.option1_value, v.option2_value) if x)
    title = f"{base} · {spec}" if base and spec else (base or spec)
    return {"id": v.id, "title": title, "price": v.price}


def _rows_payload(db: Session, rows: list[tuple[Exchange, OrderItem, Order]]) -> list[dict]:
    vids = set()
    for ex, _item, _order in rows:
        vids.add(ex.old_variant_id)
        vids.add(ex.new_variant_id)
    vmap = repo.variants_by_ids(db, list(vids)) if vids else {}
    pmap = repo.products_by_ids(db, {v.product_id for v in vmap.values()})
    out = []
    for ex, item, order in rows:
        out.append({
            "exchange_no": ex.exchange_no,
            "order_no": order.order_no,
            "email": order.email,
            "status": ex.status,
            "status_label": STATUS_LABELS.get(ex.status, str(ex.status)),
            "qty": ex.qty,
            "price_diff": ex.price_diff,
            "shipment_id": ex.shipment_id,
            "created_at": ex.created_at.isoformat() if ex.created_at else None,
            "item": {
                "order_item_id": item.id, "variant_id": item.variant_id,
                "title": item.title_snapshot, "image": item.image,
                "unit_price": item.unit_price, "qty": item.qty,
            } if item else None,
            "old_variant": _variant_view(vmap.get(ex.old_variant_id), pmap),
            "new_variant": _variant_view(vmap.get(ex.new_variant_id), pmap),
        })
    return out


def _email_match(email: Optional[str], order: Order) -> bool:
    return email is not None and email.strip().lower() == order.email.lower()


def _new_exchange_no(db: Session) -> str:
    """换货单号：EX+yymmdd+8hex（列宽 16 顶格）；查重循环防极小概率撞唯一索引 500"""
    for _ in range(3):
        no = "EX" + utcnow().strftime("%y%m%d") + uuid.uuid4().hex[:8].upper()
        if not repo.exchange_by_no(db, no):
            return no
    raise HTTPException(status_code=503, detail="exchange_no conflict, retry")


def _new_shipment_no(db: Session) -> str:
    """重发单号：SP+yymmdd+8hex（列宽 16 顶格）；查重循环防撞唯一索引 500"""
    for _ in range(3):
        no = "SP" + utcnow().strftime("%y%m%d") + uuid.uuid4().hex[:8].upper()
        if not db.query(Shipment.id).filter(Shipment.shipment_no == no).first():
            return no
    raise HTTPException(status_code=503, detail="shipment_no conflict, retry")


def create_exchange(db: Session, user: Optional[User], body: ExchangeCreateRequest) -> dict:
    order = repo.order_by_no(db, body.order_no.strip().upper())
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    is_owner = user is not None and order.user_id == user.id
    if not (is_owner or _email_match(body.email, order)):
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.status not in EXCHANGEABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"not_exchangeable:{order.status}")
    return_days = int(_setting(db, "return_days", 30))
    if order.paid_at and utcnow() - order.paid_at > timedelta(days=return_days):
        raise HTTPException(status_code=409, detail="return_window_closed")

    item = repo.get_order_item(db, body.order_item_id)
    if not item or item.order_id != order.id:
        raise HTTPException(status_code=404, detail="order_item_not_found")
    # 可换余叠加在途量（在途换货 + 未终态 RMA，P0-1）：申请即占额，防 1 件货连发多笔换货
    inflight = repo.exchange_inflight_qty(db, item.id) + repo.rma_inflight_qty(db, item.id)
    available = item.qty - item.refunded_qty - item.exchanged_qty - inflight
    if body.qty > available:
        raise HTTPException(status_code=409, detail=f"qty_exceeds_available:{available}")

    new_v = repo.get_variant(db, body.new_variant_id)
    if not new_v or not new_v.is_active:
        raise HTTPException(status_code=404, detail="variant_not_found")
    if new_v.stock < body.qty:
        raise HTTPException(status_code=409, detail="variant_out_of_stock")
    # CAS 抢占未决占用（可换量含 pending 守卫进 WHERE）：并发重复申请/超量申请 rowcount=0 → 409
    if repo.claim_item_exchange(db, item.id, body.qty) == 0:
        db.rollback()
        db.expire(item)
        available = max(0, item.qty - item.refunded_qty - item.exchanged_qty
                        - item.rma_pending_qty - item.ex_pending_qty)
        raise HTTPException(status_code=409, detail=f"qty_exceeds_available:{available}")

    # 差价按订单实付比例折算实际支付单价（折扣/积分/礼品卡抵扣摊入，对齐 refund_rma 口径）；
    # subtotal=0（纯抵扣单）防护回退原价；int(x+0.5) 取整到分与现有金额口径一致
    if order.subtotal > 0:
        paid_unit = int(item.unit_price * order.grand_total / order.subtotal + 0.5)
    else:
        paid_unit = item.unit_price
    ex = Exchange(
        exchange_no=_new_exchange_no(db),
        order_id=order.id,
        order_item_id=item.id,
        old_variant_id=item.variant_id,
        new_variant_id=new_v.id,
        qty=body.qty,
        price_diff=(new_v.price - paid_unit) * body.qty,
        status=0,
    )
    db.add(ex)
    db.flush()
    repo.add_timeline(db, order.id, "exchange_created", actor="user", detail={
        "exchange_no": ex.exchange_no, "order_item_id": item.id,
        "old_variant_id": item.variant_id, "new_variant_id": new_v.id,
        "qty": ex.qty,
        "price_diff": ex.price_diff, "reason": body.reason,
    })
    db.commit()
    return _rows_payload(db, [(ex, item, order)])[0]


def list_exchanges(
    db: Session, user: Optional[User], email: Optional[str],
    *, page: Optional[int] = None, size: Optional[int] = None,
) -> dict:
    if user is not None:
        rows = repo.list_user_exchanges(db, user.id)
    elif email:
        rows = repo.list_exchanges_by_email(db, email)
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
    items = _rows_payload(db, rows)
    # 分页可选：不传 page 保持全量旧结构（向后兼容）；传了才返回分页四件套
    if page is None:
        return {"items": items}
    size = size or PER_PAGE
    total = len(items)
    return {
        "items": items[(page - 1) * size: page * size],
        "page": page, "size": size, "total": total,
        "pages": (total + size - 1) // size,
    }


def exchange_detail(
    db: Session, user: Optional[User], exchange_no: str, email: Optional[str],
) -> dict:
    ex = repo.exchange_by_no(db, exchange_no.strip().upper())
    if not ex:
        raise HTTPException(status_code=404, detail="exchange_not_found")
    order = repo.get_order(db, ex.order_id)
    is_owner = user is not None and order is not None and order.user_id == user.id
    if not (is_owner or (order is not None and _email_match(email, order))):
        raise HTTPException(status_code=404, detail="exchange_not_found")
    item = repo.get_order_item(db, ex.order_item_id)
    return _rows_payload(db, [(ex, item, order)])[0]


def _get_exchange(db: Session, exchange_no: str) -> Exchange:
    ex = repo.exchange_by_no(db, exchange_no.strip().upper())
    if not ex:
        raise HTTPException(status_code=404, detail="exchange_not_found")
    return ex


def _owned_exchange(
    db: Session, user: Optional[User], exchange_no: str, email: Optional[str] = None,
) -> Exchange:
    """用户侧归属校验（与订单域 ensure_order_owner 同口径）：登录属主 或 email 双因子，
    非本人换货一律 404（不泄露存在性）。"""
    ex = _get_exchange(db, exchange_no)
    order = repo.get_order(db, ex.order_id)
    is_owner = user is not None and order is not None and order.user_id == user.id
    if not (is_owner or (order is not None and _email_match(email, order))):
        raise HTTPException(status_code=404, detail="exchange_not_found")
    return ex


def cancel_exchange(
    db: Session, user: Optional[User], exchange_no: str, email: Optional[str] = None,
) -> dict:
    """误建换货撤销：仅 status=0（申请中）可 CAS 删除，删后可重新申请；非申请中 409。"""
    ex = _owned_exchange(db, user, exchange_no, email)
    deleted = (
        db.query(Exchange)
        .filter(Exchange.id == ex.id, Exchange.status == 0)
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        db.rollback()
        db.expire(ex)
        raise HTTPException(status_code=409, detail=f"exchange_not_cancellable:{ex.status}")
    # 释放未决占用（守卫防负数，rowcount=0 为无害空操作），撤销后可重新申请
    repo.release_item_exchange(db, ex.order_item_id, ex.qty)
    repo.add_timeline(db, ex.order_id, "exchange_withdrawn", actor="user", detail={
        "exchange_no": ex.exchange_no,
    })
    db.commit()
    return {"exchange_no": ex.exchange_no, "status": "canceled"}


def settle_diff_paid(db: Session, ex: Exchange, payment: Payment, *, actor: str) -> bool:
    """差价支付核销（调用方 commit）：CAS 2→1 与 mock-pay/webhook/admin mark-paid 三方互斥；
    抢占成功才推进 payment 为 SUCCESS 并落 timeline，输者幂等返回 False 不重复记账。"""
    if repo.claim_exchange_diff_paid(db, ex.id) == 0:
        return False
    repo.claim_payment_paid(db, payment.id)
    ex.status = 1
    payment.status = 1
    repo.add_timeline(db, ex.order_id, "exchange_diff_paid", actor=actor, detail={
        "exchange_no": ex.exchange_no, "price_diff": ex.price_diff,
        "payment_intent": payment.stripe_payment_intent,
    })
    return True


def create_diff_intent(
    db: Session, user: Optional[User], exchange_no: str, email: Optional[str] = None,
) -> dict:
    """换货差价支付 intent：status=2 专属；Payment 行挂在原订单（amount=price_diff），
    diff_payment_id 双向关联 —— webhook 据此路由到换货核销而非订单 mark_paid。
    mock provider 开关未放行时 409（与订单 create-intent 同门禁）。"""
    ex = _owned_exchange(db, user, exchange_no, email)
    if ex.price_diff <= 0:
        raise HTTPException(status_code=409, detail="no_diff_to_pay")
    if ex.status != 2:
        raise HTTPException(status_code=409, detail=f"exchange_not_awaiting_diff:{ex.status}")
    provider = get_provider(db)
    if provider.name == "mock" and not mock_pay_enabled(db):
        raise HTTPException(status_code=409, detail="mock_provider_disabled")
    # 幂等：已挂 PENDING payment 直接复用（不堆积新行）；已核销 409
    if ex.diff_payment_id:
        payment = db.get(Payment, ex.diff_payment_id)
        if payment is not None:
            if payment.status == 1:
                raise HTTPException(status_code=409, detail="diff_already_paid")
            return {
                "payment_intent": payment.stripe_payment_intent,
                "client_secret": (
                    payment.stripe_checkout_session
                    or f"{payment.stripe_payment_intent}_secret_mock"
                ),
                "amount": payment.amount,
                "redirect_url": "",
            }
    # shim.order_no=exchange_no：Stripe idempotency_key / PayPal request-id 与原订单支付隔离
    intent = provider.create_intent(SimpleNamespace(order_no=ex.exchange_no), ex.price_diff)
    payment = Payment(
        order_id=ex.order_id,
        stripe_payment_intent=intent["payment_intent"],
        stripe_checkout_session=(intent.get("client_secret") or "")[:255],
        amount=ex.price_diff,
        status=0,
    )
    db.add(payment)
    db.flush()
    ex.diff_payment_id = payment.id
    repo.add_timeline(db, ex.order_id, "exchange_diff_intent", actor="user", detail={
        "exchange_no": ex.exchange_no, "price_diff": ex.price_diff,
        "payment_intent": payment.stripe_payment_intent,
    })
    db.commit()
    return {
        "payment_intent": payment.stripe_payment_intent,
        "client_secret": intent["client_secret"],
        "amount": payment.amount,
        "redirect_url": intent.get("redirect_url", ""),
    }


def mock_pay_diff(
    db: Session, user: Optional[User], exchange_no: str, succeed: bool,
    email: Optional[str] = None,
) -> dict:
    """换货差价 mock 支付（仅开关放行时开放）：镜像订单 mock-pay 门禁与失败语义。"""
    if not mock_pay_enabled(db):
        raise HTTPException(status_code=404, detail="not_found")
    provider = get_provider(db)
    if provider.name != "mock":
        raise HTTPException(status_code=409, detail="use_webhook")
    ex = _owned_exchange(db, user, exchange_no, email)
    if ex.status == 1:
        raise HTTPException(status_code=409, detail="diff_already_paid")
    if ex.status != 2:
        raise HTTPException(status_code=409, detail=f"exchange_not_awaiting_diff:{ex.status}")
    payment = db.get(Payment, ex.diff_payment_id) if ex.diff_payment_id else None
    if payment is None:
        raise HTTPException(status_code=404, detail="payment_not_found")
    if payment.status == 1:
        raise HTTPException(status_code=409, detail="diff_already_paid")
    if succeed:
        settle_diff_paid(db, ex, payment, actor="user")
    else:
        payment.status = 2
        payment.failure_reason = "mock_declined"
        repo.add_timeline(db, ex.order_id, "payment_failed", actor="user", detail={
            "payment_intent": payment.stripe_payment_intent,
            "reason": "mock_declined", "exchange_no": ex.exchange_no,
        })
    db.commit()
    db.expire(ex)
    db.expire(payment)
    return {
        "ok": True,
        "exchange_no": ex.exchange_no,
        "exchange_status": ex.status,
        "payment_status": payment.status,
    }


def _admin_log(db: Session, admin: User, action: str, ex: Exchange, diff: dict | None) -> None:
    repo.add_admin_log(
        db, admin_id=admin.id, action=action, entity="exchange",
        entity_id=ex.id, diff_json=diff or {},
    )


def admin_list_exchanges(
    db: Session, status: Optional[int], page: int, size: int = PER_PAGE,
    q: Optional[str] = None,
) -> dict:
    rows, total = repo.paginate_exchanges(db, status=status, page=page, per_page=size, q=q)
    return {
        "items": _rows_payload(db, rows),
        "page": page, "per_page": size, "total": total,
        "pages": (total + size - 1) // size,
    }


def approve_exchange(db: Session, admin: User, exchange_no: str) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 0:
        raise HTTPException(status_code=409, detail=f"exchange_not_approvable:{ex.status}")
    # 订单现态守卫（P1-5）：待付/取消/整退后的订单不可再批准换货（自身状态机看不到订单终态）
    order = repo.get_order(db, ex.order_id)
    if not order or order.status not in service_admin.FULFILLABLE_ORDER_STATUSES:
        raise HTTPException(status_code=409, detail=f"order_state_invalid:{order.status if order else -1}")
    # CAS 抢占（0 → 按 price_diff 分流 2 待差价/1 直批）：与 reject/重复 approve 并发互斥；
    # 原生 UPDATE 不经过身份映射，expire 后重读保证响应 status 与 CAS 写入一致
    if repo.claim_exchange_approved(db, ex.id) == 0:
        db.rollback()
        db.expire(ex)
        raise HTTPException(status_code=409, detail=f"exchange_not_approvable:{ex.status}")
    db.expire(ex)
    repo.add_timeline(db, ex.order_id, "exchange_approved", actor="admin", detail={
        "exchange_no": ex.exchange_no, "to": ex.status, "price_diff": ex.price_diff,
    })
    _admin_log(db, admin, "exchange_approve", ex, {
        "to": ex.status, "price_diff": ex.price_diff,
    })
    db.commit()
    return {"exchange_no": ex.exchange_no, "status": ex.status}


def reject_exchange(db: Session, admin: User, exchange_no: str, reason: Optional[str]) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 0:
        raise HTTPException(status_code=409, detail=f"exchange_not_rejectable:{ex.status}")
    # CAS 抢占（0 → 5 拒绝）：与 approve 并发互斥
    if repo.claim_exchange_rejected(db, ex.id) == 0:
        db.rollback()
        db.expire(ex)
        raise HTTPException(status_code=409, detail=f"exchange_not_rejectable:{ex.status}")
    db.expire(ex)
    # 拒绝释放未决占用（守卫防负数），可换量回补
    repo.release_item_exchange(db, ex.order_item_id, ex.qty)
    repo.add_timeline(db, ex.order_id, "exchange_rejected", actor="admin", detail={
        "exchange_no": ex.exchange_no, "reason": reason,
    })
    _admin_log(db, admin, "exchange_reject", ex, {"to": 5, "reason": reason})
    db.commit()
    return {"exchange_no": ex.exchange_no, "status": ex.status}


def mark_paid_exchange(
    db: Session, admin: User, exchange_no: str, note: Optional[str] = None,
) -> dict:
    """后台代记差价已收：必须携带收款凭据备注（note/流水号，P1-7）——无凭据不落账，
    凭据随 timeline/AdminLog 留痕备查（admin 强置 SUCCESS 属高危记账动作）。"""
    ex = _get_exchange(db, exchange_no)
    if ex.status != 2:
        raise HTTPException(status_code=409, detail=f"exchange_not_awaiting_diff:{ex.status}")
    note = (note or "").strip()
    if not note:
        raise HTTPException(status_code=422, detail="diff_payment_proof_required")
    payment = db.get(Payment, ex.diff_payment_id) if ex.diff_payment_id else None
    if payment is not None:
        # 用户已自助建差价 payment：走共享核销（CAS 互斥 + payment 推进 + timeline）
        settle_diff_paid(db, ex, payment, actor="admin")
        db.expire(ex)
        if ex.status != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"exchange_not_awaiting_diff:{ex.status}")
    else:
        # 无 payment 行的后台代打款：复用 2→1 CAS（与用户自助支付核销并发互斥）
        if repo.claim_exchange_diff_paid(db, ex.id) == 0:
            db.rollback()
            db.expire(ex)
            raise HTTPException(status_code=409, detail=f"exchange_not_awaiting_diff:{ex.status}")
        db.expire(ex)
        repo.add_timeline(db, ex.order_id, "exchange_diff_paid", actor="admin", detail={
            "exchange_no": ex.exchange_no, "price_diff": ex.price_diff, "note": note,
        })
    _admin_log(db, admin, "exchange_mark_paid", ex, {
        "price_diff": ex.price_diff, "to": 1, "note": note,
    })
    db.commit()
    return {"exchange_no": ex.exchange_no, "status": ex.status, "price_diff": ex.price_diff}


def ship_exchange(db: Session, admin: User, exchange_no: str, body: ShipRequest) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 1:
        raise HTTPException(status_code=409, detail=f"exchange_not_shippable:{ex.status}")
    # 订单现态守卫（P1-5）：取消/整退后的订单不可再发换货新品
    order = repo.get_order(db, ex.order_id)
    if not order or order.status not in service_admin.FULFILLABLE_ORDER_STATUSES:
        raise HTTPException(status_code=409, detail=f"order_state_invalid:{order.status if order else -1}")
    # 先 CAS 1→3 抢占（与 mark-paid 竞态/重复发货互斥），再占量/扣库存；
    # 任一失败 db.rollback 整体回滚（CAS 一并撤销，状态不悬空）
    if repo.claim_exchange_shipped(db, ex.id) == 0:
        db.rollback()
        db.expire(ex)
        raise HTTPException(status_code=409, detail=f"exchange_not_shippable:{ex.status}")
    # 发新货前原子占量（P0-1）：exchanged_qty 可换余守卫进 WHERE，与并发 RMA 收货/
    # 整单退款互斥，余量不足（多笔换货穿透）→ 409 回滚连带 CAS 一并撤销
    if repo.claim_item_exchanged(db, ex.order_item_id, ex.qty) == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="qty_exceeded")
    if repo.reserve_stock(db, ex.new_variant_id, ex.qty) == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="variant_out_of_stock")
    repo.add_stock_movement(
        db, variant_id=ex.new_variant_id, change=-ex.qty,
        stock_after=repo.stock_of(db, ex.new_variant_id),
        type=3, ref_type="exchange", ref_id=ex.id,
    )
    now = utcnow()
    shipment = Shipment(
        shipment_no=_new_shipment_no(db),
        order_id=ex.order_id,
        carrier=body.carrier,
        tracking_no=body.tracking_no,
        status=3,
        item_json=[{"orderItemId": ex.order_item_id, "qty": ex.qty}],
        shipped_at=now,
    )
    db.add(shipment)
    db.flush()
    db.expire(ex)
    ex.shipment_id = shipment.id
    repo.add_timeline(db, ex.order_id, "exchange_shipped", actor="admin", detail={
        "exchange_no": ex.exchange_no, "shipment_no": shipment.shipment_no,
        "carrier": body.carrier, "tracking_no": body.tracking_no,
        "new_variant_id": ex.new_variant_id,
    })
    _admin_log(db, admin, "exchange_ship", ex, {
        "shipment_no": shipment.shipment_no, "carrier": body.carrier,
        "tracking_no": body.tracking_no,
    })
    db.commit()
    return {
        "exchange_no": ex.exchange_no, "status": ex.status,
        "shipment_no": shipment.shipment_no,
    }


def _force_payment_refund(db: Session, order: Order, amount: int, ex: Exchange) -> Optional[dict]:
    """负差价退款兜底（apply_refund 可退余校验误拒时）：对齐 apply_refund 部分退账务写法 ——
    Payment.refunded_amount 累计 + status=4、timeline refund_issued，不驱动订单状态变化；
    无可退 Payment 行（纯积分/礼品卡抵扣单）时返回 None（无款可退，不阻断 complete）。"""
    payment = service_admin.goods_payment_of_order(db, order)
    if payment is None or amount <= 0:
        return None
    # 剩余可退额度钳制：不把 refunded_amount 记超实付（apply_refund 误拒绕过校验的兜底路径）
    amount = min(amount, payment.amount - payment.refunded_amount)
    if amount <= 0:
        return None
    payment.refunded_amount += amount
    if payment.status != 3:
        payment.status = 4
    repo.add_timeline(db, order.id, "refund_issued", actor="admin", detail={
        "amount": amount, "reason": f"exchange_diff:{ex.exchange_no}", "full": False,
    })
    return {"amount": amount, "full": False, "payment_status": payment.status}


def _refund_negative_diff(db: Session, ex: Exchange, admin: User) -> Optional[dict]:
    """换货负差价退款（complete 时调用）：|price_diff| 经退款公共路径 apply_refund 退给买家；
    timeline exchange_diff_refunded 标记防重复（重调 complete 本就 409，标记兜底防状态回退重放）。"""
    if ex.price_diff >= 0:
        return None
    if repo.exchange_diff_refunded(db, ex.order_id, ex.exchange_no):
        return None
    amount = -ex.price_diff
    order = repo.get_order(db, ex.order_id)
    try:
        result = service_admin.apply_refund(
            db, order, amount, reason=f"exchange_diff:{ex.exchange_no}",
            actor="admin", admin=admin,
        )
    except HTTPException as exc:
        detail = str(exc.detail)
        bypass = (
            detail in ("no_refundable_payment", "already_fully_refunded")
            or detail.startswith("invalid_refund_amount")
        )
        if not bypass:
            raise
        # 可退余校验误拒（多笔退款累计/积分礼品卡抵扣单）：绕过校验单独走 Payment 退差价
        result = _force_payment_refund(db, order, amount, ex)
    repo.add_timeline(db, ex.order_id, "exchange_diff_refunded", actor="admin", detail={
        "exchange_no": ex.exchange_no, "amount": result["amount"] if result else 0,
        "price_diff": ex.price_diff,
    })
    return result


def complete_exchange(db: Session, admin: User, exchange_no: str) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 3:
        raise HTTPException(status_code=409, detail=f"exchange_not_completable:{ex.status}")
    # CAS 抢占（3→4）：与重复 complete 并发互斥，成功后再回补旧变体/退差价
    if repo.claim_exchange_completed(db, ex.id) == 0:
        db.rollback()
        db.expire(ex)
        raise HTTPException(status_code=409, detail=f"exchange_not_completable:{ex.status}")
    db.expire(ex)
    item = repo.get_order_item(db, ex.order_item_id)
    # 占量已随 ship 原子计入 exchanged_qty（发新货前，P0-1）：complete 只回补旧变体+退差价；
    # 原生 UPDATE 绕过身份映射 → expire 重读现值供 timeline/响应
    db.expire(item)
    repo.release_stock(db, ex.old_variant_id, ex.qty)
    repo.add_stock_movement(
        db, variant_id=ex.old_variant_id, change=ex.qty,
        stock_after=repo.stock_of(db, ex.old_variant_id),
        type=5, ref_type="exchange", ref_id=ex.id,
    )
    # 负差价退给买家：|price_diff| 退款 + 防重复标记（时间线）
    diff_refund = _refund_negative_diff(db, ex, admin)
    repo.add_timeline(db, ex.order_id, "exchange_completed", actor="admin", detail={
        "exchange_no": ex.exchange_no, "restock_variant_id": ex.old_variant_id,
        "exchanged_qty": item.exchanged_qty,
        "diff_refund": diff_refund["amount"] if diff_refund else 0,
    })
    _admin_log(db, admin, "exchange_complete", ex, {
        "to": 4, "restock_variant_id": ex.old_variant_id,
        "exchanged_qty": item.exchanged_qty,
        "diff_refund": diff_refund["amount"] if diff_refund else 0,
    })
    db.commit()
    return {
        "exchange_no": ex.exchange_no, "status": ex.status,
        "exchanged_qty": item.exchanged_qty,
        "diff_refund": diff_refund["amount"] if diff_refund else 0,
    }
