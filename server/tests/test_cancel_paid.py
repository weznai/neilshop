"""已付未发货取消 / RMA 撤销 回归（GM_DB=sqlite:///test_cp.sqlite 独立库；
BigInteger 垫片同 test_payments.py）。覆盖：
- paid+未发货 → 200 状态9 全额退款（库存回补 / 积分双向 / 礼品卡回补 / outbox order.refunded）
- 已发货 → 409
- 无可退 payment → 降级仅 CAS+timeline（状态 8 / refund null）
- 误建 RMA → 撤销 → 可重新申请；非申请中 → 409；他人 RMA → 404"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_cp.sqlite").replace("\\", "/")
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
from app.core.enums import PointsReason  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Category, GiftCard, GiftCardLedger, Order, OrderItem, OrderTimeline,
    OutboxEvent, Payment, PointsLedger, Product, Rma, StockMovement, User,
    Variant,
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

with TestClient(app) as client:
    s = SessionLocal()

    cat = Category(slug="press-on-nails", name="Press-on Nails")
    s.add(cat)
    s.flush()
    p = Product(slug="cp-gems", title="CP Gems", category_id=cat.id, status=1,
                hero_image="https://img/c.jpg", price_min=2000, price_max=2000)
    s.add(p)
    s.flush()
    v = Variant(product_id=p.id, sku="CP-1", option1_value="Short",
                option2_value="24pcs", price=2000, stock=10)
    s.add(v)
    s.flush()
    emma = User(email="emma@glow.test", password_hash=hash_password("x"),
                name="Emma", role=0, points=1000)
    bob = User(email="bob@glow.test", password_hash=hash_password("x"),
               name="Bob", role=0, points=0)
    s.add_all([emma, bob])
    s.flush()
    s.add(PointsLedger(user_id=emma.id, change=1000, balance_after=1000,
                       reason=int(PointsReason.CHECKIN), frozen=0))
    for code in ("GC-CP-0001", "GC-CP-0002", "GC-CP-0003", "GC-CP-0004"):
        s.add(GiftCard(code=code, initial_amount=3000, balance=3000,
                       status=1, purchaser_email="emma@glow.test"))
    s.commit()

    emma_auth = {"Authorization": f"Bearer {create_token(emma.id, emma.role)}"}
    bob_auth = {"Authorization": f"Bearer {create_token(bob.id, bob.role)}"}

    def order_by_no(no):
        s.expire_all()
        return s.query(Order).filter(Order.order_no == no).first()

    def place_and_pay(tag, *, points=500, gc_code):
        """下单（默认 500 分 + 礼品卡 1500）→ mock 支付成功；返回 order_no。"""
        cart_tok = f"tok-cp-{tag}"
        r = client.post("/api/cart/items", headers={"X-Cart-Token": cart_tok, **emma_auth},
                        json={"variant_id": v.id, "qty": 1})
        assert r.status_code == 201, r.text
        r = client.post("/api/checkout/place",
                        headers={"X-Cart-Token": cart_tok, **emma_auth},
                        json={"email": "emma@glow.test", "address": ADDR,
                              "points": points, "gift_card_code": gc_code})
        assert r.status_code == 201, r.text
        no = r.json()["order_no"]
        r = client.post("/api/payments/create-intent", headers=emma_auth,
                        json={"order_no": no})
        assert r.status_code == 200, r.text
        r = client.post("/api/payments/mock-pay", headers=emma_auth,
                        json={"order_no": no, "succeed": True})
        assert r.status_code == 200 and r.json()["order_status"] == 1, r.text
        return no

    # ===== 1. paid + 未发货 → 取消 → 200 状态 9 全额退款 =====
    no1 = place_and_pay("a", gc_code="GC-CP-0001")
    o1 = order_by_no(no1)
    s.expire_all()
    # 试算：subtotal 2000 - 积分 500 - 礼品卡 1500 + 运费 499 + 税 37 = 536
    check("下单支付基线：giftcard_discount 1500 / points_used 500 / grand 536",
          o1.giftcard_discount == 1500 and o1.points_used == 500
          and o1.grand_total == 536 and o1.points_earned == 53
          and s.get(Variant, v.id).stock == 9
          and s.get(User, emma.id).points == 553,
          (o1.giftcard_discount, o1.points_used, o1.grand_total, o1.points_earned))
    pay1 = (s.query(Payment).filter(Payment.order_id == o1.id)
            .order_by(Payment.id.desc()).first())
    check("支付行 SUCCESS 金额 536", pay1 is not None and pay1.status == 1
          and pay1.amount == 536, pay1 and pay1.amount)

    r = client.post(f"/api/orders/{no1}/cancel", headers=emma_auth)
    d = r.json()
    o1 = order_by_no(no1)
    s.expire_all()
    check("paid 取消 → 200 状态 9 + refund{amount=536, full, payment_status=3}",
          r.status_code == 200 and d["status"] == 9
          and d["refund"] == {"amount": 536, "full": True, "payment_status": 3}, d)
    pay1 = (s.query(Payment).filter(Payment.order_id == o1.id)
            .order_by(Payment.id.desc()).first())
    check("payment 全额退款（refunded_amount=536 / status=3）",
          pay1.status == 3 and pay1.refunded_amount == 536,
          (pay1.status, pay1.refunded_amount))
    check("库存回补 9→10 + RESTOCK(type=5) 流水",
          s.get(Variant, v.id).stock == 10
          and s.query(StockMovement).filter(StockMovement.type == 5,
                                            StockMovement.ref_id == o1.id).count() == 1,
          s.get(Variant, v.id).stock)
    s.expire_all()
    emma_db = s.get(User, emma.id)
    void_row = s.query(PointsLedger).filter(
        PointsLedger.user_id == emma.id, PointsLedger.ref_id == o1.id,
        PointsLedger.reason == int(PointsReason.REFUND_VOID)).first()
    ret_row = s.query(PointsLedger).filter(
        PointsLedger.user_id == emma.id, PointsLedger.ref_id == o1.id,
        PointsLedger.reason == int(PointsReason.REFUND_RETURN)).first()
    check("积分双向：赚的 53 作废（REFUND_VOID）+ 用的 500 返还（REFUND_RETURN）→ 余额回 1000",
          emma_db.points == 1000 and void_row is not None and void_row.change == -53
          and ret_row is not None and ret_row.change == 500, emma_db.points)
    gc = s.query(GiftCard).filter(GiftCard.code == "GC-CP-0001").first()
    check("礼品卡回补 1500 → 余额 3000 + change_type=5 流水",
          gc.balance == 3000 and s.query(GiftCardLedger).filter(
              GiftCardLedger.gift_card_id == gc.id,
              GiftCardLedger.change_type == 5).count() == 1, gc.balance)
    check("outbox order.refunded 事件落库（full=True）",
          s.query(OutboxEvent).filter(OutboxEvent.event_type == "order.refunded",
                                      OutboxEvent.aggregate_id == o1.id).count() == 1)
    tl = s.query(OrderTimeline).filter(OrderTimeline.order_id == o1.id,
                                       OrderTimeline.event == "status_changed",
                                       OrderTimeline.actor == "user").all()
    check("timeline status_changed actor=user（1→9 user_cancel_paid）",
          any(t.detail.get("from") == 1 and t.detail.get("to") == 9
              and t.detail.get("reason") == "user_cancel_paid" for t in tl),
          [t.detail for t in tl])
    r = client.post(f"/api/orders/{no1}/cancel", headers=emma_auth)
    check("已取消（终态 9）再取消 → 409", r.status_code == 409, r.text)

    # ===== 2. 已发货 → 409 =====
    no2 = place_and_pay("b", gc_code="GC-CP-0002")
    o2 = order_by_no(no2)
    o2.status = 3
    o2.shipping_status = 2
    s.commit()
    r = client.post(f"/api/orders/{no2}/cancel", headers=emma_auth)
    check("已发货取消 → 409 not_cancellable:3",
          r.status_code == 409 and r.json()["detail"] == "not_cancellable:3", r.text)
    o2 = order_by_no(no2)
    check("已发货取消被拒后状态不变（仍 3）", o2.status == 3)

    # 已付但部分发货（shipping_status=1）同样不可取消
    o2.status = 1
    o2.shipping_status = 1
    s.commit()
    r = client.post(f"/api/orders/{no2}/cancel", headers=emma_auth)
    check("部分发货取消 → 409 not_cancellable:1", r.status_code == 409, r.text)

    # ===== 3. 无可退 payment → 降级：仅 CAS + timeline，不阻断 =====
    no3 = place_and_pay("c", gc_code="GC-CP-0003")
    o3 = order_by_no(no3)
    s.query(Payment).filter(Payment.order_id == o3.id).delete(synchronize_session=False)
    s.commit()
    r = client.post(f"/api/orders/{no3}/cancel", headers=emma_auth)
    d = r.json()
    o3 = order_by_no(no3)
    s.expire_all()
    tl3 = s.query(OrderTimeline).filter(OrderTimeline.order_id == o3.id,
                                        OrderTimeline.event == "status_changed",
                                        OrderTimeline.actor == "user").all()
    check("无 payment 降级取消 → 200 状态 8 / refund null / timeline 不缺",
          r.status_code == 200 and d["status"] == 8 and d["refund"] is None
          and any(t.detail.get("from") == 1 and t.detail.get("to") == 8 for t in tl3),
          d)

    # ===== 4. 他人订单 → 404 =====
    r = client.post(f"/api/orders/{no2}/cancel", headers=bob_auth)
    check("非归属人取消 → 404", r.status_code == 404, r.text)

    # ===== 5. RMA 撤销：误建 → 撤销 → 可重新申请 =====
    no4 = place_and_pay("d", points=0, gc_code="GC-CP-0004")
    o4 = order_by_no(no4)
    o4.status = 4  # DELIVERED 可退
    s.commit()
    item4 = s.query(OrderItem).filter(OrderItem.order_id == o4.id).first()
    r = client.post("/api/returns", headers=emma_auth, json={
        "order_no": no4, "order_item_id": item4.id, "qty": 1, "reason": 3})
    rma_no = r.json().get("rma_no", "")
    check("误建 RMA → 201 申请中", r.status_code == 201 and rma_no.startswith("RMA"), r.text)
    r = client.post(f"/api/returns/{rma_no}/cancel", headers=emma_auth)
    check("RMA 撤销 → 200 {rma_no, status:canceled}",
          r.status_code == 200 and r.json() == {"rma_no": rma_no, "status": "canceled"},
          r.text)
    s.expire_all()
    check("RMA 行已删 + timeline rma_canceled(actor=user)",
          s.query(Rma).filter(Rma.rma_no == rma_no).count() == 0
          and s.query(OrderTimeline).filter(OrderTimeline.order_id == o4.id,
                                            OrderTimeline.event == "rma_canceled",
                                            OrderTimeline.actor == "user").count() == 1)
    r = client.post("/api/returns", headers=emma_auth, json={
        "order_no": no4, "order_item_id": item4.id, "qty": 1, "reason": 3})
    rma2_no = r.json().get("rma_no", "")
    check("撤销后可重新申请（新 RMA 单号）",
          r.status_code == 201 and rma2_no.startswith("RMA") and rma2_no != rma_no, r.text)

    r = client.post(f"/api/returns/{rma2_no}/cancel", headers=bob_auth)
    check("他人 RMA 撤销 → 404", r.status_code == 404, r.text)

    s.expire_all()
    rma2 = s.query(Rma).filter(Rma.rma_no == rma2_no).first()
    rma2.status = 2  # 已批
    s.commit()
    r = client.post(f"/api/returns/{rma2_no}/cancel", headers=emma_auth)
    check("非申请中 RMA 撤销 → 409 rma_not_cancellable:2",
          r.status_code == 409 and r.json()["detail"] == "rma_not_cancellable:2", r.text)
    check("不存在的 RMA 撤销 → 404",
          client.post("/api/returns/RMA404/cancel",
                      headers=emma_auth).status_code == 404)

    s.close()

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
