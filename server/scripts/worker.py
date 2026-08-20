"""GLOWMAG 后台任务 worker —— outbox 消费/超时关单/弃购三封阶梯召回/积分过期/每日对账（standalone 进程 + MySQL GET_LOCK 单实例）"""

import argparse
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine, utcnow
from app.core.enums import OrderStatus, PointsReason, StockMovementType
from app.models import (
    Cart, DataRequest, EmailPreference, Order, OrderItem, OrderTimeline,
    OutboxEvent, Payment, PointsLedger, Product, ReconciliationDaily, Rma,
    Setting, StockMovement, StockNotification, User, UserAddress, Variant,
    WishlistItem,
)
from app.services import emails
from app.services import points as points_svc

log = logging.getLogger("glowmag.worker")

LOCK_NAME = "glowmag_worker"
OUTBOX_BATCH = 50
OUTBOX_MAX_RETRY = 5
ABANDON_LIMIT = 100
ABANDON_STAGES = (
    (timedelta(hours=1), "ABANDON10"),
    (timedelta(hours=24), "ABANDON15"),
    (timedelta(hours=72), None),
)
_ABANDON_SUBJECTS = {
    1: "Still thinking about your GLOWMAG cart?",
    2: "15% off your favorites",
    3: "Last call: your cart items are almost gone",
}

_EVENT_EMAILS = {
    "order.paid": ("order_paid", "Order {order_no} confirmed - thank you!"),
    "order.shipped": ("order_shipped", "Your order {order_no} has shipped!"),
    "order.refunded": ("order_refunded", "Refund confirmed for order {order_no}"),
    "cart.abandoned": ("abandoned_cart",
                       lambda p: _ABANDON_SUBJECTS.get(p.get("stage"),
                                                       "Your GLOWMAG picks are still waiting")),
    "user.welcome": ("welcome_coupon", "Welcome to GLOWMAG - 10% off inside"),
    "stock.restocked": ("restock_notify", "Back in stock: {product_title}"),
}

# 营销类事件 → EmailPreference 开关（sub_promo=0 或 unsubscribed_at 非空 → 消费侧跳过不发）；
# 事务性邮件（order.*/stock.restocked）不受限；cart.abandoned 已在 scan_abandoned_carts 侧过滤
_MARKETING_PREF_KEYS = {
    "user.welcome": "sub_promo",
}

_STAGE_ADVANCE_SQL = text(
    "UPDATE carts SET abandoned_mails_sent = :next_stage, recovery_token = :token "
    "WHERE id = :cart_id AND abandoned_mails_sent = :stage"
)

_RELEASE_SQL = text(
    "UPDATE variants SET stock = stock + :qty, version = version + 1 WHERE id = :vid"
)
_STOCK_SQL = text("SELECT stock FROM variants WHERE id = :vid")
# 超时关单 CAS 抢占：rowcount=1 才回补库存/写流水，与支付回调（mark_order_paid 的
# WHERE status=0 抢占）互斥，杜绝 paid+canceled 脏状态与库存双释放
_CLOSE_CLAIM_SQL = text(
    "UPDATE orders SET status = 8, canceled_at = :now, cancel_reason = 'timeout' "
    "WHERE id = :oid AND status = 0"
)
_LAST_LEDGER_SQL = text(
    "SELECT COALESCE(SUM(balance_after), 0) FROM ("
    "  SELECT balance_after,"
    "         ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id DESC) AS rn"
    "  FROM points_ledger"
    ") t WHERE rn = 1"
)


def _setting_int(db: Session, key: str, default: int) -> int:
    row = db.get(Setting, key)
    if row is not None and row.value is not None:
        try:
            return int(row.value)
        except (TypeError, ValueError):
            pass
    return default


def _fmt_subject(tpl: str, payload: dict) -> str:
    try:
        return tpl.format(**payload)
    except (KeyError, IndexError, ValueError):
        return "GLOWMAG update"


