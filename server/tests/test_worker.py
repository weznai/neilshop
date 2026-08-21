"""智能体 B 自测 —— worker 五任务全链路（GM_DB=glowmag_test_w，夹具直建；锁互斥/幂等/合规跳过）"""

import logging
import os
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pymysql

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute("DROP DATABASE IF EXISTS glowmag_test_w")
    _cur.execute("CREATE DATABASE glowmag_test_w CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag_test_w?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))  # worker.py 在 scripts/

from app.core.db import SessionLocal, init_db, utcnow
from app.core.enums import PointsReason
from app.models import (
    Cart, Category, EmailPreference, GiftCard, GiftCardLedger, Order, OrderItem,
    OrderTimeline, OutboxEvent, Payment, PointsLedger, Product, ReconciliationDaily,
    StockMovement, User, Variant,
)
from app.services import emails
import worker

PASSED = 0
FAILED = []


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok  {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}  {info}")


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


cap = _Capture()
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(cap)

init_db()
s = SessionLocal()
now = utcnow()
addr = {"full_name": "Emma Rodriguez", "line1": "2847 Mission St", "city": "San Francisco",
        "state": "CA", "zip": "94110", "country": "US"}

cat = Category(slug="press-on-nails", name="Press-on Nails")
s.add(cat)
s.flush()
prod = Product(slug="bare-gems", title="Bare Gems", category_id=cat.id, status=1,
               hero_image="https://img/bare.jpg", price_min=1599, price_max=1599)
s.add(prod)
s.flush()
v1 = Variant(product_id=prod.id, sku="BG-SA", option1_value="Short Almond",
             option2_value="24pcs", price=1599, stock=98)
v2 = Variant(product_id=prod.id, sku="BG-SS", option1_value="Short Square",
             option2_value="24pcs", price=1599, stock=49)
s.add_all([v1, v2])
s.flush()

emma = User(email="emma@glow.test", name="Emma", points=500)
grace = User(email="grace@glow.test", name="Grace", points=300)
heidi = User(email="heidi@glow.test", name="Heidi", points=0)
s.add_all([emma, grace, heidi])
s.flush()
s.add(PointsLedger(user_id=emma.id, change=500, balance_after=500,
                   reason=int(PointsReason.CHECKIN), frozen=0))
s.add(PointsLedger(user_id=grace.id, change=500, balance_after=500,
                   reason=int(PointsReason.REVIEW_REWARD), frozen=0,
                   expires_at=now - timedelta(days=1)))
s.add(PointsLedger(user_id=grace.id, change=-200, balance_after=300,
                   reason=int(PointsReason.SPEND), frozen=0))
s.add(PointsLedger(user_id=heidi.id, change=50, balance_after=50,
                   reason=int(PointsReason.CHECKIN), frozen=0,
                   expires_at=now - timedelta(days=1)))
s.add(PointsLedger(user_id=heidi.id, change=-50, balance_after=0,
                   reason=int(PointsReason.SPEND), frozen=0))

pay1 = Order(order_no="NSW2608001", user_id=emma.id, email="emma@glow.test", status=1,
             subtotal=3110, grand_total=3110, shipping_address=addr,
             placed_at=now, paid_at=now)
pay2 = Order(order_no="NSW2608002", email="mia@glow.test", status=1,
             subtotal=1599, grand_total=1599, shipping_address=addr,
             placed_at=now, paid_at=now)
stale = Order(order_no="NSW2608003", user_id=emma.id, email="emma@glow.test", status=0,
              subtotal=4788, grand_total=4788, shipping_address=addr,
              placed_at=now - timedelta(minutes=40))
fresh = Order(order_no="NSW2608004", user_id=emma.id, email="emma@glow.test", status=0,
              subtotal=1599, grand_total=1599, shipping_address=addr,
              placed_at=now - timedelta(minutes=20))
s.add_all([pay1, pay2, stale, fresh])
s.flush()
s.add_all([
    OrderItem(order_id=pay1.id, variant_id=v1.id, product_slug="bare-gems",
              title_snapshot="Bare Gems · Short Almond", qty=1, unit_price=1599, subtotal=1599),
    OrderItem(order_id=pay2.id, variant_id=v2.id, product_slug="bare-gems",
              title_snapshot="Bare Gems · Short Square", qty=1, unit_price=1599, subtotal=1599),
    OrderItem(order_id=stale.id, variant_id=v1.id, product_slug="bare-gems",
              title_snapshot="Bare Gems · Short Almond", qty=2, unit_price=1599, subtotal=3198),
    OrderItem(order_id=stale.id, variant_id=v2.id, product_slug="bare-gems",
              title_snapshot="Bare Gems · Short Square", qty=1, unit_price=1599, subtotal=1599),
])
s.add(Payment(order_id=pay1.id, amount=3110, status=1, stripe_payment_intent="PI_W1", created_at=now))
s.add(Payment(order_id=pay2.id, amount=1599, status=1, stripe_payment_intent="PI_W2", created_at=now))

# 超时关单回补回归：stale 单曾用礼品卡（MVP 下单即扣 + change_type=3 流水）
gc_stale = GiftCard(code="GC-W-STALE", initial_amount=1000, balance=0, status=3,
                    purchaser_email="emma@glow.test")
s.add(gc_stale)
s.flush()
stale.giftcard_discount = 1000
s.add(GiftCardLedger(gift_card_id=gc_stale.id, order_id=stale.id, change_type=3,
                     amount=1000, balance_after=0))

s.add(OutboxEvent(aggregate_type="order", aggregate_id=pay1.id, event_type="order.paid",
                  payload={"order_no": pay1.order_no, "grand_total": 3110,
                           "email": "emma@glow.test"}))
s.add(OutboxEvent(aggregate_type="order", aggregate_id=pay2.id, event_type="order.paid",
                  payload={"order_no": pay2.order_no, "grand_total": 1599}))

cart_oli = Cart(session_id="tok-oli", email="olivia@glow.test",
                items=[{"variantId": v1.id, "qty": 1}], abandoned_mails_sent=0,
                created_at=now - timedelta(hours=3), updated_at=now - timedelta(hours=2))
cart_mia = Cart(session_id="tok-mia", email="mia@glow.test",
                items=[{"variantId": v2.id, "qty": 2}], abandoned_mails_sent=0,
                created_at=now - timedelta(hours=3), updated_at=now - timedelta(hours=2))
s.add_all([cart_oli, cart_mia])
s.add(EmailPreference(email="mia@glow.test", sub_cart_abandon=1, unsubscribed_at=now))
s.commit()

_samples = {
    "order_paid": dict(email="a@b.c", order_no="NS1", grand_total=3110),
    "order_shipped": dict(email="a@b.c", order_no="NS1", carrier="usps", tracking_no="T1"),
    "order_refunded": dict(email="a@b.c", order_no="NS1", amount=1599, reason="late"),
    "abandoned_cart": dict(email="a@b.c", recovery_token="t", items=[{"title": "Bare Gems", "qty": 1}]),
    "welcome_coupon": dict(email="a@b.c", code="GLOW10", discount=10),
    "restock_notify": dict(email="a@b.c", product_title="Bare Gems", variant="Short Almond"),
}
check("6 模板渲染成功且均含 GLOWMAG 页脚+Unsubscribe",
      all("GLOWMAG" in emails.render(k, **v) and "Unsubscribe" in emails.render(k, **v)
          for k, v in _samples.items()))


def email_logs():
    return [m for m in cap.msgs if m.startswith("[EMAIL]")]


# ===== 锁互斥 =====
mutex = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123",
                        database="glowmag_test_w")
