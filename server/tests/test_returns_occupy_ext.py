"""RMA/换货占量回归（P0-1/P0-3）—— 在途申请占用量 / 收货-发货原子占量 / consume 守卫 /
纯礼品卡多笔 RMA 比例回补（不翻倍）/ P1 订单现态守卫。
（GM_DB=sqlite:///test_occupy_ext.sqlite 独立库；BigInteger 垫片同 test_admin_flow_ext.py）"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_occupy_ext.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
os.environ["GM_RATE_RULES"] = '{"/api/returns": 100, "/api/exchanges": 100}'
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
    Category, Exchange, GiftCard, GiftCardLedger, Order, OrderItem, Payment,
    Product, Rma, User, Variant,
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
        "zip": "94110", "country": "US"}


def make_order(s, no, lines, *, user_id, status=1, subtotal=None, grand_total=None,
               giftcard_discount=0, paid=True):
    sub = subtotal if subtotal is not None else sum(p * q for _v, q, p in lines)
    gt = grand_total if grand_total is not None else sub
    o = Order(order_no=no, user_id=user_id, email="occ@glow.test", status=status,
              subtotal=sub, grand_total=gt, giftcard_discount=giftcard_discount,
              shipping_address=ADDR, placed_at=utcnow(),
              paid_at=utcnow() if paid else None, points_earned=0)
    s.add(o)
    s.flush()
    items = []
    for vid, qty, price in lines:
        it = OrderItem(order_id=o.id, variant_id=vid, product_slug="occ-gel",
                       title_snapshot="Occ Gel", qty=qty, unit_price=price,
                       subtotal=price * qty)
        s.add(it)
        items.append(it)
    s.flush()
    return o, items


def main() -> int:
    with TestClient(app) as client:
        s = SessionLocal()

        cat = Category(slug="occ-cat", name="Occ Cat")
        s.add(cat)
        s.flush()
        p = Product(slug="occ-gel", title="Occ Gel", category_id=cat.id, status=1,
                    hero_image="https://img/e.jpg", price_min=800, price_max=1000)
        s.add(p)
        s.flush()
        v_a = Variant(product_id=p.id, sku="OCC-A", option1_value="Short",
                      option2_value="24pcs", price=1000, stock=50)
        v_b = Variant(product_id=p.id, sku="OCC-B", option1_value="Mini",
                      option2_value="12pcs", price=1000, stock=50)
        s.add_all([v_a, v_b])
        emma = User(email="occ@glow.test", password_hash=hash_password("x"),
                    name="Occ", role=0)
        ops = User(email="occops@glow.test", password_hash=hash_password("x"),
                   name="OccOps", role=9)
        s.add_all([emma, ops])
        s.commit()
        H_EMMA = {"Authorization": f"Bearer {create_token(emma.id, emma.role)}"}
        H_OPS = {"Authorization": f"Bearer {create_token(ops.id, ops.role)}"}

        # ===== 1. RMA 在途占量（P0-1a）：qty=1 连发两笔 → 第二笔 409 =====
        o1, it1 = make_order(s, "OCC260825RMA01", [(v_a.id, 1, 1000)], user_id=emma.id)
        s.commit()
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "OCC260825RMA01", "order_item_id": it1[0].id,
            "qty": 1, "reason": 3})
        rma1_no = r.json().get("rma_no", "")
        check("qty=1 件第一笔 RMA → 201",
              r.status_code == 201 and rma1_no.startswith("RMA"), r.text[:120])
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "OCC260825RMA01", "order_item_id": it1[0].id,
            "qty": 1, "reason": 3})
        check("在途未结案同件第二笔 RMA → 409 qty_exceeds_available:0（防双回补）",
              r.status_code == 409 and "qty_exceeds_available:0" in r.text, r.text[:120])

        # qty=2 分两笔可、第三笔拒
        o2, it2 = make_order(s, "OCC260825RMA02", [(v_a.id, 2, 1000)], user_id=emma.id)
        s.commit()
        nos = []
        for _ in range(2):
            r = client.post("/api/returns", headers=H_EMMA, json={
                "order_no": "OCC260825RMA02", "order_item_id": it2[0].id,
                "qty": 1, "reason": 3})
            nos.append(r.status_code)
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "OCC260825RMA02", "order_item_id": it2[0].id,
            "qty": 1, "reason": 3})
        check("qty=2 件两笔各 1 通过 / 第三笔 → 409 qty_exceeds_available:0",
              nos == [201, 201] and r.status_code == 409
              and "qty_exceeds_available:0" in r.text, (nos, r.text[:120]))

        # ===== 2. 换货在途占量（P0-1a）：qty=1 连发两笔 → 第二笔 409 =====
        o3, it3 = make_order(s, "OCC260825EXC01", [(v_a.id, 1, 1000)], user_id=emma.id)
        s.commit()
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "OCC260825EXC01", "order_item_id": it3[0].id,
            "new_variant_id": v_b.id})
        ex1_no = r.json().get("exchange_no", "")
        check("qty=1 件第一笔换货 → 201",
              r.status_code == 201 and ex1_no.startswith("EX"), r.text[:120])
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "OCC260825EXC01", "order_item_id": it3[0].id,
            "new_variant_id": v_b.id})
        check("在途同件第二笔换货 → 409 qty_exceeds_available:0（防双补发）",
              r.status_code == 409 and "qty_exceeds_available:0" in r.text, r.text[:120])

        # ===== 3. RMA 与换货互相穿透（P0-1d）：任一在途另一侧即 409 =====
        o4, it4 = make_order(s, "OCC260825MIX01", [(v_a.id, 1, 1000)], user_id=emma.id)
        s.commit()
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "OCC260825MIX01", "order_item_id": it4[0].id,
            "qty": 1, "reason": 3})
        check("MIX01 第一笔 RMA → 201（在途占量起点）", r.status_code == 201, r.text[:120])
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "OCC260825MIX01", "order_item_id": it4[0].id,
            "new_variant_id": v_b.id})
        check("RMA 在途 → 换货 409 qty_exceeds_available:0",
              r.status_code == 409 and "qty_exceeds_available:0" in r.text, r.text[:120])

        o5, it5 = make_order(s, "OCC260825MIX02", [(v_a.id, 1, 1000)], user_id=emma.id)
        s.commit()
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "OCC260825MIX02", "order_item_id": it5[0].id,
            "new_variant_id": v_b.id})
        check("换货在途建单 → 201", r.status_code == 201, r.text[:120])
        r = client.post("/api/returns", headers=H_EMMA, json={
            "order_no": "OCC260825MIX02", "order_item_id": it5[0].id,
            "qty": 1, "reason": 3})
        check("换货在途 → RMA 409 qty_exceeds_available:0",
              r.status_code == 409 and "qty_exceeds_available:0" in r.text, r.text[:120])

        # ===== 4. receive 原子占量 + refund 不重复累计（P0-1b）=====
        s.add(Payment(order_id=o1.id, stripe_payment_intent="PI_OCC1",
                      amount=1000, status=1, refunded_amount=0))
        s.commit()
        r = client.post(f"/api/admin/trade/rmas/{rma1_no}/approve", headers=H_OPS)
        check("RMA approve 200（订单 status=1 在履约态）",
              r.status_code == 200 and r.json()["status"] == 2, r.text[:120])
        r = client.post(f"/api/admin/trade/rmas/{rma1_no}/receive", headers=H_OPS)
        s.expire_all()
        check("receive 200 → refunded_qty 即时占量 1（发新货/回补前占）",
              r.status_code == 200 and s.get(OrderItem, it1[0].id).refunded_qty == 1,
              (r.status_code, r.text[:120]))
        r = client.post(f"/api/admin/trade/rmas/{rma1_no}/refund", headers=H_OPS)
        s.expire_all()
        check("refund 200 → refunded_qty 仍 1（不重复累计）/ Payment 全退",
              r.status_code == 200
              and s.get(OrderItem, it1[0].id).refunded_qty == 1
              and (s.query(Payment).filter(Payment.order_id == o1.id).first()
                   .refunded_amount == 1000),
              r.text[:160])

        # ===== 5. consume 守卫：直达 4 态的穿透单退款被余量守卫拦截 =====
        o6, it6 = make_order(s, "OCC260825GUARD1", [(v_a.id, 1, 1000)], user_id=emma.id)
        s.add(Payment(order_id=o6.id, stripe_payment_intent="PI_OCC6",
                      amount=1000, status=1, refunded_amount=0))
        s.add(Rma(rma_no="RMAOCCGUARD01", order_id=o6.id, order_item_id=it6[0].id,
                  qty=1, reason=3, status=4))
        s.add(Rma(rma_no="RMAOCCGUARD02", order_id=o6.id, order_item_id=it6[0].id,
                  qty=1, reason=3, status=4))
        s.commit()
        r = client.post("/api/admin/trade/rmas/RMAOCCGUARD01/refund", headers=H_OPS)
        s.expire_all()
        check("穿透单 #1 退款 200（退款时补占 refunded_qty=1）",
              r.status_code == 200 and s.get(OrderItem, it6[0].id).refunded_qty == 1,
              r.text[:160])
        r = client.post("/api/admin/trade/rmas/RMAOCCGUARD02/refund", headers=H_OPS)
        s.expire_all()
        pay6 = s.query(Payment).filter(Payment.order_id == o6.id).first()
        check("穿透单 #2 退款 → 409 qty_exceeded（余量守卫，防同件双退）",
              r.status_code == 409 and "qty_exceeded" in r.text
              and pay6.refunded_amount == 1000,
              (r.status_code, r.text[:120]))

        # ===== 6. ship 原子占量 + complete 不重复累计（P0-1c）=====
        r = client.post(f"/api/admin/trade/exchanges/{ex1_no}/approve", headers=H_OPS)
        check("同价换货 approve → 1 直批",
              r.status_code == 200 and r.json()["status"] == 1, r.text[:120])
        s.expire_all()
        stock_a_before = s.get(Variant, v_a.id).stock
        stock_b_before = s.get(Variant, v_b.id).stock
        r = client.post(f"/api/admin/trade/exchanges/{ex1_no}/ship", headers=H_OPS,
                        json={"carrier": "usps", "tracking_no": "9400OCC0001"})
        s.expire_all()
        check("ship 200 → exchanged_qty 即时占量 1 + 新变体 -1（complete 前）",
              r.status_code == 200
              and s.get(OrderItem, it3[0].id).exchanged_qty == 1
              and s.get(Variant, v_b.id).stock == stock_b_before - 1,
              r.text[:160])
        r = client.post(f"/api/admin/trade/exchanges/{ex1_no}/complete", headers=H_OPS)
        s.expire_all()
        check("complete 200 → exchanged_qty 仍 1 / 旧变体回补 +1",
              r.status_code == 200
              and s.get(OrderItem, it3[0].id).exchanged_qty == 1
              and s.get(Variant, v_a.id).stock == stock_a_before + 1,
              r.text[:160])

        # ===== 7. 纯礼品卡多笔 RMA 比例回补（P0-3：不翻倍）=====
        o8, it8 = make_order(s, "OCC260825GC001",
                             [(v_a.id, 1, 1000), (v_b.id, 1, 1000)],
                             user_id=emma.id, giftcard_discount=2000)
        gc = GiftCard(code="GC-OCC-0001", initial_amount=2000, balance=0,
                      status=3, purchaser_email="occ@glow.test")
        s.add(gc)
        s.flush()
        s.add(GiftCardLedger(gift_card_id=gc.id, order_id=o8.id, change_type=3,
                             amount=2000, balance_after=0))
        s.add_all([
            Rma(rma_no="RMAOCCGC0001", order_id=o8.id, order_item_id=it8[0].id,
                qty=1, reason=3, status=4),
            Rma(rma_no="RMAOCCGC0002", order_id=o8.id, order_item_id=it8[1].id,
                qty=1, reason=3, status=4),
        ])
        s.commit()
        r = client.post("/api/admin/trade/rmas/RMAOCCGC0001/refund", headers=H_OPS)
        s.expire_all()
        gc = s.get(GiftCard, gc.id)
        check("纯礼品卡单 RMA#1 退款 → 按比例回补 1000（非整单 2000）",
              r.status_code == 200 and gc.balance == 1000,
              (r.text[:160], gc.balance))
        r = client.post("/api/admin/trade/rmas/RMAOCCGC0002/refund", headers=H_OPS)
        s.expire_all()
        gc = s.get(GiftCard, gc.id)
        ledger5 = (s.query(GiftCardLedger)
                   .filter(GiftCardLedger.gift_card_id == gc.id,
                           GiftCardLedger.change_type == 5).count())
        check("RMA#2 退款 → 余额 2000 封顶（不翻倍）/ 两条返还流水 / 用尽卡复活",
              r.status_code == 200 and gc.balance == 2000 and ledger5 == 2
              and gc.status == 1,
              (r.text[:160], gc.balance, ledger5, gc.status))

        # ===== 8. P1-5 订单现态守卫：终态订单 RMA/换货不可推进 =====
        o9, it9 = make_order(s, "OCC260825ST001", [(v_a.id, 1, 1000)],
                             user_id=emma.id, status=9)
        s.add(Rma(rma_no="RMAOCCST0001", order_id=o9.id, order_item_id=it9[0].id,
                  qty=1, reason=3, status=0))
        s.add(Exchange(exchange_no="EXOCCST0001", order_id=o9.id,
                       order_item_id=it9[0].id, old_variant_id=v_a.id,
                       new_variant_id=v_b.id, price_diff=0, status=0))
        s.commit()
        r = client.post("/api/admin/trade/rmas/RMAOCCST0001/approve", headers=H_OPS)
        check("整退(9)订单 RMA approve → 409 order_state_invalid:9",
              r.status_code == 409 and "order_state_invalid:9" in r.text, r.text[:120])
        r = client.post("/api/admin/trade/exchanges/EXOCCST0001/approve", headers=H_OPS)
        check("整退(9)订单换货 approve → 409 order_state_invalid:9",
              r.status_code == 409 and "order_state_invalid:9" in r.text, r.text[:120])

        # ===== 9. P1-11 待退单预估可退额（列表 refund_amount 非 null）=====
        o10, it10 = make_order(s, "OCC260825EST001", [(v_a.id, 1, 1000)],
                               user_id=emma.id, status=4, grand_total=1200)
        s.add(Rma(rma_no="RMAOCCEST001", order_id=o10.id, order_item_id=it10[0].id,
                  qty=1, reason=3, status=4))
        s.commit()
        r = client.get("/api/admin/trade/rmas", headers=H_OPS, params={"status": 4, "q": "OCC260825EST001"})
        d = r.json()
        check("status=4 待退单列表预填 refund_amount=1200（实付比例折算）",
              r.status_code == 200 and d["total"] == 1
              and d["items"][0]["refund_amount"] == 1200, d.get("items"))

        s.close()

    print(f"\n{PASSED} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed:", FAILED)
        return 1
    return 0


def test_returns_occupy_ext():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
