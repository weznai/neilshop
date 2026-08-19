"""智能体 A（P0）自测 —— 州级税表 + GDPR 数据导出/删除请求/worker 匿化
（GM_DB=sqlite:///test_p0a.sqlite 独立库；BigInteger 垫片同 test_payments.py）"""

import os
import sys
from datetime import date, datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_p0a.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))  # worker.py 在 scripts/

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, utcnow  # noqa: E402
from app.core.enums import PointsReason, ReferralStatus  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Cart, Category, CookieConsent, DataRequest, DiscountCode, Order, OrderItem,
    PointsLedger, Product, Referral, Review, Setting, Subscription, Ticket,
    TicketMessage, User, UserAddress, Variant, WishlistItem,
)
from app.services.pricing import price_cart  # noqa: E402
from app.services.tax_rates import RATES, rate_for  # noqa: E402

import worker  # noqa: E402

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
                     status=1, hero_image="https://img/bare.jpg",
                     price_min=1599, price_max=1599)
    p_glue = Product(slug="magic-glue", title="Magic Glue", category_id=cat_acc.id,
                     status=1, hero_image="https://img/glue.jpg",
                     price_min=1399, price_max=1399)
    s.add_all([p_bare, p_glue])
    s.flush()
    v_bare = Variant(product_id=p_bare.id, sku="BG-SA", option1_value="Short Almond",
                     option2_value="24pcs", price=1599, stock=99)
    v_glue = Variant(product_id=p_glue.id, sku="GL-01", option1_value="Standard",
                     option2_value="0.5oz", price=1399, stock=50)
    s.add_all([v_bare, v_glue])
    s.flush()

    emma = User(email="emma@glow.test", password_hash=hash_password("glow12345"),
                name="Emma", points=500, birthday=date(1996, 5, 20))
    s.add(emma)
    s.flush()
    s.add(PointsLedger(user_id=emma.id, change=500, balance_after=500,
                       reason=int(PointsReason.CHECKIN), frozen=0))
    s.add(DiscountCode(code="WELCOME20", name="首单 8 折", type=1, value=20,
                       max_discount=1000, min_subtotal=0, first_order_only=1,
                       per_user_limit=1, is_active=1))
    s.add(Setting(key="shipping_standard", value=499))
    s.add(Setting(key="shipping_express", value=1499))
    s.add(Cart(user_id=emma.id, session_id="tok-p0",
               items=[{"variantId": v_bare.id, "qty": 1}, {"variantId": v_glue.id, "qty": 1}]))
    s.commit()

    emma_auth = {"Authorization": f"Bearer {create_token(emma.id, emma.role)}"}
    base_items = [{"variant_id": v_bare.id, "qty": 1}, {"variant_id": v_glue.id, "qty": 1}]

    print("\n== tax_rates 州表 ==")
    check("州表覆盖 50 州 + DC", len(RATES) == 51, len(RATES))
    check("CA 精确 0.0735 对齐基线", rate_for("CA", 0.09) == 0.0735)
    check("NY 0.08875 / TX 0.0625 / FL 0.06 / WA 0.065",
          rate_for("NY", 0.0) == 0.08875 and rate_for("TX", 0.0) == 0.0625
          and rate_for("FL", 0.0) == 0.06 and rate_for("WA", 0.0) == 0.065)
    check("免税州 OR/MT/NH/DE 均 0.0",
          all(rate_for(x, 0.0735) == 0.0 for x in ("OR", "MT", "NH", "DE")))
    check("未知州回退 fallback", rate_for("ZZ", 0.08125) == 0.08125)
    check("None/空州回退 fallback",
          rate_for(None, 0.0735) == 0.0735 and rate_for("", 0.0735) == 0.0735)
    check("小写/空白州码归一命中", rate_for(" ca ", 0.09) == 0.0735)

    print("\n== price_cart 州级税（直接调用）==")
    d = price_cart(s, items=base_items, code="WELCOME20",
                   email="emma@glow.test", user_id=emma.id, state="CA")
    check("CA 州税 213 / 总额 3110（基线 $31.10 不变）",
          d["subtotal"] == 2998 and d["code_discount"] == 600 and d["shipping_fee"] == 499
          and d["tax"] == 213 and d["grand_total"] == 3110
          and d["tax_rate"] == 0.0735 and d["tax_state"] == "CA", d)
    d = price_cart(s, items=base_items, code="WELCOME20",
                   email="emma@glow.test", user_id=emma.id, state="NY")
    check("NY 州税 (2998-600+499)*0.08875 → 257",
          d["tax"] == 257 and d["tax_rate"] == 0.08875 and d["grand_total"] == 3154, d)
    d = price_cart(s, items=base_items, code="WELCOME20",
                   email="emma@glow.test", user_id=emma.id, state="OR")
    check("OR 免税州 tax=0 / 总额 2897",
          d["tax"] == 0 and d["grand_total"] == 2897 and d["tax_state"] == "OR", d)
    d = price_cart(s, items=base_items, code="WELCOME20",
                   email="emma@glow.test", user_id=emma.id)
    check("无地址（纯 items preview）回退 settings → tax 213",
          d["tax"] == 213 and d["tax_rate"] == 0.0735 and d["tax_state"] is None, d)

    print("\n== HTTP preview/place 口径 ==")
    r = client.post("/api/checkout/preview", headers=emma_auth,
                    json={"code": "WELCOME20", "email": "emma@glow.test"})
    d = r.json()
    check("preview 无地址回退 tax 213 + tax_state 键（纯加法）",
          r.status_code == 200 and d["tax"] == 213 and d["grand_total"] == 3110
          and "tax_state" in d and d["tax_state"] is None, d)
    r = client.post("/api/checkout/preview",
                    json={"items": [{"variant_id": v_bare.id, "qty": 1},
                                    {"variant_id": v_glue.id, "qty": 1}],
                          "code": "WELCOME20"})
    d = r.json()
    check("preview 游客纯 items → tax 213",
          r.status_code == 200 and d["tax"] == 213, d)

    addr = {"full_name": "Emma Rodriguez", "line1": "2847 Mission St",
            "city": "San Francisco", "state": "CA", "zip": "94110",
            "country": "US", "phone": "+14155550123"}
    r = client.post("/api/checkout/place", headers=emma_auth, json={
        "email": "emma@glow.test", "address": addr, "shipping_method": "standard",
        "code": "WELCOME20"})
    d = r.json()
    check("place CA 地址 → 201 总额 3110",
          r.status_code == 201 and d["grand_total"] == 3110 and d["tax"] == 213, d)

    print("\n== GDPR 导出 ==")
    r = client.post("/api/account/addresses", headers=emma_auth,
                    json={**addr, "is_default": True})
    check("地址簿 1 条（导出素材）", r.status_code == 201, r.text)
    s.add(CookieConsent(session_id="sess-p0", user_id=emma.id, necessary=1,
                        analytics=1, marketing=0, region="US-CA"))
    s.add(Subscription(user_id=emma.id, stripe_subscription_id="sub_p0", plan=1,
                       status=1, next_billing_at=utcnow() + timedelta(days=28)))
    s.add(Referral(code="GLOW-P0AAAA", referrer_user_id=emma.id,
                   invited_email="friend@glow.test", status=int(ReferralStatus.CLICKED)))
    emma_order = s.query(Order).filter(Order.user_id == emma.id).first()
    s.add(Review(product_id=p_bare.id, user_id=emma.id,
                 order_item_id=s.query(OrderItem).filter(
                     OrderItem.order_id == emma_order.id).first().id,
                 rating=5, content="Gorgeous", status=1))
    tk = Ticket(ticket_no="TKP0" + "0001", user_id=emma.id, email="emma@glow.test",
                category=1, priority=1, subject="Where is my order?")
    s.add(tk)
    s.flush()
    s.add(TicketMessage(ticket_id=tk.id, sender=1, content="Hello"))
    s.commit()

    r = client.get("/api/account/export", headers=emma_auth)
    d = r.json()
    check("export 200 全量键齐",
          r.status_code == 200 and all(k in d for k in (
              "profile", "addresses", "orders", "points_ledger", "reviews",
              "tickets", "subscriptions", "referrals", "cookie_consents")), d.keys())
    check("export profile 脱敏 password_hash + 订单含 items",
          "password_hash" not in d["profile"] and d["profile"]["email"] == "emma@glow.test"
          and len(d["orders"]) >= 1 and len(d["orders"][0]["items"]) >= 2
          and d["orders"][0]["grand_total"] == 3110, d.get("profile"))
    check("export 地址/流水/评价/工单(+messages)/订阅/推荐/cookie 全有数",
          len(d["addresses"]) == 1 and len(d["points_ledger"]) >= 1
          and len(d["reviews"]) == 1 and len(d["tickets"]) == 1
          and len(d["tickets"][0]["messages"]) == 1 and len(d["subscriptions"]) == 1
          and len(d["referrals"]["referrer"]) == 1 and len(d["cookie_consents"]) == 1)
    s.expire_all()
    exports = s.query(DataRequest).filter(DataRequest.user_id == emma.id,
                                          DataRequest.type == 1).all()
    check("export 落 DataRequest type=1 status=1 fulfilled_at",
          len(exports) >= 1 and all(e.status == 1 and e.fulfilled_at is not None
                                    for e in exports))

    print("\n== GDPR 删除请求 ==")
    r = client.post("/api/account/delete-request", headers=emma_auth)
    d = r.json()
    eff = datetime.fromisoformat(d["effective_at"]) if r.status_code == 202 else None
    check("delete-request 202 → request_id + effective_at≈now+7d",
          r.status_code == 202 and d.get("request_id")
          and eff is not None
          and timedelta(days=6, hours=23) < eff - utcnow() < timedelta(days=7, hours=1), d)
    r2 = client.post("/api/account/delete-request", headers=emma_auth)
    check("重复提交 pending → 409", r2.status_code == 409, r2.text)
    r3 = client.delete("/api/account/delete-request", headers=emma_auth)
    check("DELETE 取消 → ok 且 pending 清零",
          r3.status_code == 200 and r3.json().get("ok") is True
          and s.query(DataRequest).filter(DataRequest.user_id == emma.id,
                                          DataRequest.type == 2,
                                          DataRequest.status == 0).count() == 0)
    r4 = client.post("/api/account/delete-request", headers=emma_auth)
    check("取消后可再提 202（新 pending 落库）",
          r4.status_code == 202 and r4.json().get("request_id")
          and s.query(DataRequest).filter(DataRequest.user_id == emma.id,
                                          DataRequest.type == 2,
                                          DataRequest.status == 0).count() == 1, r4.text)
    client.delete("/api/account/delete-request", headers=emma_auth)
    r5 = client.get("/api/account/export")
    check("export/delete-request 未登录 → 401",
          r5.status_code == 401
          and client.post("/api/account/delete-request").status_code == 401)

    print("\n== worker 匿化 ==")
    gina = User(email="gina@glow-test.com", password_hash=hash_password("glow12345"),
                name="Gina", points=300, birthday=date(1994, 4, 1))
    hank = User(email="hank@glow-test.com", password_hash=hash_password("glow12345"),
                name="Hank", points=100)
    s.add_all([gina, hank])
    s.flush()
    s.add(UserAddress(user_id=gina.id, full_name="Gina Doe", line1="9 Market St",
                      city="SF", state="CA", zip="94103", country="US",
                      phone="+14155550002", is_default=1))
    s.add(Cart(user_id=gina.id, session_id="tok-gina",
               items=[{"variantId": v_bare.id, "qty": 1}]))
    s.add(WishlistItem(user_id=gina.id, product_id=p_bare.id))
    gina_order = Order(order_no="NSP0G00001", user_id=gina.id, email="gina@glow-test.com",
                       status=1, currency="USD", subtotal=2998, shipping_fee=499,
                       tax=213, grand_total=3110,
                       shipping_address={"full_name": "Gina Doe", "line1": "9 Market St",
                                         "city": "SF", "state": "CA", "zip": "94103",
                                         "country": "US", "phone": "+14155550002"},
                       placed_at=utcnow(), paid_at=utcnow())
    s.add(gina_order)
    s.flush()
    s.add(OrderItem(order_id=gina_order.id, variant_id=v_bare.id,
                    product_slug="bare-gems", title_snapshot="Bare Gems · Short Almond",
                    qty=1, unit_price=1599, subtotal=1599))
    now = utcnow()
    s.add(DataRequest(user_id=gina.id, type=2, status=0,
                      created_at=now - timedelta(days=8)))
    s.add(DataRequest(user_id=hank.id, type=2, status=0, created_at=now))
    s.commit()
    gina_id, hank_id = gina.id, hank.id

    wdb = SessionLocal()
    worker.process_data_requests(wdb)
    wdb.close()
    s.expire_all()

    g2 = s.get(User, gina_id)
    check("到期用户匿化：deleted+ 前缀邮箱/无密码/清名/清分/注销/清生日",
          g2.email == f"deleted+{gina_id}@anonymized.local"
          and g2.email.startswith("deleted+")
          and g2.password_hash is None and g2.name == "" and g2.points == 0
          and g2.status == -1 and g2.birthday is None,
          (g2.email, g2.status, g2.points))
    check("地址/购物车/心愿单全删",
          s.query(UserAddress).filter(UserAddress.user_id == gina_id).count() == 0
          and s.query(Cart).filter(Cart.user_id == gina_id).count() == 0
          and s.query(WishlistItem).filter(WishlistItem.user_id == gina_id).count() == 0)
    s.expire_all()
    go = s.query(Order).filter(Order.order_no == "NSP0G00001").first()
    check("订单保留但脱敏：匿化邮箱 + Deleted User/空电话，金额状态不动",
          go.email == f"deleted+{gina_id}@anonymized.local"
          and go.shipping_address["full_name"] == "Deleted User"
          and go.shipping_address["phone"] == ""
          and go.grand_total == 3110 and go.tax == 213 and go.status == 1
          and go.subtotal == 2998,
          (go.email, go.shipping_address, go.grand_total))
    gr = s.query(DataRequest).filter(DataRequest.user_id == gina_id,
                                     DataRequest.type == 2).first()
    check("DataRequest 置 status=1 + fulfilled_at", gr.status == 1 and gr.fulfilled_at is not None)
    h2 = s.get(User, hank_id)
    hr = s.query(DataRequest).filter(DataRequest.user_id == hank_id,
                                     DataRequest.type == 2).first()
    check("未到期不动：hank 用户与 pending 请求原样",
          h2.email == "hank@glow-test.com" and h2.status == 1 and h2.points == 100
          and hr.status == 0 and hr.fulfilled_at is None)
    r = client.post("/api/account/login",
                    json={"email": "gina@glow-test.com", "password": "glow12345"})
    check("匿化后登录 → 401", r.status_code == 401, r.text)
    r = client.get("/api/account/me",
                   headers={"Authorization": f"Bearer {create_token(gina_id, 0)}"})
    check("匿化后旧 token 访问 /me → 401", r.status_code == 401, r.text)

    wdb = SessionLocal()
    worker.process_data_requests(wdb)
    wdb.close()
    s.expire_all()
    check("worker 幂等：再跑一轮无新增处理",
          s.query(DataRequest).filter(DataRequest.status == 0,
                                      DataRequest.type == 2).count() == 1)

print(f"\n==== test_p0: {PASSED} passed, {len(FAILED)} failed ====")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
