"""支付服务 —— intent 创建 / mock-pay 核心事务 / webhook 幂等事件处理。
支付成功核心事务 mark_order_paid 由 mock-pay 与 webhook 共用（调用方 commit），
内部对 orders/payments 状态推进做 CAS 抢占（UPDATE ... WHERE status=0/!=1 + rowcount），
抢占失败即并发方已处理 → 幂等返回，不再重复发积分/计数。
赢者语义：先 CAS 订单（WHERE status=0），赢了才推进 payment 为 SUCCESS；
订单已被取消/关单（输者）不碰 payment 状态 —— 防已取消订单的迟到回调假支付。
真实 Stripe 模式：GM_STRIPE_KEY / GM_STRIPE_WEBHOOK_SECRET（pip install stripe）自动启用；
无密钥或缺包回落 MockProvider，行为与 mock 版一致。
环境门禁（GM_ENV，默认 dev）：非 dev 下 mock-pay 404；webhook 在非 dev 且
未配置 provider 验签密钥时 400 拒绝处理。"""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.models import Order, Payment, User
from app.services import points as points_svc
from app.services.payment_provider import (
    InvalidSignatureError, MockProvider, ProviderUnavailable,
    WebhookVerificationError, get_provider, mock_pay_enabled, normalize_event,
)

log = logging.getLogger("glowmag.payments")


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


def ensure_order_owner(
    order: Order, user: User | None, email: str | None,
) -> None:
    """订单归属校验：会员单必须登录本人；游客单 body.email 须与订单 email
    归一化（strip+lower）相等，否则 403 not_order_owner（create-intent/mock-pay 共用，
    置于幂等复用与业务动作之前）。"""
    if order.user_id:
        if user is None or user.id != order.user_id:
            raise HTTPException(status_code=403, detail="not_order_owner")
    elif not email or email.strip().lower() != (order.email or "").strip().lower():
        raise HTTPException(status_code=403, detail="not_order_owner")


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


def _refund_late_success(db: Session, order: Order, payment: Payment) -> None:
    """迟到成功回调的自动退款：订单已取消(8)/已退款(9)时用户在 provider 侧已真实扣款
    —— payment 记 SUCCESS 后全额退（payment→3，订单按退款语义推到 9），仅退资金：
    取消路径已回补库存/积分/礼品卡，不再重复补偿；幂等（已退款/部分退款不二次退）。"""
    if payment.status in (3, 4) or payment.refunded_amount >= payment.amount:
        return
    if payment.status != 1:
        payment.status = 1
        _timeline(db, order.id, "payment_succeeded", detail={
            "payment_intent": payment.stripe_payment_intent,
            "amount": payment.amount, "source": "webhook",
            "late": True, "order_status": order.status,
        })
    refund_amount = payment.amount - payment.refunded_amount
    payment.refunded_amount += refund_amount
    payment.status = 3
    order.status = 9
    repo.add_outbox_event(
        db, aggregate_type="order", aggregate_id=order.id,
        event_type="order.refunded",
        payload={
            "order_no": order.order_no, "amount": refund_amount,
            "full": True, "reason": "late_success_auto_refund",
        },
    )
    _timeline(db, order.id, "refund_issued", detail={
        "amount": refund_amount, "reason": "late_success_auto_refund", "full": True,
    })
    log.warning(
        "late webhook success on canceled/refunded order=%s auto-refunded: "
        "payment=%s amount=%s",
        order.order_no, payment.id, refund_amount,
    )


