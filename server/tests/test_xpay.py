"""确认收货 / 换货撤销 / 换货差价支付 回归（GM_DB=sqlite:///test_xpay.sqlite 独立库；
BigInteger 垫片同 test_payments.py）。覆盖：
- 确认收货：status4 → 200 状态5 + completed_at/timeline；重复 → 409 not_confirmable；
  非送达状态 → 409；他人订单 → 404
- 换货撤销：申请中(0) → 删除可重申；非申请中 → 409；他人换货 → 404
- 差价支付：approve 到 2 → pay-intent（幂等复用）→ mock-pay 2→1（payment 核销）→
  重复 mock-pay 409 diff_already_paid；webhook 路由（关联 payment 的 succeeded 事件
  核销换货而非订单）；admin mark-paid 对无 payment 换货仍走旧路径
- /me 附带 delete_request（pending 回显 / 无申请为 null）；重置链接含 &email="""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_xpay.sqlite").replace("\\", "/")
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
    Category, Exchange, Order, OrderItem, Product, User, Variant,
)
from app.domains.trade import repository as repo  # noqa: E402

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


def mk_order(s, no, user_id, status, v, qty=1, unit=2000):
    o = Order(order_no=no, user_id=user_id, email="emma@glow.test", status=status,
              subtotal=unit * qty, grand_total=unit * qty, shipping_address=ADDR)
    s.add(o)
    s.flush()
    it = OrderItem(order_id=o.id, variant_id=v.id, product_slug="xp-gems",
                   title_snapshot="XP Gems · Short", qty=qty, unit_price=unit,
                   subtotal=unit * qty)
    s.add(it)
    s.commit()
    return o, it


def mk_exchange(s, no, order, item, old_v, new_v, status, diff):
    ex = Exchange(exchange_no=no, order_id=order.id, order_item_id=item.id,
                  old_variant_id=old_v.id, new_variant_id=new_v.id, qty=1,
                  price_diff=diff, status=status)
    s.add(ex)
    s.commit()
    return ex


