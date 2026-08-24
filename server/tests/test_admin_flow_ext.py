"""admin trade/support/catalog 扩展自测 —— 订单状态机补全（prepare/mark-completed）/ 改地址 /
换货负差价退款 / RMA 可调金额+部分退款(7) / 工单列表最后消息 / 变体删除保护 /
低库存口径 max(safety_stock,8) / 到货通知名单 / catalog 列表 pages。
（GM_DB=sqlite:///test_admin_flow_ext.sqlite 独立库；BigInteger 垫片同 test_admin_ops_ext.py；
直跑与 pytest 双兼容：main() 承载全部断言，尾部 __main__ 约定 + pytest 包装函数）"""

import os
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_admin_flow_ext.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
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
    AdminLog, Cart, Category, Exchange, Order, OrderItem, OrderTimeline, Payment,
    Product, Rma, StockNotification, Ticket, TicketMessage, User, Variant,
    VariantImage,
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


ADDR = {"full_name": "T", "line1": "1 Main St", "line2": "Apt 5", "city": "SF",
        "state": "CA", "zip": "94110", "country": "US", "phone": "+14155550001"}


def make_order(s, no, lines, *, email="flow@glow.test", status=1, subtotal=None,
               grand_total=None):
    sub = subtotal if subtotal is not None else sum(p * q for _v, q, p in lines)
    gt = grand_total if grand_total is not None else sub
    o = Order(order_no=no, email=email, status=status, subtotal=sub, grand_total=gt,
              shipping_address=ADDR, placed_at=utcnow(), paid_at=utcnow(),
              points_earned=0, giftcard_discount=0)
    s.add(o)
    s.flush()
    items = []
    for vid, qty, price in lines:
        it = OrderItem(order_id=o.id, variant_id=vid, product_slug="flow-gel",
                       title_snapshot="Flow Gel", qty=qty, unit_price=price,
                       subtotal=price * qty)
        s.add(it)
        items.append(it)
    s.flush()
    return o, items


def ev_detail(s, order_id, event):
    s.expire_all()
    row = (s.query(OrderTimeline)
           .filter(OrderTimeline.order_id == order_id,
                   OrderTimeline.event == event).first())
    return row.detail if row else None