def consume_outbox(db: Session) -> None:
    events = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.published == 0, OutboxEvent.retry_count < OUTBOX_MAX_RETRY)
        .order_by(OutboxEvent.id).limit(OUTBOX_BATCH).all()
    )
    emailed = skipped = failed = compliance_skipped = 0
    for ev in events:
        try:
            payload = dict(ev.payload or {})
            if not payload.get("email") and ev.aggregate_type == "order":
                order = db.get(Order, ev.aggregate_id)
                if order is None and payload.get("order_no"):
                    order = db.query(Order).filter(Order.order_no == payload["order_no"]).first()
                if order:
                    payload["email"] = order.email
            mapping = _EVENT_EMAILS.get(ev.event_type)
            if mapping and payload.get("email"):
                pref_key = _MARKETING_PREF_KEYS.get(ev.event_type)
                if pref_key:
                    pref = db.get(EmailPreference, payload["email"])
                    if pref and (getattr(pref, pref_key) == 0
                                 or pref.unsubscribed_at is not None):
                        ev.published = 1
                        ev.published_at = utcnow()
                        db.commit()
                        compliance_skipped += 1
                        continue
                template, subject_tpl = mapping
                subject = (subject_tpl(payload) if callable(subject_tpl)
                           else _fmt_subject(subject_tpl, payload))
                emails.deliver(
                    payload["email"], subject,
                    emails.render(template, **payload),
                )
                emailed += 1
            else:
                skipped += 1
            ev.published = 1
            ev.published_at = utcnow()
            db.commit()
        except Exception:
            db.rollback()
            ev.retry_count = (ev.retry_count or 0) + 1
            db.commit()
            failed += 1
            log.exception("outbox event %s (%s) failed", ev.id, ev.event_type)
    log.info("[outbox] picked=%d emailed=%d no_email=%d failed=%d compliance_skipped=%d",
             len(events), emailed, skipped, failed, compliance_skipped)


def cancel_timeout_orders(db: Session) -> None:
    timeout_min = _setting_int(db, "order_timeout_minutes", 30)
    cutoff = utcnow() - timedelta(minutes=timeout_min)
    orders = (
        db.query(Order)
        .filter(Order.status == int(OrderStatus.PENDING), Order.placed_at < cutoff)
        .order_by(Order.id).all()
    )
    canceled = released = 0
    for order in orders:
        try:
            now = utcnow()
            # CAS 抢占：仅当订单仍为 PENDING 时置 CANCELED；支付回调已抢先置 PAID
            # 则 rowcount=0，直接跳过（不回补库存/不写流水），避免互踩
            if db.execute(_CLOSE_CLAIM_SQL, {"oid": order.id, "now": now}).rowcount != 1:
                db.rollback()
                continue
            order.status = int(OrderStatus.CANCELED)
            order.canceled_at = now
            order.cancel_reason = "timeout"
            items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
            for item in items:
                remaining = item.qty - item.refunded_qty
                if remaining <= 0:
                    continue
                db.execute(_RELEASE_SQL, {"vid": item.variant_id, "qty": remaining})
                stock_after = int(db.execute(_STOCK_SQL, {"vid": item.variant_id}).scalar())
                db.add(StockMovement(
                    variant_id=item.variant_id, change=remaining, stock_after=stock_after,
                    type=int(StockMovementType.RELEASE), ref_type="order", ref_id=order.id,
                ))
                released += remaining
            # 超时关单返还该单已用积分（points_used=0 跳过，同单幂等）
            points_svc.refund_return(db, order, order.user_id, order.points_used)
            db.add(OrderTimeline(
                order_id=order.id, event="status_changed", actor="system",
                detail={"from": int(OrderStatus.PENDING), "to": int(OrderStatus.CANCELED),
                        "reason": "timeout"},
            ))
            db.add(OutboxEvent(
                aggregate_type="order", aggregate_id=order.id, event_type="order.canceled",
                payload={"order_no": order.order_no, "reason": "timeout"},
            ))
            db.commit()
            canceled += 1
        except Exception:
            db.rollback()
            log.exception("timeout-cancel order %s failed", order.order_no)
    log.info("[timeout-cancel] canceled=%d stock_released=%d timeout=%dmin",
             canceled, released, timeout_min)


