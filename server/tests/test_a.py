"""智能体 A 自测：账户/目录/购物车/后台目录，独立 sqlite 库。"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "glowmag_test_a"
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

from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    AdminLog, Cart, Category, Collection, CollectionProduct, CookieConsent,
    EmailPreference, NewsletterSubscriber, Product, Review, User, Variant,
)


def T(month: int, day: int, year: int = 2026) -> datetime:
    return datetime(year, month, day)


def build_fixtures() -> dict:
    db = SessionLocal()
    try:
        cat_root = Category(slug="press-on-nails", name="Press-on Nails")
        cat_child = Category(slug="french-nails", name="French Nails")
        cat_acc = Category(slug="accessories", name="Accessories")
        db.add_all([cat_root, cat_child, cat_acc])
        db.flush()
        cat_child.parent_id = cat_root.id

        p1 = Product(slug="bare-gems", title="Bare Gems", subtitle="Nude french tips",
                     category_id=cat_child.id, status=1, compare_at_price=2200,
                     price_min=1500, price_max=1800, hero_image="/img/bare.jpg",
                     images=["/img/bare-1.jpg", "/img/bare-2.jpg"],
                     tags=["new", "french"], is_new=1, rating_avg=487,
                     rating_count=12, sold_count=50, published_at=T(1, 2))
        p2 = Product(slug="cherry-pop", title="Cherry Pop",
                     subtitle="Classic red nails", category_id=cat_root.id,
                     status=1, price_min=1200, price_max=1200,
                     hero_image="/img/cherry.jpg", tags=["best"],
                     is_best_seller=1, rating_avg=460, rating_count=8,
                     sold_count=120, published_at=T(12, 20, 2025))
        p3 = Product(slug="velvet-matte", title="Velvet Matte",
                     category_id=cat_child.id, status=1, price_min=900,
                     price_max=950, hero_image="/img/velvet.jpg", tags=["new"],
                     is_new=1, rating_avg=400, rating_count=2, sold_count=10,
                     published_at=T(1, 5))
        p4 = Product(slug="ghost-set", title="Ghost Set",
                     category_id=cat_root.id, status=0, price_min=1000,
                     price_max=1000, hero_image="/img/ghost.jpg")
        p5 = Product(slug="old-set", title="Old Set", category_id=cat_root.id,
                     status=2, price_min=800, price_max=800,
                     hero_image="/img/old.jpg")
        db.add_all([p1, p2, p3, p4, p5])
        db.flush()

        v1 = Variant(product_id=p1.id, sku="BG-SA-SHORT", option1_value="Short Almond",
                     option2_value="24pcs", price=1500, stock=10, safety_stock=5)
        v2 = Variant(product_id=p1.id, sku="BG-LS-LONG", option1_value="Long Stiletto",
                     option2_value="24pcs", price=1800, stock=3, safety_stock=5)
        v3 = Variant(product_id=p2.id, sku="CP-STD", option1_value="Standard",
                     option2_value="24pcs", price=1200, stock=0, safety_stock=5)
        v4 = Variant(product_id=p3.id, sku="VM-SA", option1_value="Short Almond",
                     option2_value="24pcs", price=900, stock=100, safety_stock=5)
        db.add_all([v1, v2, v3, v4])
        db.flush()

        c_rule = Collection(slug="new-arrivals", title="New Arrivals",
                            rule_json={"tags": ["new"]})
        c_mat = Collection(slug="editors-picks", title="Editor's Picks", rule_json={})
        db.add_all([c_rule, c_mat])
        db.flush()
        db.add_all([
            CollectionProduct(collection_id=c_mat.id, product_id=p3.id, sort_order=0),
            CollectionProduct(collection_id=c_mat.id, product_id=p1.id, sort_order=1),
        ])

        maya = User(email="maya@glowmag.com",
                    password_hash=hash_password("mayapass123"), name="Maya Chen")
        bo = User(email="bo@glowmag.com",
                  password_hash=hash_password("bopass1234"), name="Bo")
        admin = User(email="admin@glowmag.com",
                     password_hash=hash_password("adminpass123"),
                     name="Admin", role=2)
        db.add_all([maya, bo, admin])
        db.flush()
        db.add_all([
            Review(product_id=p1.id, user_id=maya.id, order_item_id=9001, rating=5,
                   content="Gorgeous!", images=["/img/r1.jpg"], status=1,
                   created_at=T(2, 10)),
            Review(product_id=p1.id, user_id=bo.id, order_item_id=9002, rating=4,
                   content="Nice fit", status=1, created_at=T(2, 5)),
            Review(product_id=p1.id, user_id=bo.id, order_item_id=9003, rating=3,
                   content="pending one", status=0, created_at=T(2, 12)),
        ])
        db.commit()
        return {"p1": p1.id, "p2": p2.id, "p3": p3.id, "p4": p4.id, "p5": p5.id,
                "v1": v1.id, "v2": v2.id, "v3": v3.id, "v4": v4.id,
                "cat_root": cat_root.id, "cat_child": cat_child.id,
                "c_rule": c_rule.id, "c_mat": c_mat.id, "admin": admin.id}
    finally:
        db.close()


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fresh_db():
    return SessionLocal()


@case
def register_and_login(client, fx):
    r = client.post("/api/account/register", json={
        "email": "user1@glowmag.com", "password": "password8", "name": "User One"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"] and body["user"]["email"] == "user1@glowmag.com"
    assert body["user"]["points"] == 0 and body["user"]["tier"] == 0
    r2 = client.post("/api/account/register", json={
        "email": "user1@glowmag.com", "password": "password8", "name": "Dup"})
    assert r2.status_code == 409
    r3 = client.post("/api/account/register", json={
        "email": "weak@glowmag.com", "password": "short", "name": "Weak"})
    assert r3.status_code == 422


@case
def login_flow(client, fx):
    r = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "password8"})
    assert r.status_code == 200, r.text
    assert r.json()["token"]
    db = fresh_db()
    try:
        u = db.query(User).filter(User.email == "user1@glowmag.com").first()
        assert u.last_login_at is not None
    finally:
        db.close()
    bad = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "wrongpass"})
    assert bad.status_code == 401


@case
def me_endpoints(client, fx):
    tok = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "password8"}).json()["token"]
    r = client.get("/api/account/me", headers=auth(tok))
    assert r.status_code == 200, r.text
    me = r.json()
    assert set(me) >= {"id", "email", "name", "points", "tier",
                       "total_spent", "birthday", "created_at"}
    assert client.get("/api/account/me").status_code == 401
    up = client.put("/api/account/me", headers=auth(tok),
                    json={"name": "Renamed", "birthday": "1995-06-15"})
    assert up.status_code == 200 and up.json()["name"] == "Renamed"
    assert up.json()["birthday"] == "1995-06-15"


@case
def address_crud(client, fx):
    tok = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "password8"}).json()["token"]
    h = auth(tok)
    a1 = client.post("/api/account/addresses", headers=h, json={
        "full_name": "User One", "line1": "5 Main St", "city": "Austin",
        "zip": "78701"})
    assert a1.status_code == 201, a1.text
    assert a1.json()["country"] == "US" and a1.json()["is_default"] is False
    a2 = client.post("/api/account/addresses", headers=h, json={
        "full_name": "User One", "line1": "9 Oak Ave", "city": "Dallas",
        "state": "TX", "zip": "75201", "is_default": True})
    assert a2.status_code == 201 and a2.json()["is_default"] is True
    lst = client.get("/api/account/addresses", headers=h).json()
    assert len(lst) == 2 and lst[0]["id"] == a2.json()["id"]
    assert sum(1 for a in lst if a["is_default"]) == 1
    upd = client.put(f"/api/account/addresses/{a1.json()['id']}", headers=h, json={
        "full_name": "User One", "line1": "5 Main St", "city": "El Paso",
        "zip": "79901", "is_default": True})
    assert upd.status_code == 200 and upd.json()["city"] == "El Paso"
    lst = client.get("/api/account/addresses", headers=h).json()
    assert lst[0]["id"] == a1.json()["id"]
    assert all(a["is_default"] is False for a in lst if a["id"] != a1.json()["id"])
    client.post("/api/account/register", json={
        "email": "user2@glowmag.com", "password": "password8", "name": "Two"})
    tok2 = client.post("/api/account/login", json={
        "email": "user2@glowmag.com", "password": "password8"}).json()["token"]
    foreign = client.put(f"/api/account/addresses/{a1.json()['id']}",
                         headers=auth(tok2), json={
                             "full_name": "X", "line1": "1 St", "city": "Y",
                             "zip": "1"})
    assert foreign.status_code == 404
    dele = client.delete(f"/api/account/addresses/{a2.json()['id']}", headers=h)
    assert dele.status_code == 200
    assert client.delete(f"/api/account/addresses/{a2.json()['id']}",
                         headers=h).status_code == 404


@case
def wishlist_flow(client, fx):
    tok = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "password8"}).json()["token"]
    h = auth(tok)
    r1 = client.post(f"/api/account/wishlist/{fx['p1']}", headers=h)
    assert r1.status_code == 201, r1.text
    r2 = client.post(f"/api/account/wishlist/{fx['p1']}", headers=h)
    assert r2.status_code == 200
    items = client.get("/api/account/wishlist", headers=h).json()
    assert len(items) == 1
    card = items[0]
    assert card["slug"] == "bare-gems" and card["rating"] == 487
    assert card["price_min"] == 1500 and card["price_max"] == 1800
    assert card["compare_at_price"] == 2200
    assert card["stock_summary"]["total"] == 13 and card["stock_summary"]["low"] == 1
    assert card["stock_summary"]["out"] is False
    assert client.post("/api/account/wishlist/999999", headers=h).status_code == 404
    d = client.delete(f"/api/account/wishlist/{fx['p1']}", headers=h)
    assert d.status_code == 200
    assert client.delete(f"/api/account/wishlist/{fx['p1']}",
                         headers=h).status_code == 404


@case
def catalog_list_filters(client, fx):
    r = client.get("/api/catalog/products")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3 and len(body["items"]) == 3
    assert body["page"] == 1 and body["size"] == 12
    slugs = {i["slug"] for i in body["items"]}
    assert slugs == {"bare-gems", "cherry-pop", "velvet-matte"}
    card = next(i for i in body["items"] if i["slug"] == "bare-gems")
    assert card["rating"] == 4.87 and card["rating_count"] == 12
    assert card["tags"] == ["new", "french"] and card["is_new"] == 1
    assert card["stock_summary"] == {"total": 13, "low": 1, "out": False}
    cherry = next(i for i in body["items"] if i["slug"] == "cherry-pop")
    assert cherry["stock_summary"]["out"] is True

    root = client.get("/api/catalog/products",
                      params={"category": "press-on-nails"}).json()
    assert root["total"] == 3
    child = client.get("/api/catalog/products",
                       params={"category": "french-nails"}).json()
    assert child["total"] == 2
    none = client.get("/api/catalog/products",
                      params={"category": "nope"}).json()
    assert none["total"] == 0
    tagged = client.get("/api/catalog/products", params={"tag": "new"}).json()
    assert {i["slug"] for i in tagged["items"]} == {"bare-gems", "velvet-matte"}
    q = client.get("/api/catalog/products", params={"q": "Bare"}).json()
    assert q["total"] == 1 and q["items"][0]["slug"] == "bare-gems"
    assert client.get("/api/catalog/products",
                      params={"sort": "bad"}).status_code == 400


@case
def catalog_sort_and_paging(client, fx):
    asc = client.get("/api/catalog/products", params={"sort": "price_asc"}).json()
    assert asc["items"][0]["slug"] == "velvet-matte"
    desc = client.get("/api/catalog/products", params={"sort": "price_desc"}).json()
    assert desc["items"][0]["slug"] == "bare-gems"
    best = client.get("/api/catalog/products", params={"sort": "best"}).json()
    assert best["items"][0]["slug"] == "cherry-pop"
    new = client.get("/api/catalog/products", params={"sort": "new"}).json()
    assert new["items"][0]["slug"] == "velvet-matte"
    pg = client.get("/api/catalog/products",
                    params={"sort": "price_asc", "size": 2, "page": 2}).json()
    assert pg["total"] == 3 and len(pg["items"]) == 1 and pg["page"] == 2
    assert pg["items"][0]["slug"] == "bare-gems"


@case
def product_detail(client, fx):
    r = client.get("/api/catalog/products/bare-gems")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["images"] == ["/img/bare-1.jpg", "/img/bare-2.jpg"]
    assert d["compare_at_price"] == 2200 and d["description_md"] is None
    vs = {v["sku"]: v for v in d["variants"]}
    assert set(vs) == {"BG-SA-SHORT", "BG-LS-LONG"}
    assert vs["BG-SA-SHORT"]["stock_status"] == "in"
    assert vs["BG-LS-LONG"]["stock_status"] == "low"
    assert vs["BG-SA-SHORT"]["safety_stock"] == 5
    assert d["related"][0]["slug"] == "velvet-matte" and len(d["related"]) == 1
    assert d["category_slug"] == "french-nails"
    by_id = client.get(f"/api/catalog/products-by-id/{d['id']}").json()
    assert by_id["category_slug"] == "french-nails"
    cherry = client.get("/api/catalog/products/cherry-pop").json()
    assert cherry["variants"][0]["stock_status"] == "out"
    assert cherry["category_slug"] == "press-on-nails"
    assert client.get("/api/catalog/products/ghost-set").status_code == 404
    assert client.get("/api/catalog/products/no-such").status_code == 404


@case
def category_tree(client, fx):
    tree = client.get("/api/catalog/categories").json()
    assert len(tree) == 2
    root = next(c for c in tree if c["slug"] == "press-on-nails")
    assert [c["slug"] for c in root["children"]] == ["french-nails"]


@case
def collections(client, fx):
    lst = client.get("/api/catalog/collections").json()["items"]
    assert {c["slug"] for c in lst} == {"new-arrivals", "editors-picks"}
    rule = client.get("/api/catalog/collections/new-arrivals").json()
    assert [p["slug"] for p in rule["products"]] == ["velvet-matte", "bare-gems"]
    mat = client.get("/api/catalog/collections/editors-picks").json()
    assert [p["slug"] for p in mat["products"]] == ["velvet-matte", "bare-gems"]
    assert client.get("/api/catalog/collections/nope").status_code == 404


@case
def search(client, fx):
    r = client.get("/api/catalog/search", params={"q": "Bare"}).json()
    assert len(r["products"]) == 1 and r["products"][0]["slug"] == "bare-gems"
    assert r["categories"] == []
    r2 = client.get("/api/catalog/search", params={"q": "nails"}).json()
    cats = {c["slug"] for c in r2["categories"]}
    assert "press-on-nails" in cats and "french-nails" in cats
    assert any(p["slug"] == "cherry-pop" for p in r2["products"])
    r3 = client.get("/api/catalog/search", params={"q": "best"}).json()
    assert [p["slug"] for p in r3["products"]] == ["cherry-pop"]


@case
def reviews(client, fx):
    r = client.get("/api/catalog/reviews", params={"product_id": fx["p1"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    names = [i["user"] for i in body["items"]]
    assert "M***n" in names and "B***o" in names
    assert all("pending" not in (i["content"] or "") for i in body["items"])
    top = body["items"][0]
    assert top["rating"] in (4, 5) and top["created_at"] is not None
    empty = client.get("/api/catalog/reviews",
                       params={"product_id": fx["p3"]}).json()
    assert empty["total"] == 0 and empty["items"] == []


@case
def cart_guest_flow(client, fx):
    r = client.post("/api/cart/items",
                    json={"variant_id": fx["v1"], "qty": 2})
    assert r.status_code == 201, r.text
    tok = r.headers.get("x-cart-token")
    assert tok
    body = r.json()
    assert body["token"] == tok
    assert len(body["items"]) == 1
    it = body["items"][0]
    assert it["title"] == "Bare Gems · Short Almond"
    assert it["price"] == 1500 and it["qty"] == 2 and it["line_total"] == 3000
    assert it["product_slug"] == "bare-gems" and it["stock"] == 10
    assert it["stock_status"] == "in"
    assert body["subtotal_cents"] == 3000

    r2 = client.post("/api/cart/items", headers={"X-Cart-Token": tok},
                     json={"variant_id": fx["v1"], "qty": 1})
    assert r2.json()["items"][0]["qty"] == 3
    assert r2.json()["subtotal_cents"] == 4500
    over = client.post("/api/cart/items", headers={"X-Cart-Token": tok},
                       json={"variant_id": fx["v2"], "qty": 5})
    assert over.status_code == 409 and over.json()["detail"] == "insufficient_stock"
    outstock = client.post("/api/cart/items", headers={"X-Cart-Token": tok},
                           json={"variant_id": fx["v3"], "qty": 1})
    assert outstock.status_code == 409
    missing = client.post("/api/cart/items", headers={"X-Cart-Token": tok},
                          json={"variant_id": 999999, "qty": 1})
    assert missing.status_code == 404

    got = client.get("/api/cart/", headers={"X-Cart-Token": tok}).json()
    assert got["token"] == tok and len(got["items"]) == 1


@case
def cart_update_delete(client, fx):
    tok = client.post("/api/cart/items",
                      json={"variant_id": fx["v1"], "qty": 3}).headers["x-cart-token"]
    h = {"X-Cart-Token": tok}
    up = client.put(f"/api/cart/items/{fx['v1']}", headers=h, json={"qty": 1})
    assert up.status_code == 200 and up.json()["subtotal_cents"] == 1500
    over = client.put(f"/api/cart/items/{fx['v1']}", headers=h, json={"qty": 99})
    assert over.status_code == 409
    zero = client.put(f"/api/cart/items/{fx['v1']}", headers=h, json={"qty": 0})
    assert zero.status_code == 200 and zero.json()["items"] == []
    miss = client.put(f"/api/cart/items/{fx['v1']}", headers=h, json={"qty": 1})
    assert miss.status_code == 404
    client.post("/api/cart/items", headers=h,
                json={"variant_id": fx["v4"], "qty": 1})
    dele = client.delete(f"/api/cart/items/{fx['v4']}", headers=h)
    assert dele.status_code == 200 and dele.json()["items"] == []
    assert client.delete(f"/api/cart/items/{fx['v4']}",
                         headers=h).status_code == 404


@case
def cart_merge(client, fx):
    gtok = client.post("/api/cart/items",
                       json={"variant_id": fx["v1"], "qty": 2}).headers["x-cart-token"]
    client.post("/api/cart/items", headers={"X-Cart-Token": gtok},
                json={"variant_id": fx["v4"], "qty": 2})
    utok = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "password8"}).json()["token"]
    client.post("/api/cart/items", headers=auth(utok),
                json={"variant_id": fx["v1"], "qty": 1})
    r = client.post("/api/cart/merge", headers=auth(utok),
                    json={"token": gtok})
    assert r.status_code == 200, r.text
    items = {i["variant_id"]: i["qty"] for i in r.json()["items"]}
    assert items == {fx["v1"]: 3, fx["v4"]: 2}
    assert r.headers.get("x-cart-token")
    db = fresh_db()
    try:
        assert db.query(Cart).filter(Cart.session_id == gtok).count() == 0
    finally:
        db.close()
    again = client.get("/api/cart/", headers={"X-Cart-Token": gtok}).json()
    assert again["items"] == []
    merged_view = client.get("/api/cart/", headers=auth(utok)).json()
    assert len(merged_view["items"]) == 2


@case
def newsletter_and_consent(client, fx):
    r = client.post("/api/account/newsletter",
                    json={"email": "fan@glowmag.com", "source": "popup"})
    assert r.status_code == 200, r.text
    client.post("/api/account/newsletter",
                json={"email": "fan@glowmag.com", "source": "footer"})
    db = fresh_db()
    try:
        assert db.query(NewsletterSubscriber).filter_by(
            email="fan@glowmag.com").count() == 1
        sub = db.get(NewsletterSubscriber, "fan@glowmag.com")
        assert sub.source == "footer"
        pref = db.get(EmailPreference, "fan@glowmag.com")
        assert pref.sub_promo == 1 and pref.sub_new_arrival == 1
        assert pref.sub_cart_abandon == 1 and pref.source == "footer"
    finally:
        db.close()
    c = client.post("/api/account/consent", json={
        "session_id": "sess-abc-123", "necessary": True, "analytics": True,
        "marketing": False, "region": "US-CA"})
    assert c.status_code == 201
    # 前端 CookieConsent.vue 会额外提交 personalization：schema 须接收（模型暂无该列不落库）
    c2 = client.post("/api/account/consent", json={
        "session_id": "sess-abc-456", "necessary": True, "analytics": False,
        "marketing": False, "personalization": True, "region": "US-CA"})
    assert c2.status_code == 201, c2.text
    db = fresh_db()
    try:
        row = db.query(CookieConsent).filter_by(session_id="sess-abc-123").first()
        assert row and row.necessary == 1 and row.analytics == 1
        assert row.marketing == 0 and row.region == "US-CA"
    finally:
        db.close()


@case
def admin_guard_and_list(client, fx):
    cust = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "password8"}).json()["token"]
    assert client.get("/api/admin/catalog/products",
                      headers=auth(cust)).status_code == 403
    assert client.get("/api/admin/catalog/products").status_code == 401
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    r = client.get("/api/admin/catalog/products",
                   headers=auth(atok), params={"size": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 5
    ghost = next(p for p in body["items"] if p["slug"] == "ghost-set")
    assert ghost["status"] == 0 and ghost["variant_count"] == 0
    bare = next(p for p in body["items"] if p["slug"] == "bare-gems")
    assert bare["variant_count"] == 2 and bare["total_stock"] == 13
    assert bare["low_stock_count"] == 1
    drafts = client.get("/api/admin/catalog/products",
                        headers=auth(atok), params={"status": 0}).json()
    assert drafts["total"] == 1 and drafts["items"][0]["slug"] == "ghost-set"
    q = client.get("/api/admin/catalog/products",
                   headers=auth(atok), params={"q": "velvet"}).json()
    assert q["total"] == 1


@case
def admin_product_crud(client, fx):
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    h = auth(atok)
    r = client.post("/api/admin/catalog/products", headers=h, json={
        "slug": "aurora-shine", "title": "Aurora Shine",
        "category_id": fx["cat_root"], "price_min": 1300, "price_max": 1600,
        "hero_image": "/img/aurora.jpg", "tags": ["new"]})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["status"] == 0
    db = fresh_db()
    try:
        log = db.query(AdminLog).filter_by(
            action="create", entity="product", entity_id=pid).first()
        assert log is not None and log.admin_id == fx["admin"]
    finally:
        db.close()
    dup = client.post("/api/admin/catalog/products", headers=h, json={
        "slug": "aurora-shine", "title": "Again",
        "category_id": fx["cat_root"], "price_min": 1, "price_max": 2})
    assert dup.status_code == 409
    badcat = client.post("/api/admin/catalog/products", headers=h, json={
        "slug": "x-set", "title": "X", "category_id": 999,
        "price_min": 1, "price_max": 2})
    assert badcat.status_code == 400

    before_total = client.get("/api/catalog/products").json()["total"]
    up = client.put(f"/api/admin/catalog/products/{pid}", headers=h, json={
        "price_min": 1350, "price_max": 1650, "tags": ["new", "glow"]})
    assert up.status_code == 200, up.text
    assert up.json()["price_min"] == 1350 and up.json()["tags"] == ["new", "glow"]
    db = fresh_db()
    try:
        log = db.query(AdminLog).filter_by(
            action="update", entity="product", entity_id=pid).first()
        diff = log.diff_json
        assert diff["price_min"] == {"before": 1300, "after": 1350}
        assert diff["tags"] == {"before": ["new"], "after": ["new", "glow"]}
    finally:
        db.close()

    pub = client.post(f"/api/admin/catalog/products/{pid}/publish", headers=h)
    assert pub.status_code == 200 and pub.json()["status"] == 1
    assert pub.json()["published_at"] is not None
    assert client.get("/api/catalog/products/aurora-shine").status_code == 200
    mid_total = client.get("/api/catalog/products").json()["total"]
    assert mid_total == before_total + 1
    unp = client.post(f"/api/admin/catalog/products/{pid}/unpublish", headers=h)
    assert unp.json()["status"] == 2
    assert client.get("/api/catalog/products/aurora-shine").status_code == 404
    final_total = client.get("/api/catalog/products").json()["total"]
    assert final_total == before_total
    assert client.post("/api/admin/catalog/products/424242/publish",
                       headers=h).status_code == 404


@case
def admin_variants(client, fx):
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    h = auth(atok)
    r = client.post(f"/api/admin/catalog/products/{fx['p4']}/variants",
                    headers=h, json={
                        "sku": "GS-STD", "option1_value": "Standard",
                        "option2_value": "24pcs", "price": 1000, "stock": 20})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert r.json()["safety_stock"] == 5 and r.json()["weight_gram"] == 30
    dup = client.post(f"/api/admin/catalog/products/{fx['p4']}/variants",
                      headers=h, json={
                          "sku": "GS-STD", "option1_value": "S",
                          "option2_value": "24pcs", "price": 1000})
    assert dup.status_code == 409
    nope = client.post("/api/admin/catalog/products/999/variants", headers=h,
                       json={"sku": "X", "option1_value": "S",
                             "option2_value": "24", "price": 1})
    assert nope.status_code == 404
    up = client.put(f"/api/admin/catalog/variants/{vid}", headers=h,
                    json={"price": 1100, "safety_stock": 8})
    assert up.status_code == 200 and up.json()["price"] == 1100
    assert up.json()["safety_stock"] == 8
    off = client.put(f"/api/admin/catalog/variants/{vid}", headers=h,
                     json={"is_active": False})
    assert not off.json()["is_active"]
    db = fresh_db()
    try:
        logs = db.query(AdminLog).filter_by(
            action="update", entity="variant", entity_id=vid).count()
        assert logs == 2
    finally:
        db.close()
    assert client.put("/api/admin/catalog/variants/999", headers=h,
                      json={"price": 1}).status_code == 404


@case
def admin_categories_collections(client, fx):
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    h = auth(atok)
    cats = client.get("/api/admin/catalog/categories", headers=h).json()
    assert len(cats) == 3
    nc = client.post("/api/admin/catalog/categories", headers=h,
                     json={"slug": "holiday", "name": "Holiday",
                           "parent_id": fx["cat_root"]})
    assert nc.status_code == 201, nc.text
    assert nc.json()["parent_id"] == fx["cat_root"]
    dup = client.post("/api/admin/catalog/categories", headers=h,
                      json={"slug": "holiday", "name": "Holiday"})
    assert dup.status_code == 409
    tree = client.get("/api/catalog/categories").json()
    assert any(c["slug"] == "holiday" for c in
               next(t for t in tree if t["slug"] == "press-on-nails")["children"])

    co = client.post("/api/admin/catalog/collections", headers=h, json={
        "slug": "under-10", "title": "Under $10", "rule_json": {"price_lt": 1000}})
    assert co.status_code == 201
    dupc = client.post("/api/admin/catalog/collections", headers=h,
                       json={"slug": "under-10", "title": "X", "rule_json": {}})
    assert dupc.status_code == 409
    detail = client.get("/api/catalog/collections/under-10").json()
    assert {p["slug"] for p in detail["products"]} == {"velvet-matte"}
    setp = client.put(f"/api/admin/catalog/collections/{co.json()['id']}/products",
                      headers=h, json={"products": [
                          {"product_id": fx["p2"], "sort_order": 1},
                          {"product_id": fx["p1"], "sort_order": 0}]})
    assert setp.status_code == 200 and setp.json()["count"] == 2
    mat = client.get("/api/catalog/collections/under-10").json()
    assert [p["slug"] for p in mat["products"]] == ["bare-gems", "cherry-pop"]
    bad = client.put(f"/api/admin/catalog/collections/{co.json()['id']}/products",
                     headers=h, json={"products": [{"product_id": 999}]})
    assert bad.status_code == 400
    assert client.put("/api/admin/catalog/collections/999/products", headers=h,
                      json={"products": []}).status_code == 404


@case
def admin_variant_list(client, fx):
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    h = auth(atok)
    assert client.get("/api/admin/catalog/variants").status_code == 401
    cust = client.post("/api/account/login", json={
        "email": "user1@glowmag.com", "password": "password8"}).json()["token"]
    assert client.get("/api/admin/catalog/variants",
                      headers=auth(cust)).status_code == 403
    allv = client.get("/api/admin/catalog/variants", headers=h).json()
    assert allv["total"] >= 5 and len(allv["items"]) == allv["total"]
    sample = allv["items"][0]
    for key in ("id", "product_id", "product_title", "sku", "price",
                "stock", "safety_stock", "is_active"):
        assert key in sample
    bare = client.get("/api/admin/catalog/variants", headers=h,
                      params={"product_id": fx["p1"]}).json()
    assert bare["total"] == 2
    assert sum(v["stock"] for v in bare["items"]) == 13
    assert all(v["product_title"] == "Bare Gems" for v in bare["items"])
    q = client.get("/api/admin/catalog/variants", headers=h,
                   params={"q": "bare"}).json()
    assert q["total"] == 2  # sku 或标题命中
    paged = client.get("/api/admin/catalog/variants", headers=h,
                       params={"page": 1, "size": 2}).json()
    assert paged["total"] == allv["total"] and len(paged["items"]) == 2


@case
def admin_product_rich_fields(client, fx):
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    h = auth(atok)
    r = client.post("/api/admin/catalog/products", headers=h, json={
        "slug": "rich-editor-demo", "title": "Rich Editor Demo",
        "subtitle": "full-field create", "description_md": "# Hello\nBody text",
        "category_id": fx["cat_root"], "price_min": 1200, "price_max": 1500,
        "compare_at_price": 1900, "hero_image": "/img/rich.jpg",
        "images": ["/img/rich-1.jpg", "/img/rich-2.jpg"],
        "video_url": "https://cdn.example.com/v.mp4",
        "tags": ["new", "editor"], "is_new": True, "is_best_seller": True})
    assert r.status_code == 201, r.text
    body = r.json()
    pid = body["id"]
    assert body["description_md"] == "# Hello\nBody text"
    assert body["images"] == ["/img/rich-1.jpg", "/img/rich-2.jpg"]
    assert body["video_url"] == "https://cdn.example.com/v.mp4"
    assert body["compare_at_price"] == 1900
    assert body["is_new"] == 1 and body["is_best_seller"] == 1

    up = client.put(f"/api/admin/catalog/products/{pid}", headers=h, json={
        "description_md": "rewritten", "images": ["/img/only-1.jpg"],
        "video_url": None, "is_new": False, "hero_image": "/img/rich2.jpg",
        "category_id": fx["cat_child"], "compare_at_price": None})
    assert up.status_code == 200, up.text
    u = up.json()
    assert u["description_md"] == "rewritten" and u["images"] == ["/img/only-1.jpg"]
    assert u["video_url"] is None and u["is_new"] == 0
    assert u["category_id"] == fx["cat_child"] and u["hero_image"] == "/img/rich2.jpg"
    assert u["compare_at_price"] is None

    badcat = client.put(f"/api/admin/catalog/products/{pid}", headers=h,
                        json={"category_id": 999})
    assert badcat.status_code == 400
    toomany = client.put(f"/api/admin/catalog/products/{pid}", headers=h,
                         json={"images": [f"/i/{n}.jpg" for n in range(9)]})
    assert toomany.status_code == 422


@case
def admin_product_get(client, fx):
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    h = auth(atok)
    assert client.get(
        f"/api/admin/catalog/products/{fx['p1']}").status_code == 401
    r = client.get(f"/api/admin/catalog/products/{fx['p1']}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "bare-gems" and body["variant_count"] == 2
    assert body["total_stock"] == 13 and body["subtitle"] == "Nude french tips"
    assert client.get("/api/admin/catalog/products/424242",
                      headers=h).status_code == 404


@case
def admin_product_bulk(client, fx):
    atok = client.post("/api/account/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"}).json()["token"]
    h = auth(atok)
    assert client.post("/api/admin/catalog/products/bulk",
                       json={"items": []}).status_code == 401
    r = client.post("/api/admin/catalog/products/bulk", headers=h, json={"items": [
        {"slug": "bulk-1", "title": "Bulk One", "category_id": fx["cat_root"],
         "price_min": 1000, "price_max": 1000},
        {"slug": "bulk-2", "title": "Bulk Two", "category_id": fx["cat_root"],
         "price_min": 1200, "price_max": 1200, "tags": ["bulk"]},
        {"slug": "bulk-1", "title": "Dup Slug", "category_id": fx["cat_root"],
         "price_min": 1, "price_max": 1},
        {"slug": "bulk-3", "title": "Bad Cat", "category_id": 999,
         "price_min": 1, "price_max": 1},
    ]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] == 2 and body["failed"] == 2
    ok_rows = [x for x in body["results"] if x["ok"]]
    bad_rows = [x for x in body["results"] if not x["ok"]]
    assert [x["slug"] for x in ok_rows] == ["bulk-1", "bulk-2"]
    assert bad_rows[0]["error"] == "slug already exists"
    assert bad_rows[1]["error"] == "category not found"
    got = client.get("/api/admin/catalog/products", headers=h,
                     params={"q": "bulk-"}).json()
    assert got["total"] == 2
    empty = client.post("/api/admin/catalog/products/bulk", headers=h,
                        json={"items": []})
    assert empty.status_code == 422


def main() -> int:
    with TestClient(app) as client:
        fx = build_fixtures()
        passed = 0
        failed = 0
        for fn in CASES:
            try:
                fn(client, fx)
                passed += 1
                print(f"PASS {fn.__name__}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {fn.__name__}: {exc}")
        print(f"{passed}/{passed + failed} passed")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
