"""性能扩展自测：N+1 审计回归——catalog variant_counts/admin 聚合、trade list_rmas
JOIN 三元组、订单 items/payments/shipments 批量 map 接口（替代逐单 N+1 调用模式）。
（MySQL scratch 库 glowmag_test_perf 与 test_perf 共用惯例，DROP 重建；顺序运行勿并行）"""

import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "glowmag_test_perf"
import pymysql  # noqa: E402

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    _cur.execute(f"CREATE DATABASE {TEST_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = f"mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/{TEST_DB}?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app.main import app  # noqa: E402
from app.core.db import SessionLocal, engine, init_db, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Order, OrderItem, Payment, Product, Rma, Shipment, User, Variant,
)
from app.domains.catalog import repository as catalog_repo  # noqa: E402
from app.domains.trade import repository as trade_repo  # noqa: E402

PASSED = 0
FAILED = []


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"PASS  {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}  {info}")


N_PRODUCTS = 120
N_ORDERS = 60
N_RMAS = 40

_SQL_COUNT = 0


def count_sql(fn):
    global _SQL_COUNT
    _SQL_COUNT = 0

    def _hook(_conn, _cursor, _stmt, _params, _ctx, _execmany):
        global _SQL_COUNT
        _SQL_COUNT += 1

    event.listen(engine, "before_cursor_execute", _hook)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _hook)
    return result, _SQL_COUNT


def build_fixtures() -> dict:
    init_db()
    db = SessionLocal()
    now = utcnow()
    try:
        admin = User(email="admin@glowmag.com", name="Perf Ext Admin", role=9,
                     password_hash=hash_password("perfext123"))
        db.add(admin)
        db.flush()

        from app.models import Category
        cat = Category(slug="pex-nails", name="Perf Ext Nails", sort_order=1)
        db.add(cat)
        db.flush()

        products = []
        for i in range(1, N_PRODUCTS + 1):
            products.append(Product(
                slug=f"pex-{i:03d}", title=f"Perf Ext Product {i}",
                subtitle=f"sub {i}", category_id=cat.id,
                status=1, price_min=900 + (i % 20) * 100, price_max=900 + (i % 20) * 100,
                hero_image="/img/p.jpg", images=["/img/p1.jpg"], tags=["pex"],
                rating_avg=450, rating_count=i % 30, sold_count=(N_PRODUCTS - i) % 500,
                published_at=now - timedelta(days=i % 90),
            ))
        db.add_all(products)
        db.flush()

        variants = []
        for p in products:
            for k in range(3):
                variants.append(Variant(
                    product_id=p.id, sku=f"PX-{p.id}-{k}", option1_value="Shape",
                    option2_value="24pcs", price=p.price_min,
                    stock=0 if k == 2 and p.id % 7 == 0 else (k * 2 if p.id % 5 == 0 else 20 + k),
                    safety_stock=5, is_active=0 if k == 2 and p.id % 11 == 0 else 1,
                ))
        db.add_all(variants)
        db.flush()

        orders = []
        for i in range(1, N_ORDERS + 1):
            orders.append(Order(
                order_no=f"NPX{i:06d}", email=f"buyer{i % 10}@pex.test",
                status=1 if i % 3 else 0, subtotal=3000, grand_total=3500,
                shipping_address={}, placed_at=now - timedelta(hours=i),
            ))
        db.add_all(orders)
        db.flush()

        items = []
        item_by_index: list[OrderItem] = []
        for o in orders:
            for j in range(2):
                it = OrderItem(order_id=o.id, variant_id=variants[(o.id * 2 + j) % len(variants)].id,
                               product_slug="pex-001", title_snapshot="Perf Ext Item",
                               qty=2, unit_price=1000, subtotal=2000)
                items.append(it)
                item_by_index.append(it)
        db.add_all(items)
        db.flush()

        payments = [Payment(order_id=o.id, amount=3500, status=1) for o in orders if o.status == 1]
        db.add_all(payments)
        shipments = [
            Shipment(shipment_no=f"SPX{o.id:06d}", order_id=o.id, carrier="usps",
                     tracking_no=f"T{o.id:06d}", status=3, item_json=[])
            for o in orders if o.id % 3 == 0
        ]
        db.add_all(shipments)
        rmas = [
            Rma(rma_no=f"RPE{i:04d}", order_id=orders[i].id,
                order_item_id=item_by_index[i].id, qty=1,
                reason=1 + i % 6, status=i % 6)
            for i in range(N_RMAS)
        ]
        db.add_all(rmas)
        db.commit()
        return {"admin": admin.id}
    finally:
        db.close()


