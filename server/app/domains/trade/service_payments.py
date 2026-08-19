"""支付服务 —— intent 创建 / mock-pay 核心事务 / webhook 幂等事件处理。
支付成功核心事务 mark_order_paid 由 mock-pay 与 webhook 共用（调用方 commit）。
真实 Stripe 模式：GM_STRIPE_KEY / GM_STRIPE_WEBHOOK_SECRET（pip install stripe）自动启用；
无密钥或缺包回落 MockProvider，行为与 mock 版一致。"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.models import Order, Payment
from app.services import points as points_svc
from app.services.payment_provider import (
    InvalidSignatureError, MockProvider, ProviderUnavailable,
    WebhookVerificationError, get_provider, normalize_event,
)


def _get_order(db: Session, order_no: str) -> Order:
    order = repo.order_by_no(db, order_no.strip().upper())
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    return order


def _get_payment(db: Session, order_id: int) -> Payment:
    payment = repo.latest_payment_of_order(db, order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="payment_not_found")
    return payment


def _timeline(
    db: Session, order_id: int, event: str,
    actor: str = "system", detail: dict | None = None,
) -> None:
    repo.add_timeline(db, order_id, event, actor=actor, detail=detail)


def _code_discount_of(db: Session, order: Order) -> int:
    tl = repo.checkout_created_event(db, order.id)
    if tl and tl.detail and "code_discount" in tl.detail:
        return int(tl.detail["code_discount"])
    return int(order.discount_total)


def mark_order_paid(
    db: Session, order: Order, payment: Payment, *, source: str = "mock",
) -> None:
    """支付成功核心事务：订单 PAID + 实扣确认 + 积分发放 + Redemption + outbox（调用方 commit）"""
    now = utcnow()
    payment.status = 1
    order.status = 1
    order.paid_at = now

    items = repo.order_items(db, order.id)
    for item in items:
        if not item.variant_id:
            continue
        stock_after = repo.stock_of(db, item.variant_id)
        repo.add_stock_movement(
            db, variant_id=item.variant_id, change=0, stock_after=stock_after,
            type=3, ref_type="order", ref_id=order.id,
        )

    _timeline(db, order.id, "payment_succeeded", detail={
        "payment_intent": payment.stripe_payment_intent,
        "amount": payment.amount, "source": source,
    })
    _timeline(db, order.id, "status_changed", detail={"from": 0, "to": 1})

    repo.add_outbox_event(
        db, aggregate_type="order", aggregate_id=order.id, event_type="order.paid",
        payload={
            "order_no": order.order_no, "grand_total": order.grand_total,
            "email": order.email,
        },
    )

    points_svc.grant_for_order(db, order, order.grand_total // 10)

    for gc in repo.giftcards_to_activate(db, order.id):
        gc.status = 1
        repo.add_giftcard_ledger(
            db, gift_card_id=gc.id, change_type=1,
            amount=gc.initial_amount, balance_after=gc.balance,
        )

    try:
        from app.services.referrals import on_order_paid as _ref_hook
        _ref_hook(db, order)
    except ImportError:
        pass

    if order.user_id:
        user = repo.get_user(db, order.user_id)
        if user:
            user.total_spent += order.grand_total
            user.last_order_at = now

    if order.discount_code_id:
        amount = _code_discount_of(db, order)
        repo.add_discount_redemption(
            db, code_id=order.discount_code_id, order_id=order.id,
            user_id=order.user_id, email=order.email, discount_amount=amount,
        )
        dc = repo.get_discount_code(db, order.discount_code_id)
        if dc:
            dc.used_count += 1


def create_intent(db: Session, order_no: str) -> dict:
    order = _get_order(db, order_no)
    if order.status != 0:
        raise HTTPException(status_code=409, detail=f"order_not_pending:{order.status}")
    try:
        intent = get_provider().create_intent(order, order.grand_total)
    except ProviderUnavailable:
        intent = MockProvider().create_intent(order, order.grand_total)
    payment = Payment(
        order_id=order.id,
        stripe_payment_intent=intent["payment_intent"],
        amount=order.grand_total,
        status=0,
    )
    db.add(payment)
    db.commit()
    return {
        "payment_intent": payment.stripe_payment_intent,
        "client_secret": intent["client_secret"],
        "amount": payment.amount,
    }


def mock_pay(db: Session, order_no: str, succeed: bool) -> dict:
    provider = get_provider()
    order = _get_order(db, order_no)
    payment = _get_payment(db, order.id)
    if provider.name != "mock":
        raise HTTPException(status_code=409, detail="use_webhook")
    if payment.status == 1:
        raise HTTPException(status_code=409, detail="already_paid")
    if provider.confirm(order, payment, succeed):
        mark_order_paid(db, order, payment, source="mock")
    else:
        payment.status = 2
        payment.failure_reason = "mock_declined"
        _timeline(db, order.id, "payment_failed", detail={
            "payment_intent": payment.stripe_payment_intent,
            "reason": "mock_declined",
        })
    db.commit()
    return {
        "ok": True,
        "order_no": order.order_no,
        "order_status": order.status,
        "payment_status": payment.status,
    }


def handle_webhook(db: Session, payload: bytes, stripe_signature: str | None) -> dict:
    provider = get_provider()
    try:
        raw_event = provider.verify_webhook(payload, stripe_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="invalid_signature")
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="invalid_event")
    event = normalize_event(raw_event)
    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]

    existing = repo.get_webhook_event(db, event_id)
    if existing and existing.status == 1:
        return {"ok": True, "duplicate": True}
    if not existing:
        repo.add_webhook_event(
            db, event_id=event_id, source="stripe", type=event_type,
            payload={"id": event_id, "type": event_type, "data": data},
        )
        db.flush()

    payment_intent = (data or {}).get("payment_intent")
    payment = repo.payment_by_intent(db, payment_intent)
    if not payment:
        db.rollback()
        raise HTTPException(status_code=404, detail="payment_intent_not_found")
    order = repo.get_order(db, payment.order_id)
    if not order:
        db.rollback()
        raise HTTPException(status_code=404, detail="order_not_found")

    if event_type == "payment_intent.succeeded":
        if payment.status != 1:
            if order.status != 1:
                mark_order_paid(db, order, payment, source="webhook")
            else:
                payment.status = 1
    elif event_type == "charge.refunded":
        from app.domains.trade.service_admin import apply_refund

        apply_refund(
            db, order, (data or {}).get("amount"),
            reason="webhook:charge.refunded", actor="system",
        )
    else:
        pass

    evt = repo.get_webhook_event(db, event_id)
    evt.status = 1
    evt.processed_at = utcnow()
    db.commit()
    return {"ok": True}