def mark_order_paid(
    db: Session, order: Order, payment: Payment, *, source: str = "mock",
) -> bool:
    """支付成功核心事务：订单 PAID + 实扣确认 + 积分发放 + Redemption + outbox（调用方 commit）。
    订单状态推进为 CAS 抢占（WHERE status=0）：rowcount=0 说明并发回调已处理或订单已被
    关单/取消 → 输者直接返回 False：不推进 payment（保持原状态，防假支付）、
    不发放积分/ Redemption / 计数。"""
    now = utcnow()
    claimed = repo.claim_order_paid(db, order.id, now)
    if claimed == 0:
        db.expire(order)
        db.expire(payment)
        log.warning(
            "mark_order_paid lost order claim: order=%s is status=%s (canceled/closed "
            "or handled concurrently), late callback keeps payment=%s in status=%s",
            order.order_no, order.status, payment.id, payment.status,
        )
        return False
    repo.claim_payment_paid(db, payment.id)
    order.status = 1
    order.paid_at = now
    payment.status = 1

    items = repo.order_items(db, order.id)
    sold_qty: dict[int, int] = {}
    for item in items:
        if not item.variant_id:
            continue
        stock_after = repo.stock_of(db, item.variant_id)
        repo.add_stock_movement(
            db, variant_id=item.variant_id, change=0, stock_after=stock_after,
            type=3, ref_type="order", ref_id=order.id,
        )
        # 商品销量按 OrderItem 聚合到 product（variant→product 映射）
        variant = repo.get_variant(db, item.variant_id)
        if variant:
            sold_qty[variant.product_id] = sold_qty.get(variant.product_id, 0) + item.qty
    for pid, qty in sold_qty.items():
        # sold_count 原子累计（读改写在并发回调下会丢失更新）
        repo.bump_product_sold_count(db, pid, qty)

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

    # 积分发放：按运营设置 points_per_dollar_earn（$1=100 分 → grand_total*rate//100）
    points_svc.grant_for_order(db, order, order.grand_total * points_svc.earn_rate(db) // 100)

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
            user.last_order_at = now
            # total_spent 原子累计（ORM 读改写并发丢失更新）；tier 晋升读原子更新后现值判断
            # （等级提升非资金关键，允许读侧；≥$100 银 / ≥$300 金，只升不降，
            # 与 seed 离线重算同口径——修复前台进度条"即将升级"承诺后端从不兑现的问题）
            total_spent = repo.add_user_total_spent(db, order.user_id, order.grand_total)
            if total_spent >= 30000 and user.tier < 2:
                user.tier = 2
                user.tier_updated_at = now
            elif total_spent >= 10000 and user.tier < 1:
                user.tier = 1
                user.tier_updated_at = now

    if order.discount_code_id:
        amount = _code_discount_of(db, order)
        repo.add_discount_redemption(
            db, code_id=order.discount_code_id, order_id=order.id,
            user_id=order.user_id, email=order.email, discount_amount=amount,
        )
        # used_count 原子自增（限额守卫进 WHERE）：并发多单抢同码不超发；
        # rowcount=0 = 已达上限 —— 支付已成功，超发一次比丢单好，仅告警不回滚
        if repo.bump_discount_used_count(db, order.discount_code_id) == 0:
            log.warning(
                "discount_code %s usage_limit exceeded on paid order=%s: "
                "over-issue accepted (payment already captured, order kept)",
                order.discount_code_id, order.order_no,
            )
    return True


def create_intent(
    db: Session, order_no: str, *, user: User | None = None,
    email: str | None = None,
) -> dict:
    order = _get_order(db, order_no)
    ensure_order_owner(order, user, email)
    if order.status != 0:
        raise HTTPException(status_code=409, detail=f"order_not_pending:{order.status}")
    provider = get_provider(db)
    # 环境门禁：mock 开关未放行时禁止 mock intent（无真实凭据时宁可 409 也不静默降级 mock）
    if provider.name == "mock" and not mock_pay_enabled(db):
        raise HTTPException(status_code=409, detail="mock_provider_disabled")
    # 幂等：同单同 provider 已有 PENDING payment 直接复用返回，不堆积新行（跨 provider 建新）
    pending = repo.pending_payment_of_order(db, order.id, provider=provider.name)
    if pending:
        return {
            "payment_intent": pending.stripe_payment_intent,
            "client_secret": (
                pending.stripe_checkout_session
                or f"{pending.stripe_payment_intent}_secret_mock"
            ),
            "amount": pending.amount,
            "redirect_url": "",
        }
    try:
        intent = provider.create_intent(order, order.grand_total)
    except ProviderUnavailable:
        if not mock_pay_enabled(db):
            raise HTTPException(status_code=409, detail="mock_provider_disabled")
        intent = MockProvider().create_intent(order, order.grand_total)
    payment = Payment(
        order_id=order.id,
        stripe_payment_intent=intent["payment_intent"],
        stripe_checkout_session=(intent.get("client_secret") or "")[:255],
        amount=order.grand_total,
        status=0,
    )
    db.add(payment)
    db.commit()
    # 双击/并发防护：先查后插的窗口可能堆积多条 PENDING —— 提交后废弃同 provider
    # 旧行（status=2 superseded），只保留最新一笔待支付
    superseded = repo.supersede_stale_pending(db, payment)
    if superseded:
        db.commit()
        log.info("superseded %d stale PENDING payment(s) for order=%s",
                 superseded, order.order_no)
    return {
        "payment_intent": payment.stripe_payment_intent,
        "client_secret": intent["client_secret"],
        "amount": payment.amount,
        "redirect_url": intent.get("redirect_url", ""),
    }


def mock_pay(
    db: Session, order_no: str, succeed: bool, *,
    user: User | None = None, email: str | None = None,
) -> dict:
    # 环境门禁：mock 支付仅在开关放行时开放（后台 settings mock_pay / GM_MOCK_PAY，默认 dev）
    if not mock_pay_enabled(db):
        raise HTTPException(status_code=404, detail="not_found")
    provider = get_provider(db)
    order = _get_order(db, order_no)
    ensure_order_owner(order, user, email)
    if provider.name != "mock":
        raise HTTPException(status_code=409, detail="use_webhook")
    payment = _get_payment(db, order.id)
    if payment.status == 1:
        db.expire(order)
        return {
            "ok": True,
            "order_no": order.order_no,
            "order_status": order.status,
            "payment_status": payment.status,
        }
    # provider 一致性：全局为 mock 时只允许核销 mock 前缀 PI（Payment 无 provider 列，
    # 以 PI 前缀判定）—— 防真实 provider 建的 PI 被通道切换后的 mock 假支付核销
    if not (payment.stripe_payment_intent or "").startswith("PI_"):
        raise HTTPException(status_code=409, detail="provider_mismatch")
    if provider.confirm(order, payment, succeed):
        # CAS 抢占失败（并发回调已处理/订单已取消）→ 直接按现状返回成功响应（幂等）
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


# webhook 不可恢复错误前缀：数据状态永久无法推进（PI 不存在/订单丢失/已全退/无可退行），
# 重试永远同结果 → 标记 status=2 落库并 200 skipped，避免 provider 无限重推打爆日志
_UNRECOVERABLE_PREFIXES = (
    "payment_intent_not_found", "order_not_found",
    "no_refundable_payment", "already_fully_refunded",
)


def handle_webhook(
    db: Session, payload: bytes, stripe_signature: str | None,
    headers: dict | None = None,
) -> dict:
    provider = get_provider(db)
    # 环境门禁：非 dev 必须配置对应 provider 的验签密钥，否则任何人可伪造回调
    # （密钥取自 provider 生效配置——settings 表 payment_config 或环境变量，二选一非空即通过）
    if settings.env != "dev" and not provider.webhook_gate_secret():
        raise HTTPException(status_code=400, detail="webhook_secret_not_configured")
    try:
        raw_event = provider.verify_webhook(payload, stripe_signature, headers=headers)
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
    if existing and existing.status == 2:
        # 曾判定不可恢复（skipped）的事件再推送：直接幂等跳过
        return {"ok": True, "skipped": True}
    if not existing:
        repo.add_webhook_event(
            db, event_id=event_id, source="stripe", type=event_type,
            payload={"id": event_id, "type": event_type, "data": data},
        )
        db.flush()

    try:
        payment_intent = (data or {}).get("payment_intent")
        payment = repo.payment_by_intent(db, payment_intent)
        if not payment:
            raise HTTPException(status_code=404, detail="payment_intent_not_found")
        order = repo.get_order(db, payment.order_id)
        if not order:
            raise HTTPException(status_code=404, detail="order_not_found")

        # 换货差价 payment（diff_payment_id 关联）：路由到换货核销，不走订单 mark_paid
        # —— 原订单已付（status>=1），CAS 抢占必然失败，旧路径会把差价回调变成空转。
        linked_ex = repo.exchange_by_diff_payment(db, payment.id)
        if linked_ex is not None:
            if event_type == "payment_intent.succeeded" and payment.status != 1:
                from app.domains.trade.service_exchanges import settle_diff_paid

                settle_diff_paid(db, linked_ex, payment, actor="system")
        elif event_type == "payment_intent.succeeded":
            if payment.status != 1:
                if order.status != 1:
                    paid = mark_order_paid(db, order, payment, source="webhook")
                    if not paid:
                        # CAS 输者：订单已被取消/关单(8)或已退款(9) → 迟到成功自动退款；
                        # 其余（并发已处理）保持幂等不报错
                        db.expire(order)
                        if order.status in (8, 9):
                            _refund_late_success(db, order, payment)
                else:
                    payment.status = 1
        elif event_type == "charge.refunded":
            from app.domains.trade.service_admin import apply_refund

            cumulative = (data or {}).get("cumulative_refunded")
            if cumulative is not None:
                # 累计口径求增量：delta = 累计退款 - 已记账 refunded_amount；
                # delta<=0（重复推送/旧事件回放）跳过，防止 amount_refunded 重复入账
                delta = int(cumulative) - int(payment.refunded_amount or 0)
                if delta > 0:
                    apply_refund(
                        db, order, delta,
                        reason="webhook:charge.refunded", actor="system",
                    )
            else:
                apply_refund(
                    db, order, (data or {}).get("amount"),
                    reason="webhook:charge.refunded", actor="system",
                )
        else:
            pass
    except HTTPException as exc:
        detail = str(exc.detail)
        if not any(detail.startswith(p) for p in _UNRECOVERABLE_PREFIXES):
            raise
        # rollback（撤回上面的 WebhookEvent 插入）→ 重插并标记 status=2 + 告警 + 200 skipped
        db.rollback()
        repo.add_webhook_event(
            db, event_id=event_id, source="stripe", type=event_type,
            payload={"id": event_id, "type": event_type, "data": data},
        )
        db.flush()
        evt = repo.get_webhook_event(db, event_id)
        evt.status = 2
        evt.processed_at = utcnow()
        db.commit()
        log.warning("webhook event %s unrecoverable, marked status=2 and skipped: %s",
                    event_id, detail)
        return {"ok": True, "skipped": detail}

    evt = repo.get_webhook_event(db, event_id)
    evt.status = 1
    evt.processed_at = utcnow()
    db.commit()
    return {"ok": True}