def main() -> int:
    fx = build_fixtures()
    db = SessionLocal()
    try:
        all_pids = [r[0] for r in db.query(Product.id).order_by(Product.id.asc()).all()]

        # ---------- catalog：variant_counts 批量聚合 ----------

        def naive_counts(pids):
            out = {}
            for pid in pids:
                vs = db.query(Variant).filter(
                    Variant.product_id == pid, Variant.is_active == 1).all()
                out[pid] = {
                    "variant_count": len(vs),
                    "total_stock": sum(v.stock for v in vs),
                    "low_stock_count": sum(1 for v in vs if v.stock <= v.safety_stock),
                }
            return {k: v for k, v in out.items() if v["variant_count"]}

        agg, agg_queries = count_sql(lambda: catalog_repo.variant_counts(db, all_pids))
        want = naive_counts(all_pids)
        check("variant_counts 语义一致（含 inactive 排除/零活跃商品缺席）", agg == want,
              f"{len(agg)} vs {len(want)}")
        check("variant_counts 批量：120 商品单条 GROUP BY（SQL==1）", agg_queries == 1,
              f"queries={agg_queries}")

        _, empty_queries = count_sql(lambda: catalog_repo.variant_counts(db, []))
        check("variant_counts 空 pids 零查询", empty_queries == 0 and
              catalog_repo.variant_counts(db, []) == {}, f"queries={empty_queries}")

        def admin_page(size):
            total, prods = catalog_repo.admin_products(
                db, status=None, q=None, offset=0, limit=size)
            agg2 = catalog_repo.variant_counts(db, [p.id for p in prods])
            return total, prods, agg2

        (total, prods50, _), q50 = count_sql(lambda: admin_page(50))
        (total2, _, _), q100 = count_sql(lambda: admin_page(100))
        check("admin_products 分页+聚合：count+page+agg 共 3 条 SQL，与页大小无关",
              q50 == 3 and q100 == 3 and total == N_PRODUCTS and len(prods50) == 50,
              f"q50={q50} q100={q100}")

        # ---------- catalog：前台列表/详情（既有批查路径回归） ----------

        def list_page():
            _t, prods = catalog_repo.list_products(
                db, category_id_list=None, tag=None, q=None, sort="new",
                offset=0, limit=60)
            catalog_repo.stock_map(db, [p.id for p in prods])
            catalog_repo.translations_map(db, [p.id for p in prods], "en-US")
            return prods

        prods60, batched_queries = count_sql(list_page)

        def naive_variants():
            for p in prods60:
                db.query(Variant).filter(
                    Variant.product_id == p.id, Variant.is_active == 1).all()

        _, naive_queries = count_sql(naive_variants)
        check("list_products 路径：count+page+stock_map+translations 共 4 条 SQL（60 商品）",
              batched_queries == 4 and len(prods60) == 60,
              f"queries={batched_queries}")
        check("list_products 批查远低于逐商品基线", batched_queries < naive_queries / 10,
              f"batched={batched_queries} naive={naive_queries}")

        def detail_path():
            p = catalog_repo.get_product_by_slug(db, "pex-007")
            vs = catalog_repo.active_variants(db, p.id)
            catalog_repo.variant_images_map(db, [v.id for v in vs])
            related = catalog_repo.related_products(db, p)
            catalog_repo.stock_map(db, [r.id for r in related])
            return p, vs, related

        (p, vs, related), detail_queries = count_sql(detail_path)
        check("product_detail 路径 SQL 固定 5 条（slug+变体+图+相关+stock_map）",
              detail_queries == 5 and p.slug == "pex-007" and len(vs) >= 1,
              f"queries={detail_queries}")

        # ---------- trade：list_rmas JOIN 三元组 ----------

        (rma_rows, rma_total), rma_queries = count_sql(
            lambda: trade_repo.list_rmas(db, None, page=1, per_page=20))
        ok_rows = all(rma.order_item_id == item.id and rma.order_id == order.id
                      for rma, item, order in rma_rows)
        check("list_rmas JOIN 三元组一次查询：count+rows 共 2 条 SQL",
              rma_queries == 2 and rma_total == N_RMAS and len(rma_rows) == 20 and ok_rows,
              f"queries={rma_queries} total={rma_total}")

        oids = [r[0] for r in db.query(Order.id).order_by(Order.id.asc()).all()]

        # ---------- trade：订单子表批量 map（替代逐单 N+1） ----------

        def naive_items():
            return [trade_repo.order_items(db, oid) for oid in oids]

        _, naive_item_queries = count_sql(naive_items)
        (imap, map_item_queries) = count_sql(lambda: trade_repo.order_items_map(db, oids))
        want_items = {oid: rows for oid, rows in zip(oids, naive_items()) if rows}
        check("order_items_map：60 单 1 条 SQL，与逐单 order_items 等价",
              map_item_queries == 1 and naive_item_queries == len(oids) and
              {k: [i.id for i in v] for k, v in imap.items()} ==
              {k: [i.id for i in v] for k, v in want_items.items()},
              f"map={map_item_queries} naive={naive_item_queries}")

        (pmap, map_pay_queries) = count_sql(lambda: trade_repo.order_payments_map(db, oids))
        want_pay = {oid: trade_repo.order_payments(db, oid) for oid in oids}
        want_pay = {k: v for k, v in want_pay.items() if v}
        check("order_payments_map：60 单 1 条 SQL，与逐单 order_payments 等价",
              map_pay_queries == 1 and
              {k: [p.id for p in v] for k, v in pmap.items()} ==
              {k: [p.id for p in v] for k, v in want_pay.items()},
              f"queries={map_pay_queries}")

        (smap, map_ship_queries) = count_sql(lambda: trade_repo.order_shipments_map(db, oids))
        want_ship = {oid: trade_repo.order_shipments(db, oid) for oid in oids}
        want_ship = {k: v for k, v in want_ship.items() if v}
        check("order_shipments_map：60 单 1 条 SQL，与逐单 order_shipments 等价",
              map_ship_queries == 1 and
              {k: [s.id for s in v] for k, v in smap.items()} ==
              {k: [s.id for s in v] for k, v in want_ship.items()},
              f"queries={map_ship_queries}")

        (_, empty_map_queries) = count_sql(lambda: (
            trade_repo.order_items_map(db, []),
            trade_repo.order_payments_map(db, []),
            trade_repo.order_shipments_map(db, []),
        ))
        check("批量 map 空 order_ids 零查询", empty_map_queries == 0,
              f"queries={empty_map_queries}")

        vids = [r[0] for r in db.query(Variant.id).order_by(Variant.id.asc()).limit(37).all()]
        (_, vstock_queries) = count_sql(lambda: trade_repo.variant_stock_map(db, vids))
        check("variant_stock_map（service 逐件 stock_of 的既有批量替代）：1 条 SQL",
              vstock_queries == 1, f"queries={vstock_queries}")

        # ---------- 端点级：后台商品列表 ----------

        with TestClient(app) as client:
            h = {"Authorization": f"Bearer {create_token(fx['admin'], 9)}"}

            def fetch_admin_products():
                return client.get("/api/admin/catalog/products",
                                  headers=h, params={"page": 1, "size": 50}).json()

            payload, ep_queries = count_sql(fetch_admin_products)
            check("端点 /api/admin/catalog/products：auth+count+page+agg 共 4 条 SQL 且 50 行带聚合字段",
                  ep_queries == 4 and len(payload["items"]) == 50 and
                  all("variant_count" in i and "total_stock" in i and
                      "low_stock_count" in i for i in payload["items"]),
                  f"queries={ep_queries} items={len(payload['items'])}")
    finally:
        db.close()

    print(f"\nPERF_EXT: {PASSED}/{PASSED + len(FAILED)} passed")
    if FAILED:
        print("failed:", FAILED)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