mcur = mutex.cursor()
mcur.execute("SELECT GET_LOCK('glowmag_worker', 0)")
check("外部连接 GET_LOCK 持锁成功", mcur.fetchone()[0] == 1)
check("锁互斥：持锁时 run_once 返回 False", worker.run_once() is False)
s.expire_all()
check("锁互斥：跳过轮零副作用（无 published / 关单）",
      s.query(OutboxEvent).filter(OutboxEvent.published == 1).count() == 0
      and s.get(Order, stale.id).status == 0)
mcur.execute("SELECT RELEASE_LOCK('glowmag_worker')")
mutex.close()

# ===== 第 1 轮 =====
check("第 1 轮 run_once 拿锁执行", worker.run_once() is True)
s.expire_all()
paid_events = s.query(OutboxEvent).filter(OutboxEvent.event_type == "order.paid").all()
check("outbox 消费：order.paid ×2 published 且 published_at 落库",
      len(paid_events) == 2 and all(e.published == 1 and e.published_at for e in paid_events))
check("邮件渲染日志含 emma 收件人与订单号",
      any("to=emma@glow.test" in m and pay1.order_no in m for m in email_logs()))
check("payload 缺 email → 查 orders 表补齐并发给 mia",
      any("to=mia@glow.test" in m and pay2.order_no in m for m in email_logs()))