def scan_abandoned_carts(db: Session) -> None:
    now = utcnow()
    carts = (
        db.query(Cart)
        .filter(Cart.updated_at < now - ABANDON_STAGES[0][0],
                Cart.abandoned_mails_sent < len(ABANDON_STAGES),
                Cart.email.isnot(None), Cart.email != "")
        .order_by(Cart.id).limit(ABANDON_LIMIT).all()
    )
    sent = [0, 0, 0]
    compliance_skipped = 0
    for cart in carts:
        items = cart.items or []
        if not items:
            continue
        stage = cart.abandoned_mails_sent
        window, coupon = ABANDON_STAGES[stage]
        if cart.updated_at >= now - window:
            continue
        pref = db.get(EmailPreference, cart.email)
        if pref and (pref.sub_cart_abandon == 0 or pref.unsubscribed_at is not None):
            compliance_skipped += 1
            continue
        summary = []
        for it in items[:10]:
            vid = it.get("variantId")
            title = f"Item #{vid}"
            stock = None
            row = (
                db.query(Variant, Product)
                .join(Product, Variant.product_id == Product.id)
                .filter(Variant.id == vid).first()
            )
            if row:
                title = f"{row[1].title} · {row[0].option1_value}"
                stock = row[0].stock
            summary.append({"title": title, "qty": int(it.get("qty") or 0),
                            "stock": stock, "variant_id": vid})
        token = uuid.uuid4().hex
        advanced = db.execute(
            _STAGE_ADVANCE_SQL,
            {"next_stage": stage + 1, "token": token, "cart_id": cart.id, "stage": stage},
        ).rowcount
        if not advanced:
            db.rollback()
            continue
        db.add(OutboxEvent(
            aggregate_type="cart", aggregate_id=cart.id, event_type="cart.abandoned",
            payload={"email": cart.email, "recovery_token": token,
                     "recovery_link": f"https://glowmag.com/cart?rc={token}",
                     "stage": stage + 1, "coupon_code": coupon, "items": summary},
        ))
        db.commit()
        sent[stage] += 1
    log.info("[abandoned-cart] scanned=%d sent_stage1=%d sent_stage2=%d sent_stage3=%d "
             "compliance_skipped=%d", len(carts), sent[0], sent[1], sent[2], compliance_skipped)


def expire_points(db: Session) -> None:
    now = utcnow()
    rows = (
        db.query(PointsLedger)
        .filter(PointsLedger.frozen == 0, PointsLedger.change > 0,
                PointsLedger.expires_at.isnot(None), PointsLedger.expires_at < now)
        .order_by(PointsLedger.user_id, PointsLedger.id).all()
    )
    by_user: dict[int, list[PointsLedger]] = {}
    for r in rows:
        by_user.setdefault(r.user_id, []).append(r)
    expired_users = expired_points = 0
    for user_id, ledgers in by_user.items():
        user = db.get(User, user_id)
        amount = min(sum(r.change for r in ledgers), user.points) if (user and user.points > 0) else 0
        for r in ledgers:
            r.expires_at = None
        if amount > 0:
            user.points -= amount
            db.add(PointsLedger(
                user_id=user_id, change=-amount, balance_after=user.points,
                reason=int(PointsReason.EXPIRE), frozen=0, expires_at=None,
            ))
            expired_users += 1
            expired_points += amount
        db.commit()
    log.info("[points-expire] rows=%d users=%d expired=%d", len(rows), expired_users, expired_points)


def reconcile_daily(db: Session) -> None:
    now = utcnow()
    today = now.date()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    payments_gross = int(db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.status.in_([1, 3, 4]), Payment.created_at >= day_start).scalar())
    orders_paid_total = int(db.query(func.coalesce(func.sum(Order.grand_total), 0)).filter(
        Order.status >= 1, Order.paid_at.isnot(None), Order.paid_at >= day_start).scalar())
    diff_payment = payments_gross - orders_paid_total
    points_ledger_sum = int(db.query(func.coalesce(func.sum(User.points), 0)).scalar())
    users_points_sum = int(db.execute(_LAST_LEDGER_SQL).scalar())
    diff_points = points_ledger_sum - users_points_sum
    status = 1 if abs(diff_payment) > 1 or diff_points != 0 else 0
    row = db.query(ReconciliationDaily).filter(
        ReconciliationDaily.reconcile_date == today).first()
    if row is None:
        row = ReconciliationDaily(reconcile_date=today)
        db.add(row)
    row.payments_gross = payments_gross
    row.orders_paid_total = orders_paid_total
    row.diff_payment = diff_payment
    row.diff_refund = 0
    row.points_ledger_sum = points_ledger_sum
    row.users_points_sum = users_points_sum
    row.diff_points = diff_points
    row.status = status
    row.checked_at = now
    db.commit()
    log.info("[reconcile] date=%s payments_gross=%d orders_paid=%d diff_payment=%d "
             "points_sum=%d ledger_last=%d diff_points=%d status=%d",
             today, payments_gross, orders_paid_total, diff_payment,
             points_ledger_sum, users_points_sum, diff_points, status)


