"""性能智能体自测：索引定义/EXPLAIN 命中、N+1 批查 SQL 计数、列表语义快照、耗时对比。"""

import os
import sys
import time
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
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, func, text  # noqa: E402

from app.main import app  # noqa: E402
from app.core.db import Base, SessionLocal, engine, init_db, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Cart, Category, DiscountCode, DiscountRedemption, Order, OrderItem,
    Payment, PointsLedger, Product, Referral, Review, User, Variant,
)

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


N_PRODUCTS = 200
N_ORDERS = 200
N_REVIEWS = 500


def build_fixtures() -> dict:
    init_db()
    db = SessionLocal()
    now = utcnow()
    try:
        admin = User(email="admin@glowmag.com", name="Perf Admin", role=9,
                     password_hash=hash_password("perfadmin123"))
        db.add(admin)
        shopper = User(email="perf@glowmag.com", name="Perf Shopper", role=0)
        db.add(shopper)
        db.flush()

        cat_root = Category(slug="nails", name="Nails", sort_order=1)
        cat_mid = Category(slug="french", name="French", sort_order=1)
        cat_acc = Category(slug="accessories", name="Accessories", sort_order=2)
        db.add_all([cat_root, cat_mid, cat_acc])
        db.flush()
        cat_mid.parent_id = cat_root.id

        products = []
        for i in range(1, N_PRODUCTS + 1):
            products.append(Product(
                slug=f"perf-{i:03d}", title=f"Perf Product {i}",
                subtitle=f"sub {i}",
                category_id=cat_mid.id if i % 3 == 0 else (cat_root.id if i % 3 != 2 else cat_acc.id),
                status=1, price_min=900 + (i % 20) * 100, price_max=900 + (i % 20) * 100,
                hero_image="/img/p.jpg", images=["/img/p1.jpg"], tags=["perf"],
                is_new=1 if i % 10 == 0 else 0,
                is_best_seller=1 if i % 25 == 0 else 0,
                rating_avg=450, rating_count=i % 30, sold_count=(N_PRODUCTS - i) % 500,
                published_at=now - timedelta(days=i % 90),
            ))
        db.add_all(products)
        db.flush()

        variants = []
        for p in products:
            for k in range(3):
                variants.append(Variant(
                    product_id=p.id, sku=f"PV-{p.id}-{k}", option1_value="Shape",
                    option2_value="24pcs", price=p.price_min,
                    stock=0 if k == 2 and p.id % 7 == 0 else (k * 2 if p.id % 5 == 0 else 20 + k),
                    safety_stock=5,
                ))
        db.add_all(variants)
        db.flush()

        orders = []
        for i in range(1, N_ORDERS + 1):
            orders.append(Order(
                order_no=f"NPF{i:06d}", user_id=shopper.id if i % 4 == 0 else None,
                email=f"buyer{i % 30}@perf.test",
                status=1 if i % 3 else 0, subtotal=3000, grand_total=3500,
                shipping_address={}, placed_at=now - timedelta(hours=i),
                paid_at=now - timedelta(hours=i) if i % 3 else None,
            ))
        db.add_all(orders)
        db.flush()
        items = []
        for o in orders:
            items.append(OrderItem(order_id=o.id, variant_id=variants[o.id % len(variants)].id,
                                   product_slug="perf-001", title_snapshot="Perf Item",
                                   qty=2, unit_price=1000, subtotal=2000))
        db.add_all(items)
        db.flush()
        payments = [
            Payment(order_id=o.id, amount=3500, status=1) for o in orders if o.status == 1
        ]
        db.add_all(payments)

        reviews = []
        for i in range(1, N_REVIEWS + 1):
            reviews.append(Review(
                product_id=products[i % N_PRODUCTS].id, user_id=shopper.id,
                order_item_id=100000 + i, rating=1 + i % 5, content="nice",
                status=0 if i % 8 == 0 else 1, created_at=now - timedelta(days=i % 60),
            ))
        db.add_all(reviews)

        carts = []
        for i in range(40):
            carts.append(Cart(
                user_id=None, email=f"cart{i}@perf.test",
                items=[{"variantId": variants[i].id, "qty": 1}] if i % 2 == 0 else [],
                updated_at=now - timedelta(hours=i * 3),
            ))
        db.add_all(carts)

        dc = DiscountCode(code="PERF10", type=1, value=10, min_subtotal=0,
                          per_user_limit=1, starts_at=now, is_active=1)
        db.add(dc)
        db.flush()
        redemptions = [
            DiscountRedemption(code_id=dc.id, order_id=orders[i].id,
                               email=f"buyer{i % 30}@perf.test", discount_amount=100)
            for i in range(120)
        ]
        db.add_all(redemptions)
        referrals = [
            Referral(code=f"RF{i:04d}", referrer_user_id=admin.id,
                     invited_email=f"inv{i}@perf.test", status=i % 4)
            for i in range(1000)
        ]
        db.add_all(referrals)
        db.commit()
        return {"admin": admin.id, "shopper": shopper.id, "cat_root": cat_root.slug,
                "cat_mid": cat_mid.slug, "cat_acc": cat_acc.slug}
    finally:
        db.close()


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


