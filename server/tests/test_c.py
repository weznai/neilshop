import os
import sys
from datetime import timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)

import pymysql

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute("DROP DATABASE IF EXISTS glowmag_test_c")
    _cur.execute("CREATE DATABASE glowmag_test_c CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag_test_c?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话

from fastapi.testclient import TestClient

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


from app.core.db import SessionLocal, init_db, utcnow
from app.core.security import create_token, hash_password
from app.main import app
from app.services import promo_rules

promo_rules.utcnow = lambda: utcnow().replace(tzinfo=None)
from app.models import (
    Article,
    Cart,
    CookieConsent,
    DiscountCode,
    Faq,
    GiftCard,
    NewsletterSubscriber,
    Order,
    OrderItem,
    PointsLedger,
    PopupConfig,
    Product,
    ReplyTemplate,
    Setting,
    Variant,
)
from app.models.user import User

PASSED = 0


def check(name, cond):
    global PASSED
    assert cond, f"FAIL: {name}"
    PASSED += 1
    print(f"  ok {PASSED:02d} - {name}")


init_db()
db = SessionLocal()

admin = User(email="ops@glowmag.test", name="Ops Admin", role=2, status=1, password_hash=hash_password("x"))
customer = User(email="cindy@glowmag.test", name="Cindy Smith", role=0, status=1, points=500, password_hash=hash_password("x"))
db.add_all([admin, customer])
db.flush()

product = Product(slug="bare-gems", title="Bare Gems", category_id=1, status=1,
                  price_min=1999, price_max=1999, hero_image="/img.jpg", sold_count=7)
db.add(product)
db.flush()
variant = Variant(product_id=product.id, sku="BG-SA-24", option1_value="Short Almond",
                  option2_value="24pcs", price=1999, stock=3)
db.add(variant)

db.add_all([
    DiscountCode(code="WELCOME20", name="新客20%", type=1, value=20, max_discount=1000,
                 min_subtotal=0, per_user_limit=1, first_order_only=0, is_active=1,
                 starts_at=utcnow() - timedelta(days=1)),
    GiftCard(code="GC-TEST", initial_amount=5000, balance=3499, status=1,
             purchaser_email="buyer@glowmag.test", expires_at=utcnow() + timedelta(days=365)),
    GiftCard(code="GC-INACT", initial_amount=1000, balance=1000, status=0,
             purchaser_email="buyer@glowmag.test"),
    PopupConfig(scene="welcome", title="Welcome to GLOWMAG", content_md="**10% off**",
                coupon_code="WELCOME20", trigger_rules={"delaySec": 3},
                start_at=utcnow() - timedelta(hours=1), end_at=utcnow() + timedelta(hours=1), active=1),
    Faq(category=1, question="How to choose size?", answer_md="Measure first.", sort_order=2, active=1),
    Faq(category=1, question="Are they reusable?", answer_md="Yes, up to 2 weeks.", sort_order=1, active=1),
    Faq(category=3, question="When will it ship?", answer_md="Within 24h.", sort_order=1, active=1),
    Faq(category=2, question="hidden one", answer_md="x", sort_order=1, active=0),
    Article(slug="nail-care-101", title="Nail Care 101", cover="/cover.jpg",
            content_md="# Heading\n" + "glow tips " * 40, author="Maya Chen",
            tags=["care", "howto"], status=1, published_at=utcnow() - timedelta(days=1)),
    Article(slug="draft-post", title="Draft", content_md="secret", author="Team GLOWMAG", status=0),
    Setting(key="free_shipping_threshold", value=3500),
    ReplyTemplate(category=1, title="物流查询模板", content="您的包裹已发出", active=1),
    NewsletterSubscriber(email="news@glowmag.test", source="footer"),
    CookieConsent(session_id="s-1"),
    Cart(session_id="cart-old", items=[{"variantId": 1, "qty": 1}],
          updated_at=utcnow() - timedelta(hours=30)),
])

order = Order(order_no="NS260815TEST1", user_id=customer.id, email=customer.email, status=5,
              subtotal=1999, grand_total=1999, shipping_address={},
              placed_at=utcnow(), paid_at=utcnow())
db.add(order)
db.flush()
item1 = OrderItem(order_id=order.id, variant_id=variant.id, product_slug="bare-gems",
                  title_snapshot="Bare Gems · Short Almond", qty=1, unit_price=1999, subtotal=1999)
db.add(item1)

order2 = Order(order_no="NS260814TEST2", user_id=customer.id, email=customer.email, status=4,
               subtotal=1999, grand_total=1999, shipping_address={},
               placed_at=utcnow() - timedelta(days=1), paid_at=utcnow() - timedelta(days=1))
db.add(order2)
db.flush()
item2 = OrderItem(order_id=order2.id, variant_id=variant.id, product_slug="bare-gems",
                  title_snapshot="Bare Gems · Short Almond", qty=1, unit_price=1999, subtotal=1999)
db.add(item2)

db.add_all([
    PointsLedger(user_id=customer.id, change=300, reason=1, balance_after=300,
                 ref_type="order", ref_id=order.id, frozen=1,
                 expires_at=utcnow() + timedelta(days=60), created_at=utcnow() - timedelta(days=3)),
    PointsLedger(user_id=customer.id, change=200, reason=4, balance_after=500, frozen=0,
                 expires_at=utcnow() + timedelta(days=10), created_at=utcnow() - timedelta(days=2)),
    PointsLedger(user_id=customer.id, change=100, reason=6, balance_after=600, frozen=0,
                 expires_at=utcnow() + timedelta(days=45), created_at=utcnow() - timedelta(days=1)),
    PointsLedger(user_id=customer.id, change=-100, reason=7, balance_after=500, frozen=0,
                 created_at=utcnow() - timedelta(hours=12)),
])
db.commit()

ADMIN_H = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}
CUST_H = {"Authorization": f"Bearer {create_token(customer.id, customer.role)}"}

