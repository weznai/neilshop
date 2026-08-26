"""GLOWMAG 后台任务 worker —— outbox 消费/超时关单/弃购三封阶梯召回/积分过期/每日对账
（standalone 进程；MySQL GET_LOCK / SQLite 跨平台文件锁 单实例互斥）"""

import argparse
import logging
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 跨平台文件锁原语：Windows msvcrt.locking / POSIX fcntl.flock（二者必有其一）
try:
    import msvcrt
except ImportError:
    msvcrt = None
try:
    import fcntl
except ImportError:
    fcntl = None

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, engine, utcnow
from app.core.enums import OrderStatus, PaymentStatus, PointsReason, StockMovementType
from app.models import (
    Cart, DataRequest, EmailPreference, Order, OrderItem, OrderTimeline,
    OutboxEvent, Payment, PointsLedger, Product, ReconciliationDaily, Rma,
    Setting, StockMovement, StockNotification, User, Variant,
)
from app.services import emails
from app.services import points as points_svc
from app.domains.trade.service_admin import _refund_giftcard_debit

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
    "user.welcome": ("welcome_coupon", "Welcome to GLOWMAG - your discount inside"),
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
# SQLite 分支互斥不走 GET_LOCK（MySQL 专有），改用文件锁判别后端
_IS_SQLITE = engine.url.get_backend_name() == "sqlite"
# 积分过期原子扣减（余额守卫进 WHERE，对齐 points.py _ADMIN_DEBIT_SQL 风格）：
# points_svc.add_points 无守卫（负增量并发下可扣穿成负数），故本地同款 SQL；
# rowcount=0 = 并发花分致余额不足 → 本轮跳过该用户下轮重算
_EXPIRE_DEDUCT_SQL = text(
    "UPDATE users SET points = points - :amt WHERE id = :uid AND points >= :amt"
)
_POINTS_BALANCE_SQL = text("SELECT points FROM users WHERE id = :uid")


def _setting_int(db: Session, key: str, default: int) -> int:
    row = db.get(Setting, key)
    if row is not None and row.value is not None:
        try:
            return int(row.value)
        except (TypeError, ValueError):
            pass
    return default


def _site_url(db: Session) -> str:
    """站点根地址（召回链接等外链前缀）：ops settings 表 site_url/base_url 优先，
    其次环境变量 GM_SITE_URL，最后默认站（对齐 member 域 _site_url 的读取方式，
    但不 import member 域避免耦合）。"""
    for key in ("site_url", "base_url"):
        row = db.get(Setting, key)
        if row is not None and row.value:
            val = str(row.value).strip().rstrip("/")
            if val.startswith(("http://", "https://")):
                return val
    val = (os.getenv("GM_SITE_URL") or "").strip().rstrip("/")
    return val or "https://glowmag.com"


def _fmt_subject(tpl: str, payload: dict) -> str:
    try:
        return tpl.format(**payload)
    except (KeyError, IndexError, ValueError):
        return "GLOWMAG update"