def unfreeze_points(db: Session) -> None:
    """退货期满且无未完结 RMA 的冻结积分解冻（paid_at + return_days 之后）"""
    return_days = _setting_int(db, "return_days", 30)
    cutoff = utcnow() - timedelta(days=return_days)
    rows = (db.query(PointsLedger)
            .filter(PointsLedger.frozen == 1, PointsLedger.change > 0,
                    PointsLedger.ref_type == "order", PointsLedger.created_at < cutoff)
            .limit(500).all())
    scanned = unfrozen = 0
    for row in rows:
        scanned += 1
        order = db.get(Order, row.ref_id) if row.ref_id else None
        if (not order or not order.paid_at or order.paid_at > cutoff
                or order.status in (8, 9)):
            continue
        has_open_rma = (db.query(Rma.id)
                        .filter(Rma.order_id == order.id, Rma.status.in_([0, 1, 2, 3, 4]))
                        .first())
        if has_open_rma:
            continue
        row.frozen = 0
        unfrozen += 1
    if unfrozen:
        db.commit()
    log.info("[points-unfreeze] rows=%d scanned=%d unfrozen=%d", len(rows), scanned, unfrozen)


def process_data_requests(db: Session) -> None:
    grace_days = _setting_int(db, "gdpr_delete_delay_days", 7)
    cutoff = utcnow() - timedelta(days=grace_days)
    requests = (
        db.query(DataRequest)
        .filter(DataRequest.type == 2, DataRequest.status == 0,
                DataRequest.created_at < cutoff)
        .order_by(DataRequest.id).all()
    )
    anonymized = 0
    for req in requests:
        user = db.get(User, req.user_id)
        if user is not None:
            anon_email = f"deleted+{user.id}@anonymized.local"
            user.email = anon_email
            user.password_hash = None
            user.name = ""
            user.points = 0
            user.status = -1
            user.birthday = None
            db.query(UserAddress).filter(UserAddress.user_id == user.id).delete(
                synchronize_session=False)
            db.query(Cart).filter(Cart.user_id == user.id).delete(
                synchronize_session=False)
            db.query(WishlistItem).filter(WishlistItem.user_id == user.id).delete(
                synchronize_session=False)
            for order in db.query(Order).filter(Order.user_id == user.id).all():
                order.email = anon_email
                addr = dict(order.shipping_address or {})
                addr["full_name"] = "Deleted User"
                addr["phone"] = ""
                order.shipping_address = addr
            anonymized += 1
        req.status = 1
        req.fulfilled_at = utcnow()
        db.commit()
        log.info("[gdpr] data request %s fulfilled, user %s anonymized", req.id, req.user_id)
    log.info("[gdpr] due=%d anonymized=%d grace=%dd", len(requests), anonymized, grace_days)