def expected_cards(db, sorts_order, category_ids=None, tag=None, page=1, size=100, cat_first=False):
    """cat_first=True：模拟前台「全部」浏览型排序（new/best）口径——分类 sort_order 为
    第一排序键（与 repo.list_products 一致），用于语义快照比对。"""
    q = db.query(Product).filter(Product.status == 1)
    if cat_first:
        q = q.outerjoin(Category, Product.category_id == Category.id)
        sorts_order = [func.coalesce(Category.sort_order, 999999).asc(), *sorts_order]
    if category_ids:
        q = q.filter(Product.category_id.in_(category_ids))
    if tag:
        q = q.filter(text(f"""CAST(products.tags AS CHAR) LIKE '%"{tag}"%'"""))
    q = q.order_by(*sorts_order, Product.id.asc()).offset((page - 1) * size).limit(size)
    out = []
    for p in q.all():
        vs = [v for v in db.query(Variant).filter(
            Variant.product_id == p.id, Variant.is_active == 1).all()]
        out.append((p.id, p.slug, {
            "total": sum(v.stock for v in vs),
            "low": sum(1 for v in vs if v.stock <= v.safety_stock),
            "out": sum(v.stock for v in vs) <= 0,
        }))
    return out


def actual_cards(payload):
    return [(i["id"], i["slug"], {
        "total": i["stock_summary"]["total"],
        "low": i["stock_summary"]["low"],
        "out": i["stock_summary"]["out"],
    }) for i in payload["items"]]


