"""交易域修复回归 —— RMA/换货未决占用 CAS（抢占/释放/结转全终态路径）、0 元单直接标付、
换货游客三端点、mock-pay ok:false、购物车行数上限、游客单并入账户列表、列表分页可选。
（GM_DB=sqlite:///test_tradefix.sqlite 独立库；BigInteger 垫片同 test_payments.py）"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_tradefix.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"
os.environ["GM_RATE_RULES"] = '{"/api/exchanges": 100, "/api/checkout/place": 30}'
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Cart, Category, Exchange, GiftCard, Order, OrderItem, Payment, Product,
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


ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US", "phone": "+14155550001"}


def mk_item(s, order_id, v, qty=2, unit=1000):
    it = OrderItem(order_id=order_id, variant_id=v.id, product_slug="tf-gel",
                   title_snapshot="TF Gel", qty=qty, unit_price=unit, subtotal=unit * qty)
    s.add(it)
    return it


try:
    with TestClient(app) as client:
        s = SessionLocal()

        cat = Category(slug="press-on-nails", name="Press-on Nails")
        s.add(cat)
        s.flush()
        p = Product(slug="tf-gel", title="TF Gel", category_id=cat.id, status=1,
                    hero_image="https://img/t.jpg", price_min=1000, price_max=1600)
        s.add(p)
        s.flush()
        v_mid = Variant(product_id=p.id, sku="TF-MID", option1_value="Short",
                        option2_value="24pcs", price=1000, stock=50)
        v_hi = Variant(product_id=p.id, sku="TF-HI", option1_value="Long",
                       option2_value="24pcs", price=1600, stock=50)
        s.add_all([v_mid, v_hi])
        s.flush()
        emma = User(email="emma@glow.test", password_hash=hash_password("x"),
                    name="Emma", role=0, points=0)
        ops = User(email="ops@glow.test", password_hash=hash_password("x"),
                   name="Ops", role=9)
        s.add_all([emma, ops])
        s.flush()
        # 0 元单前提：免邮门槛 0 + 税率 0（礼品卡可全额覆盖）
        s.add_all([Setting(key="free_shipping_threshold", value=0),
                   Setting(key="tax_rate", value=0)])
        s.commit()

        H_EMMA = {"Authorization": f"Bearer {create_token(emma.id, emma.role)}"}
        H_OPS = {"Authorization": f"Bearer {create_token(ops.id, ops.role)}"}

        def mk_paid_order(no, *, user_id=emma.id, email="emma@glow.test", qty=2):
            o = Order(order_no=no, user_id=user_id, email=email, status=4,
                      subtotal=1000 * qty, grand_total=1000 * qty,
                      shipping_address=ADDR, placed_at=utcnow(), paid_at=utcnow())
            s.add(o)
            s.flush()
            it = mk_item(s, o.id, v_mid, qty=qty)
            s.commit()
            return o, it

        print("== RMA 未决占用：抢占 / 超量 409 / 撤销释放 ==")
        o1, it1 = mk_paid_order("TF260826RMA01")
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "TF260826RMA01", "order_item_id": it1.id, "qty": 1, "reason": 3})
        rma1_no = r.json().get("rma_no", "")
        check("RMA 抢占 1 件 → 201", r.status_code == 201 and rma1_no.startswith("RMA"), r.text)
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "TF260826RMA01", "order_item_id": it1.id, "qty": 2, "reason": 3})
        check("未决占用后再申 2 件 → 409 qty_exceeds_available:1（真实余量）",
              r.status_code == 409 and r.json()["detail"] == "qty_exceeds_available:1", r.text)
        s.expire_all()
        it1_db = s.get(OrderItem, it1.id)
        check("占用落列 rma_pending_qty=1（ex_pending=0）",
              it1_db.rma_pending_qty == 1 and it1_db.ex_pending_qty == 0)
        r = client.get("/api/orders/TF260826RMA01", headers=H_EMMA)
        check("订单详情 available 同步扣 pending（2-1=1）且回传占用列",
              r.json()["items"][0]["available"] == 1
              and r.json()["items"][0]["rma_pending_qty"] == 1, r.json()["items"][0])
        r = client.post(f"/api/returns/{rma1_no}/cancel", headers=H_EMMA)
        s.expire_all()
        check("RMA 撤销 → 释放占用（pending 回 0）后可重新全额申请",
              r.status_code == 200 and s.get(OrderItem, it1.id).rma_pending_qty == 0
              and client.post("/api/returns", headers=H_EMMA, json={
                  "order_no": "TF260826RMA01", "order_item_id": it1.id,
                  "qty": 2, "reason": 3}).status_code == 201)

        print("== RMA 拒绝释放 / 退款结转 refunded_qty ==")
        o2, it2 = mk_paid_order("TF260826RMA02")
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "TF260826RMA02", "order_item_id": it2.id, "qty": 1, "reason": 3})
        rma2_no = r.json()["rma_no"]
        r = client.post(f"/api/admin/trade/rmas/{rma2_no}/reject", headers=H_OPS)
        s.expire_all()
        check("RMA 拒绝 → 释放占用（pending 1→0，refunded 不动）",
              r.status_code == 200 and s.get(OrderItem, it2.id).rma_pending_qty == 0
              and s.get(OrderItem, it2.id).refunded_qty == 0, r.text)
        o3, it3 = mk_paid_order("TF260826RMA03")
        s.add(Payment(order_id=o3.id, stripe_payment_intent="PI_TFRMA3",
                      amount=2000, status=1))
        s.commit()
        rma3_no = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "TF260826RMA03", "order_item_id": it3.id,
            "qty": 1, "reason": 3}).json()["rma_no"]
        client.post(f"/api/admin/trade/rmas/{rma3_no}/approve", headers=H_OPS)
        client.post(f"/api/admin/trade/rmas/{rma3_no}/receive", headers=H_OPS)
        r = client.post(f"/api/admin/trade/rmas/{rma3_no}/refund", headers=H_OPS)
        s.expire_all()
        it3_db = s.get(OrderItem, it3.id)
        check("RMA 退款 → 原子结转 refunded_qty=1 / pending 1→0",
              r.status_code == 200 and it3_db.refunded_qty == 1
              and it3_db.rma_pending_qty == 0, (r.text[:120], it3_db.refunded_qty))

        print("== 换货未决占用：抢占 / 超量 409 / 拒绝释放 / 完成结转 ==")
        o4, it4 = mk_paid_order("TF260826EX001")
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "TF260826EX001", "order_item_id": it4.id,
            "new_variant_id": v_hi.id, "qty": 1})
        ex4_no = r.json().get("exchange_no", "")
        check("换货抢占 1 件 → 201", r.status_code == 201, r.text)
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "TF260826EX001", "order_item_id": it4.id,
            "new_variant_id": v_hi.id, "qty": 2})
        check("未决占用后再申 2 件 → 409 qty_exceeds_available:1",
              r.status_code == 409 and r.json()["detail"] == "qty_exceeds_available:1", r.text)
        s.expire_all()
        check("占用落列 ex_pending_qty=1（rma_pending=0，与 RMA 互斥占额）",
              s.get(OrderItem, it4.id).ex_pending_qty == 1
              and s.get(OrderItem, it4.id).rma_pending_qty == 0)
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "TF260826EX001", "order_item_id": it4.id, "qty": 2, "reason": 3})
        check("换货占用同样吃掉 RMA 可退量 → 409 qty_exceeds_available:1",
              r.status_code == 409 and r.json()["detail"] == "qty_exceeds_available:1", r.text)
        r = client.post(f"/api/admin/trade/exchanges/{ex4_no}/reject", headers=H_OPS)
        s.expire_all()
        check("换货拒绝 → 释放占用（ex_pending 1→0）",
              r.status_code == 200 and s.get(OrderItem, it4.id).ex_pending_qty == 0, r.text)
        ex4b_no = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "TF260826EX001", "order_item_id": it4.id,
            "new_variant_id": v_hi.id, "qty": 2}).json()["exchange_no"]
        client.post(f"/api/admin/trade/exchanges/{ex4b_no}/approve", headers=H_OPS)
        client.post(f"/api/admin/trade/exchanges/{ex4b_no}/mark-paid", headers=H_OPS)
        client.post(f"/api/admin/trade/exchanges/{ex4b_no}/ship", headers=H_OPS,
                    json={"carrier": "usps", "tracking_no": "9400TFEX0001"})
        r = client.post(f"/api/admin/trade/exchanges/{ex4b_no}/complete", headers=H_OPS)
        s.expire_all()
        it4_db = s.get(OrderItem, it4.id)
        check("换货完成 → 原子结转 exchanged_qty=2 / ex_pending 2→0",
              r.status_code == 200 and r.json()["exchanged_qty"] == 2
              and it4_db.exchanged_qty == 2 and it4_db.ex_pending_qty == 0, r.text[:120])

        print("== 换货游客三端点：email 双因子 ==")
        o5, it5 = mk_paid_order("TF260826EXG01", user_id=None, email="guest@glow.test", qty=1)
        ex5_no = client.post("/api/exchanges", json={
            "order_no": "TF260826EXG01", "order_item_id": it5.id,
            "new_variant_id": v_hi.id, "email": "guest@glow.test"}).json()["exchange_no"]
        check("游客 cancel 无凭据 → 401",
              client.post(f"/api/exchanges/{ex5_no}/cancel").status_code == 401)
        check("游客 cancel 错 email → 404",
              client.post(f"/api/exchanges/{ex5_no}/cancel",
                          params={"email": "evil@glow.test"}).status_code == 404)
        r = client.post(f"/api/exchanges/{ex5_no}/cancel",
                        params={"email": "guest@glow.test"})
        s.expire_all()
        check("游客 cancel email 双因子 → 200 且释放占用",
              r.status_code == 200 and s.get(OrderItem, it5.id).ex_pending_qty == 0, r.text)
        ex5b_no = client.post("/api/exchanges", json={
            "order_no": "TF260826EXG01", "order_item_id": it5.id,
            "new_variant_id": v_hi.id, "email": "guest@glow.test"}).json()["exchange_no"]
        client.post(f"/api/admin/trade/exchanges/{ex5b_no}/approve", headers=H_OPS)
        r = client.post(f"/api/exchanges/{ex5b_no}/pay-intent",
                        params={"email": "guest@glow.test"})
        check("游客 pay-intent email 双因子 → 200 带 PI",
              r.status_code == 200 and r.json()["payment_intent"].startswith("PI_"), r.text)
        r = client.post(f"/api/exchanges/{ex5b_no}/mock-pay",
                        json={"succeed": True, "email": "guest@glow.test"})
        check("游客 mock-pay body.email 双因子 → 2→1",
              r.status_code == 200 and r.json()["exchange_status"] == 1, r.text)

        print("== 0 元单：下单即标付 + create-intent 拒绝 ==")
        s.add(GiftCard(code="GC-TF-FULL01", initial_amount=5000, balance=5000,
                       status=1, purchaser_email="emma@glow.test"))
        s.commit()
        # 登录用户单购物车行（carts.user_id 唯一）：直接 ORM 装载后 place（auth 解析用户车）
        cart_free = Cart(user_id=emma.id, session_id="tok-tf-free",
                         items=[{"variantId": v_mid.id, "qty": 1}])
        s.add(cart_free)
        s.commit()
        r = client.post("/api/checkout/place",
                        headers={"X-Cart-Token": "tok-tf-free", **H_EMMA},
                        json={"email": "emma@glow.test", "address": ADDR,
                              "gift_card_code": "GC-TF-FULL01"})
        d = r.json()
        free_no = d.get("order_no", "")
        s.expire_all()
        free_order = s.query(Order).filter(Order.order_no == free_no).first()
        free_pay = (s.query(Payment).filter(Payment.order_id == free_order.id)
                    .order_by(Payment.id.desc()).first())
        check("0 元单 place → 201 status=1 / paid:true / paid_at 落库",
              r.status_code == 201 and d["status"] == 1 and d["paid"] is True
              and free_order.paid_at is not None, d)
        check("0 元 Payment 落账（amount=0 status=1 PI_FREE 前缀）",
              free_pay.amount == 0 and free_pay.status == 1
              and free_pay.stripe_payment_intent.startswith("PI_FREE"), free_pay.amount)
        check("0 元单 create-intent → 409 already_paid",
              client.post("/api/payments/create-intent", headers=H_EMMA,
                          json={"order_no": free_no}).status_code == 409
              and client.post("/api/payments/create-intent", headers=H_EMMA,
                              json={"order_no": free_no}).json()["detail"] == "already_paid")

        print("== mock-pay 失败 ok:false / 成功 ok:true ==")
        def set_user_cart(items):
            s.expire_all()
            c = s.query(Cart).filter(Cart.user_id == emma.id).first()
            c.items = items
            s.commit()

        set_user_cart([{"variantId": v_mid.id, "qty": 1}])
        pay_no = client.post("/api/checkout/place",
                             headers={"X-Cart-Token": "tok-tf-pay", **H_EMMA},
                             json={"email": "emma@glow.test", "address": ADDR}
                             ).json()["order_no"]
        client.post("/api/payments/create-intent", headers=H_EMMA,
                    json={"order_no": pay_no})
        r = client.post("/api/payments/mock-pay", headers=H_EMMA,
                        json={"order_no": pay_no, "succeed": False})
        d = r.json()
        check("mock-pay 失败 → ok:false（保留 order/payment_status）",
              r.status_code == 200 and d["ok"] is False and d["payment_status"] == 2
              and d["order_status"] == 0, d)
        client.post("/api/payments/create-intent", headers=H_EMMA,
                    json={"order_no": pay_no})
        r = client.post("/api/payments/mock-pay", headers=H_EMMA,
                        json={"order_no": pay_no, "succeed": True})
        check("mock-pay 成功 → ok:true",
              r.status_code == 200 and r.json()["ok"] is True, r.text)

        print("== 购物车行数上限 99 ==")
        cap_variants = []
        for i in range(100):
            v = Variant(product_id=p.id, sku=f"TF-CAP-{i:03d}",
                        option1_value=f"C{i:03d}", option2_value="24pcs",
                        price=1000, stock=5)
            s.add(v)
            cap_variants.append(v)
        s.commit()
        # 上限守卫在 _save 公共路径：独立游客车 ORM 预置 99 行后走 add API
        cart_cap = Cart(session_id="tok-tf-cap",
                        items=[{"variantId": v.id, "qty": 1} for v in cap_variants[:99]])
        s.add(cart_cap)
        s.commit()
        r = client.post("/api/cart/items", headers={"X-Cart-Token": "tok-tf-cap"},
                        json={"variant_id": cap_variants[99].id, "qty": 1})
        check("第 100 行加购 → 409 cart_too_large（车保持 99 行）",
              r.status_code == 409 and r.json()["detail"] == "cart_too_large"
              and len(s.get(Cart, cart_cap.id).items) == 99, r.text)
        r = client.post("/api/cart/items", headers={"X-Cart-Token": "tok-tf-cap"},
                        json={"variant_id": cap_variants[0].id, "qty": 1})
        check("已有行内加量不触发行数上限 → 201",
              r.status_code == 201 and len(r.json()["items"]) == 99, r.text[:120])

        print("== 游客同邮箱订单并入账户列表 ==")
        cart_guest = Cart(session_id="tok-tf-guest",
                          items=[{"variantId": v_mid.id, "qty": 1}])
        s.add(cart_guest)
        s.commit()
        guest_no = client.post("/api/checkout/place", headers={"X-Cart-Token": "tok-tf-guest"},
                               json={"email": "Emma@Glow.Test ".strip().lower(),
                                     "address": ADDR}).json()["order_no"]
        r = client.get("/api/orders", headers=H_EMMA)
        check("游客同 email 下单 → 登录列表可见（去重无重复行）",
              guest_no in {o["order_no"] for o in r.json()["items"]},
              [o["order_no"] for o in r.json()["items"]])

        print("== shipping-methods bundle_discounts / returns·exchanges 可选分页 ==")
        r = client.get("/api/checkout/shipping-methods")
        check("shipping-methods 含 bundle_discounts（默认 15/20）",
              r.json().get("bundle_discounts") == {"bundle_2_off": 15, "bundle_3_off": 20},
              r.json().get("bundle_discounts"))
        s.add(Setting(key="bundle_2_off", value=25))
        s.commit()
        check("settings 覆盖后 bundle_2_off=25 生效",
              client.get("/api/checkout/shipping-methods").json()
              ["bundle_discounts"]["bundle_2_off"] == 25)
        r = client.get("/api/returns", headers=H_EMMA)
        check("returns 不传 page → 旧结构 {items}",
              r.status_code == 200 and set(r.json()) == {"items"}, list(r.json()))
        r = client.get("/api/returns", headers=H_EMMA, params={"page": 1, "size": 2})
        d = r.json()
        check("returns page=1&size=2 → {items,page,size,total,pages} 截断正确",
              r.status_code == 200 and d["page"] == 1 and d["size"] == 2
              and d["total"] == 3 and d["pages"] == 2 and len(d["items"]) == 2, d)
        r = client.get("/api/exchanges", headers=H_EMMA, params={"page": 2, "size": 1})
        d = r.json()
        check("exchanges page=2&size=1 → 分页四件套",
              r.status_code == 200 and d["page"] == 2 and d["size"] == 1
              and d["total"] == 2 and d["pages"] == 2 and len(d["items"]) == 1, d)

        print("== 取消原因 reason 落库（截断/默认 user） ==")
        set_user_cart([{"variantId": v_mid.id, "qty": 1}])
        c_no = client.post("/api/checkout/place",
                           headers={"X-Cart-Token": "tok-tf-cancel", **H_EMMA},
                           json={"email": "emma@glow.test", "address": ADDR}).json()["order_no"]
        r = client.post(f"/api/orders/{c_no}/cancel", headers=H_EMMA,
                        json={"reason": "wrong size"})
        s.expire_all()
        check("带 body.reason 取消 → cancel_reason='wrong size'",
              r.status_code == 200
              and s.query(Order).filter(Order.order_no == c_no).first().cancel_reason
              == "wrong size", r.text)
        set_user_cart([{"variantId": v_mid.id, "qty": 1}])
        c2_no = client.post("/api/checkout/place",
                            headers={"X-Cart-Token": "tok-tf-cancel", **H_EMMA},
                            json={"email": "emma@glow.test", "address": ADDR}).json()["order_no"]
        client.post(f"/api/orders/{c2_no}/cancel", headers=H_EMMA)
        s.expire_all()
        check("不带 body → cancel_reason 默认 'user'",
              s.query(Order).filter(Order.order_no == c2_no).first().cancel_reason == "user")

        s.close()
finally:
    pass

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