def restock_notify(db: Session) -> None:
    """到货通知：pending（notified_at IS NULL）订阅 join 已回补（stock>0）变体
    → 逐条 outbox(stock.restocked)（消费端 _EVENT_EMAILS 已映射 restock_notify 邮件）
    + notified_at 置位防重复。"""
    now = utcnow()
    rows = (
        db.query(StockNotification, Variant, Product)
        .join(Variant, Variant.id == StockNotification.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .filter(StockNotification.notified_at.is_(None), Variant.stock > 0)
        .order_by(StockNotification.id)
        .all()
    )
    notified = 0
    for sn, v, p in rows:
        db.add(OutboxEvent(
            aggregate_type="stock", aggregate_id=sn.variant_id,
            event_type="stock.restocked",
            payload={"email": sn.email, "variant_id": v.id, "sku": v.sku,
                     "product_title": p.title, "variant": v.option1_value,
                     "stock": v.stock},
        ))
        sn.notified_at = now
        notified += 1
    if notified:
        db.commit()
    log.info("[restock-notify] pending=%d notified=%d", len(rows), notified)


def publish_scheduled(db: Session) -> None:
    """定时上架巡检（查询时生效，无需改 status）：
    - 统计未来 published_at 商品数（运营巡检）；
    - 轻量到点通知：水位线（settings key=last_publish_scan）之后才到点的商品
      发 outbox(product.published, payload 含 slug/title)；水位推进防重复。"""
    now = utcnow()
    upcoming = (
        db.query(func.count()).select_from(Product)
        .filter(Product.status == 1, Product.published_at.isnot(None),
                Product.published_at > now)
        .scalar()
    ) or 0
    row = db.get(Setting, "last_publish_scan")
    watermark = None
    if row is not None and row.value:
        try:
            watermark = datetime.fromisoformat(str(row.value))
        except (TypeError, ValueError):
            watermark = None
    scanned_from = watermark or (now - timedelta(days=1))
    due = (
        db.query(Product)
        .filter(Product.status == 1, Product.published_at.isnot(None),
                Product.published_at > scanned_from, Product.published_at <= now)
        .order_by(Product.id)
        .all()
    )
    for p in due:
        db.add(OutboxEvent(
            aggregate_type="product", aggregate_id=p.id, event_type="product.published",
            payload={"slug": p.slug, "title": p.title},
        ))
    if row is None:
        db.add(Setting(key="last_publish_scan", value=now.isoformat(),
                       description="定时上架扫描水位（ISO 时间戳，防重复发 product.published）"))
    else:
        row.value = now.isoformat()
    db.commit()
    log.info("[publish-scheduled] upcoming=%d newly_visible=%d watermark=%s",
             upcoming, len(due), scanned_from.isoformat())


def daily_digest(db: Session) -> None:
    """运营日报（昨日 00:00-24:00 UTC）：GMV/订单/支付/退款/新增/待办清单/Top3/库存预警
    → settings key=digest_recipients（JSON 数组，默认 ["ops@glowmag.com"]）循环 deliver（不走 outbox）；
    水位线（settings key=digest_last_date）!= 昨天才执行，执行后写回防同日重复（抄 publish_scheduled 模式）。
    昨日窗口零支付侧活动（GMV/支付/退款/新用户/Top 全 0）→ 不投递（sent=0）仅推水位。"""
    from app.models import Exchange, Review, Ticket, UgcSubmission

    now = utcnow()
    target = (now - timedelta(days=1)).date()
    row = db.get(Setting, "digest_last_date")
    if row is not None and str(row.value) == target.isoformat():
        return
    day_start = datetime(target.year, target.month, target.day)
    day_end = day_start + timedelta(days=1)

    gmv = int(db.query(func.coalesce(func.sum(Order.grand_total), 0)).filter(
        Order.status >= 1, Order.paid_at.isnot(None),
        Order.paid_at >= day_start, Order.paid_at < day_end).scalar())
    paid_count = int(db.query(func.count(Order.id)).filter(
        Order.status >= 1, Order.paid_at.isnot(None),
        Order.paid_at >= day_start, Order.paid_at < day_end).scalar() or 0)
    orders = int(db.query(func.count(Order.id)).filter(
        Order.placed_at >= day_start, Order.placed_at < day_end).scalar() or 0)
    refund_count = int(db.query(func.count(Rma.id)).filter(
        Rma.refunded_at.isnot(None),
        Rma.refunded_at >= day_start, Rma.refunded_at < day_end).scalar() or 0)
    refund_amount = int(db.query(func.coalesce(func.sum(Rma.refund_amount), 0)).filter(
        Rma.refunded_at.isnot(None),
        Rma.refunded_at >= day_start, Rma.refunded_at < day_end).scalar())
    new_users = int(db.query(func.count(User.id)).filter(
        User.created_at >= day_start, User.created_at < day_end).scalar() or 0)
    carts = db.query(Cart).filter(
        Cart.updated_at >= day_start, Cart.updated_at < day_end).all()
    abandoned_new = sum(1 for c in carts if c.items)
    todos = [
        ("Pending orders", db.query(func.count(Order.id)).filter(
            Order.status == 0).scalar() or 0),
        ("RMA to review", db.query(func.count(Rma.id)).filter(
            Rma.status == 0).scalar() or 0),
        ("Exchanges to review", db.query(func.count(Exchange.id)).filter(
            Exchange.status == 0).scalar() or 0),
        ("Reviews to moderate", db.query(func.count(Review.id)).filter(
            Review.status == 0).scalar() or 0),
        ("UGC to moderate", db.query(func.count(UgcSubmission.id)).filter(
            UgcSubmission.status == 0).scalar() or 0),
        ("Open tickets", db.query(func.count(Ticket.id)).filter(
            Ticket.status.in_([0, 1, 2])).scalar() or 0),
    ]
    top_rows = (
        db.query(OrderItem.product_slug, func.coalesce(func.sum(OrderItem.qty), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status >= 1, Order.paid_at.isnot(None),
                Order.paid_at >= day_start, Order.paid_at < day_end)
        .group_by(OrderItem.product_slug)
        .order_by(func.sum(OrderItem.qty).desc(), OrderItem.product_slug.asc())
        .limit(3).all()
    )
    slugs = [r[0] for r in top_rows]
    titles = ({r[0]: r[1] for r in db.query(Product.slug, Product.title)
               .filter(Product.slug.in_(slugs)).all()} if slugs else {})
    top_products = [{"slug": sl, "title": titles.get(sl, sl), "qty": int(q)}
                    for sl, q in top_rows]
    low_stock_count = int(db.query(func.count(Variant.id)).filter(
        Variant.stock <= 8).scalar() or 0)

    recipients = ["ops@glowmag.com"]
    pref = db.get(Setting, "digest_recipients")
    if pref is not None and isinstance(pref.value, list) and pref.value:
        recipients = [str(x) for x in pref.value if x]

    ctx = {
        "date": target.isoformat(),
        "gmv": gmv, "orders": orders, "paid_count": paid_count,
        "refund_count": refund_count, "refund_amount": refund_amount,
        "new_users": new_users, "abandoned_new": abandoned_new,
        "todos": [{"name": n, "count": int(c)} for n, c in todos],
        "top_products": top_products,
        "low_stock_count": low_stock_count,
    }
    subject = f"GLOWMAG Daily Digest — {target.isoformat()}"
    sent = 0
    if any((gmv, paid_count, refund_count, new_users, top_products)):
        for rcpt in recipients:
            emails.deliver(rcpt, subject, emails.render("daily_digest", email=rcpt, **ctx))
        sent = len(recipients)
    if row is None:
        db.add(Setting(key="digest_last_date", value=target.isoformat(),
                       description="运营日报水位（昨日日期，防同日重复发送）"))
    else:
        row.value = target.isoformat()
    db.commit()
    log.info("[daily-digest] date=%s sent=%d", target.isoformat(), sent)


TASKS = (
    consume_outbox,
    cancel_timeout_orders,
    scan_abandoned_carts,
    expire_points,
    unfreeze_points,
    reconcile_daily,
    process_data_requests,
    restock_notify,
    publish_scheduled,
    daily_digest,
)


def _get_lock(conn) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT GET_LOCK(%s, 0)", (LOCK_NAME,))
    got = cur.fetchone()[0] == 1
    cur.close()
    return got


def _release_lock(conn) -> None:
    try:
        cur = conn.cursor()
        cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
        cur.close()
    except Exception:
        log.warning("release lock failed", exc_info=True)


def run_once() -> bool:
    lock_conn = engine.raw_connection()
    try:
        if not _get_lock(lock_conn):
            log.warning("lock %s held by another worker, skip this round", LOCK_NAME)
            return False
    except Exception:
        lock_conn.close()
        raise
    db = SessionLocal()
    try:
        for task in TASKS:
            try:
                task(db)
            except Exception:
                db.rollback()
                log.exception("task %s failed", task.__name__)
    finally:
        db.close()
        _release_lock(lock_conn)
        lock_conn.close()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="GLOWMAG background worker")
    parser.add_argument("--once", action="store_true", help="run a single round and exit")
    parser.add_argument("--loop", action="store_true", help="run forever")
    parser.add_argument("--interval", type=int, default=60, help="loop interval seconds")
    args = parser.parse_args()
    if not args.loop or args.once:
        run_once()
        return
    log.info("worker loop started, interval=%ds", args.interval)
    while True:
        run_once()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