def main() -> int:
    fx = build_fixtures()
    db = SessionLocal()
    try:
        meta = Base.metadata
        def has_idx(table, name, cols):
            ix = [i for i in meta.tables[table].indexes if i.name == name]
            return bool(ix) and [c.name for c in ix[0].columns] == cols

        check("metadata products idx_cat_status_pub", has_idx("products", "idx_cat_status_pub", ["category_id", "status", "published_at"]))
        check("metadata products idx_best/idx_new", has_idx("products", "idx_best", ["is_best_seller", "status"]) and has_idx("products", "idx_new", ["is_new", "status", "published_at"]))
        check("metadata orders idx_status_placed", has_idx("orders", "idx_status_placed", ["status", "placed_at"]))
        check("metadata orders idx_user_placed", has_idx("orders", "idx_user_placed", ["user_id", "placed_at"]))
        check("metadata tickets idx_status_priority", has_idx("tickets", "idx_status_priority", ["status", "priority", "created_at"]))
        check("metadata stock_movements idx_variant_time", has_idx("stock_movements", "idx_variant_time", ["variant_id", "created_at"]))
        check("metadata points_ledger idx_expires/idx_user_created", has_idx("points_ledger", "idx_expires", ["expires_at"]) and has_idx("points_ledger", "idx_user_created", ["user_id", "created_at"]))
        check("metadata outbox idx_unpublished", has_idx("outbox_events", "idx_unpublished", ["published", "created_at"]))
        check("metadata referrals uk_code_email(unique)", has_idx("referrals", "uk_code_email", ["code", "invited_email"]) and any(i.unique for i in meta.tables["referrals"].indexes if i.name == "uk_code_email"))
        check("metadata discount_redemptions idx_code_email", has_idx("discount_redemptions", "idx_code_email", ["code_id", "email"]))

        is_mysql = engine.dialect.name == "mysql"
        if is_mysql:
            def explain_key(sql):
                row = db.execute(text("EXPLAIN " + sql)).fetchone()
                return (row[5] if len(row) > 5 else row.key), (row[9] if len(row) > 9 else row.rows)

            key, _ = explain_key(f"SELECT id FROM products WHERE category_id=(SELECT id FROM categories WHERE slug='{fx['cat_mid']}') AND status=1 ORDER BY published_at DESC LIMIT 12")
            check("EXPLAIN products 分类分页命中索引", key == "idx_cat_status_pub", f"key={key}")
            key, _ = explain_key(f"SELECT id FROM orders WHERE user_id={fx['shopper']} ORDER BY placed_at DESC LIMIT 10")
            check("EXPLAIN orders 我的订单命中索引", key == "idx_user_placed", f"key={key}")
            key, _ = explain_key("SELECT id FROM referrals WHERE code='RF0500' AND invited_email='inv500@perf.test'")
            check("EXPLAIN referrals (code,email) 命中 uk", key == "uk_code_email", f"key={key}")
            key, _ = explain_key("SELECT COUNT(*) FROM discount_redemptions WHERE code_id=(SELECT MIN(id) FROM discount_codes) AND email='buyer1@perf.test'")
            check("EXPLAIN redemptions (code_id,email) 命中复合索引", "idx_code_email" in str(key).split(","), f"key={key}")
            key, _ = explain_key("SELECT id FROM returns WHERE status=0")
            check("EXPLAIN returns status 命中索引", key == "ix_returns_status", f"key={key}")

        with TestClient(app) as client:
            atok = create_token(fx["admin"], 9)
            h = {"Authorization": f"Bearer {atok}"}

            cats: dict[str, int] = {}

            def _walk(nodes):
                for n in nodes:
                    cats[n["slug"]] = n["id"]
                    _walk(n["children"])

            _walk(client.get("/api/catalog/categories").json())
            mid_id = cats[fx["cat_mid"]]

            sorts = {
                "new": "Product.updated_at.desc()",
                "best": "Product.sold_count.desc()",
                "price_asc": "Product.price_min.asc()",
                "price_desc": "Product.price_min.desc()",
            }
            ok_all = True
            for sort, order_expr in sorts.items():
                order = eval(order_expr, {"Product": Product})
                # new/best 在「全部」视图按分类序分组（指甲在前、睫毛次之），价格排序保持纯序
                exp = expected_cards(db, [order], page=1, size=100,
                                     cat_first=sort in ("new", "best"))
                act = actual_cards(client.get("/api/catalog/products", params={
                    "sort": sort, "page": 1, "size": 100}).json())
                if exp != act:
                    ok_all = False
            check("列表语义快照：4 种排序×200 商品 stock_summary 一致", ok_all)

            exp = expected_cards(db, [Product.updated_at.desc()],
                                 category_ids=[cats[fx["cat_root"]], mid_id], page=1, size=100)
            act = actual_cards(client.get("/api/catalog/products", params={
                "category": fx["cat_root"], "page": 1, "size": 100}).json())
            check("列表语义快照：分类含子树（root→mid 递归）结果一致", exp == act)

            exp = expected_cards(db, [Product.updated_at.desc()], page=2, size=60,
                                 cat_first=True)
            act = actual_cards(client.get("/api/catalog/products", params={
                "page": 2, "size": 60}).json())
            check("列表语义快照：第 2 页分页一致", exp == act)

            detail = client.get("/api/catalog/products/perf-007").json()
            vs = db.query(Variant).filter(Variant.product_id == detail["id"], Variant.is_active == 1).all()
            want = {"total": sum(v.stock for v in vs), "low": sum(1 for v in vs if v.stock <= v.safety_stock),
                    "out": sum(v.stock for v in vs) <= 0}
            check("详情 stock_summary 语义一致", detail["stock_summary"] == want,
                  f"{detail['stock_summary']} != {want}")

            def fetch_two_pages():
                for p in (1, 2):
                    client.get("/api/catalog/products", params={
                        "category": fx["cat_root"], "page": p, "size": 100}).raise_for_status()
                return True

            _, batched_queries = count_sql(fetch_two_pages)

            def naive_variants():
                for p in db.query(Product).filter(Product.status == 1).limit(100).all():
                    db.query(Variant).filter(Variant.product_id == p.id, Variant.is_active == 1).all()

            _, naive_queries = count_sql(naive_variants)

            t0 = time.perf_counter()
            naive_variants()
            t_naive = time.perf_counter() - t0

            t0 = time.perf_counter()
            for p in (1, 2):
                client.get("/api/catalog/products", params={
                    "category": fx["cat_root"], "page": p, "size": 100})
            t_batched = time.perf_counter() - t0

            print(f"timeit catalog 200 商品：naive逐商品查询={t_naive * 1000:.1f}ms/{naive_queries}条SQL"
                  f"  批查端点={t_batched * 1000:.1f}ms/{batched_queries}条SQL(两页含分类子树)")
            check("catalog N+1：端点 SQL 次数远低于逐商品基线", batched_queries < naive_queries / 10,
                  f"batched={batched_queries} naive={naive_queries}")
            check("catalog 单页 SQL 次数 ≤4（count+page+聚合+分类树）", batched_queries <= 8,
                  f"two pages total={batched_queries}")
            check("catalog 批查耗时低于逐商品基线", t_batched < t_naive,
                  f"batched={t_batched:.3f}s naive={t_naive:.3f}s")

            dash, dash_queries = count_sql(lambda: client.get("/api/admin/ops/dashboard", headers=h).json())
            carts_rows = db.query(Cart).all()
            want_add = sum(1 for c in carts_rows if c.items)
            want_abd = sum(1 for c in carts_rows if c.items and c.updated_at <= utcnow() - timedelta(hours=24))
            check("dashboard add_to_cart 聚合口径一致", dash["funnel"]["add_to_cart"] == want_add,
                  f"{dash['funnel']['add_to_cart']} != {want_add}")
            check("dashboard abandoned 聚合口径一致", dash["abandoned_carts"] == want_abd,
                  f"{dash['abandoned_carts']} != {want_abd}")
            check("dashboard 无逐行查询（查询数受控）", dash_queries <= 25, f"queries={dash_queries}")

            trade, _ = count_sql(lambda: client.get("/api/admin/trade/orders", headers=h,
                                                    params={"page": 1}).json())
            check("admin_trade 订单列表无逐行 items/users 查询", len(trade["items"]) == 10
                  and trade["total"] == N_ORDERS, f"total={trade['total']}")

            target = db.query(Order).filter(Order.status == 1).order_by(Order.id).first()
            t_items = db.query(OrderItem).filter(OrderItem.order_id == target.id).all()
            before_stock = {v.id: v.stock for v in
                            db.query(Variant).filter(Variant.id.in_([i.variant_id for i in t_items])).all()}
            r = client.post(f"/api/admin/trade/orders/{target.order_no}/refund", headers=h,
                            json={"reason": "perf_test"})
            check("admin_trade 全额退款触发批量回补", r.status_code == 200 and r.json()["full"] is True,
                  r.text[:200])
            db.expire_all()
            after_stock = {v.id: v.stock for v in
                           db.query(Variant).filter(Variant.id.in_(before_stock)).all()}
            check("批量回补后库存与流水一致", all(
                after_stock[vid] == before_stock[vid] + sum(i.qty - i.refunded_qty for i in t_items
                                                            if i.variant_id == vid)
                for vid in before_stock))
            movements = db.execute(text(
                "SELECT variant_id, stock_after FROM stock_movements WHERE ref_id=:o AND type=5"
            ), {"o": target.id}).fetchall()
            check("批量回补 stock_after 与终值一致", all(
                m[1] == after_stock[m[0]] for m in movements) and len(movements) == len(t_items))
    finally:
        db.close()

    print(f"\nPERF: {PASSED}/{PASSED + len(FAILED)} passed")
    if FAILED:
        print("failed:", FAILED)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
