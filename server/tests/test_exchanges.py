"""智能体 A 自测 —— 换货 exchanges 全流程：创建校验矩阵 / price_diff 三态 / 列表详情 /
后台状态机（approve 分流 → mark-paid → ship 扣库存+shipment → complete 回补+exchanged_qty）/
库存与流水断言 / timeline 事件 / 401·403 守卫。
（GM_DB=sqlite:///test_ex.sqlite 独立库；BigInteger 垫片同 test_payments.py）"""

import os
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_ex.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
# 本套件对 /api/exchanges 打满 20+ 次功能用例，临时调高该规则阈值避免误触限流
os.environ["GM_RATE_RULES"] = '{"/api/exchanges": 100}'
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient

from app.core.db import SessionLocal, utcnow
from app.core.security import create_token, hash_password
from app.main import app
from app.models import (
    AdminLog, Category, Exchange, Order, OrderItem, OrderTimeline, Product,
    Shipment, StockMovement, User, Variant,
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


def make_order(s, no, lines, *, user_id=None, email="ex@glow.test", status=1,
               paid_days_ago=0):
    placed = utcnow() - timedelta(days=paid_days_ago + 1)
    o = Order(order_no=no, user_id=user_id, email=email, status=status,
              subtotal=sum(p * q for _v, q, p in lines),
              grand_total=sum(p * q for _v, q, p in lines),
              shipping_address=ADDR, placed_at=placed,
              paid_at=placed + timedelta(hours=1))
    s.add(o)
    s.flush()
    items = []
    for vid, qty, price in lines:
        it = OrderItem(order_id=o.id, variant_id=vid, product_slug="ex-gel",
                       title_snapshot="Ex Gel", qty=qty, unit_price=price,
                       subtotal=price * qty)
        s.add(it)
        items.append(it)
    s.flush()
    return o, items


try:
    with TestClient(app) as client:
        s = SessionLocal()

        cat = Category(slug="ex-cat", name="Ex Cat")
        s.add(cat)
        s.flush()
        p = Product(slug="ex-gel", title="Ex Gel", category_id=cat.id, status=1,
                    hero_image="https://img/e.jpg", price_min=800, price_max=1500)
        s.add(p)
        s.flush()
        v_old = Variant(product_id=p.id, sku="EX-OLD", option1_value="Short",
                        option2_value="24pcs", price=1000, stock=10)
        v_hi = Variant(product_id=p.id, sku="EX-HI", option1_value="Long",
                       option2_value="24pcs", price=1500, stock=8)
        v_lo = Variant(product_id=p.id, sku="EX-LO", option1_value="Mini",
                       option2_value="12pcs", price=800, stock=6)
        v_same = Variant(product_id=p.id, sku="EX-SAME", option1_value="Wide",
                         option2_value="24pcs", price=1000, stock=5)
        v_off = Variant(product_id=p.id, sku="EX-OFF", option1_value="Off",
                        option2_value="24pcs", price=900, stock=5, is_active=0)
        v_zero = Variant(product_id=p.id, sku="EX-ZERO", option1_value="Zero",
                         option2_value="24pcs", price=900, stock=0)
        s.add_all([v_old, v_hi, v_lo, v_same, v_off, v_zero])
        s.flush()
        emma = User(email="emma@glow.test", password_hash=hash_password("x"),
                    name="Emma", role=0)
        bob = User(email="bob@glow.test", password_hash=hash_password("x"),
                   name="Bob", role=0)
        ops = User(email="ops@glow.test", password_hash=hash_password("x"),
                   name="Ops", role=9)
        s.add_all([emma, bob, ops])
        s.flush()

        o_ok, items_ok = make_order(s, "EX260816OK01", [(v_old.id, 2, 1000)],
                                    user_id=emma.id, email="emma@glow.test")
        o_guest, items_guest = make_order(s, "EX260816GUEST", [(v_old.id, 1, 1000)],
                                          email="guest@glow.test")
        o_old, items_old = make_order(s, "EX260816OLD01", [(v_old.id, 1, 1000)],
                                      user_id=emma.id, paid_days_ago=45)
        o_gone, items_gone = make_order(s, "EX260816GONE1", [(v_old.id, 1, 1000)],
                                        user_id=emma.id)
        items_gone[0].refunded_qty = 1
        o_used, items_used = make_order(s, "EX260816USED1", [(v_old.id, 1, 1000)],
                                        user_id=emma.id)
        items_used[0].exchanged_qty = 1
        s.commit()

        H_EMMA = {"Authorization": f"Bearer {create_token(emma.id, emma.role)}"}
        H_BOB = {"Authorization": f"Bearer {create_token(bob.id, bob.role)}"}
        H_OPS = {"Authorization": f"Bearer {create_token(ops.id, ops.role)}"}

        def ev_count(order_id, event):
            s.expire_all()
            return (s.query(OrderTimeline)
                     .filter(OrderTimeline.order_id == order_id,
                             OrderTimeline.event == event).count())

        print("== 创建：校验矩阵 ==")
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816OK01", "order_item_id": items_ok[0].id,
            "new_variant_id": v_hi.id, "reason": "want longer"})
        d = r.json()
        check("本人创建换货 201 → EX+yymmdd+4hex / status 0 / diff 贵 500",
              r.status_code == 201 and d["exchange_no"].startswith("EX")
              and len(d["exchange_no"]) == 12 and d["status"] == 0
              and d["price_diff"] == 500
              and d["status_label"] == "申请"
              and d["old_variant"]["id"] == v_old.id
              and d["new_variant"]["id"] == v_hi.id, d)
        ex_hi_no = d["exchange_no"]
        check("创建 timeline exchange_created（含 price_diff/reason）",
              ev_count(o_ok.id, "exchange_created") == 1
              and s.query(OrderTimeline).filter(
                  OrderTimeline.order_id == o_ok.id,
                  OrderTimeline.event == "exchange_created").first().detail["reason"] == "want longer")

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816OK01", "order_item_id": items_old[0].id,
            "new_variant_id": v_hi.id})
        check("item 不属于该单 → 404 order_item_not_found",
              r.status_code == 404 and "order_item_not_found" in r.text, r.text)

        r = client.post("/api/exchanges", json={
            "order_no": "EX260816GUEST", "order_item_id": items_guest[0].id,
            "new_variant_id": v_hi.id, "email": "guest@glow.test"})
        d = r.json()
        check("游客 email 双因子创建 → 201 diff 贵",
              r.status_code == 201 and d["price_diff"] == 500, d)
        ex_guest_no = d["exchange_no"]

        r = client.post("/api/exchanges", json={
            "order_no": "EX260816GUEST", "order_item_id": items_guest[0].id,
            "new_variant_id": v_hi.id, "email": "evil@glow.test"})
        check("游客错 email → 404", r.status_code == 404, r.text)

        r = client.post("/api/exchanges", json={
            "order_no": "EX260816GUEST", "order_item_id": items_guest[0].id,
            "new_variant_id": v_hi.id})
        check("游客无 email 无 token → 401", r.status_code == 401, r.text)

        r = client.post("/api/exchanges", headers=H_BOB, json={
            "order_no": "EX260816OK01", "order_item_id": items_ok[0].id,
            "new_variant_id": v_hi.id})
        check("他人订单（登录无 email）→ 404", r.status_code == 404, r.text)

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816OLD01", "order_item_id": items_old[0].id,
            "new_variant_id": v_hi.id})
        check("窗口外（45 天）→ 409 return_window_closed",
              r.status_code == 409 and "return_window_closed" in r.text, r.text)

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816GONE1", "order_item_id": items_gone[0].id,
            "new_variant_id": v_hi.id})
        check("可换量 0（已全退）→ 409 qty_exceeds_available:0",
              r.status_code == 409 and "qty_exceeds_available:0" in r.text, r.text)

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816USED1", "order_item_id": items_used[0].id,
            "new_variant_id": v_hi.id})
        check("可换量 0（已换过）→ 409 qty_exceeds_available:0",
              r.status_code == 409 and "qty_exceeds_available:0" in r.text, r.text)

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816OK01", "order_item_id": items_ok[0].id,
            "new_variant_id": v_off.id})
        check("禁用变体 → 404 variant_not_found",
              r.status_code == 404 and "variant_not_found" in r.text, r.text)

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816OK01", "order_item_id": items_ok[0].id,
            "new_variant_id": v_zero.id})
        check("零库存变体 → 409 variant_out_of_stock",
              r.status_code == 409 and "variant_out_of_stock" in r.text, r.text)

        print("== price_diff 三态（便宜 / 同价）==")
        o_lo, items_lo = make_order(s, "EX260816LO001", [(v_old.id, 1, 1000)],
                                    user_id=emma.id, email="emma@glow.test")
        s.commit()
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816LO001", "order_item_id": items_lo[0].id,
            "new_variant_id": v_lo.id})
        d = r.json()
        check("便宜变体 → diff -200", r.status_code == 201 and d["price_diff"] == -200, d)
        ex_lo_no = d["exchange_no"]

        o_eq, items_eq = make_order(s, "EX260816EQ001", [(v_old.id, 1, 1000)],
                                    user_id=emma.id, email="emma@glow.test")
        s.commit()
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816EQ001", "order_item_id": items_eq[0].id,
            "new_variant_id": v_same.id})
        d = r.json()
        check("同价变体 → diff 0", r.status_code == 201 and d["price_diff"] == 0, d)
        ex_eq_no = d["exchange_no"]

        print("== 列表与详情 ==")
        r = client.get("/api/exchanges", headers=H_EMMA)
        d = r.json()
        nos = {x["exchange_no"] for x in d["items"]}
        check("本人列表含 3 单换货（游客单不可见）+ item 快照 + 新旧变体标题 + 状态中文",
              r.status_code == 200 and len(d["items"]) == 3
              and {ex_hi_no, ex_lo_no, ex_eq_no} == nos
              and ex_guest_no not in nos
              and all(x["item"]["title"] == "Ex Gel" for x in d["items"])
              and all(x["old_variant"]["title"].startswith("Ex Gel") for x in d["items"])
              and all(x["status_label"] in {"申请", "批准", "待差价支付", "已发货", "完成", "拒绝"}
                      for x in d["items"]), nos)

        r = client.get("/api/exchanges", params={"email": "guest@glow.test"})
        d = r.json()
        check("游客 ?email= 列表只看本人单",
              r.status_code == 200 and [x["exchange_no"] for x in d["items"]] == [ex_guest_no], d)

        r = client.get("/api/exchanges")
        check("列表无凭据 → 401", r.status_code == 401, r.text)

        r = client.get(f"/api/exchanges/{ex_hi_no}", headers=H_EMMA)
        check("本人详情 200 含 price_diff",
              r.status_code == 200 and r.json()["price_diff"] == 500, r.text[:120])

        r = client.get(f"/api/exchanges/{ex_hi_no}", headers=H_BOB)
        check("他人登录查详情 → 404", r.status_code == 404, r.text[:120])

        r = client.get(f"/api/exchanges/{ex_guest_no}",
                       params={"email": "guest@glow.test"})
        check("游客详情 email 双因子 → 200",
              r.status_code == 200 and r.json()["exchange_no"] == ex_guest_no, r.text[:120])

        r = client.get(f"/api/exchanges/{ex_guest_no}",
                       params={"email": "evil@glow.test"})
        check("游客详情错 email → 404", r.status_code == 404, r.text[:120])

        r = client.get(f"/api/exchanges/{ex_hi_no}")
        check("详情无凭据 → 401", r.status_code == 401, r.text[:120])

        print("== 订单详情纯加法键 ==")
        r = client.get("/api/orders/EX260816USED1", headers=H_EMMA)
        it = r.json()["items"][0]
        check("订单详情 items 含 refunded_qty + exchanged_qty",
              r.status_code == 200 and it["refunded_qty"] == 0 and it["exchanged_qty"] == 1, it)

        print("== 后台：队列与守卫 ==")
        r = client.get("/api/admin/trade/exchanges", headers=H_OPS)
        d = r.json()
        check("后台队列 4 条（含 email/商品/新旧变体/diff/状态/分页）",
              r.status_code == 200 and d["total"] == 4 and d["page"] == 1
              and all("email" in x and "item" in x and "old_variant" in x
                      and "new_variant" in x and "price_diff" in x for x in d["items"]), d.get("total"))

        r = client.get("/api/admin/trade/exchanges", headers=H_OPS,
                       params={"status": 0})
        check("status=0 过滤 → 4 条待审",
              r.status_code == 200 and r.json()["total"] == 4, r.json().get("total"))

        r = client.get("/api/admin/trade/exchanges")
        check("后台队列无 token → 401", r.status_code == 401, r.text[:120])

        r = client.get("/api/admin/trade/exchanges", headers=H_EMMA)
        check("普通用户访问后台 → 403", r.status_code == 403, r.text[:120])

        print("== 后台：状态机 ==")
        r = client.post(f"/api/admin/trade/exchanges/{ex_hi_no}/approve", headers=H_OPS)
        check("approve diff>0 → 2 待差价 + timeline exchange_approved",
              r.status_code == 200 and r.json()["status"] == 2
              and ev_count(o_ok.id, "exchange_approved") == 1, r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_eq_no}/approve", headers=H_OPS)
        check("approve diff=0 → 1 直批",
              r.status_code == 200 and r.json()["status"] == 1, r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_lo_no}/approve", headers=H_OPS)
        check("approve diff<0 → 1 直批",
              r.status_code == 200 and r.json()["status"] == 1, r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_hi_no}/approve", headers=H_OPS)
        check("重复 approve → 409", r.status_code == 409, r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_hi_no}/mark-paid", headers=H_OPS)
        check("mark-paid 2→1 + timeline 记 diff 500",
              r.status_code == 200 and r.json()["status"] == 1
              and ev_count(o_ok.id, "exchange_diff_paid") == 1
              and s.query(OrderTimeline).filter(
                  OrderTimeline.order_id == o_ok.id,
                  OrderTimeline.event == "exchange_diff_paid").first().detail["price_diff"] == 500,
              r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_hi_no}/mark-paid", headers=H_OPS)
        check("mark-paid 非 2 态 → 409", r.status_code == 409, r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_guest_no}/reject",
                        headers=H_OPS, json={"reason": "out of season"})
        check("reject 0→5 + timeline exchange_rejected",
              r.status_code == 200 and r.json()["status"] == 5
              and ev_count(o_guest.id, "exchange_rejected") == 1, r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_guest_no}/reject", headers=H_OPS)
        check("重复 reject → 409", r.status_code == 409, r.text[:120])

        print("== 后台：ship 扣库存 + shipment ==")
        s.expire_all()
        stock_hi_before = s.get(Variant, v_hi.id).stock
        r = client.post(f"/api/admin/trade/exchanges/{ex_hi_no}/ship", headers=H_OPS,
                        json={"carrier": "usps", "tracking_no": "9400111EX0001"})
        d = r.json()
        s.expire_all()
        ship_mv = (s.query(StockMovement)
                   .filter(StockMovement.variant_id == v_hi.id,
                           StockMovement.type == 3,
                           StockMovement.ref_type == "exchange").all())
        ship_ex = s.query(Exchange).filter(Exchange.exchange_no == ex_hi_no).first()
        shipment = s.query(Shipment).filter(Shipment.id == ship_ex.shipment_id).first()
        check("ship 1→3 + 新变体库存 -1 + type=3 流水 ref exchange",
              r.status_code == 200 and d["status"] == 3 and d["shipment_no"].startswith("SP")
              and s.get(Variant, v_hi.id).stock == stock_hi_before - 1
              and len(ship_mv) == 1 and ship_mv[0].change == -1
              and ship_mv[0].ref_id == ship_ex.id
              and ev_count(o_ok.id, "exchange_shipped") == 1, d)

        check("shipment item_json=[{orderItemId,qty:1}] + carrier/tracking",
              shipment is not None and shipment.item_json == [
                  {"orderItemId": items_ok[0].id, "qty": 1}]
              and shipment.carrier == "usps"
              and shipment.tracking_no == "9400111EX0001", 
              shipment.item_json if shipment else None)

        r = client.post(f"/api/admin/trade/exchanges/{ex_eq_no}/ship", headers=H_OPS,
                        json={"carrier": "usps", "tracking_no": "9400111EX0002"})
        eq_shipped = r.json()
        check("第二单 ship 成功（同价路径）", r.status_code == 200 and eq_shipped["status"] == 3, r.text[:120])

        r = client.post(f"/api/admin/trade/exchanges/{ex_lo_no}/ship", headers=H_OPS,
                        json={"carrier": "ups", "tracking_no": "1ZEXLO"})
        check("LO 单 ship 成功（diff<0 路径也走发货）",
              r.status_code == 200 and r.json()["status"] == 3, r.text[:120])

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816LO001", "order_item_id": items_lo[0].id,
            "new_variant_id": v_hi.id})
        ex_pending_no = r.json()["exchange_no"]
        r = client.post(f"/api/admin/trade/exchanges/{ex_pending_no}/ship", headers=H_OPS,
                        json={"carrier": "usps", "tracking_no": "1ZPENDING"})
        check("未批准（0 态）ship → 409 exchange_not_shippable:0",
              r.status_code == 409 and "exchange_not_shippable:0" in r.text, r.text[:120])

        o_st, items_st = make_order(s, "EX260816STK01", [(v_old.id, 1, 1000)],
                                    user_id=emma.id, email="emma@glow.test")
        s.add(Exchange(exchange_no="EXSTOCK0001", order_id=o_st.id,
                       order_item_id=items_st[0].id, old_variant_id=v_old.id,
                       new_variant_id=v_zero.id, price_diff=-100, status=1))
        s.commit()
        r = client.post("/api/admin/trade/exchanges/EXSTOCK0001/ship", headers=H_OPS,
                        json={"carrier": "usps", "tracking_no": "9400Z"})
        check("零库存 ship → 409 原子扣失败回滚",
              r.status_code == 409 and "variant_out_of_stock" in r.text, r.text[:120])

        print("== 后台：complete 回补旧变体 + exchanged_qty ==")
        s.expire_all()
        stock_old_before = s.get(Variant, v_old.id).stock
        r = client.post(f"/api/admin/trade/exchanges/{ex_hi_no}/complete", headers=H_OPS)
        d = r.json()
        s.expire_all()
        restock_mv = (s.query(StockMovement)
                      .filter(StockMovement.variant_id == v_old.id,
                              StockMovement.type == 5,
                              StockMovement.ref_type == "exchange").all())
        item_after = s.get(OrderItem, items_ok[0].id)
        check("complete 3→4 + 旧变体回补 +1（type=5 ref exchange）+ exchanged_qty+=1",
              r.status_code == 200 and d["status"] == 4 and d["exchanged_qty"] == 1
              and s.get(Variant, v_old.id).stock == stock_old_before + 1
              and len(restock_mv) == 1 and restock_mv[0].change == 1
              and item_after.exchanged_qty == 1
              and ev_count(o_ok.id, "exchange_completed") == 1, d)

        r = client.post(f"/api/admin/trade/exchanges/{ex_hi_no}/complete", headers=H_OPS)
        check("重复 complete → 409", r.status_code == 409, r.text[:120])

        print("== 收尾断言 ==")
        s.expire_all()
        logs = (s.query(AdminLog).filter(AdminLog.entity == "exchange")
                .order_by(AdminLog.id).all())
        check("AdminLog 记录 approve/mark_paid/ship/complete/reject 全链",
              {x.action for x in logs} >= {"exchange_approve", "exchange_mark_paid",
                                           "exchange_ship", "exchange_complete",
                                           "exchange_reject"}, [x.action for x in logs])

        r = client.get("/api/admin/trade/exchanges", headers=H_OPS, params={"status": 4})
        check("队列 status=4 → 1 条已完成",
              r.status_code == 200 and r.json()["total"] == 1
              and r.json()["items"][0]["status_label"] == "完成", r.text[:120])

        r = client.get("/api/admin/trade/exchanges", headers=H_OPS, params={"status": 5})
        check("队列 status=5 → 1 条已拒绝",
              r.status_code == 200 and r.json()["total"] == 1, r.text[:120])

        r = client.get("/api/exchanges", headers=H_EMMA)
        labels = {x["exchange_no"]: x["status_label"] for x in r.json()["items"]}
        check("用户侧状态中文全覆盖（0申请/1批准/3已发货/4完成）",
              labels[ex_pending_no] == "申请" and labels[ex_lo_no] == "已发货"
              and labels[ex_eq_no] == "已发货" and labels[ex_hi_no] == "完成", labels)

        print("== qty=2 全链路（多件换货）==")
        o_q2, items_q2 = make_order(s, "EX260816QTY001", [(v_old.id, 3, 1000)],
                                    user_id=emma.id, email="emma@glow.test")
        s.commit()
        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816QTY001", "order_item_id": items_q2[0].id,
            "new_variant_id": v_hi.id, "qty": 2, "reason": "two sizes off"})
        d = r.json()
        check("qty=2 创建 → qty=2 / price_diff=500×2=1000 / 响应含 qty",
              r.status_code == 201 and d["qty"] == 2 and d["price_diff"] == 1000, d)
        ex_q2_no = d["exchange_no"]
        tl_q2 = (s.query(OrderTimeline)
                 .filter(OrderTimeline.order_id == o_q2.id,
                         OrderTimeline.event == "exchange_created").first())
        check("qty=2 timeline exchange_created detail 含 qty=2",
              tl_q2 is not None and tl_q2.detail.get("qty") == 2
              and tl_q2.detail.get("price_diff") == 1000,
              tl_q2 and tl_q2.detail)

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816QTY001", "order_item_id": items_q2[0].id,
            "new_variant_id": v_hi.id, "qty": 4})
        check("qty=4 超可换量 3 → 409 qty_exceeds_available:3",
              r.status_code == 409 and "qty_exceeds_available:3" in r.text, r.text)

        r = client.post("/api/exchanges", headers=H_EMMA, json={
            "order_no": "EX260816QTY001", "order_item_id": items_q2[0].id,
            "new_variant_id": v_same.id})
        d = r.json()
        check("不传 qty → 默认 1 兼容（diff 0×1）",
              r.status_code == 201 and d["qty"] == 1 and d["price_diff"] == 0, d)
        ex_q2_d1_no = d["exchange_no"]

        r = client.post(f"/api/admin/trade/exchanges/{ex_q2_no}/approve", headers=H_OPS)
        check("qty=2 diff>0 → approve 到 2 待差价",
              r.status_code == 200 and r.json()["status"] == 2, r.text[:120])
        r = client.post(f"/api/admin/trade/exchanges/{ex_q2_no}/mark-paid", headers=H_OPS)
        check("qty=2 mark-paid → 1（补差 1000）",
              r.status_code == 200 and r.json()["status"] == 1
              and r.json()["price_diff"] == 1000, r.text[:120])

        s.expire_all()
        stock_hi_q2_before = s.get(Variant, v_hi.id).stock
        r = client.post(f"/api/admin/trade/exchanges/{ex_q2_no}/ship", headers=H_OPS,
                        json={"carrier": "usps", "tracking_no": "9400111QTY002"})
        d = r.json()
        s.expire_all()
        ship_q2_mv = (s.query(StockMovement)
                      .filter(StockMovement.variant_id == v_hi.id,
                              StockMovement.type == 3,
                              StockMovement.ref_type == "exchange",
                              StockMovement.ref_id == s.query(Exchange)
                              .filter(Exchange.exchange_no == ex_q2_no).first().id)
                      .all())
        ship_q2_ex = s.query(Exchange).filter(Exchange.exchange_no == ex_q2_no).first()
        shipment_q2 = s.query(Shipment).filter(Shipment.id == ship_q2_ex.shipment_id).first()
        check("qty=2 ship → 新变体库存 -2 + type=3 流水 change=-2",
              r.status_code == 200 and d["status"] == 3
              and s.get(Variant, v_hi.id).stock == stock_hi_q2_before - 2
              and len(ship_q2_mv) == 1 and ship_q2_mv[0].change == -2, d)
        check("qty=2 shipment item_json=[{orderItemId,qty:2}]",
              shipment_q2 is not None
              and shipment_q2.item_json == [{"orderItemId": items_q2[0].id, "qty": 2}],
              shipment_q2 and shipment_q2.item_json)

        s.expire_all()
        stock_old_q2_before = s.get(Variant, v_old.id).stock
        r = client.post(f"/api/admin/trade/exchanges/{ex_q2_no}/complete", headers=H_OPS)
        d = r.json()
        s.expire_all()
        item_q2_after = s.get(OrderItem, items_q2[0].id)
        check("qty=2 complete → exchanged_qty+2 / 旧变体回补 +2（type=5 change=2）",
              r.status_code == 200 and d["status"] == 4 and d["exchanged_qty"] == 2
              and item_q2_after.exchanged_qty == 2
              and s.get(Variant, v_old.id).stock == stock_old_q2_before + 2
              and (s.query(StockMovement)
                   .filter(StockMovement.variant_id == v_old.id,
                           StockMovement.type == 5,
                           StockMovement.ref_type == "exchange",
                           StockMovement.change == 2).count() == 1), d)

        r = client.post(f"/api/admin/trade/exchanges/{ex_q2_d1_no}/reject",
                        headers=H_OPS, json={"reason": "cleanup"})
        check("qty=2 单上的默认 qty=1 同件换货可独立拒绝（互不影响）",
              r.status_code == 200 and r.json()["status"] == 5, r.text[:120])

        s.close()
finally:
    pass

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