check("超时关单：40min 前 PENDING → CANCELED(8) + reason=timeout",
      s.get(Order, stale.id).status == 8 and s.get(Order, stale.id).cancel_reason == "timeout")
check("20min 前 PENDING 不误伤（status=0）", s.get(Order, fresh.id).status == 0)
check("库存释放：v1 98→100 / v2 49→50",
      s.get(Variant, v1.id).stock == 100 and s.get(Variant, v2.id).stock == 49 + 1)
check("RELEASE 流水 2 条（type=4 ref_type=order ref_id=stale）",
      s.query(StockMovement).filter(StockMovement.type == 4,
                                    StockMovement.ref_id == stale.id).count() == 2)
tl = s.query(OrderTimeline).filter(OrderTimeline.order_id == stale.id,
                                   OrderTimeline.event == "status_changed").first()
check("timeline status_changed actor=system detail.reason=timeout",
      tl is not None and tl.actor == "system" and tl.detail.get("reason") == "timeout")
check("outbox 追加 order.canceled 事件（不发邮件）",
      s.query(OutboxEvent).filter(OutboxEvent.event_type == "order.canceled",
                                  OutboxEvent.aggregate_id == stale.id).count() == 1)
s.expire_all()
gc_w = s.query(GiftCard).filter(GiftCard.code == "GC-W-STALE").first()
check("超时关单：礼品卡余额回补 1000（用尽→有效）+ change_type=5 流水",
      gc_w.balance == 1000 and gc_w.status == 1
      and s.query(GiftCardLedger).filter(GiftCardLedger.gift_card_id == gc_w.id,
                                         GiftCardLedger.change_type == 5).count() == 1,
      (gc_w.balance, gc_w.status))
s.expire_all()
oli = s.get(Cart, cart_oli.id)
mia = s.get(Cart, cart_mia.id)
ab_ev = s.query(OutboxEvent).filter(OutboxEvent.event_type == "cart.abandoned").all()
check("弃购：olivia token(uuid4.hex) + mails_sent=1 + 事件入 outbox",
      len(oli.recovery_token or "") == 32 and oli.abandoned_mails_sent == 1
      and len(ab_ev) == 1 and ab_ev[0].published == 0)
check("合规跳过：mia 已退订 → 无 token/未标记/无事件",
      mia.recovery_token is None and mia.abandoned_mails_sent == 0
      and all(e.payload["email"] != "mia@glow.test" for e in ab_ev))
s.expire_all()
grace_u, heidi_u = s.get(User, grace.id), s.get(User, heidi.id)
expire_rows = s.query(PointsLedger).filter(PointsLedger.reason == int(PointsReason.EXPIRE)).all()
grace_expired = s.query(PointsLedger).filter(
    PointsLedger.user_id == grace.id, PointsLedger.expires_at.isnot(None)).count()
check("积分过期：grace 过期 500 但余额 300 → 扣至 0 不为负 + EXPIRE 流水(-300, ba=0)",
      grace_u.points == 0 and len(expire_rows) == 1 and expire_rows[0].user_id == grace.id
      and expire_rows[0].change == -300 and expire_rows[0].balance_after == 0)
check("过期行 expires_at 置 NULL 防重复（grace+heidi 全清）",
      grace_expired == 0 and s.query(PointsLedger).filter(
          PointsLedger.user_id == heidi.id, PointsLedger.expires_at.isnot(None)).count() == 0)
check("余额 0 用户（heidi）不产生 EXPIRE 流水且 points 仍 0",
      heidi_u.points == 0 and all(r.user_id != heidi.id for r in expire_rows))
rec = s.query(ReconciliationDaily).all()
check("对账行落库且唯一：payments_gross=4709=orders_paid_total → diff_payment=0",
      len(rec) == 1 and rec[0].payments_gross == 4709 and rec[0].orders_paid_total == 4709
      and rec[0].diff_payment == 0)
