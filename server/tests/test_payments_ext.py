"""支付链路修复回归（智能体补充）—— P0-1 差价污染退款池 / P0-2 双扣款自动退款 /
P0-3 PayPal webhook 事件结构 / P0-5 per-user 核销守卫 / P1-6 下架商品 / P1-7 配送参数校验。
GM_DB=sqlite:///test_pe.sqlite 独立库；BigInteger 垫片同 test_payments.py。"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_pe.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Category, DiscountCode, DiscountRedemption, Exchange, Order, OrderItem,
    OutboxEvent, Payment, Product, User, Variant,
)
from app.domains.trade import repository as repo  # noqa: E402
from app.services import payment_provider as pp  # noqa: E402

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


ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US", "phone": "+14155550001"}


def make_order(s, no, total, lines, *, user_id=None, code_id=None,
               discount_total=0, email="ext@glow.test"):
    o = Order(order_no=no, user_id=user_id, email=email, status=0,
              subtotal=total, discount_total=discount_total,
              grand_total=total, shipping_address=ADDR, discount_code_id=code_id)
    s.add(o)
    s.flush()
    for vid, qty, price in lines:
        s.add(OrderItem(order_id=o.id, variant_id=vid, product_slug="ext-gems",
                        title_snapshot="Ext Gems", qty=qty, unit_price=price,
                        subtotal=price * qty))
    return o


def pay_via_webhook(client, order_no, pi, event_id, amount=None):
    data = {"payment_intent": pi}
    if amount is not None:
        data["amount"] = amount
    return client.post("/api/payments/webhook", json={
        "id": event_id, "type": "payment_intent.succeeded", "data": data})


try:
    with TestClient(app) as client:
        s = SessionLocal()

        cat = Category(slug="press-on-nails", name="Press-on Nails")
        s.add(cat)
        s.flush()
        p1 = Product(slug="ext-gems", title="Ext Gems", category_id=cat.id, status=1,
                     hero_image="https://img/e.jpg", price_min=2000, price_max=2000)
        p2 = Product(slug="arch-gems", title="Archived Gems", category_id=cat.id,
                     status=2, hero_image="https://img/a.jpg",
                     price_min=1000, price_max=1000)
        s.add_all([p1, p2])
        s.flush()
        v1 = Variant(product_id=p1.id, sku="EXT-1", option1_value="Short",
                     option2_value="24pcs", price=2000, stock=10)
        v2 = Variant(product_id=p2.id, sku="ARCH-1", option1_value="Short",
                     option2_value="24pcs", price=1000, stock=10)
        s.add_all([v1, v2])
        s.flush()
        emma = User(email="emma@glow.test", password_hash=hash_password("x"),
                    name="Emma", role=0, points=0)
        s.add(emma)
        s.flush()
        emma_auth = {"Authorization": f"Bearer {create_token(emma.id, 0)}"}

        # ===== P0-1 换货差价支付污染退款池：退款池取主支付行，差价行退款不进整单语义 =====
        o1 = make_order(s, "NSEXT0001", 2000, [(v1.id, 1, 2000)], user_id=emma.id)
        s.commit()
        pi_main = client.post("/api/payments/create-intent", headers=emma_auth,
                              json={"order_no": "NSEXT0001"}).json()["payment_intent"]
        r = pay_via_webhook(client, "NSEXT0001", pi_main, "evt_ext_paid_1")
        check("P0-1 前置：主款 webhook 支付 → 订单 PAID", r.status_code == 200, r.text)
        # 换货差价行（settle 后 status=1，挂原订单，amount=600 << grand_total，id 更大）
        pay_diff = Payment(order_id=o1.id, stripe_payment_intent="PI_ext_diff_1",
                           amount=600, status=1)
        s.add(pay_diff)
        s.flush()
        item1 = s.query(OrderItem).filter(OrderItem.order_id == o1.id).first()
        ex1 = Exchange(exchange_no="EXEXT0001", order_id=o1.id,
                       order_item_id=item1.id, old_variant_id=v1.id,
                       new_variant_id=v1.id, qty=1, price_diff=600, status=1,
                       diff_payment_id=pay_diff.id)
        s.add(ex1)
        s.commit()
        s.expire_all()
        main_row = s.query(Payment).filter(
            Payment.stripe_payment_intent == pi_main).first()
        check("P0-1 refundable_payment_of_order 取主支付行（金额=grand_total 优先）",
              repo.refundable_payment_of_order(s, o1.id).id == main_row.id)
        r = client.post("/api/payments/webhook", json={
            "id": "evt_ext_diff_refund", "type": "charge.refunded",
            "data": {"payment_intent": "PI_ext_diff_1", "amount": 600}})
        s.expire_all()
        pay_diff = s.query(Payment).filter(
            Payment.stripe_payment_intent == "PI_ext_diff_1").first()
        main_row = s.query(Payment).filter(
            Payment.stripe_payment_intent == pi_main).first()
        o1_db = s.query(Order).filter(Order.order_no == "NSEXT0001").first()
        check("P0-1 差价行退款回调：仅差价行记账（600/状态3），订单保持 PAID",
              r.status_code == 200 and pay_diff.refunded_amount == 600
              and pay_diff.status == 3 and o1_db.status == 1
              and main_row.refunded_amount == 0,
              (r.text, pay_diff.refunded_amount, o1_db.status))
        r = client.post("/api/payments/webhook", json={
            "id": "evt_ext_main_refund", "type": "charge.refunded",
            "data": {"payment_intent": pi_main, "amount": 2000}})
        s.expire_all()
        main_row = s.query(Payment).filter(
            Payment.stripe_payment_intent == pi_main).first()
        o1_db = s.query(Order).filter(Order.order_no == "NSEXT0001").first()
        check("P0-1 主款全额退款：退 grand_total 2000 → 订单 REFUNDED(9)",
              r.status_code == 200 and main_row.refunded_amount == 2000
              and main_row.status == 3 and o1_db.status == 9,
              (r.text, main_row.refunded_amount, o1_db.status))

        # ===== P0-5 per-user 限额支付核销守卫：囤多张 PENDING 逐一支付不超发 =====
        dc = DiscountCode(code="PUEXT1", name="per-user 1", type=2, value=300,
                          max_discount=300, min_subtotal=0, first_order_only=0,
                          per_user_limit=1, is_active=1)
        s.add(dc)
        s.flush()
        o2 = make_order(s, "NSEXT0002", 2000, [(v1.id, 1, 2000)], user_id=emma.id,
                        code_id=dc.id, discount_total=300, email="pu@glow.test")
        o3 = make_order(s, "NSEXT0003", 2000, [(v1.id, 1, 2000)], user_id=emma.id,
                        code_id=dc.id, discount_total=300, email="pu@glow.test")
        s.commit()
        pi2 = client.post("/api/payments/create-intent", headers=emma_auth,
                          json={"order_no": "NSEXT0002"}).json()["payment_intent"]
        pi3 = client.post("/api/payments/create-intent", headers=emma_auth,
                          json={"order_no": "NSEXT0003"}).json()["payment_intent"]
        r2 = pay_via_webhook(client, "NSEXT0002", pi2, "evt_ext_pu_1")
        r3 = pay_via_webhook(client, "NSEXT0003", pi3, "evt_ext_pu_2")
        s.expire_all()
        redemptions = s.query(DiscountRedemption).filter(
            DiscountRedemption.code_id == dc.id).all()
        dc_db = s.query(DiscountCode).filter(DiscountCode.code == "PUEXT1").first()
        o2_db = s.query(Order).filter(Order.order_no == "NSEXT0002").first()
        o3_db = s.query(Order).filter(Order.order_no == "NSEXT0003").first()
        check("P0-5 两单均支付成功（订单保留 PAID，不 5xx）",
              r2.status_code == 200 and r3.status_code == 200
              and o2_db.status == 1 and o3_db.status == 1,
              (r2.text, r3.text, o2_db.status, o3_db.status))
        check("P0-5 第二单不插 Redemption / used_count 不再自增（per-user 守卫）",
              len(redemptions) == 1 and dc_db.used_count == 1
              and redemptions[0].order_id == o2.id,
              (len(redemptions), dc_db.used_count))

        # ===== P0-2 superseded 旧 intent 迟到成功 → 自动退款防双扣款 =====
        o4 = make_order(s, "NSEXT0004", 2000, [(v1.id, 1, 2000)], user_id=emma.id)
        s.commit()
        pi4 = client.post("/api/payments/create-intent", headers=emma_auth,
                          json={"order_no": "NSEXT0004"}).json()["payment_intent"]
        r = pay_via_webhook(client, "NSEXT0004", pi4, "evt_ext_dup_1")
        # 模拟被 supersede 的旧 PENDING 行：用户在 provider 侧完成了旧 intent 支付
        stale = Payment(order_id=o4.id, stripe_payment_intent="PI_ext_stale_1",
                        amount=2000, status=0)
        s.add(stale)
        s.commit()
        r = pay_via_webhook(client, "NSEXT0004", "PI_ext_stale_1", "evt_ext_dup_2")
        s.expire_all()
        stale = s.query(Payment).filter(
            Payment.stripe_payment_intent == "PI_ext_stale_1").first()
        o4_db = s.query(Order).filter(Order.order_no == "NSEXT0004").first()
        outbox_dup = s.query(OutboxEvent).filter(
            OutboxEvent.aggregate_id == o4.id,
            OutboxEvent.event_type == "order.refunded").all()
        check("P0-2 旧 intent 迟到成功 → 本行全额自动退款（status 3 / refunded 2000）",
              r.status_code == 200 and stale.status == 3
              and stale.refunded_amount == 2000,
              (r.text, stale.status, stale.refunded_amount))
        check("P0-2 订单保持 PAID + 退款资金事件 full=False",
              o4_db.status == 1 and any(
                  (e.payload or {}).get("reason") == "duplicate_charge_auto_refund"
                  and (e.payload or {}).get("full") is False for e in outbox_dup),
              (o4_db.status, [e.payload for e in outbox_dup]))

        # ===== P0-3 PayPal 真实事件结构：normalize 映射 + webhook provider 路由 =====
        ne = pp.normalize_event({
            "id": "WH-EXT-1", "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {"id": "CAP-9", "custom_id": "NSEXT0009",
                         "amount": {"currency_code": "USD", "value": "15.00"},
                         "supplementary_data": {"related_ids": {
                             "order_id": "PAYID-EXT-9"}}},
        })
        check("P0-3 normalize PayPal COMPLETED → succeeded 语义 + intent/金额/订单号",
              ne["type"] == "payment_intent.succeeded"
              and ne["data"]["payment_intent"] == "PAYID-EXT-9"
              and ne["data"]["amount"] == 1500
              and ne["data"]["metadata"]["order_no"] == "NSEXT0009", ne)
        ne_r = pp.normalize_event({
            "id": "WH-EXT-2", "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "resource": {"id": "CAP-9", "amount": {"value": "5.00"}},
        })
        check("P0-3 normalize PayPal REFUNDED → charge.refunded + 美分换算",
              ne_r["type"] == "charge.refunded" and ne_r["data"]["amount"] == 500, ne_r)

        app_settings.paypal_client_id = "pid_ext"
        app_settings.paypal_secret = "psecret_ext"
        try:
            o5 = make_order(s, "NSEXT0005", 1500, [(v1.id, 1, 1500)], user_id=emma.id)
            o6 = make_order(s, "NSEXT0006", 1500, [(v1.id, 1, 1500)], user_id=emma.id)
            s.add(Payment(order_id=o5.id, stripe_payment_intent="PAYID-EXT-5",
                          amount=1500, status=0))
            s.add(Payment(order_id=o6.id, stripe_payment_intent="PAYID-EXT-6",
                          amount=1500, status=0))
            s.commit()
            r = client.post("/api/payments/webhook", json={
                "id": "WH-EXT-5", "event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {"id": "CAP-5", "custom_id": "NSEXT0005",
                             "amount": {"currency_code": "USD", "value": "15.00"},
                             "supplementary_data": {"related_ids": {
                                 "order_id": "PAYID-EXT-5"}}}})
            s.expire_all()
            o5_db = s.query(Order).filter(Order.order_no == "NSEXT0005").first()
            evt5 = s.get(repo.WebhookEvent, "WH-EXT-5")
            check("P0-3 PayPal webhook 按 intent 定位 → 订单 PAID（source=paypal）",
                  r.status_code == 200 and o5_db.status == 1
                  and evt5 is not None and evt5.source == "paypal",
                  (r.text, o5_db.status))
            r = client.post("/api/payments/webhook", json={
                "id": "WH-EXT-6", "event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {"id": "CAP-6", "custom_id": "NSEXT0006",
                             "amount": {"currency_code": "USD", "value": "15.00"}}})
            s.expire_all()
            o6_db = s.query(Order).filter(Order.order_no == "NSEXT0006").first()
            check("P0-3 PayPal 无 intent（capture id）→ 按 custom_id 订单定位 PENDING",
                  r.status_code == 200 and o6_db.status == 1,
                  (r.text, o6_db.status))
        finally:
            app_settings.paypal_client_id = ""
            app_settings.paypal_secret = ""
            pp._provider = None

        # ===== P1-6 下架（归档）商品不可加购：variant 仍 is_active 也拦截 =====
        r = client.post("/api/checkout/preview", json={
            "items": [{"variant_id": v2.id, "qty": 1}]})
        check("P1-6 归档商品(status=2)加购 → 409 product_unavailable",
              r.status_code == 409
              and r.json()["detail"] == f"product_unavailable:{v2.id}", r.text)

        # ===== P1-7 配送参数校验：country 非 2 字母 / shipping_method 白名单 =====
        r = client.post("/api/checkout/preview", json={
            "items": [{"variant_id": v1.id, "qty": 1}], "country": "USA"})
        check("P1-7 country=USA（非 2 字母）→ 422 invalid_country",
              r.status_code == 422 and "invalid_country" in r.text, r.text)
        r = client.post("/api/checkout/preview", json={
            "items": [{"variant_id": v1.id, "qty": 1}],
            "shipping_method": "rocket"})
        check("P1-7 shipping_method=rocket（白名单外）→ 422",
              r.status_code == 422, r.text)
        r = client.post("/api/checkout/preview", json={
            "items": [{"variant_id": v1.id, "qty": 1}],
            "country": "us", "shipping_method": "express"})
        check("P1-7 country 小写归一 + express 白名单 → 200 正常试算",
              r.status_code == 200 and r.json().get("shipping_method") == "express",
              r.text[:200])

        s.close()
finally:
    app_settings.paypal_client_id = ""
    app_settings.paypal_secret = ""
    app_settings.env = "dev"
    pp._provider = None
    pp._mock_warned = False
    pp._paypal_warned = False

print(f"\n==== test_payments_ext: {PASSED} passed, {len(FAILED)} failed ====")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