def consume_outbox(db: Session) -> None:
    # 原子认领：模型仅 published 0/1 无 status 字段（create_all 不做列迁移，不能加列），
    # 用 published_at=认领时间戳抢占——先 UPDATE 圈定再按值取回，防 MySQL 多实例
    # 「先查后置位」竞态重复发送；崩溃残留行 published 仍 0，下轮可再认领（at-least-once）。
    # 同秒两次认领碰撞由外层单实例锁（GET_LOCK/文件锁）互斥兜底
    claim_ids = [
        r[0] for r in (
            db.query(OutboxEvent.id)
            .filter(OutboxEvent.published == 0, OutboxEvent.retry_count < OUTBOX_MAX_RETRY)
            .order_by(OutboxEvent.id).limit(OUTBOX_BATCH).all()
        )
    ]
    events = []
    if claim_ids:
        claim_ts = utcnow()
        db.query(OutboxEvent).filter(
            OutboxEvent.id.in_(claim_ids), OutboxEvent.published == 0,
            OutboxEvent.retry_count < OUTBOX_MAX_RETRY,
        ).update({OutboxEvent.published_at: claim_ts}, synchronize_session=False)
        db.commit()
        events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.id.in_(claim_ids), OutboxEvent.published == 0,
                    OutboxEvent.published_at == claim_ts)
            .order_by(OutboxEvent.id).all()
        )
    # 死信汇总：OutboxEvent 仅 published 0/1 语义（无 status 字段），retry 打满的事件
    # 不再置位，每轮 logger.error 汇总一条待人工介入
    dead = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.published == 0, OutboxEvent.retry_count >= OUTBOX_MAX_RETRY)
        .count()
    )
    if dead:
        log.error("[outbox] %d dead events (retry_count>=%d) need manual inspection",
                  dead, OUTBOX_MAX_RETRY)
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
    log.info("[outbox] picked=%d emailed=%d no_email=%d failed=%d compliance_skipped=%d dead=%d",
             len(events), emailed, skipped, failed, compliance_skipped, dead)


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
            # 礼品卡扣款回补（MVP 下单即扣；无 change_type=3 流水时为空操作）
            _refund_giftcard_debit(db, order)
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
                     "recovery_link": f"{_site_url(db)}/cart?rc={token}",
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
        if amount > 0:
            # 原子扣减（守卫 points>=amt，rowcount=0=并发余额不足）：本轮跳过该用户、
            # 过期标记保留 下轮按新余额重算；杜绝 ORM 读改写并发丢更新，
            # balance_after 用扣减后回读现值（不改 user.points 属性，防 flush 脏快照回写）
            if db.execute(_EXPIRE_DEDUCT_SQL, {"uid": user_id, "amt": amount}).rowcount != 1:
                db.rollback()
                continue
            balance = int(db.execute(_POINTS_BALANCE_SQL, {"uid": user_id}).scalar())
            db.add(PointsLedger(
                user_id=user_id, change=-amount, balance_after=balance,
                reason=int(PointsReason.EXPIRE), frozen=0, expires_at=None,
            ))
            expired_users += 1
            expired_points += amount
        for r in ledgers:
            r.expires_at = None
        db.commit()
    log.info("[points-expire] rows=%d users=%d expired=%d", len(rows), expired_users, expired_points)


def reconcile_daily(db: Session) -> None:
    now = utcnow()
    today = now.date()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 支付/订单两侧统一按支付归属日（Payment.created_at 当日）开窗：
    # 原 payment.created_at vs order.paid_at 双时钟跨午夜必错位（23:59 支付 / 00:00 落 paid_at → 恒误报）；
    # 订单侧 = 当日成功支付对应订单实付合计（subquery 去重防一单多次支付重复计数），
    # 原口径 status>=1 含 8(取消)/9(全额退款) 语义含糊 → 统一排除：取消单本就无成功支付，
    # 全额退款的支付 status=3/4 已被支付侧过滤，此排除只拦真正的脏数据（对账本应暴露）
    paid_today = select(Payment.order_id).where(
        Payment.status == int(PaymentStatus.SUCCESS), Payment.created_at >= day_start)
    payments_gross = int(db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.status == int(PaymentStatus.SUCCESS), Payment.created_at >= day_start).scalar())
    orders_paid_total = int(db.query(func.coalesce(func.sum(Order.grand_total), 0)).filter(
        Order.id.in_(paid_today), Order.status >= 1, Order.status.notin_((8, 9))).scalar())
    diff_payment = payments_gross - orders_paid_total
    # 退款列补真实值：Payment.refunded_amount 无退款时间戳无法按日开窗，取单一时钟
    # RMA 退款流水（refunded_at 当日）合计为当日退款额；退款本身非异常，不参与 status 判定
    refund_total = int(db.query(func.coalesce(func.sum(Rma.refund_amount), 0)).filter(
        Rma.refunded_at.isnot(None), Rma.refunded_at >= day_start).scalar())
    # 积分对账两列：台账侧 = 每用户最后一条流水余额合计（_LAST_LEDGER_SQL）；
    # 用户表侧 = SUM(users.points)；diff = 台账 - 用户表（0 为平）
    points_ledger_sum = int(db.execute(_LAST_LEDGER_SQL).scalar())
    users_points_sum = int(db.query(func.coalesce(func.sum(User.points), 0)).scalar())
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
    row.diff_refund = refund_total
    row.points_ledger_sum = points_ledger_sum
    row.users_points_sum = users_points_sum
    row.diff_points = diff_points
    row.status = status
    row.checked_at = now
    db.commit()
    log.info("[reconcile] date=%s payments_gross=%d orders_paid=%d diff_payment=%d "
             "refund=%d points_sum=%d ledger_last=%d diff_points=%d status=%d",
              today, payments_gross, orders_paid_total, diff_payment, refund_total,
              users_points_sum, points_ledger_sum, diff_points, status)


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
    """GDPR 删除请求到期执行：匿化核心已抽到 member 域 anonymize_user
    （与后台 data-requests execute 端点共用同一实现），本函数只负责到期筛选与逐单提交"""
    from app.domains.member.service_account import anonymize_user

    grace_days = _setting_int(db, "gdpr_delete_delay_days", 7)
    cutoff = utcnow() - timedelta(days=grace_days)
    requests = (
        db.query(DataRequest)
        .filter(DataRequest.type == 2, DataRequest.status == 0,
                DataRequest.created_at < cutoff)
        .order_by(DataRequest.id).all()
    )
    from app.domains.ops.repository import claim_data_request

    anonymized = failed = 0
    for req in requests:
        # 逐条隔离：单条失败不阻塞其余请求；DataRequest 无 failed 字段，
        # 失败条保持 pending（status=0）下轮重试
        try:
            # CAS 抢占 0→1：与后台 execute/reject 端点互斥（驳回后 worker 不再匿化）
            if claim_data_request(db, req.id, 1) == 0:
                db.rollback()
                continue
            if anonymize_user(db, req.user_id):
                anonymized += 1
            req.fulfilled_at = utcnow()
            db.commit()
            log.info("[gdpr] data request %s fulfilled, user %s anonymized", req.id, req.user_id)
        except Exception:
            db.rollback()
            failed += 1
            log.exception("[gdpr] data request %s failed, keep pending", req.id)
    log.info("[gdpr] due=%d anonymized=%d failed=%d grace=%dd",
             len(requests), anonymized, failed, grace_days)


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