check("diff_points=0（Σusers.points=500 与每人最后流水 500 一致）且 status=0",
      rec[0].diff_points == 0 and rec[0].points_ledger_sum == 500
      and rec[0].users_points_sum == 500 and rec[0].status == 0)

# ===== 第 2 轮：消费弃购事件 =====
check("第 2 轮 run_once 执行", worker.run_once() is True)
s.expire_all()
token = oli.recovery_token
check("cart.abandoned 下一轮消费：发 olivia 弃购邮件含 token 与商品名",
      any("to=olivia@glow.test" in m and token in m and "Bare Gems" in m for m in email_logs()))
check("order.canceled 事件被标记 published 且不发邮件（EMAIL 总数 3）",
      s.query(OutboxEvent).filter(OutboxEvent.published == 0).count() == 0
      and len(email_logs()) == 3)

# ===== 第 3 轮：幂等 =====
s.expire_all()
before = {
    "outbox": s.query(OutboxEvent).count(),
    "timeline": s.query(OrderTimeline).count(),
    "moves": s.query(StockMovement).count(),
    "ledger": s.query(PointsLedger).count(),
    "rec": s.query(ReconciliationDaily).count(),
    "emails": len(email_logs()),
    "stock": (s.get(Variant, v1.id).stock, s.get(Variant, v2.id).stock),
    "points": (s.get(User, emma.id).points, s.get(User, grace.id).points),
}
check("第 3 轮 run_once 执行（空转）", worker.run_once() is True)
s.expire_all()
after = {
    "outbox": s.query(OutboxEvent).count(),
    "timeline": s.query(OrderTimeline).count(),
    "moves": s.query(StockMovement).count(),
    "ledger": s.query(PointsLedger).count(),
    "rec": s.query(ReconciliationDaily).count(),
    "emails": len(email_logs()),
    "stock": (s.get(Variant, v1.id).stock, s.get(Variant, v2.id).stock),
    "points": (s.get(User, emma.id).points, s.get(User, grace.id).points),
}
check("幂等：再跑一轮全指标无变化（事件/流水/库存/积分/邮件）", before == after, (before, after))
check("幂等：弃购标记防重复（mia 永不发送、olivia 不再发）",
      s.get(Cart, cart_oli.id).abandoned_mails_sent == 1
      and sum(1 for m in email_logs() if "to=olivia@glow.test" in m) == 1
      and not any("to=mia@glow.test" in m and "picks" in m for m in email_logs()))

# ===== 死信告警：retry 打满的事件不拾取不置位，每轮汇总一条 error =====
s.add(OutboxEvent(aggregate_type="order", aggregate_id=pay1.id, event_type="order.paid",
                  retry_count=worker.OUTBOX_MAX_RETRY,
                  payload={"email": "dead@glow.test", "order_no": pay1.order_no}))
s.commit()
dead_logs_before = sum(1 for m in cap.msgs if "dead events" in m)
worker.consume_outbox(s)
s.expire_all()
dead_ev = s.query(OutboxEvent).filter(
    OutboxEvent.retry_count >= worker.OUTBOX_MAX_RETRY).all()
check("死信事件不拾取不置位（published 仍 0 / 不发邮件）",
      len(dead_ev) == 1 and dead_ev[0].published == 0
      and not any("to=dead@glow.test" in m for m in email_logs()))
check("死信每轮汇总一条 error「N dead events」",
      sum(1 for m in cap.msgs if "dead events" in m) == dead_logs_before + 1
      and any("1 dead events" in m for m in cap.msgs))


# ===== 三封阶梯序列 =====
base = utcnow()
cart_lily = Cart(session_id="tok-lily", email="lily@glow.test",
                 items=[{"variantId": v1.id, "qty": 1}, {"variantId": v2.id, "qty": 1}],
                 abandoned_mails_sent=0, created_at=base - timedelta(hours=80),
                 updated_at=base - timedelta(minutes=90))
cart_nora = Cart(session_id="tok-nora", email="nora@glow.test",
                 items=[{"variantId": v1.id, "qty": 1}], abandoned_mails_sent=0,
                 created_at=base - timedelta(minutes=40),
                 updated_at=base - timedelta(minutes=30))
s.add_all([cart_lily, cart_nora])
s.commit()


