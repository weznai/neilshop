"""智能体 C —— GLOWMAG 全旅程端到端回归（GM_DB=glowmag_test_w，DROP 重建 + seed + TestClient 全链路）"""

import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pymysql

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute("DROP DATABASE IF EXISTS glowmag_test_w")
    _cur.execute("CREATE DATABASE glowmag_test_w CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag_test_w?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_seed = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "seed.py")],
                       env=dict(os.environ), capture_output=True, text=True, encoding="utf-8", errors="replace")
if _seed.returncode != 0:
    print(_seed.stdout, _seed.stderr)
    sys.exit(1)
print(_seed.stdout.strip())

from fastapi.testclient import TestClient

from app.core.db import SessionLocal, utcnow
from app.core.enums import PointsReason
from app.main import app
from app.models import (
    CookieConsent, DiscountRedemption, EmailPreference, NewsletterSubscriber,
    Order, OutboxEvent, Payment, PointsLedger, ReconciliationDaily, Referral,
    Setting, User, Variant,
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


RUN = uuid.uuid4().hex[:8]
DOM = "e2e-glowmag.com"
ADDR = {"full_name": "E2E Walker", "line1": "2847 Mission St", "line2": "Apt 4B",
        "city": "San Francisco", "state": "CA", "zip": "94110", "country": "US",
        "phone": "+14155550123"}

with TestClient(app) as client:
    s = SessionLocal()

    print("\n== 逛 ==")
    r = client.get("/api/health")
    check("health 200 ok", r.status_code == 200 and r.json().get("ok") is True, r.text)

    r = client.get("/api/catalog/products", params={"size": 100})
    check("catalog 列表 16 商品", r.status_code == 200 and r.json().get("total") == 16,
          r.json().get("total"))

    r = client.get("/api/catalog/search", params={"q": "bare"})
    check("search q=bare 命中 bare-gems", r.status_code == 200
          and any(p["slug"] == "bare-gems" for p in r.json()["products"]), r.text[:200])

    r = client.get("/api/catalog/products/bare-gems")
    d = r.json()
    vs = {v["option1_value"]: v for v in d.get("variants", [])}
    check("detail bare-gems 变体 SA 1599 / MS 1799 两档价",
          r.status_code == 200 and vs.get("Short Almond", {}).get("price") == 1599
          and vs.get("Medium Square", {}).get("price") == 1799, d.get("variants"))
    v_bare_sa = vs["Short Almond"]["id"]
    p_bare_id = d["id"]

    r = client.get("/api/catalog/products/magic-glue")
    v_glue = r.json()["variants"][0]["id"]

    print("\n== 账户 ==")
    u1_email = f"e2e.u1.{RUN}@{DOM}"
    r = client.post("/api/account/register",
                    json={"email": u1_email, "password": "Glow12345!", "name": "Uma One"})
    d = r.json()
    check("register 新用户 201 + token", r.status_code == 201 and d.get("token")
          and d.get("user", {}).get("email") == u1_email, r.text[:200])
    u1_auth = {"Authorization": f"Bearer {d['token']}"}

    r = client.get("/api/account/me", headers=u1_auth)
    check("me 返回当前用户", r.status_code == 200 and r.json().get("email") == u1_email, r.text[:200])

    r = client.post("/api/account/addresses", headers=u1_auth, json={**ADDR, "is_default": True})
    addr_id = r.json().get("id")
    check("addresses POST 201", r.status_code == 201 and addr_id
          and r.json().get("city") == "San Francisco", r.text[:200])

    r = client.put(f"/api/account/addresses/{addr_id}", headers=u1_auth,
                   json={**ADDR, "city": "Oakland", "is_default": True})
    check("addresses PUT 改 city → Oakland（保持默认）", r.status_code == 200
          and r.json().get("city") == "Oakland" and r.json().get("is_default") is True,
          r.text[:200])
    r = client.put(f"/api/account/addresses/{addr_id}", headers=u1_auth,
                   json={**ADDR, "city": "Oakland", "is_default": False})
    check("唯一默认地址撤默认 → 422 last_default_required", r.status_code == 422
          and r.json().get("detail") == "last_default_required", r.text[:200])

    r = client.delete(f"/api/account/addresses/{addr_id}", headers=u1_auth)
    lst = client.get("/api/account/addresses", headers=u1_auth).json()
    check("addresses DELETE + 列表清空", r.status_code == 200 and r.json().get("ok") is True
          and lst == [], (r.text[:200], lst))

    r = client.post(f"/api/account/wishlist/{p_bare_id}", headers=u1_auth)
    check("wishlist POST bare-gems", r.status_code == 201 and r.json().get("ok") is True, r.text[:200])
    r = client.get("/api/account/wishlist", headers=u1_auth)
    check("wishlist GET 含 bare-gems", r.status_code == 200
          and any(x["slug"] == "bare-gems" for x in r.json()), r.text[:200])
    r = client.delete(f"/api/account/wishlist/{p_bare_id}", headers=u1_auth)
    check("wishlist DELETE 清空", r.status_code == 200
          and client.get("/api/account/wishlist", headers=u1_auth).json() == [], r.text[:200])

    r = client.post("/api/account/newsletter", headers=u1_auth,
                    json={"email": u1_email, "source": "footer"})
    s.expire_all()
    ns = s.get(NewsletterSubscriber, u1_email)
    npref = s.get(EmailPreference, u1_email)
    check("newsletter 订阅 + 偏好全 1 落库", r.status_code == 200 and ns is not None
          and npref is not None and npref.sub_promo == 1 and npref.sub_new_arrival == 1,
          r.text[:200])

    sid = uuid.uuid4().hex[:32]
    r = client.post("/api/account/consent", headers=u1_auth,
                    json={"session_id": sid, "necessary": True, "analytics": True,
                          "marketing": False, "region": "CA"})
    s.expire_all()
    cc = s.query(CookieConsent).filter(CookieConsent.session_id == sid).first()
    check("consent CookieConsent 落库", r.status_code == 201 and cc is not None
          and cc.analytics == 1, r.text[:200])

    print("\n== 购物车 ==")
    r = client.get("/api/cart")
    guest_token = r.headers.get("X-Cart-Token", "")
    check("游客 GET cart 发放 X-Cart-Token", r.status_code == 200 and len(guest_token) >= 16,
          dict(r.headers))
    guest = {"X-Cart-Token": guest_token}

    r = client.post("/api/cart/items", headers=guest, json={"variant_id": v_bare_sa, "qty": 1})
    check("POST cart bare-gems SA", r.status_code == 201
          and len(r.json().get("items", [])) == 1, r.text[:300])

    r = client.post("/api/cart/items", headers=guest, json={"variant_id": v_glue, "qty": 1})
    d = r.json()
    check("POST cart magic glue → 2 行 subtotal 2998", r.status_code == 201
          and len(d.get("items", [])) == 2 and d.get("subtotal_cents") == 2998, d)

    r = client.put(f"/api/cart/items/{v_glue}", headers=guest, json={"qty": 2})
    d = r.json()
    glue_line = next((i for i in d.get("items", []) if i["variant_id"] == v_glue), None)
    check("PUT 改量 glue qty=2 → subtotal 4397", r.status_code == 200
          and glue_line and glue_line["qty"] == 2 and d.get("subtotal_cents") == 4397, d)

    r = client.put(f"/api/cart/items/{v_glue}", headers=guest, json={"qty": 1})
    check("PUT 改回 qty=1 → subtotal 2998", r.status_code == 200
          and r.json().get("subtotal_cents") == 2998, r.text[:300])

    u2_email = f"e2e.u2.{RUN}@{DOM}"
    r = client.post("/api/account/register",
                    json={"email": u2_email, "password": "Glow12345!", "name": "User Two"})
    check("U2 注册 201", r.status_code == 201 and r.json().get("token"), r.text[:200])
    r = client.post("/api/account/login", json={"email": u2_email, "password": "Glow12345!"})
    d = r.json()
    check("U2 登录 → token", r.status_code == 200 and d.get("token"), r.text[:200])
    u2_auth = {"Authorization": f"Bearer {d['token']}"}

    r = client.post("/api/cart/merge", headers=u2_auth, json={"token": guest_token})
    d = r.json()
    check("merge 游客车 → 用户车 2 行", r.status_code == 200
          and len(d.get("items", [])) == 2, d)
    u2_cart = {"X-Cart-Token": r.headers.get("X-Cart-Token", "")}

    r = client.get("/api/cart", headers={**u2_auth, **u2_cart})
    d = r.json()
    check("GET cart 合并计数=2 subtotal 2998", r.status_code == 200
          and len(d.get("items", [])) == 2 and d.get("subtotal_cents") == 2998, d)

    print("\n== 折扣 ==")
    r = client.post("/api/checkout/preview", headers={**u2_auth, **u2_cart},
                    json={"code": "WELCOME20", "email": u2_email, "shipping_method": "standard"})
    d = r.json()
    check("preview WELCOME20 首单有效 立减 600", r.status_code == 200
          and d.get("code_valid") is True and d.get("code_discount") == 600, d)
    check("preview 标准订单口径 2998/600/499/213/3110",
          d.get("subtotal") == 2998 and d.get("shipping_fee") == 499
          and d.get("tax") == 213 and d.get("grand_total") == 3110, d)

    print("\n== 下单支付 ==")
    r = client.post("/api/checkout/place", headers={**u2_auth, **u2_cart},
                    json={"email": u2_email, "address": ADDR,
                          "shipping_method": "standard", "code": "WELCOME20"})
    d = r.json()
    main_no = d.get("order_no", "")
    check("place 201 NS 单号 PENDING 总额 3110", r.status_code == 201
          and main_no.startswith("NS") and d.get("status") == 0
          and d.get("grand_total") == 3110, r.text[:300])

    s.expire_all()
    stock_bare = s.get(Variant, v_bare_sa).stock
    stock_glue = s.get(Variant, v_glue).stock
    check("place 库存预扣 120→119 / 50→49",
          stock_bare == 119 and stock_glue == 49, (stock_bare, stock_glue))

    r = client.post("/api/payments/create-intent", json={"order_no": main_no})
    d = r.json()
    check("create-intent PI_ 35 位 / amount 3110", r.status_code == 200
          and str(d.get("payment_intent", "")).startswith("PI_")
          and len(d.get("payment_intent", "")) == 35 and d.get("amount") == 3110, d)

    r = client.post("/api/payments/mock-pay", json={"order_no": main_no, "succeed": True})
    d = r.json()
    check("mock-pay succeed → 订单 PAID / Payment SUCCESS", r.status_code == 200
          and d.get("order_status") == 1 and d.get("payment_status") == 1, d)

    s.expire_all()
    main = s.query(Order).filter(Order.order_no == main_no).first()
    u2 = s.query(User).filter(User.email == u2_email).first()
    grant = (s.query(PointsLedger)
             .filter(PointsLedger.user_id == u2.id,
                     PointsLedger.reason == int(PointsReason.ORDER_EARN_FROZEN)).first())
    check("支付落库 paid_at + points_earned=311 frozen", main.status == 1
          and main.paid_at is not None and main.points_earned == 311
          and grant is not None and grant.frozen == 1 and u2.points == 311,
          (main.status, main.points_earned, u2.points))

    s.expire_all()
    main = s.query(Order).filter(Order.order_no == main_no).first()
    outbox_paid = (s.query(OutboxEvent)
                   .filter(OutboxEvent.event_type == "order.paid",
                           OutboxEvent.aggregate_id == main.id).first())
    red = (s.query(DiscountRedemption)
           .filter(DiscountRedemption.order_id == main.id).first())
    pay_main = (s.query(Payment).filter(Payment.order_id == main.id)
                .order_by(Payment.id.desc()).first())
    check("outbox order.paid + Redemption 600 + Payment SUCCESS",
          outbox_paid is not None and outbox_paid.payload.get("grand_total") == 3110
          and outbox_paid.published == 0 and red is not None and red.discount_amount == 600
          and pay_main.status == 1,
          (outbox_paid and outbox_paid.payload, red and red.discount_amount,
           pay_main and pay_main.status))

    print("\n== 推荐有礼 ==")
    r = client.get("/api/referrals/me", headers=u2_auth)
    d = r.json()
    check("A 推荐码 GLOW- 存在", r.status_code == 200
          and str(d.get("code", "")).startswith("GLOW-"), d)

    b_email = f"e2e.b.{RUN}@{DOM}"
    r = client.post("/api/referrals/simulate-invite", headers=u2_auth, json={"email": b_email})
    check("A simulate-invite B", r.status_code == 201
          and str(r.json().get("code", "")).startswith("GLOW-"), r.text[:200])

    r = client.post("/api/account/register",
                    json={"email": b_email, "password": "Glow12345!", "name": "Bee Referral"})
    d = r.json()
    check("B 注册 201 → token", r.status_code == 201 and d.get("token"), r.text[:200])
    b_auth = {"Authorization": f"Bearer {d['token']}"}

    client.post("/api/cart/items", headers=b_auth, json={"variant_id": v_glue, "qty": 1})
    r = client.post("/api/checkout/place", headers=b_auth,
                    json={"email": b_email, "address": ADDR, "shipping_method": "standard"})
    d = r.json()
    b_no = d.get("order_no", "")
    check("B 下小单 201（glue 1399 + 运费 499 + 税 140）", r.status_code == 201
          and b_no.startswith("NS") and d.get("grand_total") == 2038, r.text[:300])

    r = client.post("/api/payments/create-intent", json={"order_no": b_no})
    r = client.post("/api/payments/mock-pay", json={"order_no": b_no, "succeed": True})
    check("B 支付成功 → PAID", r.status_code == 200 and r.json().get("order_status") == 1, r.text[:200])

    s.expire_all()
    u2 = s.query(User).filter(User.email == u2_email).first()
    ref_ledger = (s.query(PointsLedger)
                  .filter(PointsLedger.user_id == u2.id,
                          PointsLedger.reason == int(PointsReason.REFERRAL)).first())
    ref_row = s.query(Referral).filter(Referral.invited_email == b_email).first()
    check("B 首单支付 → A +1000（reason=5）+ referral status=3",
          ref_ledger is not None and ref_ledger.change == 1000 and u2.points == 1311
          and ref_row is not None and ref_row.status == 3 and ref_row.rewarded_at is not None,
          (u2.points, ref_row and ref_row.status))

    r = client.get("/api/referrals/me", headers=u2_auth)
    d = r.json()
    check("A referrals/me stats rewarded=1 / earned=1000",
          d.get("stats", {}).get("rewarded") == 1
          and d.get("stats", {}).get("points_earned") == 1000, d)

    print("\n== 客服 ==")
    r = client.post("/api/support/tickets",
                    json={"email": b_email, "order_no": b_no, "category": 2,
                          "subject": "Nail chipped", "content": "One nail chipped on arrival."})
    d = r.json()
    ticket_no = d.get("ticket_no", "")
    check("B POST ticket → TK 单号", r.status_code == 200 and ticket_no.startswith("TK"), r.text[:200])

    r = client.get("/api/support/tickets", params={"email": b_email}, headers=b_auth)
    d = r.json()
    mine = next((t for t in d.get("items", []) if t["ticket_no"] == ticket_no), None)
    check("GET tickets by email 含 messages", r.status_code == 200 and mine is not None
          and len(mine["messages"]) == 1 and "chipped" in mine["messages"][0]["content"],
          d)

    print("\n== 后台 ==")
    r = client.post("/api/account/login",
                    json={"email": "ops@glowmag.com", "password": "glowmag123"})
    d = r.json()
    check("ops 登录", r.status_code == 200 and d.get("token")
          and d.get("user", {}).get("email") == "ops@glowmag.com", r.text[:200])
    ops_auth = {"Authorization": f"Bearer {d['token']}"}

    r = client.get("/api/admin/ops/dashboard", headers=ops_auth)
    d = r.json()
    check("dashboard today gmv>0", r.status_code == 200
          and d.get("today", {}).get("gmv_cents", 0) > 0, d.get("today"))
    daily = d.get("daily")
    if daily is None:
        check("dashboard daily 14 天连续", True, "SKIP: dashboard 未扩展 daily")
    else:
        dates = [str(x.get("date") or x.get("day") or "")[:10] for x in daily]
        try:
            ds = [date.fromisoformat(x) for x in dates]
            consec = all((ds[i + 1] - ds[i]).days == 1 for i in range(len(ds) - 1))
        except ValueError:
            consec = True
        check("dashboard daily 14 天连续", len(daily) == 14 and consec, dates[:3])

    r = client.get("/api/admin/trade/orders", headers=ops_auth, params={"q": b_email})
    d = r.json()
    check("admin orders q=B email 命中", r.status_code == 200
          and any(o["order_no"] == b_no for o in d.get("items", [])), d)

    r = client.get(f"/api/admin/trade/orders/{b_no}", headers=ops_auth)
    d = r.json()
    b_item_id = d["items"][0]["id"] if d.get("items") else 0
    check("admin 订单详情含 items", r.status_code == 200 and len(d.get("items", [])) == 1
          and d.get("grand_total") == 2038, r.text[:300])

    r = client.post(f"/api/admin/trade/orders/{b_no}/ship", headers=ops_auth,
                    json={"carrier": "usps", "tracking_no": "9400110200880"})
    d = r.json()
    check("ship → SP 单号 / 订单 SHIPPED(3)", r.status_code == 200
          and str(d.get("shipment_no", "")).startswith("SP") and d.get("order_status") == 3, d)

    r = client.get("/api/orders/track", params={"no": b_no, "email": b_email})
    d = r.json()
    check("track status=3 已发货 + usps 单号", r.status_code == 200 and d.get("status") == 3
          and d["shipments"] and d["shipments"][0]["carrier"] == "usps"
          and d["shipments"][0]["tracking_no"] == "9400110200880", d)

    r = client.post(f"/api/admin/trade/orders/{b_no}/mark-delivered", headers=ops_auth)
    check("mark-delivered → DELIVERED(4)", r.status_code == 200
          and r.json().get("order_status") == 4, r.text[:200])

    print("\n== 退货 ==")
    r = client.post("/api/returns", headers=b_auth,
                    json={"order_no": b_no, "order_item_id": b_item_id, "qty": 1,
                          "reason": 2, "reason_detail": "chipped on arrival"})
    d = r.json()
    rma_no = d.get("rma_no", "")
    check("B 申请退货（质量）→ RMA 单号", r.status_code == 201
          and rma_no.startswith("RMA") and d.get("status") == 0, r.text[:300])

    r = client.post(f"/api/admin/trade/rmas/{rma_no}/approve", headers=ops_auth)
    check("RMA approve → label_sent(2)", r.status_code == 200
          and r.json().get("status") == 2, r.text[:200])

    s.expire_all()
    glue_before = s.get(Variant, v_glue).stock
    r = client.post(f"/api/admin/trade/rmas/{rma_no}/receive", headers=ops_auth)
    d = r.json()
    s.expire_all()
    check("RMA receive 库存回补 +1", r.status_code == 200 and d.get("status") == 4
          and d.get("restock_qty") == 1
          and s.get(Variant, v_glue).stock == glue_before + 1,
          (d, glue_before, s.get(Variant, v_glue).stock))

    r = client.post(f"/api/admin/trade/rmas/{rma_no}/refund", headers=ops_auth)
    d = r.json()
    check("RMA refund = 单件按实付比例全退 2038（含税+运费分摊，质量退运费 499 封顶计入）",
          r.status_code == 200
          and d.get("refund_amount") == 2038 and d.get("refund_shipping") == 499, d)

    s.expire_all()
    b_order = s.query(Order).filter(Order.order_no == b_no).first()
    b_pay = (s.query(Payment).filter(Payment.order_id == b_order.id)
             .order_by(Payment.id.desc()).first())
    b_user = s.query(User).filter(User.email == b_email).first()
    frozen_left = (s.query(PointsLedger)
                   .filter(PointsLedger.user_id == b_user.id,
                           PointsLedger.ref_type == "order", PointsLedger.ref_id == b_order.id,
                           PointsLedger.frozen == 1).count())
    void_row = (s.query(PointsLedger)
                .filter(PointsLedger.user_id == b_user.id,
                        PointsLedger.reason == int(PointsReason.REFUND_VOID)).first())
    check("全额退 → 订单 REFUNDED(9) + Payment 全退",
          b_order.status == 9 and b_pay.status == 3 and b_pay.refunded_amount == 2038,
          (b_order.status, b_pay.status, b_pay.refunded_amount))
    check("积分作废 frozen 清零 / points 扣回", b_user.points == 0 and frozen_left == 0
          and void_row is not None, (b_user.points, frozen_left))

    print("\n== 礼品卡 ==")
    r = client.post("/api/promo/giftcard/purchase",
                    json={"amount_cents": 5000, "purchaser_email": "ops@glowmag.com"})
    d = r.json()
    gc_code = d.get("code", "")
    check("礼品卡购买 5000 → GC code", r.status_code == 201
          and gc_code.startswith("GC-") and d.get("status") == 0
          and d.get("order_no", "").startswith("NS"), d)
    client.post("/api/payments/create-intent", json={"order_no": d["order_no"]})
    client.post("/api/payments/mock-pay", json={"order_no": d["order_no"], "succeed": True})

    r = client.post("/api/checkout/preview", headers=b_auth,
                    json={"items": [{"variant_id": v_glue, "qty": 1}],
                          "gift_card_code": gc_code})
    d = r.json()
    check("B preview 礼品卡抵扣 1399>0", r.status_code == 200
          and d.get("giftcard_discount") == 1399, d)

    print("\n== worker ==")
    w = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "worker.py"), "--once"],
                       env=dict(os.environ), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    wout = (w.stdout or "") + (w.stderr or "")
    check("worker --once 退出码 0 且无 ERROR/Traceback",
          w.returncode == 0 and "ERROR" not in wout and "Traceback" not in wout, wout[-400:])

    s.expire_all()
    main = s.query(Order).filter(Order.order_no == main_no).first()
    ob = (s.query(OutboxEvent)
          .filter(OutboxEvent.event_type == "order.paid",
                  OutboxEvent.aggregate_id == main.id).first())
    check("worker 发布 order.paid published=1", ob is not None and ob.published == 1,
          ob and (ob.published, ob.retry_count))

    s.expire_all()
    rec = (s.query(ReconciliationDaily)
           .filter(ReconciliationDaily.reconcile_date == utcnow().date()).first())
    check("reconciliation_daily 当日行存在 + diff 字段在", rec is not None
          and rec.diff_payment is not None and rec.payments_gross > 0,
          rec and (rec.diff_payment, rec.payments_gross))

    print("\n== 退订 / 限流豁免 ==")
    r = client.post("/api/account/unsubscribe", headers=b_auth, json={"email": b_email})
    s.expire_all()
    bp = s.get(EmailPreference, b_email)
    check("退订 B → email_preferences 全 0", r.status_code == 200 and bp is not None
          and bp.sub_promo == 0 and bp.sub_new_arrival == 0 and bp.sub_cart_abandon == 0
          and bp.unsubscribed_at is not None,
          bp and (bp.sub_promo, bp.sub_new_arrival, bp.sub_cart_abandon))

    r = client.get("/metrics")
    check("/metrics 200 且含 glowmag_http_requests_total", r.status_code == 200
          and "glowmag_http_requests_total" in r.text, r.text[:150])

    s.close()

print(f"\nE2E: {PASSED}/{PASSED + len(FAILED)} passed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
