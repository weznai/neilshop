"""智能体 B 自测 —— 结算/订单/支付/退货/库存 全链路（GM_DB=sqlite:///./test_b.sqlite，夹具直建）"""

import os
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pymysql

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute("DROP DATABASE IF EXISTS glowmag_test_b")
    _cur.execute("CREATE DATABASE glowmag_test_b CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag_test_b?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.core.db import SessionLocal, utcnow
from app.core.enums import PointsReason
from app.core.security import create_token, hash_password
from app.main import app
from app.models import (
    Cart, Category, DiscountCode, DiscountRedemption, GiftCard, GiftCardLedger,
    Order, OrderItem, OrderTimeline, OutboxEvent, Payment, PointsLedger, Product,
    Setting, ShippingRate, StockMovement, User, Variant,
)

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


with TestClient(app) as client:
    s = SessionLocal()

    cat_nails = Category(slug="press-on-nails", name="Press-on Nails")
    cat_acc = Category(slug="accessories", name="Accessories")
    s.add_all([cat_nails, cat_acc])
    s.flush()
    p_bare = Product(slug="bare-gems", title="Bare Gems", category_id=cat_nails.id,
                     status=1, hero_image="https://img/bare.jpg", price_min=1599, price_max=1599)
    p_cherry = Product(slug="cherry-bomb", title="Cherry Bomb", category_id=cat_nails.id,
                       status=1, hero_image="https://img/cherry.jpg", price_min=1399, price_max=1399)
    p_winter = Product(slug="winter-storm", title="Winter Storm", category_id=cat_nails.id,
                       status=1, hero_image="https://img/winter.jpg", price_min=1599, price_max=1599)
    p_glue = Product(slug="magic-glue", title="Magic Glue", category_id=cat_acc.id,
                     status=1, hero_image="https://img/glue.jpg", price_min=1399, price_max=1399)
    s.add_all([p_bare, p_cherry, p_winter, p_glue])
    s.flush()
    v_bare = Variant(product_id=p_bare.id, sku="BG-SA", option1_value="Short Almond",
                     option2_value="24pcs", price=1599, stock=99)
    v_cherry = Variant(product_id=p_cherry.id, sku="CB-SS", option1_value="Short Square",
                       option2_value="24pcs", price=1399, stock=99)
    v_winter = Variant(product_id=p_winter.id, sku="WS-X", option1_value="Xtreme",
                       option2_value="24pcs", price=1599, stock=99)
    v_glue = Variant(product_id=p_glue.id, sku="GL-01", option1_value="Standard",
                     option2_value="0.5oz", price=1399, stock=50)
    s.add_all([v_bare, v_cherry, v_winter, v_glue])

    emma = User(email="emma@glow.test", password_hash=hash_password("x"), name="Emma",
                role=0, points=500)
    admin = User(email="admin@glow.test", password_hash=hash_password("x"), name="Ops",
                 role=9)
    s.add_all([emma, admin])
    s.flush()
    s.add(PointsLedger(user_id=emma.id, change=500, balance_after=500,
                       reason=int(PointsReason.CHECKIN), frozen=0))

    s.add(DiscountCode(code="WELCOME20", name="首单 8 折", type=1, value=20,
                       max_discount=1000, min_subtotal=0, first_order_only=1,
                       per_user_limit=1, is_active=1))
    s.add(GiftCard(code="GC-TEST-0001", initial_amount=2000, balance=2000,
                   status=1, purchaser_email="emma@glow.test"))
    s.add_all([
        Setting(key="shipping_standard", value=499),
        Setting(key="shipping_express", value=1499),
    ])
    s.add_all([
        ShippingRate(dest_country="US", carrier="usps", method="standard",
                     max_weight_g=500, price=499, free_over=3500,
                     eta_min_days=3, eta_max_days=6),
        ShippingRate(dest_country="US", carrier="ups", method="express",
                     max_weight_g=500, price=1499,
                     eta_min_days=1, eta_max_days=3),
        ShippingRate(dest_country="*", carrier="dhl", method="standard",
                     max_weight_g=500, price=1299,
                     eta_min_days=6, eta_max_days=12),
    ])
    cart_main = Cart(user_id=emma.id, session_id="tok-main",
                     items=[{"variantId": v_bare.id, "qty": 1}, {"variantId": v_glue.id, "qty": 1}])
    cart_gc = Cart(session_id="tok-gc",
                   items=[{"variantId": v_bare.id, "qty": 1}, {"variantId": v_glue.id, "qty": 1}])
    s.add_all([cart_main, cart_gc])
    s.commit()

    emma_auth = {"Authorization": f"Bearer {create_token(emma.id, emma.role)}"}
    admin_auth = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}
    guest_main = {"X-Cart-Token": "tok-main"}
    guest_gc = {"X-Cart-Token": "tok-gc"}

    def stock(vid):
        s.expire_all()
        return s.get(Variant, vid).stock

    def order_by_no(no):
        s.expire_all()
        return s.query(Order).filter(Order.order_no == no).first()

    def last_payment(order_id):
        s.expire_all()
        return (s.query(Payment).filter(Payment.order_id == order_id)
                .order_by(Payment.id.desc()).first())

    def set_cart_items(cart_id, items):
        s.expire_all()
        c = s.get(Cart, cart_id)
        c.items = items
        s.commit()

    # ===== preview =====
    r = client.post("/api/checkout/preview", headers={**guest_main, **emma_auth},
                    json={"code": "WELCOME20", "email": "emma@glow.test"})
    d = r.json()
    check("preview 主车 subtotal=2998", r.status_code == 200 and d["subtotal"] == 2998, d)
    check("preview WELCOME20 立减 600（对齐原型 −$6.00）",
          d["code_valid"] is True and d["code_discount"] == 600, d)
    check("preview 运费 499 / 税 213 / 总额 3110（原型 $31.10）",
          d["shipping_fee"] == 499 and d["tax"] == 213 and d["grand_total"] == 3110, d)

    r = client.post("/api/checkout/preview", json={
        "items": [{"variant_id": v_bare.id, "qty": 1}, {"variant_id": v_cherry.id, "qty": 1}]})
    d = r.json()
    check("preview 捆绑 2 件 press-on → 15% off = 449",
          d["bundle_qty"] == 2 and d["bundle_discount"] == 449, d)

    r = client.post("/api/checkout/preview", json={
        "items": [{"variant_id": v_bare.id, "qty": 1}, {"variant_id": v_cherry.id, "qty": 1},
                  {"variant_id": v_winter.id, "qty": 1}]})
    d = r.json()
    check("preview 捆绑 3 件 → 20% off = 919 且满 3500 免邮",
          d["bundle_discount"] == 919 and d["shipping_fee"] == 0 and d["grand_total"] == 3948, d)

    r = client.post("/api/checkout/preview", json={
        "items": [{"variant_id": v_bare.id, "qty": 1}, {"variant_id": v_glue.id, "qty": 1}],
        "code": "NOPE123"})
    d = r.json()
    check("preview 无效码 → code_not_found 不计折扣",
          d["code_valid"] is False and d["code_reason"] == "code_not_found"
          and d["grand_total"] == 3754, d)

    r = client.post("/api/checkout/preview", json={
        "items": [{"variant_id": v_bare.id, "qty": 1}], "points": 100})
    check("preview 游客用分 → 401", r.status_code == 401, r.text)

    r = client.post("/api/checkout/preview", headers=emma_auth, json={
        "items": [{"variant_id": v_bare.id, "qty": 1}], "points": 900})
    check("preview 积分超可用余额 → 409", r.status_code == 409, r.text)

    r = client.post("/api/checkout/preview", json={
        "items": [{"variant_id": v_bare.id, "qty": 1}, {"variant_id": v_glue.id, "qty": 1}],
        "gift_card_code": "GC-TEST-0001"})
    d = r.json()
    check("preview 礼品卡抵 2000 → tax 110 / 总额 1607",
          d["giftcard_discount"] == 2000 and d["tax"] == 110 and d["grand_total"] == 1607, d)

    # ===== place =====
    addr = {"full_name": "Emma Rodriguez", "line1": "2847 Mission St", "line2": "Apt 4B",
            "city": "San Francisco", "state": "CA", "zip": "94110", "country": "US",
            "phone": "+14155550123"}

    r = client.post("/api/checkout/place", headers={**guest_main, **emma_auth}, json={
        "email": "emma@glow.test", "address": addr, "shipping_method": "standard",
        "code": "WELCOME20"})
    d = r.json()
    main_no = d.get("order_no", "")
    main = order_by_no(main_no)
    check("place 主单 201 → NS 单号 PENDING 总额 3110",
          r.status_code == 201 and main_no.startswith("NS") and d["grand_total"] == 3110
          and d["status"] == 0, d)
    check("place 库存预扣 99/50 → 98/49 + RESERVE 流水",
          stock(v_bare.id) == 98 and stock(v_glue.id) == 49
          and s.query(StockMovement).filter(StockMovement.type == 2).count() == 2)
    check("place 清空购物车 + timeline checkout_created",
          s.get(Cart, cart_main.id).items == []
          and s.query(OrderTimeline).filter(OrderTimeline.order_id == main.id,
                                            OrderTimeline.event == "checkout_created").count() == 1)
    check("place 回填 cart.email（弃购召回依赖）",
          s.get(Cart, cart_main.id).email == "emma@glow.test", s.get(Cart, cart_main.id).email)

    # 90s 内同用户 items 完全相同的 PENDING 单 → 幂等返回原单（不重复建单扣库存）
    set_cart_items(cart_main.id, [{"variantId": v_bare.id, "qty": 1},
                                  {"variantId": v_glue.id, "qty": 1}])
    r = client.post("/api/checkout/place", headers={**guest_main, **emma_auth}, json={
        "email": "emma@glow.test", "address": addr, "shipping_method": "standard"})
    s.expire_all()
    check("place 重复提交幂等 → 返回原单 / 无新单 / 库存不再扣减",
          r.status_code == 201 and r.json()["order_no"] == main_no
          and s.query(Order).filter(Order.user_id == emma.id).count() == 1
          and stock(v_bare.id) == 98 and stock(v_glue.id) == 49, r.text[:200])

    set_cart_items(cart_main.id, [{"variantId": v_glue.id, "qty": 5000}])
    r = client.post("/api/checkout/place", headers={**guest_main, **emma_auth}, json={
        "email": "emma@glow.test", "address": addr})
    s.expire_all()
    check("place 超库存 → 409 整单回滚",
          r.status_code == 409 and "insufficient_stock" in r.text
          and s.query(Order).filter(Order.user_id == emma.id).count() == 1
          and stock(v_glue.id) == 49, r.text)

    # 用分下单：items 与主单不同（cherry+glue），避免命中 90s 幂等防重
    set_cart_items(cart_main.id, [{"variantId": v_cherry.id, "qty": 1},
                                  {"variantId": v_glue.id, "qty": 1}])
    r = client.post("/api/checkout/place", headers={**guest_main, **emma_auth}, json={
        "email": "emma@glow.test", "address": addr, "points": 300})
    d = r.json()
    order3_no = d.get("order_no", "")
    order3 = order_by_no(order3_no)
    s.expire_all()
    check("place 用分 300 → 总额 3217 / points_used 300 / 余额 500→200",
          r.status_code == 201 and d["grand_total"] == 3217 and order3.points_used == 300
          and s.get(User, emma.id).points == 200, d)
    check("place SPEND 积分流水落库",
          s.query(PointsLedger).filter(PointsLedger.user_id == emma.id,
                                       PointsLedger.reason == int(PointsReason.SPEND)).count() == 1)

    r = client.post(f"/api/orders/{order3_no}/cancel", headers=emma_auth)
    s.expire_all()
    check("cancel 待付单 → CANCELED + 库存回补 cherry 98→99 / glue 48→49 + RELEASE 流水",
          r.status_code == 200 and r.json()["status"] == 8
          and stock(v_cherry.id) == 99 and stock(v_glue.id) == 49
          and s.query(StockMovement).filter(StockMovement.type == 4).count() == 2, r.text)
    s.expire_all()
    check("cancel 已用积分返还 300（200→500）+ REFUND_RETURN 流水",
          s.get(User, emma.id).points == 500
          and s.query(PointsLedger).filter(
              PointsLedger.user_id == emma.id,
              PointsLedger.reason == int(PointsReason.REFUND_RETURN),
              PointsLedger.ref_id == order3.id).count() == 1,
          s.get(User, emma.id).points)
    r = client.post(f"/api/orders/{order3_no}/cancel", headers=emma_auth)
    check("cancel 非待付单 → 409", r.status_code == 409, r.text)

    # ===== payments =====
    r = client.post("/api/payments/create-intent", json={"order_no": main_no})
    d = r.json()
    check("create-intent → PI_+32hex / amount 3110 / 模拟 client_secret",
          r.status_code == 200 and d["payment_intent"].startswith("PI_")
          and len(d["payment_intent"]) == 35 and d["amount"] == 3110
          and d["client_secret"].endswith("_secret_mock"), d)

    r = client.post("/api/payments/mock-pay", json={"order_no": main_no, "succeed": False})
    d = r.json()
    check("mock-pay 失败 → Payment FAILED 订单保持 PENDING",
          r.status_code == 200 and d["payment_status"] == 2 and d["order_status"] == 0, d)

    r = client.post("/api/payments/create-intent", json={"order_no": main_no})
    r = client.post("/api/payments/mock-pay", json={"order_no": main_no, "succeed": True})
    d = r.json()
    main = order_by_no(main_no)
    s.expire_all()
    emma_db = s.get(User, emma.id)
    outbox_paid = s.query(OutboxEvent).filter(OutboxEvent.event_type == "order.paid",
                                              OutboxEvent.aggregate_id == main.id).first()
    redemption = s.query(DiscountRedemption).filter(DiscountRedemption.order_id == main.id).first()
    grant_ledger = s.query(PointsLedger).filter(
        PointsLedger.user_id == emma.id,
        PointsLedger.reason == int(PointsReason.ORDER_EARN_FROZEN)).first()
    check("mock-pay 成功 → 订单 PAID / 支付 SUCCESS",
          r.status_code == 200 and main.status == 1 and main.paid_at is not None
          and d["payment_status"] == 1, d)
    check("mock-pay 积分入账 311 分冻结（$31.10×10）",
          main.points_earned == 311 and grant_ledger is not None and grant_ledger.frozen == 1
          and emma_db.points == 811, main.points_earned)
    check("mock-pay total_spent 3110 + outbox order.paid + Redemption 600 + used_count+1",
          emma_db.total_spent == 3110 and outbox_paid is not None
          and outbox_paid.payload["grand_total"] == 3110
          and redemption is not None and redemption.discount_amount == 600
          and s.query(DiscountCode).filter(DiscountCode.code == "WELCOME20").first().used_count == 1)
    check("mock-pay 库存实扣确认 DEDUCT(type=3, 库存不再变动)",
          s.query(StockMovement).filter(StockMovement.type == 3).count() == 2
          and stock(v_bare.id) == 98, stock(v_bare.id))

    # ===== orders =====
    r = client.get("/api/orders", headers=emma_auth)
    d = r.json()
    check("GET /api/orders 登录列表含两单",
          r.status_code == 200 and d["total"] == 2
          and {o["order_no"] for o in d["items"]} == {main_no, order3_no}, d)
    r = client.get("/api/orders")
    check("GET /api/orders 未登录 → 401", r.status_code == 401, r.text)

    r = client.get(f"/api/orders/{main_no}", params={"email": "emma@glow.test"})
    d = r.json()
    check("GET /api/orders/{no}?email= 游客可查含 items/timeline/payments",
          r.status_code == 200 and len(d["items"]) == 2 and len(d["timeline"]) >= 3
          and len(d["payments"]) == 2, d)
    r = client.get(f"/api/orders/{main_no}", params={"email": "wrong@x.test"})
    check("GET /api/orders/{no} 邮箱不符 → 404", r.status_code == 404, r.text)

    r = client.get("/api/orders/track", params={"no": main_no, "email": "emma@glow.test"})
    check("track 付费单无 shipment", r.status_code == 200 and r.json()["shipments"] == [], r.text)

    r = client.get("/api/admin/trade/orders", headers=emma_auth)
    check("admin 接口非管理员 → 403", r.status_code == 403, r.text)

    # ===== 礼品卡 + webhook =====
    r = client.post("/api/checkout/place", headers=guest_gc, json={
        "email": "mia@glow.test", "address": addr, "gift_card_code": "GC-TEST-0001"})
    d = r.json()
    order2_no = d.get("order_no", "")
    s.expire_all()
    gc = s.query(GiftCard).filter(GiftCard.code == "GC-TEST-0001").first()
    gc_ledger = s.query(GiftCardLedger).filter(GiftCardLedger.order_id.isnot(None)).first()
    check("place 礼品卡 MVP 即扣 → balance 0 / 状态用尽 / ledger change_type=3",
          r.status_code == 201 and d["grand_total"] == 1607 and d["giftcard_discount"] == 2000
          and gc.balance == 0 and gc.status == 3
          and gc_ledger is not None and gc_ledger.change_type == 3, d)

    r = client.post("/api/payments/create-intent", json={"order_no": order2_no})
    pi2 = r.json()["payment_intent"]
    r = client.post("/api/payments/webhook", json={
        "id": "evt_gc_1", "type": "payment_intent.succeeded", "data": {"payment_intent": pi2}})
    order2 = order_by_no(order2_no)
    check("webhook payment_intent.succeeded → 订单 PAID",
          r.status_code == 200 and order2.status == 1, r.text)
    r = client.post("/api/payments/webhook", json={
        "id": "evt_gc_1", "type": "payment_intent.succeeded", "data": {"payment_intent": pi2}})
    check("webhook 同 event_id 幂等 → ok-duplicate",
          r.status_code == 200 and r.json().get("duplicate") is True, r.text)

    # ===== admin 履约 + RMA =====
    r = client.get("/api/admin/trade/orders", headers=admin_auth, params={"q": main_no})
    d = r.json()
    check("admin 订单搜索 q=order_no 命中",
          r.status_code == 200 and any(o["order_no"] == main_no for o in d["items"]), d)
    r = client.get(f"/api/admin/trade/orders/{main_no}", headers=admin_auth)
    d = r.json()
    check("admin 订单详情含 Redemption 600",
          r.status_code == 200 and len(d["redemptions"]) == 1
          and d["redemptions"][0]["discount_amount"] == 600, d)

    r = client.post(f"/api/admin/trade/orders/{main_no}/ship", headers=admin_auth,
                    json={"carrier": "usps", "tracking_no": "9400110200880"})
    d = r.json()
    main = order_by_no(main_no)
    check("admin ship → SP 单号 IN_TRANSIT / 订单 SHIPPED / tracking 冗余",
          r.status_code == 200 and d["shipment_no"].startswith("SP") and main.status == 3
          and main.tracking_no == "9400110200880" and main.shipping_status == 2, d)

    r = client.get("/api/orders/track", params={"no": main_no, "email": "emma@glow.test"})
    d = r.json()
    check("track 显示 shipment(tracking/carrier)",
          r.status_code == 200 and d["shipments"][0]["tracking_no"] == "9400110200880"
          and d["shipments"][0]["carrier"] == "usps", d)

    r = client.post(f"/api/admin/trade/orders/{main_no}/mark-delivered", headers=admin_auth)
    main = order_by_no(main_no)
    check("admin mark-delivered → DELIVERED + delivered_at",
          r.status_code == 200 and main.status == 4 and main.delivered_at is not None, r.text)

    main = order_by_no(main_no)
    main_item = s.query(OrderItem).filter(OrderItem.order_id == main.id,
                                          OrderItem.variant_id == v_bare.id).first()
    r = client.post("/api/returns", headers=emma_auth, json={
        "order_no": main_no, "order_item_id": main_item.id, "qty": 1,
        "reason": 2, "reason_detail": "chipped on arrival"})
    d = r.json()
    rma_no = d.get("rma_no", "")
    check("RMA 申请 → RMA 单号 status=0 + timeline rma_created",
          r.status_code == 201 and rma_no.startswith("RMA") and d["status"] == 0
          and s.query(OrderTimeline).filter(OrderTimeline.event == "rma_created").count() == 1, d)

    r = client.get("/api/returns", headers=emma_auth)
    check("RMA 列表含快照", r.status_code == 200 and any(
        x["rma_no"] == rma_no and "Bare Gems" in (x["item"] or {}).get("title", "")
        for x in r.json()["items"]), r.text)
    r = client.get(f"/api/returns/{rma_no}", headers=emma_auth)
    check("RMA 详情", r.status_code == 200 and r.json()["rma_no"] == rma_no, r.text)

    r = client.post("/api/returns", headers=emma_auth, json={
        "order_no": order3_no, "order_item_id": main_item.id, "qty": 1, "reason": 3})
    check("RMA 不可退状态订单 → 409", r.status_code == 409, r.text)
    r = client.post("/api/returns", headers=emma_auth, json={
        "order_no": main_no, "order_item_id": main_item.id, "qty": 5, "reason": 3})
    check("RMA 超可退量 → 409", r.status_code == 409, r.text)
    r = client.post("/api/returns", headers=emma_auth, json={
        "order_no": main_no, "order_item_id": main_item.id, "qty": 1, "reason": 9})
    check("RMA reason 越界 → 422", r.status_code == 422, r.text)

    main = order_by_no(main_no)
    main.paid_at = utcnow() - timedelta(days=40)
    s.commit()
    r = client.post("/api/returns", headers=emma_auth, json={
        "order_no": main_no, "order_item_id": main_item.id, "qty": 1, "reason": 3})
    check("RMA 超 30 天窗口 → 409", r.status_code == 409 and "window" in r.text, r.text)
    main.paid_at = utcnow()
    s.commit()

    r = client.get("/api/admin/trade/rmas", headers=admin_auth, params={"status": 0})
    d = r.json()
    check("admin RMA 队列含 email/商品快照",
          r.status_code == 200 and any(x["rma_no"] == rma_no and x["email"] == "emma@glow.test"
                                       and "Bare Gems" in x["item_title"] for x in d["items"]), d)

    r = client.post(f"/api/admin/trade/rmas/{rma_no}/approve", headers=admin_auth)
    d = r.json()
    check("RMA approve → label_sent + 模拟面单",
          r.status_code == 200 and d["status"] == 2 and d["label_url"].startswith("https://mock"), d)

    r = client.post(f"/api/admin/trade/rmas/{rma_no}/receive", headers=admin_auth)
    d = r.json()
    check("RMA receive → 收货回补库存 97→98 + restock 流水(type=5 rma)",
          r.status_code == 200 and d["status"] == 4 and d["restock_qty"] == 1
          and stock(v_bare.id) == 98, d)

    r = client.post(f"/api/admin/trade/rmas/{rma_no}/refund", headers=admin_auth)
    d = r.json()
    main = order_by_no(main_no)
    payment = last_payment(main.id)
    s.expire_all()
    main_item = s.query(OrderItem).filter(OrderItem.order_id == main.id,
                                          OrderItem.variant_id == v_bare.id).first()
    check("RMA refund → 退款 1599×(3110/2998)=1659 + 运费按件分摊 499×1/2=250 → 1909"
          "（含税分摊）/ Payment 部分退 / refunded_qty=1 / 订单状态不变",
          r.status_code == 200 and d["refund_amount"] == 1909 and d["refund_shipping"] == 250
          and payment.status == 4 and payment.refunded_amount == 1909
          and main_item.refunded_qty == 1 and main.status == 4, d)

    r = client.post(f"/api/admin/trade/orders/{main_no}/refund", headers=admin_auth,
                    json={"reason": "customer service full refund"})
    d = r.json()
    main = order_by_no(main_no)
    payment = last_payment(main.id)
    s.expire_all()
    emma_db = s.get(User, emma.id)
    outbox_refunded = s.query(OutboxEvent).filter(
        OutboxEvent.event_type == "order.refunded",
        OutboxEvent.aggregate_id == main.id).first()
    void_ledger = s.query(PointsLedger).filter(
        PointsLedger.user_id == emma.id,
        PointsLedger.reason == int(PointsReason.REFUND_VOID)).first()
    check("admin 全额退（补齐剩余 1201）→ Payment 全退 3110 / 订单 REFUNDED",
          r.status_code == 200 and payment.status == 3 and payment.refunded_amount == 3110
          and main.status == 9, d)
    check("全额退 → 积分作废 311（811→500）+ outbox order.refunded",
          emma_db.points == 500 and void_ledger is not None and outbox_refunded is not None,
          emma_db.points)
    check("全额退库存只回补未退部分（bare 不重复回补 98 / glue +1=49）",
          stock(v_bare.id) == 98 and stock(v_glue.id) == 49,
          (stock(v_bare.id), stock(v_glue.id)))

    # ===== 库存管理 =====
    r = client.post("/api/admin/trade/stock/adjust", headers=admin_auth,
                    json={"variant_id": v_cherry.id, "change": 5, "reason": "补货入库"})
    d = r.json()
    check("库存手工调增 +5 → 104 + MANUAL 流水(operator=admin)",
          r.status_code == 200 and d["stock"] == 104 and stock(v_cherry.id) == 104
          and s.query(StockMovement).filter(StockMovement.type == 7,
                                            StockMovement.operator == "admin@glow.test").count() == 1, d)
    r = client.post("/api/admin/trade/stock/adjust", headers=admin_auth,
                    json={"variant_id": v_winter.id, "change": -200, "reason": "越界"})
    check("库存调负越界 → 409", r.status_code == 409, r.text)
    r = client.post("/api/admin/trade/stock/adjust", headers=admin_auth,
                    json={"variant_id": v_winter.id, "change": -96, "reason": "促销消耗"})
    check("库存调减 -96 → 3", r.status_code == 200 and stock(v_winter.id) == 3, r.text)

    r = client.get("/api/admin/trade/stock/low", headers=admin_auth, params={"threshold": 8})
    d = r.json()
    check("低库存预警 → winter(3) 命中且带商品名",
          any(x["variant_id"] == v_winter.id and x["stock"] == 3
              and "Winter" in x["product_title"] for x in d["items"])
          and not any(x["variant_id"] == v_cherry.id for x in d["items"]), d)

    r = client.get("/api/admin/trade/stock/movements", headers=admin_auth,
                   params={"variant_id": v_bare.id})
    types = [m["type"] for m in r.json()["items"]]
    check("库存流水分页含 RESERVE/DEDUCT/RESTOCK",
          r.status_code == 200 and 2 in types and 3 in types and 5 in types, types)

    # ===== 运费模板（ShippingRate 激活：管理 CRUD + pricing 实时读取） =====
    r = client.get("/api/admin/trade/shipping-rates", headers=admin_auth)
    rates = r.json()["items"]
    check("运费模板列表含 seed（usps standard 499 / ups express 1499 / dhl *）",
          r.status_code == 200 and len(rates) >= 3
          and any(x["carrier"] == "usps" and x["price"] == 499 for x in rates)
          and any(x["carrier"] == "ups" and x["method"] == "express" for x in rates), rates)
    usps = next(x for x in rates if x["carrier"] == "usps")
    r = client.put(f"/api/admin/trade/shipping-rates/{usps['id']}", headers=admin_auth,
                   json={"price": 599})
    check("改模板价 499→599 → preview 运费即时变化（表驱动）",
          r.status_code == 200 and r.json()["price"] == 599
          and client.post("/api/checkout/preview", json={
              "items": [{"variant_id": v_bare.id, "qty": 1}]}).json()["shipping_fee"] == 599,
          r.text)
    r = client.put(f"/api/admin/trade/shipping-rates/{usps['id']}", headers=admin_auth,
                   json={"price": 499})
    check("还原 499 → preview 恢复基线",
          r.status_code == 200
          and client.post("/api/checkout/preview", json={
              "items": [{"variant_id": v_bare.id, "qty": 1}]}).json()["shipping_fee"] == 499)
    r = client.post("/api/admin/trade/shipping-rates", headers=admin_auth, json={
        "dest_country": "CA", "carrier": "canada-post", "method": "standard",
        "price": 899, "eta_min_days": 5, "eta_max_days": 9})
    check("新建 CA 模板 899（country 精确优先）",
          r.status_code == 201 and r.json()["active"] is True, r.text)
    ca_id = r.json()["id"]
    check("公开 shipping-methods 聚合（US standard=499 / express=1499）",
          (lambda ms: any(m["method"] == "standard" and m["price"] == 499 for m in ms)
           and any(m["method"] == "express" and m["price"] == 1499 for m in ms))(
              client.get("/api/checkout/shipping-methods").json()["items"]))
    check("运费模板未授权 401",
          client.get("/api/admin/trade/shipping-rates").status_code == 401)
    check("eta 倒挂 422",
          client.post("/api/admin/trade/shipping-rates", headers=admin_auth, json={
              "dest_country": "MX", "carrier": "dhl", "method": "standard",
              "price": 799, "eta_min_days": 9, "eta_max_days": 3}).status_code == 422)
    check("改不存在模板 404",
          client.put("/api/admin/trade/shipping-rates/999", headers=admin_auth,
                     json={"price": 1}).status_code == 404)

    s.close()

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
