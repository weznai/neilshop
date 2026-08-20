"""worker 深度审计扩展测试 —— 营销邮件偏好 gating/模板完整性/unfreeze RMA 阻断/
daily_digest product_slug 冒烟/outbox 失败重试
（GM_DB=sqlite test_wx.sqlite + BigInteger 垫片；worker 任务直调避开 GET_LOCK，抄 test_stocknotify.py）"""

import logging
import os
import sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_wx.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))  # worker.py 在 scripts/

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from app.core.db import SessionLocal, init_db, utcnow
from app.core.enums import OrderStatus, PointsReason, RmaStatus
from app.models import (
    Category, EmailPreference, Order, OrderItem, OutboxEvent, PointsLedger,
    Product, Rma, User, Variant,
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
for _name in ("glowmag.emails", "glowmag.worker"):
    _lg = logging.getLogger(_name)
    _lg.setLevel(logging.INFO)
    _lg.addHandler(cap)


def email_logs():
    return [m for m in cap.msgs if m.startswith("[EMAIL]")]


ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US"}

init_db()
db = SessionLocal()
now = utcnow()

# ===== 1. 模板完整性：_EVENT_EMAILs 引用的模板全部存在且样例 payload 渲染不抛错 =====
_tpl_payloads = {
    "order_paid": dict(email="a@b.co", order_no="NSWX1", grand_total=3110),
    "order_shipped": dict(email="a@b.co", order_no="NSWX1", carrier="usps", tracking_no="T9"),
    "order_refunded": dict(email="a@b.co", order_no="NSWX1", amount=1599, reason="size"),
    "welcome_coupon": dict(email="a@b.co", discount=10, code="GLOW10"),
    "restock_notify": dict(email="a@b.co", product_title="Bare Gems", variant="Short Almond"),
}
missing = [tpl for tpl, _sub in worker._EVENT_EMAILS.values()
           if tpl not in emails.TEMPLATES]
check("模板完整性：_EVENT_EMAILS 引用的模板名全部存在于 emails.TEMPLATES（含 daily_digest）",
      missing == [] and "daily_digest" in emails.TEMPLATES, missing)

rendered_ok = True
for tpl, ctx in _tpl_payloads.items():
    try:
        html = emails.render(tpl, **ctx)
        rendered_ok = rendered_ok and "GLOWMAG" in html and "Unsubscribe" in html
    except Exception as exc:  # noqa: BLE001
        rendered_ok = False
        print(f"  render {tpl} raised: {exc!r}")
check("5 个固定模板样例 payload 渲染成功且含页脚+Unsubscribe", rendered_ok)

_stage_ok = True
for stage, coupon in ((1, "ABANDON10"), (2, "ABANDON15"), (3, None)):
    try:
        html = emails.render(
            "abandoned_cart", email="a@b.co", stage=stage,
            items=[{"title": "Bare Gems · Short Almond", "qty": 1, "stock": 3}],
            coupon_code=coupon, recovery_link="https://glowmag.com/cart?rc=t")
        _stage_ok = _stage_ok and "GLOWMAG" in html
    except Exception as exc:  # noqa: BLE001
        _stage_ok = False
        print(f"  render abandoned_cart stage={stage} raised: {exc!r}")
check("abandoned_cart 三阶段（1/2/3）渲染成功不抛错", _stage_ok)

_digest_ctx = dict(
    email="ops@glowmag.com", date="2026-08-19", gmv=3198, orders=3, paid_count=1,
    refund_count=0, refund_amount=0, new_users=1, abandoned_new=1,
    todos=[{"name": "Pending orders", "count": 2}], low_stock_count=1,
    top_products=[{"slug": "bare-gems", "title": "Bare Gems", "qty": 2}])
try:
    _dh = emails.render("daily_digest", **_digest_ctx)
    check("daily_digest 样例 payload 渲染成功（$31.98 / Top1 / 待办行）",
          "GLOWMAG" in _dh and "$31.98" in _dh and "Bare Gems" in _dh
          and "Pending orders" in _dh and "Unsubscribe" in _dh)
except Exception as exc:  # noqa: BLE001
    check("daily_digest 样例 payload 渲染成功", False, repr(exc))

_xss = emails.render(
    "abandoned_cart", email="a@b.co", stage=1,
    items=[{"title": "<script>alert(1)</script>", "qty": 1, "stock": 5}],
    coupon_code="ABANDON10", recovery_link="https://glowmag.com/cart?rc=t")
check("autoescape 生效：商品名注入 <script> 被转义（HTML 邮件 XSS 面已挡）",
      "<script>alert(1)</script>" not in _xss and "&lt;script&gt;" in _xss)

# ===== 2. consume_outbox：welcome 营销 gating + 事务性邮件不受限 =====
ana = User(email="ana@glow.test", name="Ana")
db.add(ana)
db.flush()
welcome_events = []
for mail in ("ana@glow.test", "bo@glow.test", "cyd@glow.test"):
    db.add(OutboxEvent(
        aggregate_type="user", aggregate_id=ana.id, event_type="user.welcome",
        payload={"email": mail, "discount": 10, "code": "GLOW10"}))
db.flush()
db.add_all([
    EmailPreference(email="bo@glow.test", sub_promo=0),
    EmailPreference(email="cyd@glow.test", sub_promo=1, unsubscribed_at=now),
])
# 事务性邮件发给已退订用户 → 仍投递
tx = Order(order_no="NSWX26080001", email="unsub@glow.test", status=1,
           subtotal=1599, grand_total=1599, shipping_address=ADDR,
           placed_at=now, paid_at=now)
db.add(tx)
db.flush()
db.add(OutboxEvent(aggregate_type="order", aggregate_id=tx.id, event_type="order.paid",
                   payload={"order_no": tx.order_no, "grand_total": 1599,
                            "email": "unsub@glow.test"}))
db.commit()

worker.consume_outbox(db)
db.expire_all()
wel = db.query(OutboxEvent).filter(OutboxEvent.event_type == "user.welcome").all()
by_mail = {e.payload["email"]: e for e in wel}
check("welcome gating：无偏好记录（ana）正常投递 welcome 邮件",
      any("to=ana@glow.test" in m and "subject=Welcome to GLOWMAG" in m
          and "GLOW10" in m for m in email_logs()))
check("welcome gating：sub_promo=0（bo）→ 跳过不发但标记 published 防重投",
      "to=bo@glow.test" not in "".join(email_logs())
      and by_mail["bo@glow.test"].published == 1
      and by_mail["bo@glow.test"].published_at is not None)
check("welcome gating：unsubscribed_at 非空（cyd，sub_promo=1）→ 同样跳过",
      "to=cyd@glow.test" not in "".join(email_logs())
      and by_mail["cyd@glow.test"].published == 1)
check("事务性邮件不受偏好限制：order.paid 发给已全退订语义用户仍投递",
      any("to=unsub@glow.test" in m and "confirmed" in m for m in email_logs()))
check("日志行含 compliance_skipped=2（与 scan 侧弃购合规日志风格一致）",
      any("[outbox]" in m and "compliance_skipped=2" in m for m in cap.msgs),
      [m for m in cap.msgs if "[outbox]" in m][-1:])

# ===== 3. consume_outbox：渲染/投递失败 → retry_count 递增且不 published =====
db.add(OutboxEvent(
    aggregate_type="user", aggregate_id=ana.id, event_type="user.welcome",
    payload={"email": "retry@glow.test", "discount": 10, "code": "GLOW10"}))
db.commit()
_orig_deliver = emails.deliver
emails.deliver = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down"))
worker.consume_outbox(db)
emails.deliver = _orig_deliver
db.expire_all()
retry_ev = [e for e in db.query(OutboxEvent).filter(
    OutboxEvent.event_type == "user.welcome").all()
    if e.payload.get("email") == "retry@glow.test"][0]
check("投递异常 → published=0 + retry_count=1（不丢事件，5 次后进死信）",
      retry_ev.published == 0 and retry_ev.retry_count == 1
      and any("outbox event" in m and "failed" in m for m in cap.msgs))

# ===== 4. unfreeze_points：RMA 阻断语义（0-4 阻断 / 5,6 放行 / 已退款订单阻断） =====
old = now - timedelta(days=40)


def _mk_frozen(order_no, order_status, rma_status=None):
    u = User(email=f"{order_no.lower()}@glow.test", name=order_no, points=100)
    db.add(u)
    db.flush()
    o = Order(order_no=f"NSWX{order_no}", user_id=u.id, email=u.email,
              status=order_status, subtotal=1000, grand_total=1000,
              shipping_address=ADDR, placed_at=old, paid_at=old)
    db.add(o)
    db.flush()
    db.add(PointsLedger(user_id=u.id, change=100, balance_after=100,
                        reason=int(PointsReason.ORDER_EARN_FROZEN), frozen=1,
                        ref_type="order", ref_id=o.id, created_at=old))
    if rma_status is not None:
        db.add(Rma(rma_no=f"RMA{order_no}", order_id=o.id, order_item_id=0,
                   qty=1, reason=1, status=int(rma_status)))
    return o


o_open = _mk_frozen("OPEN4", int(OrderStatus.DELIVERED), RmaStatus.RECEIVED)     # 4 已收货未退款
o_refunded = _mk_frozen("RFD5", int(OrderStatus.DELIVERED), RmaStatus.REFUNDED)  # 5 已退款
o_rejected = _mk_frozen("REJ6", int(OrderStatus.DELIVERED), RmaStatus.REJECTED)  # 6 已拒绝
o_order9 = _mk_frozen("ORD9", int(OrderStatus.REFUNDED), None)                   # 订单已全额退款
o_clean = _mk_frozen("CLEAN", int(OrderStatus.DELIVERED), None)                  # 无 RMA 期满
db.commit()

worker.unfreeze_points(db)
db.expire_all()


def _frozen(order):
    return db.query(PointsLedger).filter(
        PointsLedger.ref_type == "order", PointsLedger.ref_id == order.id,
        PointsLedger.frozen == 1).count() == 1


check("RMA status=4（已收货退款中）→ 冻结保持不解冻", _frozen(o_open))
check("RMA status=5（已退款）→ 解冻放行", not _frozen(o_refunded))
check("RMA status=6（已拒绝，无退款）→ 解冻放行", not _frozen(o_rejected))
check("订单 status=9（已全额退款）→ 不解冻", _frozen(o_order9))
check("无 RMA 且过退货期 → 正常解冻", not _frozen(o_clean))
check("[points-unfreeze] 日志含 scanned/unfrozen",
      any("[points-unfreeze]" in m and "unfrozen=" in m for m in cap.msgs))

# ===== 5. daily_digest：OrderItem.product_slug 列存在 + Top 商品冒烟 =====
check("OrderItem.product_slug 列存在（trade.py 模型冒烟，无列会 500）",
      hasattr(OrderItem, "product_slug")
      and "product_slug" in OrderItem.__table__.columns)

cat = Category(slug="press-on-nails", name="Press-on Nails")
db.add(cat)
db.flush()
prod = Product(slug="bare-gems", title="Bare Gems", category_id=cat.id, status=1,
               hero_image="https://img/bare.jpg", price_min=1599, price_max=1599,
               published_at=now - timedelta(days=30))
db.add(prod)
db.flush()
dv = Variant(product_id=prod.id, sku="BG-SA", option1_value="Short Almond",
             option2_value="24pcs", price=1599, stock=3)
db.add(dv)
db.flush()
yday = now - timedelta(days=1)
y_start = datetime(yday.year, yday.month, yday.day)
y_at = y_start + timedelta(hours=10)
do = Order(order_no="NSWX26080002", email="dig@glow.test", status=1,
           subtotal=3198, grand_total=3198, shipping_address=ADDR,
           placed_at=y_at, paid_at=y_at)
db.add(do)
db.flush()
db.add(OrderItem(order_id=do.id, variant_id=dv.id, product_slug="bare-gems",
                 title_snapshot="Bare Gems · Short Almond", qty=2,
                 unit_price=1599, subtotal=3198))
db.commit()

before = len(email_logs())
worker.daily_digest(db)
db.expire_all()
dig = [m for m in email_logs()[before:] if "GLOWMAG Daily Digest" in m]
check("daily_digest 走 product_slug 分组成功（Top1=Bare Gems 2 sold，无 500）",
      len(dig) == 1 and "Bare Gems" in dig[0] and "2 sold" in dig[0], dig[:1])
check("daily_digest 水位幂等：同日二跑不重发",
      (worker.daily_digest(db), len([m for m in email_logs()[before:]
                                     if "GLOWMAG Daily Digest" in m]))[1] == 1)

db.close()
print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