def main() -> int:
    with TestClient(app) as client:
        s = SessionLocal()
        ops = User(email="flowops@glow.test", password_hash=hash_password("x"),
                   name="FlowOps", role=9)
        s.add(ops)
        s.commit()
        H = {"Authorization": f"Bearer {create_token(ops.id, ops.role)}"}

        # ===== 1. 订单状态机：prepare 1→2 / mark-completed 4→5 =====
        o_prep, _ = make_order(s, "FLW26PREP001", [(1, 1, 1000)])
        o_pend, _ = make_order(s, "FLW26PREP002", [(1, 1, 1000)], status=0)
        s.commit()
        check("prepare 端点需要鉴权",
              client.post("/api/admin/trade/orders/FLW26PREP001/prepare").status_code == 401)
        r = client.post("/api/admin/trade/orders/FLW26PREP001/prepare", headers=H)
        d = r.json()
        s.expire_all()
        check("prepare 1→2 开始备货（无 body 可）",
              r.status_code == 200 and d == {"order_no": "FLW26PREP001", "order_status": 2}
              and s.query(Order).filter(Order.order_no == "FLW26PREP001").first().status == 2,
              (r.status_code, d))
        check("prepare timeline status_changed 1→2 + 审计",
              ev_detail(s, o_prep.id, "status_changed") == {"from": 1, "to": 2}
              and s.query(AdminLog).filter(AdminLog.action == "prepare",
                                           AdminLog.entity == "order",
                                           AdminLog.entity_id == o_prep.id).count() == 1)
        r = client.post("/api/admin/trade/orders/FLW26PREP001/prepare", headers=H)
        check("重复 prepare → 409 not_prepable:2",
              r.status_code == 409 and r.json()["detail"] == "not_prepable:2",
              (r.status_code, r.json().get("detail")))
        r = client.post("/api/admin/trade/orders/FLW26PREP002/prepare", headers=H)
        check("待支付单 prepare → 409 not_prepable:0",
              r.status_code == 409 and r.json()["detail"] == "not_prepable:0",
              (r.status_code, r.json().get("detail")))

        o_done, _ = make_order(s, "FLW26DONE0001", [(1, 1, 1000)], status=4)
        o_tr, _ = make_order(s, "FLW26DONE0002", [(1, 1, 1000)], status=3)
        s.commit()
        r = client.post("/api/admin/trade/orders/FLW26DONE0001/mark-completed", headers=H)
        d = r.json()
        s.expire_all()
        o_db = s.query(Order).filter(Order.order_no == "FLW26DONE0001").first()
        check("mark-completed 4→5 代确认完成 + completed_at 落库",
              r.status_code == 200 and d == {"order_no": "FLW26DONE0001", "order_status": 5}
              and o_db.status == 5 and o_db.completed_at is not None,
              (r.status_code, d))
        check("mark-completed timeline reason=admin_confirm + 审计",
              ev_detail(s, o_done.id, "status_changed") == {
                  "from": 4, "to": 5, "reason": "admin_confirm"}
              and s.query(AdminLog).filter(AdminLog.action == "mark_completed",
                                           AdminLog.entity_id == o_done.id).count() == 1)
        r = client.post("/api/admin/trade/orders/FLW26DONE0001/mark-completed", headers=H)
        check("重复 mark-completed → 409 not_completable:5",
              r.status_code == 409 and r.json()["detail"] == "not_completable:5",
              (r.status_code, r.json().get("detail")))
        r = client.post("/api/admin/trade/orders/FLW26DONE0002/mark-completed", headers=H)
        check("在途单 mark-completed → 409 not_completable:3",
              r.status_code == 409 and r.json()["detail"] == "not_completable:3",
              (r.status_code, r.json().get("detail")))

        # ===== 2. 订单改地址：部分更新 / 已发货 409 / timeline 旧值摘要 =====
        check("改地址端点需要鉴权",
              client.put("/api/admin/trade/orders/FLW26PREP001/address",
                         json={"city": "LA"}).status_code == 401)
        r = client.put("/api/admin/trade/orders/FLW26PREP001/address", headers=H,
                       json={"city": "LA", "zip": "90001"})
        d = r.json()
        s.expire_all()
        o_db = s.query(Order).filter(Order.order_no == "FLW26PREP001").first()
        check("改地址部分更新（city/zip 改、其余保持）",
              r.status_code == 200 and d["shipping_address"]["city"] == "LA"
              and d["shipping_address"]["zip"] == "90001"
              and d["shipping_address"]["full_name"] == "T"
              and d["shipping_address"]["line1"] == "1 Main St"
              and o_db.shipping_address["city"] == "LA"
              and o_db.shipping_address["state"] == "CA", d)
        detail = ev_detail(s, o_prep.id, "address_updated")
        check("timeline address_updated 存旧值摘要（old.city=SF / new.city=LA）",
              detail is not None and detail["old"] == {"city": "SF", "zip": "94110"}
              and detail["new"] == {"city": "LA", "zip": "90001"}, detail)
        check("改地址审计落库",
              s.query(AdminLog).filter(AdminLog.action == "update_address",
                                       AdminLog.entity == "order",
                                       AdminLog.entity_id == o_prep.id).count() == 1)
        r = client.put("/api/admin/trade/orders/FLW26DONE0002/address", headers=H,
                       json={"city": "LA"})
        check("已发货（status=3）改地址 → 409 order already shipped",
              r.status_code == 409 and r.json()["detail"] == "order already shipped",
              (r.status_code, r.json().get("detail")))
        r = client.put("/api/admin/trade/orders/FLW26PREP002/address", headers=H,
                       json={})
        check("空 body 改地址 → 200 返回现址不落 timeline",
              r.status_code == 200 and r.json()["shipping_address"]["city"] == "SF"
              and (s.query(OrderTimeline)
                   .filter(OrderTimeline.order_id == o_pend.id,
                           OrderTimeline.event == "address_updated").count() == 0),
              r.text[:120])
        r = client.put("/api/admin/trade/orders/NOPE26ADDR99/address", headers=H,
                       json={"city": "LA"})
        check("未知订单改地址 → 404", r.status_code == 404, r.status_code)

        # ===== 3. 换货负差价退款：complete 退 |diff| 且防重复 =====
        cat = Category(slug="flow-cat", name="Flow Cat")
        s.add(cat)
        s.flush()
        p_ex = Product(slug="flow-ex", title="Flow Ex", category_id=cat.id, status=1,
                       hero_image="https://img/e.jpg", price_min=800, price_max=1000)
        s.add(p_ex)
        s.flush()
        v_old = Variant(product_id=p_ex.id, sku="FLW-EX-OLD", option1_value="Short",
                        option2_value="24pcs", price=1000, stock=10)
        v_new = Variant(product_id=p_ex.id, sku="FLW-EX-NEW", option1_value="Mini",
                        option2_value="12pcs", price=800, stock=6)
        s.add_all([v_old, v_new])
        s.flush()
        o_neg, it_neg = make_order(s, "FLW26EXNEG001", [(v_old.id, 1, 1000)])
        s.add(Payment(order_id=o_neg.id, stripe_payment_intent="PI_FLOWNEG",
                      amount=1000, status=1, refunded_amount=0))
        s.add(Exchange(exchange_no="FLW26EXNEG01", order_id=o_neg.id,
                       order_item_id=it_neg[0].id, old_variant_id=v_old.id,
                       new_variant_id=v_new.id, qty=1, price_diff=-200, status=1))
        s.commit()
        r = client.post("/api/admin/trade/exchanges/FLW26EXNEG01/ship", headers=H,
                        json={"carrier": "usps", "tracking_no": "9400FLWNEG1"})
        check("负差价换货 ship 1→3", r.status_code == 200 and r.json()["status"] == 3,
              r.text[:120])
        s.expire_all()
        stock_old_before = s.get(Variant, v_old.id).stock
        r = client.post("/api/admin/trade/exchanges/FLW26EXNEG01/complete", headers=H)
        d = r.json()
        s.expire_all()
        pay_neg = (s.query(Payment).filter(Payment.order_id == o_neg.id)
                   .order_by(Payment.id.desc()).first())
        check("complete 3→4 + 负差价退 200 落账（Payment 部分退 4 / refunded=200）"
              " + 旧变体回补",
              r.status_code == 200 and d["status"] == 4 and d["diff_refund"] == 200
              and pay_neg.status == 4 and pay_neg.refunded_amount == 200
              and s.get(Variant, v_old.id).stock == stock_old_before + 1
              and s.get(OrderItem, it_neg[0].id).exchanged_qty == 1, d)
        marker = ev_detail(s, o_neg.id, "exchange_diff_refunded")
        refund_ev = ev_detail(s, o_neg.id, "refund_issued")
        check("timeline exchange_diff_refunded 标记 + refund_issued 账务事件",
              marker == {"exchange_no": "FLW26EXNEG01", "amount": 200, "price_diff": -200}
              and refund_ev is not None and refund_ev["amount"] == 200
              and "exchange_diff:FLW26EXNEG01" in refund_ev["reason"],
              (marker, refund_ev))
        r = client.post("/api/admin/trade/exchanges/FLW26EXNEG01/complete", headers=H)
        s.expire_all()
        pay_neg = (s.query(Payment).filter(Payment.order_id == o_neg.id)
                   .order_by(Payment.id.desc()).first())
        check("重复 complete → 409 且退款不重复（refunded 仍 200）",
              r.status_code == 409 and pay_neg.refunded_amount == 200,
              (r.status_code, pay_neg.refunded_amount))

        # 可退余不足（remaining 100 < 200）：绕过校验单独走 Payment 账务落库，
        # 钳制到剩余可退 100 —— 不再把 refunded_amount 记超实付（P1-11）
        o_by, it_by = make_order(s, "FLW26EXBYP001", [(v_old.id, 1, 1000)])
        s.add(Payment(order_id=o_by.id, stripe_payment_intent="PI_FLOWBYP",
                      amount=1000, status=4, refunded_amount=900))
        s.add(Exchange(exchange_no="FLW26EXBYP01", order_id=o_by.id,
                       order_item_id=it_by[0].id, old_variant_id=v_old.id,
                       new_variant_id=v_new.id, qty=1, price_diff=-200, status=3))
        s.commit()
        r = client.post("/api/admin/trade/exchanges/FLW26EXBYP01/complete", headers=H)
        d = r.json()
        s.expire_all()
        pay_by = (s.query(Payment).filter(Payment.order_id == o_by.id)
                  .order_by(Payment.id.desc()).first())
        check("可退余不足绕过校验：钳制到剩余可退（refunded 900→1000，仍部分退 4，不驱动订单状态）",
              r.status_code == 200 and d["diff_refund"] == 100
              and pay_by.refunded_amount == 1000
              and pay_by.status == 4
              and s.query(Order).filter(Order.order_no == "FLW26EXBYP001").first().status == 1,
              (r.status_code, pay_by.refunded_amount))

        # 无可退 Payment（全额已退 status=3）：降级跳过退款但 complete 不阻断
        o_nr, it_nr = make_order(s, "FLW26EXNOR001", [(v_old.id, 1, 1000)])
        s.add(Payment(order_id=o_nr.id, stripe_payment_intent="PI_FLOWNOR",
                      amount=1000, status=3, refunded_amount=1000))
        s.add(Exchange(exchange_no="FLW26EXNOR01", order_id=o_nr.id,
                       order_item_id=it_nr[0].id, old_variant_id=v_old.id,
                       new_variant_id=v_new.id, qty=1, price_diff=-200, status=3))
        s.commit()
        r = client.post("/api/admin/trade/exchanges/FLW26EXNOR01/complete", headers=H)
        check("无款可退降级：complete 成功且 diff_refund=0",
              r.status_code == 200 and r.json()["diff_refund"] == 0, r.text[:120])

        # ===== 4. RMA 退款金额可调：全额→5 / 部分→7 / 超限拒 =====
        def make_rma_order(no):
            o, its = make_order(s, no, [(v_old.id, 1, 1000)], status=4)
            s.add(Payment(order_id=o.id, stripe_payment_intent=f"PI_{no}",
                          amount=1000, status=1, refunded_amount=0))
            s.flush()
            rma = Rma(rma_no=f"RMA{no[3:]}", order_id=o.id, order_item_id=its[0].id,
                      qty=1, reason=3, status=4)
            s.add(rma)
            s.commit()
            return o, its, rma

        o_rf, it_rf, rma_full = make_rma_order("FLW26RMAF0001")
        r = client.post("/api/admin/trade/rmas/RMA26RMAF0001/refund", headers=H)
        d = r.json()
        s.expire_all()
        pay_rf = (s.query(Payment).filter(Payment.order_id == o_rf.id)
                  .order_by(Payment.id.desc()).first())
        check("RMA 缺省退款（折算全额 1000）→ status=5 / Payment 全退 / 订单 REFUNDED(9)",
              r.status_code == 200 and d["refund_amount"] == 1000
              and d["status"] == 5 and d["partial"] is False
              and pay_rf.status == 3 and pay_rf.refunded_amount == 1000
              and s.query(Order).filter(Order.order_no == "FLW26RMAF0001").first().status == 9
              and s.get(OrderItem, it_rf[0].id).refunded_qty == 1, d)
        r = client.post("/api/admin/trade/rmas/RMA26RMAF0001/refund", headers=H)
        check("已退款 RMA 重复退款 → 409 rma_not_refundable:5",
              r.status_code == 409 and r.json()["detail"] == "rma_not_refundable:5",
              (r.status_code, r.json().get("detail")))

        o_rp, it_rp, rma_part = make_rma_order("FLW26RMAP0001")
        r = client.post("/api/admin/trade/rmas/RMA26RMAP0001/refund", headers=H,
                        json={"amount_cents": 400})
        d = r.json()
        s.expire_all()
        pay_rp = (s.query(Payment).filter(Payment.order_id == o_rp.id)
                  .order_by(Payment.id.desc()).first())
        check("RMA 部分退款 400 → status=7 / Payment 部分退(4) / 订单状态不变(4)",
              r.status_code == 200 and d["refund_amount"] == 400
              and d["status"] == 7 and d["partial"] is True
              and pay_rp.status == 4 and pay_rp.refunded_amount == 400
              and s.query(Order).filter(Order.order_no == "FLW26RMAP0001").first().status == 4
              and s.query(Rma).filter(Rma.rma_no == "RMA26RMAP0001").first().refund_amount == 400,
              d)

        o_ro, _it_ro, _rma_over = make_rma_order("FLW26RMAO0001")
        r = client.post("/api/admin/trade/rmas/RMA26RMAO0001/refund", headers=H,
                        json={"amount_cents": 1500})
        check("RMA 超折算额（1500>1000）→ 409 invalid refund amount",
              r.status_code == 409 and r.json()["detail"] == "invalid refund amount",
              (r.status_code, r.json().get("detail")))
        r = client.post("/api/admin/trade/rmas/RMA26RMAO0001/refund", headers=H,
                        json={"amount_cents": 0})
        check("RMA amount_cents=0 → 422（pydantic ge=1）", r.status_code == 422, r.status_code)
        r = client.post("/api/admin/trade/rmas/RMA26RMAO0001/refund", headers=H,
                        json={"amount_cents": 1000})
        check("RMA amount_cents=折算额（等于）→ status=5 全额",
              r.status_code == 200 and r.json()["status"] == 5, r.text[:120])

        # ===== 5. 工单列表最后消息（last_message_at / last_sender）=====
        now = utcnow()
        tk1 = Ticket(ticket_no="FLW26TK0001", email="a@glow.test", category=1,
                     subject="has reply", status=1)
        tk2 = Ticket(ticket_no="FLW26TK0002", email="b@glow.test", category=2,
                     subject="user only", status=0)
        tk3 = Ticket(ticket_no="FLW26TK0003", email="c@glow.test", category=3,
                     subject="no message", status=0)
        s.add_all([tk1, tk2, tk3])
        s.flush()
        m1 = TicketMessage(ticket_id=tk1.id, sender=1, content="help",
                           created_at=now - timedelta(minutes=10))
        m2 = TicketMessage(ticket_id=tk1.id, sender=2, content="on it",
                           created_at=now - timedelta(minutes=5))
        m3 = TicketMessage(ticket_id=tk2.id, sender=1, content="question",
                           created_at=now - timedelta(minutes=3))
        s.add_all([m1, m2, m3])
        s.commit()
        check("工单列表端点需要鉴权",
              client.get("/api/admin/ops/tickets").status_code == 401)
        r = client.get("/api/admin/ops/tickets", headers=H,
                       params={"size": 50, "q": "glow.test"})
        d = r.json()
        by_no = {i["ticket_no"]: i for i in d["items"]}
        check("工单列表含 last_sender（客服最后回复=2 / 仅客户=1 / 无消息=None）",
              r.status_code == 200
              and by_no["FLW26TK0001"]["last_sender"] == 2
              and by_no["FLW26TK0002"]["last_sender"] == 1
              and by_no["FLW26TK0003"]["last_sender"] is None, d.get("total"))
        check("工单列表 last_message_at 对齐最后一条消息时间",
              by_no["FLW26TK0001"]["last_message_at"] == m2.created_at.isoformat()
              and by_no["FLW26TK0002"]["last_message_at"] == m3.created_at.isoformat()
              and by_no["FLW26TK0003"]["last_message_at"] is None,
              (by_no["FLW26TK0001"]["last_message_at"], m2.created_at.isoformat()))
        r = client.post("/api/admin/ops/tickets/FLW26TK0002/reply", headers=H,
                        json={"content": "admin here"})
        check("单票响应也带 last_sender（回复后=2）",
              r.status_code == 200 and r.json()["last_sender"] == 2, r.text[:150])

        # ===== 6. 变体删除：无引用成功 / 有引用 409 =====
        p_del = Product(slug="flow-del", title="Flow Del", category_id=cat.id, status=1,
                        hero_image="https://img/d.jpg", price_min=500, price_max=900)
        s.add(p_del)
        s.flush()
        v_free = Variant(product_id=p_del.id, sku="FLW-DEL-FREE", option1_value="A",
                         option2_value="1", price=500, stock=7)
        v_img = Variant(product_id=p_del.id, sku="FLW-DEL-IMG", option1_value="B",
                        option2_value="1", price=600, stock=7)
        v_ord = Variant(product_id=p_del.id, sku="FLW-DEL-ORD", option1_value="C",
                        option2_value="1", price=700, stock=7)
        v_ex = Variant(product_id=p_del.id, sku="FLW-DEL-EX", option1_value="D",
                       option2_value="1", price=800, stock=7)
        v_cart = Variant(product_id=p_del.id, sku="FLW-DEL-CART", option1_value="E",
                         option2_value="1", price=900, stock=7)
        v_rma = Variant(product_id=p_del.id, sku="FLW-DEL-RMA", option1_value="F",
                        option2_value="1", price=900, stock=7)
        v_sn = Variant(product_id=p_del.id, sku="FLW-DEL-SN", option1_value="G",
                       option2_value="1", price=900, stock=0)
        s.add_all([v_free, v_img, v_ord, v_ex, v_cart, v_rma, v_sn])
        s.flush()
        s.add(VariantImage(variant_id=v_img.id, image_url="https://img/v1.jpg", sort_order=0))
        s.add(StockNotification(variant_id=v_sn.id, email="watcher@glow.test"))
        o_d, it_d = make_order(s, "FLW26DELO0001", [(v_ord.id, 1, 700)], status=5)
        o_r, it_r = make_order(s, "FLW26DELR0001", [(v_rma.id, 1, 900)], status=4)
        s.add(Exchange(exchange_no="FLW26DELEX01", order_id=o_d.id,
                       order_item_id=it_d[0].id, old_variant_id=v_ord.id,
                       new_variant_id=v_ex.id, qty=1, price_diff=100, status=4))
        s.add(Rma(rma_no="RMA26DELR0001", order_id=o_r.id, order_item_id=it_r[0].id,
                  qty=1, reason=3, status=5))
        s.add(Cart(session_id="tok-flow-del",
                   items=[{"variantId": v_cart.id, "qty": 1}]))
        s.commit()
        check("变体删除端点需要鉴权",
              client.delete(f"/api/admin/catalog/variants/{v_free.id}").status_code == 401)
        free_id, img_id, sn_id = v_free.id, v_img.id, v_sn.id
        ord_id, ex_id, cart_id, rma_id = v_ord.id, v_ex.id, v_cart.id, v_rma.id
        r = client.delete(f"/api/admin/catalog/variants/{free_id}", headers=H)
        s.expire_all()
        check("无引用变体删除 → 200 且物理删除 + 审计",
              r.status_code == 200 and r.json() == {"ok": True}
              and s.get(Variant, free_id) is None
              and s.query(AdminLog).filter(AdminLog.action == "delete",
                                           AdminLog.entity == "variant",
                                           AdminLog.entity_id == free_id).count() == 1,
              r.text[:120])
        r = client.delete(f"/api/admin/catalog/variants/{img_id}", headers=H)
        s.expire_all()
        check("删变体级联清变体图",
              r.status_code == 200
              and s.query(VariantImage).filter(
                  VariantImage.variant_id == img_id).count() == 0, r.text[:120])
        r = client.delete(f"/api/admin/catalog/variants/{sn_id}", headers=H)
        s.expire_all()
        check("删变体级联清到货订阅",
              r.status_code == 200
              and s.query(StockNotification).filter(
                  StockNotification.variant_id == sn_id).count() == 0, r.text[:120])
        for vid, label in ((ord_id, "order_items 引用"), (ex_id, "exchange 引用"),
                           (cart_id, "购物车引用"), (rma_id, "RMA 引用")):
            r = client.delete(f"/api/admin/catalog/variants/{vid}", headers=H)
            check(f"{label} → 409 variant in use（行保留）",
                  r.status_code == 409 and r.json()["detail"] == "variant in use"
                  and s.get(Variant, vid) is not None,
                  (r.status_code, r.json().get("detail")))
        r = client.delete("/api/admin/catalog/variants/999999", headers=H)
        check("未知变体删除 → 404", r.status_code == 404, r.status_code)

        # ===== 7. low_stock_count 口径：stock <= max(safety_stock, 8) 且 is_active =====
        p_low = Product(slug="flow-low", title="Flow Low", category_id=cat.id, status=1,
                        hero_image="https://img/l.jpg", price_min=100, price_max=300)
        s.add(p_low)
        s.flush()
        s.add_all([
            # safety=0 库存 8 → 8<=max(0,8)=8 计入；库存 9 → 不计入
            Variant(product_id=p_low.id, sku="FLW-LOW-A", option1_value="A",
                    option2_value="1", price=100, stock=8, safety_stock=0),
            # safety=20 库存 15 → 15<=max(20,8)=20 计入
            Variant(product_id=p_low.id, sku="FLW-LOW-B", option1_value="B",
                    option2_value="1", price=200, stock=15, safety_stock=20),
            Variant(product_id=p_low.id, sku="FLW-LOW-C", option1_value="C",
                    option2_value="1", price=300, stock=9, safety_stock=0),
            # 停用变体不计入
            Variant(product_id=p_low.id, sku="FLW-LOW-D", option1_value="D",
                    option2_value="1", price=300, stock=1, safety_stock=0, is_active=0),
        ])
        s.commit()
        r = client.get("/api/admin/catalog/products", headers=H,
                       params={"q": "flow-low"})
        d = r.json()
        item = next(i for i in d["items"] if i["slug"] == "flow-low")
        check("low_stock_count 口径 max(safety,8)：8/15 计入、9 与停用不计入",
              r.status_code == 200 and item["low_stock_count"] == 2
              and item["variant_count"] == 3 and item["total_stock"] == 32,
              (item.get("low_stock_count"), item.get("variant_count")))

        # ===== 8. 到货通知名单 stock-notifies =====
        p_sn = Product(slug="flow-sn", title="Flow SN", category_id=cat.id, status=1,
                       hero_image="https://img/s.jpg", price_min=400, price_max=400)
        s.add(p_sn)
        s.flush()
        v_sn1 = Variant(product_id=p_sn.id, sku="FLW-SN-1", option1_value="A",
                        option2_value="1", price=400, stock=0)
        v_sn2 = Variant(product_id=p_sn.id, sku="FLW-SN-2", option1_value="B",
                        option2_value="1", price=400, stock=0)
        s.add_all([v_sn1, v_sn2])
        s.flush()
        base = utcnow()
        s.add_all([
            StockNotification(variant_id=v_sn1.id, email="old@glow.test",
                              created_at=base - timedelta(hours=2)),
            StockNotification(variant_id=v_sn1.id, email="mid@glow.test",
                              created_at=base - timedelta(hours=1)),
            StockNotification(variant_id=v_sn2.id, email="new@glow.test",
                              created_at=base),
        ])
        s.commit()
        check("stock-notifies 需要鉴权",
              client.get("/api/admin/catalog/stock-notifies").status_code == 401)
        r = client.get("/api/admin/catalog/stock-notifies", headers=H)
        d = r.json()
        check("stock-notifies 列表（created_at 倒序 + email/product/variant 结构）",
              r.status_code == 200 and d["total"] == 3 and len(d["items"]) == 3
              and [i["email"] for i in d["items"]] == ["new@glow.test", "mid@glow.test",
                                                       "old@glow.test"]
              and d["items"][0]["variant"]["id"] == v_sn2.id
              and d["items"][0]["variant"]["sku"] == "FLW-SN-2"
              and d["items"][0]["product"]["slug"] == "flow-sn"
              and "created_at" in d["items"][0], d.get("total"))
        r = client.get("/api/admin/catalog/stock-notifies", headers=H,
                       params={"variant_id": v_sn1.id})
        d = r.json()
        check("stock-notifies variant_id 过滤 → 2 条",
              r.status_code == 200 and d["total"] == 2
              and {i["email"] for i in d["items"]} == {"old@glow.test", "mid@glow.test"},
              d.get("total"))
        r = client.get("/api/admin/catalog/stock-notifies", headers=H,
                       params={"product_id": p_sn.id, "page": 1, "size": 2})
        d = r.json()
        check("stock-notifies product_id 过滤 + 分页（size=2 → pages=2）",
              r.status_code == 200 and d["total"] == 3 and len(d["items"]) == 2
              and d["pages"] == 2 and d["page"] == 1, d)
        check("stock-notifies size>100 → 422",
              client.get("/api/admin/catalog/stock-notifies", headers=H,
                         params={"size": 101}).status_code == 422)

        # ===== 9. catalog 列表分页补 pages =====
        r = client.get("/api/admin/catalog/products", headers=H,
                       params={"q": "flow-", "page": 1, "size": 2})
        d = r.json()
        check("admin products 列表补 pages（ceil(total/size)）",
              r.status_code == 200 and d["total"] >= 3
              and d["pages"] == (d["total"] + 1) // 2
              and d["pages"] >= 2, (d.get("total"), d.get("pages")))
        r = client.get("/api/admin/catalog/products", headers=H,
                       params={"q": "flow-", "page": 1, "size": 100})
        d2 = r.json()
        check("admin products size=100 → 单页 pages=1",
              d2["pages"] == 1 and len(d2["items"]) == d2["total"], d2.get("pages"))
        r = client.get("/api/admin/catalog/variants", headers=H,
                       params={"q": "FLW-LOW", "page": 1, "size": 3})
        d = r.json()
        check("admin variants 列表补 pages（ceil(total/size)）",
              r.status_code == 200 and d["total"] == 4 and d["pages"] == 2
              and len(d["items"]) == 3, (d.get("total"), d.get("pages")))

        s.close()

    print(f"\n{PASSED} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed:", FAILED)
        return 1
    return 0


def test_admin_flow_ext():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
