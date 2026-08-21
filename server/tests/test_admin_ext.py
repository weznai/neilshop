"""admin 扩展自测 —— tickets 组合状态 / RMA 分页 / exchanges size / orders per_page /
popup 曝光转化上报 + 审计回归（重复关单 409、多笔 RMA 退款钳制）。
（GM_DB=sqlite:///test_ext.sqlite 独立库；BigInteger 垫片同 test_exchanges.py）"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_ext.sqlite").replace("\\", "/")
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
    Category, Collection, CollectionProduct, Exchange, Order, OrderItem, Payment,
    PopupConfig, Product, Rma, Ticket, User, Variant,
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


def make_order(s, no, *, email="ext@glow.test", status=1, subtotal=1000,
               grand_total=None, note=None):
    o = Order(order_no=no, email=email, status=status, subtotal=subtotal,
              grand_total=grand_total if grand_total is not None else subtotal,
              shipping_address=ADDR, placed_at=utcnow(), paid_at=utcnow(),
              points_earned=0, giftcard_discount=0, note=note)
    s.add(o)
    s.flush()
    return o


with TestClient(app) as client:
    s = SessionLocal()

    cat = Category(slug="ext-cat", name="Ext Cat")
    s.add(cat)
    s.flush()
    p = Product(slug="ext-gel", title="Ext Gel", category_id=cat.id, status=1,
                hero_image="https://img/e.jpg", price_min=1000, price_max=1000)
    s.add(p)
    s.flush()
    v = Variant(product_id=p.id, sku="EXT-1", option1_value="Short",
                option2_value="24pcs", price=1000, stock=100)
    s.add(v)
    admin = User(email="ops@glow.test", password_hash=hash_password("x"),
                 name="Ops", role=2)
    s.add(admin)
    s.flush()
    H_OPS = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}

    # ===== 1. admin orders 可选 per_page（默认 10 兼容 + 10-100 钳制）=====
    for i in range(15):
        make_order(s, f"EXT260820ORD{i:02d}")
    s.commit()
    r = client.get("/api/admin/trade/orders", headers=H_OPS)
    d = r.json()
    check("orders 默认 per_page=10 兼容（15 单首页 10 条 / pages=2）",
          r.status_code == 200 and len(d["items"]) == 10 and d["per_page"] == 10
          and d["total"] == 15 and d["pages"] == 2, d.get("per_page"))
    r = client.get("/api/admin/trade/orders", headers=H_OPS, params={"per_page": 50})
    d = r.json()
    check("orders per_page=50 生效（单页全量 15 条 / pages=1）",
          len(d["items"]) == 15 and d["per_page"] == 50 and d["pages"] == 1, d.get("per_page"))
    r = client.get("/api/admin/trade/orders", headers=H_OPS, params={"per_page": 3})
    d = r.json()
    check("orders per_page=3 → 钳到 10；per_page=500 → 钳到 100",
          d["per_page"] == 10 and len(d["items"]) == 10
          and client.get("/api/admin/trade/orders", headers=H_OPS,
                         params={"per_page": 500}).json()["per_page"] == 100, d.get("per_page"))

    # ===== 1b. orders note 字段贯通（列表 + 详情）=====
    make_order(s, "EXT260820NOTE1", note="Please gift wrap, it's a birthday gift")
    s.commit()
    r = client.get("/api/admin/trade/orders", headers=H_OPS,
                   params={"q": "EXT260820NOTE1"})
    d = r.json()
    check("orders 列表行含 note 且值完整（下单备注贯通）",
          r.status_code == 200 and d["total"] == 1
          and d["items"][0]["note"] == "Please gift wrap, it's a birthday gift",
          d.get("items"))
    r = client.get("/api/admin/trade/orders/EXT260820NOTE1", headers=H_OPS)
    d = r.json()
    check("orders 详情含 note（同值）",
          r.status_code == 200 and d["note"] == "Please gift wrap, it's a birthday gift",
          d.get("note"))

    # ===== 2. admin exchanges size（默认 10 兼容 / size=50 生效）=====
    o_ex = make_order(s, "EXT260820EXB01")
    it_ex = OrderItem(order_id=o_ex.id, variant_id=v.id, product_slug="ext-gel",
                      title_snapshot="Ext Gel", qty=1, unit_price=1000, subtotal=1000)
    s.add(it_ex)
    s.flush()
    for i in range(12):
        s.add(Exchange(exchange_no=f"EX260820E{i:03d}", order_id=o_ex.id,
                       order_item_id=it_ex.id, old_variant_id=v.id,
                       new_variant_id=v.id, price_diff=0, status=0))
    s.commit()
    r = client.get("/api/admin/trade/exchanges", headers=H_OPS)
    d = r.json()
    check("exchanges 默认 size=10 兼容（12 条首页 10 / pages=2）",
          r.status_code == 200 and len(d["items"]) == 10 and d["per_page"] == 10
          and d["total"] == 12 and d["pages"] == 2, d.get("per_page"))
    r = client.get("/api/admin/trade/exchanges", headers=H_OPS, params={"size": 50})
    d = r.json()
    check("exchanges size=50 生效（单页全量 12 条 / per_page=50）",
          len(d["items"]) == 12 and d["per_page"] == 50 and d["pages"] == 1, d.get("per_page"))
    r = client.get("/api/admin/trade/exchanges", headers=H_OPS,
                   params={"status": 0, "size": 50})
    check("exchanges size 与 status 过滤并存",
          r.json()["total"] == 12 and len(r.json()["items"]) == 12, r.text[:120])

    # ===== 3. admin RMA 分页（默认 20 / total / pages / page 翻页）=====
    o_rma = make_order(s, "EXT260820RMA01")
    it_rma = OrderItem(order_id=o_rma.id, variant_id=v.id, product_slug="ext-gel",
                       title_snapshot="Ext Gel", qty=1, unit_price=1000, subtotal=1000)
    s.add(it_rma)
    s.flush()
    for i in range(25):
        s.add(Rma(rma_no=f"RMA260820E{i:03d}", order_id=o_rma.id,
                  order_item_id=it_rma.id, qty=1, reason=1, status=0))
    s.commit()
    r = client.get("/api/admin/trade/rmas", headers=H_OPS)
    d = r.json()
    check("RMA 默认分页 page=1 / per_page=20 / total=25 / pages=2",
          r.status_code == 200 and d["page"] == 1 and d["per_page"] == 20
          and d["total"] == 25 and d["pages"] == 2 and len(d["items"]) == 20,
          {k: d.get(k) for k in ("page", "per_page", "total", "pages")})
    check("RMA items 行结构不降级（join 三元组字段齐全）",
          {"rma_no", "order_no", "email", "status", "qty", "reason",
           "item_title", "unit_price", "created_at"} <= set(d["items"][0].keys()),
          d["items"][0].keys())
    r = client.get("/api/admin/trade/rmas", headers=H_OPS, params={"page": 2})
    d = r.json()
    check("RMA page=2 → 尾页 5 条",
          d["page"] == 2 and len(d["items"]) == 5 and d["total"] == 25, len(d["items"]))
    r = client.get("/api/admin/trade/rmas", headers=H_OPS,
                   params={"per_page": 100, "page": 1})
    d = r.json()
    check("RMA per_page=100 → 单页全量 25 条",
          d["per_page"] == 100 and len(d["items"]) == 25, d.get("per_page"))
    r = client.get("/api/admin/trade/rmas", headers=H_OPS, params={"status": 0})
    check("RMA status 过滤与分页并存（total=25）",
          r.json()["total"] == 25 and len(r.json()["items"]) == 20, r.text[:120])

    # ===== 4. admin tickets 组合状态（3,4 = 全部已关）=====
    ticket_specs = [(0, "TK260820T0001"), (2, "TK260820T0002"), (3, "TK260820T0003"),
                    (3, "TK260820T0004"), (4, "TK260820T0005"), (4, "TK260820T0006")]
    for st, no in ticket_specs:
        s.add(Ticket(ticket_no=no, email="ext@glow.test", category=1,
                     subject=f"ext {st}", status=st))
    s.commit()
    r = client.get("/api/admin/ops/tickets", headers=H_OPS, params={"status": "3,4"})
    d = r.json()
    check("tickets status=3,4 → 4 条且仅含 3/4 两类",
          r.status_code == 200 and d["total"] == 4
          and {t["status"] for t in d["items"]} == {3, 4}, d.get("total"))
    r = client.get("/api/admin/ops/tickets", headers=H_OPS, params={"status": "3"})
    d = r.json()
    check("tickets 单值 status=3 行为不变（2 条）",
          d["total"] == 2 and all(t["status"] == 3 for t in d["items"]), d.get("total"))
    r = client.get("/api/admin/ops/tickets", headers=H_OPS)
    check("tickets 不带 status → 全量 6 条", r.json()["total"] == 6, r.json().get("total"))
    r = client.get("/api/admin/ops/tickets", headers=H_OPS, params={"status": "abc"})
    check("tickets 非法 status → 422", r.status_code == 422, r.status_code)
    r = client.get("/api/admin/ops/tickets", headers=H_OPS,
                   params={"status": "3,4", "q": "ext@glow.test"})
    check("tickets 组合状态与 q 检索并存", r.json()["total"] == 4, r.text[:120])

    # ===== 5. popup 曝光/转化上报（公开端点 · 原子自增 · active=0 → 404）=====
    pop_on = PopupConfig(scene="ext_scene", title="Ext", active=1)
    pop_off = PopupConfig(scene="ext_scene_off", title="Ext Off", active=0)
    s.add_all([pop_on, pop_off])
    s.commit()
    check("shown/convert 无需鉴权",
          client.post(f"/api/promo/popup/{pop_on.id}/shown").status_code == 200)
    check("convert 无需鉴权", client.post(f"/api/promo/popup/{pop_on.id}/convert").status_code == 200)
    r = client.post(f"/api/promo/popup/{pop_on.id}/shown")
    s.expire_all()
    pop = s.get(PopupConfig, pop_on.id)
    check("shown×2 + convert×1 → stats_shown=2 / stats_converted=1",
          r.status_code == 200 and r.json() == {"ok": True}
          and pop.stats_shown == 2 and pop.stats_converted == 1,
          (pop.stats_shown, pop.stats_converted))
    r = client.post(f"/api/promo/popup/{pop_off.id}/shown")
    check("active=0 上报 shown → 404（统计不增）",
          r.status_code == 404 and s.get(PopupConfig, pop_off.id).stats_shown == 0, r.status_code)
    r = client.post(f"/api/promo/popup/{pop_off.id}/convert")
    check("active=0 上报 convert → 404", r.status_code == 404, r.status_code)
    check("不存在 id 上报 → 404",
          client.post("/api/promo/popup/999999/shown").status_code == 404
          and client.post("/api/promo/popup/999999/convert").status_code == 404)
    check("停用后前台投放同步 204（scene 无 active 配置）",
          client.get("/api/promo/popup", params={"scene": "ext_scene_off"}).status_code == 204)

    # ===== 6. 审计回归：重复关单 409（3 待关 → 4 正常流保留）=====
    s.add(Ticket(ticket_no="TK260820CLOSE", email="ext@glow.test", category=1,
                 subject="close me", status=3))
    s.commit()
    r = client.post("/api/admin/ops/tickets/TK260820CLOSE/close", headers=H_OPS,
                    json={"close_reason": 1})
    check("3(已解决待关)→close 200 正常确认流",
          r.status_code == 200 and r.json()["status"] == 4, r.text[:120])
    r = client.post("/api/admin/ops/tickets/TK260820CLOSE/close", headers=H_OPS,
                    json={"close_reason": 2})
    check("重复 close 已关闭工单 → 409（closed_at/close_reason 不被覆盖）",
          r.status_code == 409 and "already" in r.text, r.status_code)

    # ===== 6b. ops logs 增强：action/admin_id/start/end 过滤 + admin_name 回填 =====
    r = client.get("/api/admin/ops/logs", headers=H_OPS,
                   params={"entity": "ticket", "action": "close"})
    d = r.json()
    check("logs entity AND action 组合过滤 + admin_name 批量回填",
          r.status_code == 200 and d["total"] >= 1
          and all(i["action"] == "close" and i["admin_name"] == admin.name
                  for i in d["items"]), d.get("total"))
    r = client.get("/api/admin/ops/logs", headers=H_OPS,
                   params={"admin_id": admin.id, "size": 5})
    d = r.json()
    check("logs admin_id 过滤（全部归属 ops）",
          d["total"] >= 1 and all(i["admin_id"] == admin.id for i in d["items"]),
          d.get("total"))
    check("logs 未知 admin_id → 空集不 400",
          client.get("/api/admin/ops/logs", headers=H_OPS,
                     params={"admin_id": 999999}).json()["total"] == 0)
    total_all = client.get("/api/admin/ops/logs", headers=H_OPS,
                           params={"size": 100}).json()["total"]
    r = client.get("/api/admin/ops/logs", headers=H_OPS,
                   params={"start": "2020-01-01", "end": utcnow().isoformat() + "Z",
                           "size": 100})
    check("logs start/end 时间窗（ISO 日期 + Z 后缀）覆盖全部",
          r.json()["total"] == total_all, (r.json()["total"], total_all))
    check("logs 未来 start → 空集 / 非法 start → 400",
          client.get("/api/admin/ops/logs", headers=H_OPS,
                     params={"start": "2099-01-01"}).json()["total"] == 0
          and client.get("/api/admin/ops/logs", headers=H_OPS,
                         params={"start": "not-a-date"}).status_code == 400)

    # ===== 6c. admin collections 补全：PUT 更新 / GET 商品清单 / DELETE 级联 =====
    r = client.post("/api/admin/catalog/collections", headers=H_OPS,
                    json={"slug": "ext-coll", "title": "Ext Coll", "rule_json": {}})
    cid = r.json()["id"]
    check("集合创建 201", r.status_code == 201 and cid, r.text[:120])
    r = client.post("/api/admin/catalog/collections", headers=H_OPS,
                    json={"slug": "ext-coll-bn", "title": "Ext Coll Banner",
                          "rule_json": {}, "banner_image": "https://img/banner.jpg"})
    d = r.json()
    s.expire_all()
    check("集合创建带 banner_image 落库（http(s) 校验通过）",
          r.status_code == 201 and d["banner_image"] == "https://img/banner.jpg"
          and s.get(Collection, d["id"]).banner_image == "https://img/banner.jpg", d)
    check("集合创建 banner 非 http(s)（相对路径/javascript:）→ 422",
          client.post("/api/admin/catalog/collections", headers=H_OPS,
                      json={"slug": "ext-coll-bad", "title": "Bad", "rule_json": {},
                            "banner_image": "/img/rel.jpg"}).status_code == 422
          and client.post("/api/admin/catalog/collections", headers=H_OPS,
                          json={"slug": "ext-coll-bad", "title": "Bad", "rule_json": {},
                                "banner_image": "javascript:alert(1)"}).status_code == 422)
    r = client.put(f"/api/admin/catalog/collections/{cid}", headers=H_OPS,
                   json={"title": "Ext Coll v2", "banner_image": "/img/banner.jpg",
                         "sort_order": 5, "is_active": False})
    d = r.json()
    check("集合 PUT 部分更新（未传 rule_json 保持原值）",
          r.status_code == 200 and d["title"] == "Ext Coll v2"
          and d["banner_image"] == "/img/banner.jpg" and d["sort_order"] == 5
          and d["is_active"] == 0 and d["rule_json"] == {}, d)
    r = client.put(f"/api/admin/catalog/collections/{cid}/products", headers=H_OPS,
                   json={"products": [{"product_id": p.id, "sort_order": 1}]})
    check("集合挂商品 ok", r.status_code == 200 and r.json()["count"] == 1, r.text[:120])
    r = client.get(f"/api/admin/catalog/collections/{cid}/products", headers=H_OPS)
    d = r.json()
    check("集合商品清单（product_id/sort_order/product 三元组）",
          r.status_code == 200 and d["items"] == [
              {"product_id": p.id, "sort_order": 1,
               "product": {"id": p.id, "title": "Ext Gel", "slug": "ext-gel"}}], d)
    r = client.delete(f"/api/admin/catalog/collections/{cid}", headers=H_OPS)
    s.expire_all()
    check("集合 DELETE → 级联清 CollectionProduct 且集合消失",
          r.status_code == 200 and s.get(Collection, cid) is None
          and s.query(CollectionProduct).filter(
              CollectionProduct.collection_id == cid).count() == 0, r.text[:120])
    check("未知集合 PUT/DELETE/GET products → 404",
          client.put("/api/admin/catalog/collections/999999", headers=H_OPS,
                     json={"title": "x"}).status_code == 404
          and client.delete("/api/admin/catalog/collections/999999",
                            headers=H_OPS).status_code == 404
          and client.get("/api/admin/catalog/collections/999999/products",
                         headers=H_OPS).status_code == 404)

    # ===== 7. 审计回归：多笔 RMA 比例折算累计超剩余可退 → 钳制收尾全额退 =====
    o_cl = make_order(s, "EXT260820CLMP1", status=4, subtotal=2998, grand_total=3110)
    it_a = OrderItem(order_id=o_cl.id, variant_id=v.id, product_slug="ext-gel",
                     title_snapshot="Ext Gel A", qty=1, unit_price=1599, subtotal=1599)
    it_b = OrderItem(order_id=o_cl.id, variant_id=v.id, product_slug="ext-gel",
                     title_snapshot="Ext Gel B", qty=1, unit_price=1399, subtotal=1399)
    s.add_all([it_a, it_b])
    s.flush()
    s.add(Payment(order_id=o_cl.id, amount=3110, status=1, refunded_amount=0))
    s.add_all([
        Rma(rma_no="RMA260820CLA1", order_id=o_cl.id, order_item_id=it_a.id,
            qty=1, reason=2, status=0),
        Rma(rma_no="RMA260820CLB1", order_id=o_cl.id, order_item_id=it_b.id,
            qty=1, reason=2, status=0),
    ])
    s.commit()
    for rma_no in ("RMA260820CLA1", "RMA260820CLB1"):
        assert client.post(f"/api/admin/trade/rmas/{rma_no}/approve", headers=H_OPS).status_code == 200
        assert client.post(f"/api/admin/trade/rmas/{rma_no}/receive", headers=H_OPS).status_code == 200
    r = client.post("/api/admin/trade/rmas/RMA260820CLA1/refund", headers=H_OPS)
    d = r.json()
    check("第一笔 RMA 退款 1659（比例折算，订单 shipping_fee=0 不补运费）→ Payment 部分退(4)",
          r.status_code == 200 and d["refund_amount"] == 1659 and d["payment_status"] == 4,
          d)
    r = client.post("/api/admin/trade/rmas/RMA260820CLB1/refund", headers=H_OPS)
    d = r.json()
    s.expire_all()
    payment = (s.query(Payment).filter(Payment.order_id == o_cl.id)
               .order_by(Payment.id.desc()).first())
    o_cl_db = s.query(Order).filter(Order.order_no == "EXT260820CLMP1").first()
    check("第二笔折算 1451 恰为剩余可退 → 全额退：refund 1451 / Payment 全退(3) / 订单 REFUNDED(9)",
          r.status_code == 200 and d["refund_amount"] == 1451 and d["full"] is True
          and payment.status == 3 and payment.refunded_amount == 3110
          and o_cl_db.status == 9, d)

    s.close()

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
