"""安全审计自测（智能体 A）—— 用户侧 IDOR / JWT / 输入校验，攻击者视角断言。
（GM_DB=sqlite:///test_s.sqlite 独立库；BigInteger 垫片同 test_payments.py）"""

import os
import sys
import time

import jwt as pyjwt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_s.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import SessionLocal, init_db, utcnow
from app.core.security import create_token, hash_password
from app.main import app
from app.models import Category, Order, OrderItem, Product, User, Variant

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


ADDR = {"full_name": "Alice", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US", "phone": "+14155550001"}


def build_fixtures():
    init_db()
    db = SessionLocal()
    try:
        alice = User(email="alice@glow.test",
                     password_hash=hash_password("alicepass123"), name="Alice")
        bob = User(email="bob@glow.test",
                   password_hash=hash_password("bobpass1234"), name="Bob")
        dave = User(email="dave@glowmail.dev", status=0,
                    password_hash=hash_password("davepass1234"), name="Dave")
        db.add_all([alice, bob, dave])
        db.flush()
        cat = Category(slug="sec-cat", name="Sec Cat")
        db.add(cat)
        db.flush()
        p = Product(slug="sec-gel", title="Sec Gel", category_id=cat.id, status=1,
                    price_min=1000, price_max=1000, hero_image="/img/sec.jpg")
        db.add(p)
        db.flush()
        v = Variant(product_id=p.id, sku="SEC-STD", option1_value="Standard",
                    option2_value="24pcs", price=1000, stock=50, safety_stock=5)
        db.add(v)
        db.flush()
        order = Order(
            order_no="SEC2608160001", user_id=alice.id, email=alice.email,
            status=5, subtotal=2000, grand_total=2000,
            shipping_address=ADDR, paid_at=utcnow(),
        )
        db.add(order)
        db.flush()
        item = OrderItem(order_id=order.id, variant_id=v.id, product_slug="sec-gel",
                         title_snapshot="Sec Gel", qty=2, unit_price=1000,
                         subtotal=2000)
        db.add(item)
        db.commit()
        ids = {"alice": alice.id, "bob": bob.id, "p": p.id,
               "order": order.id, "item": item.id}
        db.close()
        return ids
    except Exception:
        db.close()
        raise


IDS = build_fixtures()
client = TestClient(app)
H_ALICE = {"Authorization": f"Bearer {create_token(IDS['alice'], 1)}"}
H_BOB = {"Authorization": f"Bearer {create_token(IDS['bob'], 1)}"}

print("== 账户：地址簿 IDOR ==")
r = client.post("/api/account/addresses", headers=H_ALICE, json=ADDR)
addr_id = r.json()["id"]
r = client.put(f"/api/account/addresses/{addr_id}", headers=H_BOB,
               json={**ADDR, "city": "Hacked"})
check("B 改 A 地址 → 404", r.status_code == 404, r.text[:120])
r = client.delete(f"/api/account/addresses/{addr_id}", headers=H_BOB)
check("B 删 A 地址 → 404", r.status_code == 404, r.text[:120])

print("== 账户：愿望单跨用户不可见 ==")
client.post(f"/api/account/wishlist/{IDS['p']}", headers=H_ALICE)
r = client.get("/api/account/wishlist", headers=H_BOB)
check("B 心愿单看不到 A 的收藏", r.status_code == 200 and r.json() == [], r.text[:120])

print("== 订单：双因子契约 ==")
NO = "SEC2608160001"
r = client.get(f"/api/orders/{NO}", headers=H_BOB)
check("登录 B 无 email 查 A 订单 → 404", r.status_code == 404, r.text[:120])
r = client.get(f"/api/orders/{NO}")
check("游客裸 order_no → 404", r.status_code == 404, r.text[:120])
r = client.get(f"/api/orders/{NO}", params={"email": "alice@glow.test"})
check("游客 order_no+正确 email → 200", r.status_code == 200, r.text[:120])
r = client.get(f"/api/orders/{NO}", params={"email": "evil@glow.test"})
check("游客 order_no+错误 email → 404", r.status_code == 404, r.text[:120])
r = client.get(f"/api/orders/{NO}", params={"email": "alice@glow.test"}, headers=H_BOB)
check("order_no+email 双因子契约保留（等同游客）", r.status_code == 200, r.text[:120])

print("== 退货：RMA 归属 ==")
r = client.post("/api/returns", headers=H_ALICE, json={
    "order_no": NO, "order_item_id": IDS["item"], "qty": 1, "reason": 1})
rma_no = r.json()["rma_no"]
check("A 创建 RMA 成功", r.status_code == 201 and rma_no.startswith("RMA"), r.text[:120])
r = client.get(f"/api/returns/{rma_no}", headers=H_BOB)
check("登录 B 查 A 的 RMA → 404", r.status_code == 404, r.text[:120])
r = client.get(f"/api/returns/{rma_no}")
check("游客裸 rma_no 被拦（需登录）", r.status_code == 401, r.text[:120])
r = client.get(f"/api/returns/{rma_no}", headers=H_ALICE)
check("A 查自己 RMA → 200", r.status_code == 200, r.text[:120])

print("== 客服：工单归属 ==")
r = client.post("/api/support/tickets", json={
    "email": "alice@glow.test", "category": 1,
    "subject": "Where?", "content": "my parcel"})
ticket_no = r.json()["ticket_no"]
r = client.get("/api/support/tickets", params={"email": "alice@glow.test"}, headers=H_BOB)
check("登录 B 查 A email 工单列表 → 403", r.status_code == 403, r.text[:120])
r = client.get("/api/support/tickets", params={"email": "alice@glow.test"})
check("游客仅 email 无 ticket_no → 403", r.status_code == 403, r.text[:120])
r = client.get("/api/support/tickets",
               params={"email": "alice@glow.test", "ticket_no": ticket_no})
check("游客 ticket_no+正确 email → 200", r.status_code == 200
      and len(r.json()["items"]) == 1, r.text[:120])
r = client.get("/api/support/tickets",
               params={"email": "evil@glow.test", "ticket_no": ticket_no})
check("游客 ticket_no+错误 email → 404", r.status_code == 404, r.text[:120])
r = client.post(f"/api/support/tickets/{ticket_no}/messages",
                json={"email": "evil@glow.test", "content": "give me"})
check("游客错 email 追加工单留言 → 403", r.status_code == 403, r.text[:120])
r = client.get("/api/support/tickets", params={"email": "alice@glow.test"},
               headers=H_ALICE)
check("登录 A 查自己 email 工单 → 200", r.status_code == 200
      and len(r.json()["items"]) == 1, r.text[:120])

print("== 订阅：跨用户操作 ==")
r = client.post("/api/subscriptions", headers=H_ALICE, json={"plan": 1, "style_mode": 1})
sid = r.json()["id"]
r = client.post(f"/api/subscriptions/{sid}/pause", headers=H_BOB, json={})
check("B 暂停 A 的订阅 → 404", r.status_code == 404, r.text[:120])

print("== 内容：评论归属 ==")
r = client.post("/api/content/reviews", headers=H_BOB, json={
    "order_no": NO, "order_item_id": IDS["item"], "rating": 5, "content": "steal"})
check("B 对 A 的订单发评论 → 404", r.status_code == 404, r.text[:120])

print("== JWT：过期/伪造/篡改 ==")
_now = int(time.time())
H_EXPIRED = {"Authorization": "Bearer " + pyjwt.encode(
    {"sub": str(IDS["alice"]), "role": 1, "iat": _now - 800, "exp": _now - 400},
    settings.jwt_secret, algorithm="HS256")}
r = client.get("/api/account/me", headers=H_EXPIRED)
check("过期 JWT → 401", r.status_code == 401, r.text[:120])
H_FORGED = {"Authorization": "Bearer " + pyjwt.encode(
    {"sub": str(IDS["alice"]), "role": 1, "iat": _now, "exp": _now + 3600},
    "not-the-secret", algorithm="HS256")}
r = client.get("/api/account/me", headers=H_FORGED)
check("伪造签名 JWT → 401", r.status_code == 401, r.text[:120])
H_ROLE = {"Authorization": "Bearer " + pyjwt.encode(
    {"sub": str(IDS["bob"]), "role": 9, "iat": _now, "exp": _now + 3600},
    "not-the-secret", algorithm="HS256")}
r = client.get("/api/account/me", headers=H_ROLE)
check("role 篡改（签名无效）→ 401", r.status_code == 401, r.text[:120])
H_ROLE_DB = {"Authorization": "Bearer " + pyjwt.encode(
    {"sub": str(IDS["bob"]), "role": 9, "iat": _now, "exp": _now + 3600},
    settings.jwt_secret, algorithm="HS256")}
r = client.get("/api/account/me", headers=H_ROLE_DB)
check("有效签名 role=9 payload 仍可读身份", r.status_code == 200, r.text[:120])
r = client.get("/api/admin/ops/dashboard", headers=H_ROLE_DB)
check("role 从 DB 读：payload 9 实际普通用户 → 后台 403", r.status_code == 403,
      r.text[:120])

print("== 输入校验：分页 size 上限 ==")
r = client.get("/api/content/articles", params={"size": 10000})
check("articles size=10000 被拒（≤100）", r.status_code == 422, r.text[:120])
r = client.get("/api/content/reviews",
               params={"product_id": IDS["p"], "size": 10000})
check("reviews size=10000 被拒（≤100）", r.status_code == 422, r.text[:120])

print("== 登录：401 文案统一（防枚举） ==")
r = client.post("/api/account/login",
                json={"email": "dave@glowmail.dev", "password": "davepass1234"})
check("禁用账户 401 文案不泄露状态", r.status_code == 401
      and r.json().get("detail") == "invalid credentials", r.text[:120])
r = client.post("/api/account/login",
                json={"email": "nobody@glowmail.dev", "password": "whatever1"})
check("不存在用户与禁用用户文案一致", r.status_code == 401
      and r.json().get("detail") == "invalid credentials", r.text[:120])

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