def ab_events(mail):
    return [e for e in s.query(OutboxEvent).filter(
        OutboxEvent.event_type == "cart.abandoned").all()
        if e.payload.get("email") == mail]


worker.scan_abandoned_carts(s)
s.expire_all()
lily = s.get(Cart, cart_lily.id)
token1 = lily.recovery_token
ev1 = ab_events("lily@glow.test")
check("阶段1：90min 未动 → 第 1 封入队 stage=1 coupon=ABANDON10 mails_sent=1 + recovery_link",
      len(ev1) == 1 and ev1[0].payload["stage"] == 1
      and ev1[0].payload["coupon_code"] == "ABANDON10"
      and ev1[0].payload["recovery_link"] == f"https://glowmag.com/cart?rc={token1}"
      and lily.abandoned_mails_sent == 1 and len(token1 or "") == 32
      and all("stock" in i and "variant_id" in i for i in ev1[0].payload["items"]))
check("未到窗不触发：nora 30min 未动 → 无事件且 mails_sent 仍 0",
      s.get(Cart, cart_nora.id).abandoned_mails_sent == 0 and ab_events("nora@glow.test") == [])
worker.consume_outbox(s)
check("阶段1 消费：subject='Still thinking about your GLOWMAG cart?' 含码含链含商品名",
      any("to=lily@glow.test" in m
          and "subject=Still thinking about your GLOWMAG cart?" in m
          and "ABANDON10" in m and f"https://glowmag.com/cart?rc={token1}" in m
          and "Bare Gems" in m and "Your cart misses you" in m for m in email_logs()))

# ===== 召回链接前缀读 site_url（GM_SITE_URL 覆盖默认 glowmag.com）=====
os.environ["GM_SITE_URL"] = "https://shop.example.com"
try:
    cart_url = Cart(session_id="tok-url", email="url@glow.test",
                    items=[{"variantId": v1.id, "qty": 1}], abandoned_mails_sent=0,
                    created_at=base - timedelta(hours=3),
                    updated_at=base - timedelta(minutes=95))
    s.add(cart_url)
    s.commit()
    worker.scan_abandoned_carts(s)
    s.expire_all()
    ev_url = ab_events("url@glow.test")
    check("GM_SITE_URL 覆盖召回链接前缀（shop.example.com）",
          len(ev_url) == 1 and ev_url[0].payload["recovery_link"].startswith(
              "https://shop.example.com/cart?rc="),
          ev_url and ev_url[0].payload.get("recovery_link"))
finally:
    del os.environ["GM_SITE_URL"]

lily.updated_at = base - timedelta(hours=25)
s.commit()
worker.scan_abandoned_carts(s)
s.expire_all()
lily = s.get(Cart, cart_lily.id)
token2 = lily.recovery_token
ev2 = [e for e in ab_events("lily@glow.test") if e.payload["stage"] == 2]
check("阶段2：25h 未动 → 第 2 封 stage=2 coupon=ABANDON15 且 token 刷新不同于第 1 封",
      len(ev2) == 1 and ev2[0].payload["coupon_code"] == "ABANDON15"
      and lily.abandoned_mails_sent == 2 and len(token2 or "") == 32 and token2 != token1)
worker.consume_outbox(s)
check("阶段2 消费：subject='15% off your favorites' 含 ABANDON15",
      any("to=lily@glow.test" in m and "subject=15% off your favorites" in m
          and "ABANDON15" in m and "Here's more off" in m for m in email_logs()))

lily.updated_at = base - timedelta(hours=73)
s.commit()
worker.scan_abandoned_carts(s)
s.expire_all()
lily = s.get(Cart, cart_lily.id)
token3 = lily.recovery_token
ev3 = [e for e in ab_events("lily@glow.test") if e.payload["stage"] == 3]
min_stock = min(i["stock"] for i in ev3[0].payload["items"]) if ev3 else -1
check("阶段3：73h 未动 → 第 3 封无码（coupon_code=None）items 含 stock 且 token 再刷新",
      len(ev3) == 1 and ev3[0].payload["coupon_code"] is None
      and lily.abandoned_mails_sent == 3 and token3 not in (token1, token2)
      and min_stock == min(s.get(Variant, v1.id).stock, s.get(Variant, v2.id).stock))