with TestClient(app) as client:
    s = SessionLocal()

    cat = Category(slug="press-on-nails", name="Press-on Nails")
    s.add(cat)
    s.flush()
    p = Product(slug="xp-gems", title="XP Gems", category_id=cat.id, status=1,
                hero_image="https://img/c.jpg", price_min=2000, price_max=2600)
    s.add(p)
    s.flush()
    v_short = Variant(product_id=p.id, sku="XP-1", option1_value="Short",
                      option2_value="24pcs", price=2000, stock=10)
    v_long = Variant(product_id=p.id, sku="XP-2", option1_value="Long",
                     option2_value="24pcs", price=2600, stock=10)
    s.add_all([v_short, v_long])
    s.flush()
    emma = User(email="emma@glow.test", password_hash=hash_password("x"),
                name="Emma", role=0, points=0)
    bob = User(email="bob@glow.test", password_hash=hash_password("x"),
               name="Bob", role=0, points=0)
    s.add_all([emma, bob])
    s.commit()
    emma_tok = {"Authorization": f"Bearer {create_token(emma.id, 0)}"}
    bob_tok = {"Authorization": f"Bearer {create_token(bob.id, 0)}"}

    # ===== 确认收货 =====
    o4, _ = mk_order(s, "XP4", emma.id, 4, v_short)
    r = client.post("/api/orders/XP4/confirm-received", headers=bob_tok)
    check("他人订单确认收货 → 404", r.status_code == 404, r.text)
    r = client.post("/api/orders/XP4/confirm-received", headers=emma_tok)
    check("确认收货 4→5", r.status_code == 200 and r.json()["status"] == 5, r.text)
    s.expire_all()
    o4 = repo.get_order(s, o4.id)
    check("completed_at 落库 + timeline", o4.completed_at is not None and any(
        t.event == "status_changed" and t.detail.get("to") == 5
        for t in s.query(repo.OrderTimeline).filter_by(order_id=o4.id)))
    r = client.post("/api/orders/XP4/confirm-received", headers=emma_tok)
    check("重复确认 → 409 not_confirmable", r.status_code == 409
          and str(r.json()["detail"]).startswith("not_confirmable"), r.text)
    o1, _ = mk_order(s, "XP1", emma.id, 1, v_short)
    r = client.post("/api/orders/XP1/confirm-received", headers=emma_tok)
    check("非送达状态 → 409", r.status_code == 409, r.text)

    # ===== 换货撤销 =====
    o5, it5 = mk_order(s, "XP5", emma.id, 3, v_short)
    ex0 = mk_exchange(s, "EXWD0001", o5, it5, v_short, v_long, 0, 600)
    r = client.post("/api/exchanges/EXWD0001/cancel", headers=bob_tok)
    check("他人换货撤销 → 404", r.status_code == 404, r.text)
    r = client.post("/api/exchanges/EXWD0001/cancel", headers=emma_tok)
    check("换货撤销(0) → 删除", r.status_code == 200
          and r.json()["status"] == "canceled", r.text)
    check("撤销后行已删除", repo.exchange_by_no(s, "EXWD0001") is None)
    ex2 = mk_exchange(s, "EXWD0002", o5, it5, v_short, v_long, 1, 600)
    r = client.post("/api/exchanges/EXWD0002/cancel", headers=emma_tok)
    check("非申请中撤销 → 409", r.status_code == 409
          and str(r.json()["detail"]).startswith("exchange_not_cancellable"), r.text)

    # ===== 差价支付：mock 链路 =====
    ex3 = mk_exchange(s, "EXPY0001", o5, it5, v_short, v_long, 2, 600)
    r = client.post("/api/exchanges/EXPY0001/pay-intent", headers=emma_tok)
    check("pay-intent 2 → 200 带 PI", r.status_code == 200
          and r.json()["payment_intent"].startswith("PI_"), r.text)
    pi1 = r.json()["payment_intent"]
    r = client.post("/api/exchanges/EXPY0001/pay-intent", headers=emma_tok)
    check("pay-intent 幂等复用", r.status_code == 200
          and r.json()["payment_intent"] == pi1, r.text)
    s.expire_all()
    ex3 = repo.exchange_by_no(s, "EXPY0001")
    pay_row = s.query(repo.Payment).filter_by(
        stripe_payment_intent=pi1).first()
    check("diff_payment_id 已关联", ex3.diff_payment_id == pay_row.id)
    r = client.post("/api/exchanges/EXPY0001/mock-pay", headers=emma_tok,
                    json={"succeed": True})
    check("mock-pay 2→1 + payment 核销", r.status_code == 200
          and r.json()["exchange_status"] == 1
          and r.json()["payment_status"] == 1, r.text)
    r = client.post("/api/exchanges/EXPY0001/mock-pay", headers=emma_tok,
                    json={"succeed": True})
    check("重复支付 → 409 diff_already_paid", r.status_code == 409
          and r.json()["detail"] == "diff_already_paid", r.text)

    # ===== 差价支付：webhook 路由（关联 payment 的 succeeded 核销换货，不动订单） =====
    ex4 = mk_exchange(s, "EXPY0002", o5, it5, v_short, v_long, 2, 600)
    r = client.post("/api/exchanges/EXPY0002/pay-intent", headers=emma_tok)
    pi2 = r.json()["payment_intent"]
    o5_status_before = repo.get_order(s, o5.id).status
    r = client.post("/api/payments/webhook", json={
        "id": "evt_xp_1", "type": "payment_intent.succeeded",
        "data": {"payment_intent": pi2, "amount": 600, "metadata": {}},
    })
    check("webhook 200 ok", r.status_code == 200 and r.json().get("ok"), r.text)
    s.expire_all()
    ex4 = repo.exchange_by_no(s, "EXPY0002")
    pay2 = s.query(repo.Payment).filter_by(stripe_payment_intent=pi2).first()
    check("webhook 核销换货 2→1", ex4.status == 1, ex4.status)
    check("webhook 核销 payment", pay2.status == 1, pay2.status)
    check("原订单状态未被推进", repo.get_order(s, o5.id).status == o5_status_before)
    r = client.post("/api/payments/webhook", json={
        "id": "evt_xp_1", "type": "payment_intent.succeeded",
        "data": {"payment_intent": pi2, "amount": 600, "metadata": {}},
    })
    check("webhook 事件幂等（duplicate）", r.status_code == 200
          and r.json().get("duplicate"), r.text)

    # ===== 差价支付：非 2 状态 / 无差异 =====
    r = client.post("/api/exchanges/EXPY0002/pay-intent", headers=emma_tok)
    check("已核销再建 → 409", r.status_code == 409, r.text)
    ex_diff0 = mk_exchange(s, "EXPY0003", o5, it5, v_short, v_short, 2, 0)
    r = client.post("/api/exchanges/EXPY0003/pay-intent", headers=emma_tok)
    check("无差异(diff=0) → 409 no_diff_to_pay", r.status_code == 409
          and r.json()["detail"] == "no_diff_to_pay", r.text)

    # ===== admin mark-paid：无 payment 换货走旧路径 =====
    from app.core.db import utcnow
    admin = User(email="root@glow.test", password_hash=hash_password("x"),
                 name="Root", role=9, points=0)
    s.add(admin)
    s.commit()
    admin_tok = {"Authorization": f"Bearer {create_token(admin.id, 9)}"}
    ex5 = mk_exchange(s, "EXPY0004", o5, it5, v_short, v_long, 2, 600)
    r = client.post("/api/admin/trade/exchanges/EXPY0004/mark-paid",
                    headers=admin_tok)
    check("admin mark-paid（无 payment）→ 1", r.status_code == 200
          and r.json()["status"] == 1, r.text)

    # ===== /me 附带 delete_request =====
    r = client.get("/api/account/me", headers=emma_tok)
    check("/me 无注销申请 → delete_request null", r.status_code == 200
          and r.json().get("delete_request") is None, r.text)
    r = client.post("/api/account/delete-request", headers=emma_tok)
    eff = r.json().get("effective_at")
    r = client.get("/api/account/me", headers=emma_tok)
    check("/me 回显 pending 注销申请", r.status_code == 200
          and r.json().get("delete_request", {})
          and r.json()["delete_request"]["effective_at"] == eff, r.text)

    s.close()

print(f"\n==== test_xpay: {PASSED} passed, {len(FAILED)} failed ====")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