with TestClient(app) as client:
    print("promo")
    r = client.post("/api/promo/validate", json={"code": "WELCOME20", "subtotal_cents": 5000})
    check("validate 正码 20% 封顶 $10", r.status_code == 200 and r.json()["valid"] is True
          and r.json()["discount_cents"] == 1000 and r.json()["reason"] == "")
    r = client.post("/api/promo/validate", json={"code": "WELCOME20", "subtotal_cents": 3000})
    check("validate 正码 未触顶 20%", r.json()["valid"] is True and r.json()["discount_cents"] == 600)
    r = client.post("/api/promo/validate", json={"code": "NOPE", "subtotal_cents": 5000})
    check("validate 误码中文 reason", r.json()["valid"] is False and r.json()["reason"] == "折扣码不存在")
    r = client.post("/api/promo/giftcard", json={"code": "GC-TEST"})
    check("giftcard 有效性/余额", r.status_code == 200 and r.json()["balance_cents"] == 3499
          and r.json()["status"] == 1 and r.json()["expires_at"])
    r = client.post("/api/promo/giftcard", json={"code": "GC-INACT"})
    check("giftcard 未激活 404 invalid_card", r.status_code == 404 and r.json()["detail"] == "invalid_card")
    r = client.post("/api/promo/giftcard", json={"code": "GC-VOID-XX"})
    check("giftcard 不存在 404", r.status_code == 404)
    r = client.get("/api/promo/popup", params={"scene": "welcome"})
    check("popup 命中", r.status_code == 200 and r.json()["title"] == "Welcome to GLOWMAG"
          and r.json()["coupon_code"] == "WELCOME20")
    r = client.get("/api/promo/popup", params={"scene": "exit_intent"})
    check("popup 无配置 204", r.status_code == 204)

    print("points")
    r = client.get("/api/points")
    check("points 未登录 401", r.status_code == 401)
    r = client.get("/api/points", headers=CUST_H)
    check("points 三数 balance/frozen/usable", r.json() == {"balance": 500, "frozen": 300, "usable": 200})
    r = client.get("/api/points/ledger", headers=CUST_H)
    data = r.json()
    check("ledger 分页总数+倒序", data["total"] == 4 and data["page"] == 1
          and data["items"][0]["reason"] == "消费扣除")
    frozen_rows = [i for i in data["items"] if i["frozen"] == 1]
    check("ledger 冻结标注+文案映射", len(frozen_rows) == 1
          and frozen_rows[0]["reason"] == "下单获得（冻结中）")
    r = client.get("/api/points/expiring", headers=CUST_H)
    items = r.json()["items"]
    check("expiring 仅 30 天内未冻结正积分", len(items) == 1 and items[0]["change"] == 200)

    print("content: faq/article")
    r = client.get("/api/content/faqs")
    check("faqs 仅 active", len(r.json()) == 3)
    r = client.get("/api/content/faqs", params={"category": 1})
    faqs = r.json()
    check("faqs 按 sort_order", len(faqs) == 2 and faqs[0]["question"] == "Are they reusable?")
    r = client.get("/api/content/articles")
    data = r.json()
    check("articles 已发布+摘要120", data["total"] == 1 and len(data["items"][0]["summary"]) <= 120
          and data["items"][0]["tags"] == ["care", "howto"])
    r = client.get("/api/content/articles", params={"tag": "care"})
    check("articles tag 过滤命中", r.json()["total"] == 1)
    r = client.get("/api/content/articles", params={"tag": "nope"})
    check("articles tag 过滤未命中", r.json()["total"] == 0)
    r = client.get("/api/content/articles/nail-care-101")
    check("article 详情全文", r.status_code == 200 and r.json()["content_md"].startswith("# Heading"))
    r = client.get("/api/content/articles/draft-post")
    check("article 草稿 404", r.status_code == 404)

    print("dashboard（造数后）")
    r = client.get("/api/admin/ops/dashboard", headers=CUST_H)
    check("dashboard 非管理员 403", r.status_code == 403)
    r = client.get("/api/admin/ops/dashboard", headers=ADMIN_H)
    d = r.json()
    check("dashboard 今日 GMV/订单", d["today"]["gmv_cents"] == 1999 and d["today"]["orders"] == 1)
    check("dashboard 7/30 日窗口", d["last7"]["orders"] == 2 and d["last30"]["orders"] == 2)
    check("dashboard 漏斗兜底 approximate", d["funnel"]["approximate"] is True
          and d["funnel"]["views"] == 2 and d["funnel"]["orders"] == 1 and d["funnel"]["paid"] == 1)
    check("dashboard 运营计数", d["pending_orders"] == 0 and d["low_stock"] >= 1
          and d["pending_reviews"] == 0 and d["open_tickets"] == 0 and d["abandoned_carts"] == 1)
    check("dashboard top_products", d["top_products"][0]["slug"] == "bare-gems")

    print("content: review 流程")
    r = client.post("/api/content/reviews", headers=CUST_H, json={
        "order_no": "NS260815TEST1", "order_item_id": item1.id, "rating": 5,
        "content": "Love these!", "images": ["https://cdn/1.jpg"]})
    check("review 提交待审", r.status_code == 200 and r.json()["status"] == 0)
    review_id = r.json()["id"]
    r = client.post("/api/content/reviews", headers=CUST_H, json={
        "order_no": "NS260815TEST1", "order_item_id": item1.id, "rating": 4, "content": "dup"})
    check("review 重复 409", r.status_code == 409)
    r = client.post("/api/content/reviews", headers=CUST_H, json={
        "order_no": "NS9999999999", "order_item_id": item1.id, "rating": 5})
    check("review 非本人/不存在订单 404", r.status_code == 404)
    r = client.get("/api/content/reviews", params={"product_id": product.id})
    check("前台评价过审前不可见", r.json()["total"] == 0)
    r = client.get("/api/admin/ops/reviews", params={"status": 0}, headers=ADMIN_H)
    check("后台待审队列", r.json()["total"] == 1 and r.json()["items"][0]["id"] == review_id)
    r = client.post(f"/api/admin/ops/reviews/{review_id}/approve", headers=ADMIN_H)
    check("review 过审", r.status_code == 200 and r.json()["status"] == 1)
    db.expire_all()
    p = db.get(Product, product.id)
    check("过审重算 rating_avg/count", p.rating_avg == 500 and p.rating_count == 1)
    r = client.get("/api/content/reviews", params={"product_id": product.id})
    data = r.json()
    check("前台评价可见+昵称脱敏", data["total"] == 1 and data["items"][0]["user_name"] == "C***h"
          and data["items"][0]["rating"] == 5)
    r = client.post("/api/content/reviews", headers=CUST_H, json={
        "order_no": "NS260814TEST2", "order_item_id": item2.id, "rating": 2, "content": "meh"})
    reject_id = r.json()["id"]
    r = client.post(f"/api/admin/ops/reviews/{reject_id}/reject", headers=ADMIN_H,
                    json={"reason": "违规内容"})
    check("review 拒绝", r.status_code == 200 and r.json()["status"] == 2)
    db.expire_all()
    p = db.get(Product, product.id)
    check("拒绝后 rating 只统计过审", p.rating_avg == 500 and p.rating_count == 1)
    r = client.post(f"/api/admin/ops/reviews/{review_id}/approve", headers=ADMIN_H)
    check("重复审核 409", r.status_code == 409)

    print("content: ugc 流程")
    r = client.post("/api/content/ugc", json={"image_url": "https://cdn/anon.jpg",
                                              "caption": "anon look", "instagram_handle": "@anon"})
    check("ugc 匿名投稿待审", r.status_code == 200 and r.json()["status"] == 0)
    anon_ugc_id = r.json()["id"]
    r = client.post("/api/content/ugc", headers=CUST_H, json={
        "image_url": "https://cdn/cindy.jpg", "caption": "my glow", "related_product_id": product.id})
    check("ugc 登录投稿待审", r.status_code == 200 and r.json()["status"] == 0)
    ugc_id = r.json()["id"]
    r = client.post(f"/api/admin/ops/ugc/{ugc_id}/approve", headers=ADMIN_H)
    check("ugc 过审+奖励100", r.status_code == 200 and r.json()["points_rewarded"] == 100)
    r = client.get("/api/points", headers=CUST_H)
    check("ugc 奖励入账 balance=600", r.json()["balance"] == 600)
    r = client.get("/api/points/ledger", headers=CUST_H)
    check("ugc 账务流水 reason=12", r.json()["items"][0]["reason"] == "买家秀奖励"
          and r.json()["items"][0]["change"] == 100 and r.json()["items"][0]["balance_after"] == 600)
    r = client.post(f"/api/admin/ops/ugc/{ugc_id}/approve", headers=ADMIN_H)
    check("ugc 重复审核 409（不重复发分）", r.status_code == 409)
    r = client.post(f"/api/admin/ops/ugc/{anon_ugc_id}/reject", headers=ADMIN_H)
    check("ugc 拒绝（匿名无积分）", r.status_code == 200 and r.json()["status"] == 2)
    r = client.get("/api/admin/ops/ugc", params={"status": 1}, headers=ADMIN_H)
    check("ugc 队列按状态过滤", len(r.json()["items"]) == 1)

    print("support: 工单")
    r = client.post("/api/support/tickets", json={
        "email": customer.email, "category": 1, "subject": "Where is my parcel?",
        "content": "It has been 10 days."})
    check("工单创建 TK 单号", r.status_code == 200 and r.json()["ticket_no"].startswith("TK")
          and len(r.json()["ticket_no"]) == 12 and r.json()["status"] == 0)
    ticket_no = r.json()["ticket_no"]
    r = client.get("/api/support/tickets", params={"email": customer.email}, headers=CUST_H)
    data = r.json()["items"]
    check("我的工单含首条留言", len(data) == 1 and len(data[0]["messages"]) == 1
          and data[0]["messages"][0]["sender"] == 1)
    r = client.post(f"/api/support/tickets/{ticket_no}/messages",
                    json={"email": customer.email, "content": "any update?"})
    check("工单追加留言", r.status_code == 200)
    r = client.post(f"/api/support/tickets/{ticket_no}/messages",
                    json={"email": "hacker@evil.com", "content": "give me"})
    check("工单非归属 email 403", r.status_code == 403)
    r = client.get("/api/support/templates", params={"category": 1})
    check("模板列表", len(r.json()) == 1 and r.json()[0]["title"] == "物流查询模板")

    print("admin: 工单处理")
    r = client.get("/api/admin/ops/tickets", params={"q": "cindy"}, headers=ADMIN_H)
    check("工单队列 q 检索", r.json()["total"] == 1 and r.json()["items"][0]["ticket_no"] == ticket_no)
    r = client.post(f"/api/admin/ops/tickets/{ticket_no}/reply", headers=ADMIN_H,
                    json={"content": "Tracking: 1Z999. It is arriving tomorrow."})
    check("管理员回复 status→1+首回复时间", r.status_code == 200 and r.json()["status"] == 1
          and r.json()["first_reply_at"])
    r = client.post(f"/api/admin/ops/tickets/{ticket_no}/assign", headers=ADMIN_H,
                    json={"admin_id": admin.id})
    check("工单指派", r.status_code == 200 and r.json()["assignee_admin_id"] == admin.id)
    r = client.get("/api/support/tickets", params={"email": customer.email}, headers=CUST_H)
    msgs = r.json()["items"][0]["messages"]
    check("留言时间序 1/1/2", [m["sender"] for m in msgs] == [1, 1, 2])
    r = client.post(f"/api/admin/ops/tickets/{ticket_no}/close", headers=ADMIN_H,
                    json={"close_reason": 1})
    check("工单关闭 4+closed_at", r.status_code == 200 and r.json()["status"] == 4
          and r.json()["closed_at"])
    r = client.post(f"/api/support/tickets/{ticket_no}/messages",
                    json={"email": customer.email, "content": "closed?"})
    check("关闭后用户留言 409", r.status_code == 409)

    print("admin: 折扣码 CRUD")
    r = client.post("/api/admin/ops/discounts", headers=ADMIN_H, json={
        "code": "save10", "type": 2, "value": 1000, "starts_at": "2026-01-01T00:00:00Z"})
    check("折扣码创建大写化", r.status_code == 200 and r.json()["code"] == "SAVE10")
    dc_id = r.json()["id"]
    r = client.post("/api/admin/ops/discounts", headers=ADMIN_H, json={
        "code": "SAVE10", "type": 2, "value": 100, "starts_at": "2026-01-01T00:00:00Z"})
    check("折扣码重复 409", r.status_code == 409)
    r = client.post("/api/promo/validate", json={"code": "SAVE10", "subtotal_cents": 5000})
    check("新码即时可校验", r.json()["valid"] is True and r.json()["discount_cents"] == 1000)
    r = client.put(f"/api/admin/ops/discounts/{dc_id}", headers=ADMIN_H, json={"value": 500})
    check("折扣码更新", r.status_code == 200 and r.json()["value"] == 500)
    r = client.post("/api/promo/validate", json={"code": "SAVE10", "subtotal_cents": 5000})
    check("更新后校验生效", r.json()["discount_cents"] == 500)
    r = client.post(f"/api/admin/ops/discounts/{dc_id}/toggle", headers=ADMIN_H)
    check("折扣码停用", r.status_code == 200 and r.json()["is_active"] == 0)
    r = client.post("/api/promo/validate", json={"code": "SAVE10", "subtotal_cents": 5000})
    check("停用后校验拒绝", r.json()["valid"] is False)
    r = client.get("/api/admin/ops/discounts", headers=ADMIN_H, params={"page": 1})
    check("折扣码列表分页", r.json()["total"] == 2 and r.json()["page"] == 1)

    print("admin: 弹窗 CRUD")
    r = client.post("/api/admin/ops/popups", headers=ADMIN_H, json={
        "scene": "exit_intent", "title": "Wait!", "coupon_code": "BYE2025", "active": 1})
    check("弹窗创建", r.status_code == 200 and r.json()["active"] == 1)
    popup_id = r.json()["id"]
    r = client.put(f"/api/admin/ops/popups/{popup_id}", headers=ADMIN_H, json={"title": "Wait!!"})
    check("弹窗更新", r.status_code == 200 and r.json()["title"] == "Wait!!")
    db.expire_all()
    pp = db.get(PopupConfig, popup_id)
    pp.stats_shown = 5
    db.commit()
    r = client.post(f"/api/admin/ops/popups/{popup_id}/toggle", headers=ADMIN_H)
    check("弹窗 toggle 保留 stats", r.status_code == 200 and r.json()["active"] == 0
          and r.json()["stats_shown"] == 5)
    r = client.get("/api/promo/popup", params={"scene": "exit_intent"})
    check("停用后前台 204", r.status_code == 204)

    print("admin: settings/members/logs")
    r = client.put("/api/admin/ops/settings", headers=ADMIN_H,
                   json={"key": "ops_test_flag", "value": {"v": 1}})
    check("settings upsert 新键", r.status_code == 200 and r.json()["value"] == {"v": 1})
    r = client.get("/api/admin/ops/settings", headers=ADMIN_H)
    kv = {s["key"]: s["value"] for s in r.json()["items"]}
    check("settings 旧值不受影响(checkout 免邮门槛)", kv.get("free_shipping_threshold") == 3500
          and kv.get("ops_test_flag") == {"v": 1})
    r = client.put("/api/admin/ops/settings", headers=ADMIN_H,
                   json={"key": "ops_test_flag", "value": 2})
    check("settings 二次 upsert 覆盖", r.json()["value"] == 2)
    r = client.get("/api/admin/ops/members", params={"q": "cindy"}, headers=ADMIN_H)
    data = r.json()
    check("members 检索", data["total"] == 1 and data["items"][0]["email"] == customer.email
          and data["items"][0]["points"] == 600 and data["items"][0]["risk_flag"] == 0)
    r = client.get(f"/api/admin/ops/members/{customer.id}", headers=ADMIN_H)
    check("members 详情含流水", r.status_code == 200 and len(r.json()["ledger"]) >= 5
          and r.json()["ledger"][0]["reason"] == "买家秀奖励")
    r = client.get("/api/admin/ops/members/99999", headers=ADMIN_H)
    check("members 不存在 404", r.status_code == 404)
    r = client.post(f"/api/admin/ops/members/{customer.id}/risk", headers=ADMIN_H, json={"flag": 1})
    check("members 风控开关", r.status_code == 200 and r.json()["risk_flag"] == 1)
    r = client.get("/api/admin/ops/logs", params={"entity": "discount"}, headers=ADMIN_H)
    check("logs 按 entity 过滤", r.json()["total"] >= 3
          and all(i["entity"] == "discount" for i in r.json()["items"]))
    r = client.get("/api/admin/ops/logs", headers=ADMIN_H)
    check("logs 倒序落库", r.json()["total"] >= 10
          and r.json()["items"][0]["id"] > r.json()["items"][-1]["id"])
    r = client.get("/api/admin/ops/logs", headers=CUST_H)
    check("logs 非管理员 403", r.status_code == 403)

print(f"\nALL PASS: {PASSED}/{PASSED}")
db.close()