worker.consume_outbox(s)
check("阶段3 消费：subject='Last call: your cart items are almost gone' 最小 stock 紧迫感 + Complete my order 按钮且全文无折扣码",
      any("to=lily@glow.test" in m
          and "subject=Last call: your cart items are almost gone" in m
          and f"only {min_stock} left" in m and "Complete my order" in m
          and "ABANDON" not in m for m in email_logs()))

lily.updated_at = base - timedelta(hours=200)
s.commit()
worker.scan_abandoned_carts(s)
check("阶段 3 终态：updated_at 拉到 200h 前也不再入队（lily 事件总数仍 3）",
      len(ab_events("lily@glow.test")) == 3
      and s.get(Cart, cart_lily.id).abandoned_mails_sent == 3)

s.add(EmailPreference(email="pia@glow.test", sub_cart_abandon=0))
cart_pia = Cart(session_id="tok-pia", email="pia@glow.test",
                items=[{"variantId": v1.id, "qty": 2}], abandoned_mails_sent=0,
                created_at=base - timedelta(hours=90),
                updated_at=base - timedelta(hours=80))
s.add(cart_pia)
s.commit()
scan_logs_before = sum(1 for m in cap.msgs if "[abandoned-cart]" in m)
for stage in (0, 1, 2):
    s.expire_all()
    p = s.get(Cart, cart_pia.id)
    p.abandoned_mails_sent = stage
    p.updated_at = base - timedelta(hours=80)
    s.commit()
    worker.scan_abandoned_carts(s)
scan_logs = [m for m in cap.msgs if "[abandoned-cart]" in m][scan_logs_before:]
check("合规用户全阶段跳过：sub_cart_abandon=0 → 0/1/2 阶段均不入队不改状态不计发",
      ab_events("pia@glow.test") == [] and len(scan_logs) == 3
      and s.get(Cart, cart_pia.id).abandoned_mails_sent == 2
      and s.get(Cart, cart_pia.id).recovery_token is None
      and all("compliance_skipped=" in m and "compliance_skipped=0" not in m
              for m in scan_logs))

cart_zoe = Cart(session_id="tok-zoe", email="zoe@glow.test",
                items=[{"variantId": v2.id, "qty": 1}], abandoned_mails_sent=0,
                created_at=base - timedelta(hours=3),
                updated_at=base - timedelta(minutes=95))
s.add(cart_zoe)
s.commit()
r1 = worker.run_once()
r2 = worker.run_once()
s.expire_all()
check("两次 run_once 不重复入队：zoe 第 1 封恰 1 事件、阶段只推进到 1（24h 窗未到）",
      r1 is True and r2 is True and len(ab_events("zoe@glow.test")) == 1
      and ab_events("zoe@glow.test")[0].payload["stage"] == 1
      and s.get(Cart, cart_zoe.id).abandoned_mails_sent == 1)

# ===== 弃购计数重置：三封发满后回访改车（新弃购周期）→ 清零并从第 1 封重算 =====
from app.domains.trade import service_cart as _sc

s.expire_all()
lily_done = s.get(Cart, cart_lily.id)
check("前置：lily 三封阶梯已发满（mails_sent=3 终态）",
      lily_done.abandoned_mails_sent == 3)
_sc.add_item(s, lily_done, "tok-lily", v1.id, 1)
s.expire_all()
lily_back = s.get(Cart, cart_lily.id)
check("回访加购（items 变化）→ abandoned_mails_sent 重置 0",
      lily_back.abandoned_mails_sent == 0 and lily_back.items[0]["qty"] == 2,
      (lily_back.abandoned_mails_sent, lily_back.items))
lily_back.updated_at = utcnow() - timedelta(minutes=95)
s.commit()
worker.scan_abandoned_carts(s)
s.expire_all()
lily_new = s.get(Cart, cart_lily.id)
stage1_events = [e for e in ab_events("lily@glow.test") if e.payload.get("stage") == 1]
check("再弃购 → 新周期从第 1 封重算（stage=1 / coupon=ABANDON10 / mails_sent=1）",
      lily_new.abandoned_mails_sent == 1 and len(stage1_events) == 2
      and stage1_events[1].payload["coupon_code"] == "ABANDON10"
      and len(ab_events("lily@glow.test")) == 4,
      (lily_new.abandoned_mails_sent, len(stage1_events)))

s.close()
print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