# 重任务降频：对账/日报是全表+窗口函数重查询，分钟级轮询里 6h 一次足够；
# 内存水位即可（worker 常驻进程，重启即重算一次无妨；日报另有 digest_last_date
# 落库水位防同日重复发送）
_HEAVY_TASKS = ("reconcile_daily", "daily_digest")
_HEAVY_INTERVAL_SECONDS = 6 * 3600
_heavy_last_run: dict[str, float] = {}


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


def _sqlite_lock_path() -> str:
    # 锁文件落 sqlite db 同目录（内存库/无路径兜底 temp）
    db_path = engine.url.database or ""
    if db_path and db_path != ":memory:":
        directory = os.path.dirname(os.path.abspath(db_path))
    else:
        directory = tempfile.gettempdir()
    return os.path.join(directory, "worker.lock")


class _FileLock:
    """SQLite 分支单实例互斥：GET_LOCK 是 MySQL 专有，改用跨平台文件锁
    （Windows msvcrt.locking / POSIX fcntl.flock，try/except 双实现），
    锁 1 字节即可，进程存活期间持锁、退出自动释放"""

    def __init__(self, path: str):
        self.path = path
        self.fh = None

    def acquire(self) -> bool:
        try:
            self.fh = open(self.path, "a+b")
            self.fh.seek(0)
            if msvcrt is not None:
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            elif fcntl is not None:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                self.fh.close()
                self.fh = None
                return False  # 两种原语都不可用：宁可跳过也不双跑
            return True
        except OSError:
            if self.fh:
                self.fh.close()
                self.fh = None
            return False

    def release(self) -> None:
        if self.fh is None:
            return
        try:
            self.fh.seek(0)
            if msvcrt is not None:
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            log.warning("release file lock failed", exc_info=True)
        finally:
            self.fh.close()
            self.fh = None


def run_once() -> bool:
    file_lock = None
    lock_conn = None
    if _IS_SQLITE:
        file_lock = _FileLock(_sqlite_lock_path())
        if not file_lock.acquire():
            log.warning("file lock %s held by another worker, skip this round", file_lock.path)
            return False
    else:
        lock_conn = engine.raw_connection()
        try:
            if not _get_lock(lock_conn):
                log.warning("lock %s held by another worker, skip this round", LOCK_NAME)
                lock_conn.close()
                return False
        except Exception:
            lock_conn.close()
            raise
    db = SessionLocal()
    try:
        for task in TASKS:
            name = task.__name__
            if name in _HEAVY_TASKS \
                    and time.time() - _heavy_last_run.get(name, 0.0) < _HEAVY_INTERVAL_SECONDS:
                continue
            try:
                task(db)
                if name in _HEAVY_TASKS:
                    _heavy_last_run[name] = time.time()  # 成功才推水位，失败下轮重试
            except Exception:
                db.rollback()
                log.exception("task %s failed", name)
    finally:
        db.close()
        if file_lock is not None:
            file_lock.release()
        if lock_conn is not None:
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
    delay = float(args.interval)
    while True:
        try:
            run_once()
            delay = float(args.interval)
        except Exception:
            # 主循环兜底：单轮崩溃只退避不退进程，连续失败指数退避封顶 5min
            delay = min(delay * 2, 300)
            log.exception("worker round failed, backoff %.0fs", delay)
        time.sleep(delay)


if __name__ == "__main__":
    main()
