"""AI 域扩展自测 —— chat 兜底（空/超长钳制/注入不回显）+ 主题命中（运费 $35/退货 30 天/尺码）
+ 订单号脱敏 + hot size 钳制与下架过滤 + recommend cart_ids 钳制 + /chat 域内限流 429
（MySQL scratch 库 glowmag_test_w 共用惯例同 test_worker/test_e2e，DROP 重建）"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)

import pymysql

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute("DROP DATABASE IF EXISTS glowmag_test_w")
    _cur.execute("CREATE DATABASE glowmag_test_w CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag_test_w?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.enums import OrderStatus  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Faq, Order, Product, Setting, Shipment  # noqa: E402

PASSED = 0
FAILED = []


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok {PASSED:02d} - {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {PASSED + 1:02d} - {name}  {info}")


init_db()
db = SessionLocal()

# 商品：3 上架 + 1 下架（销量最高，hot 若漏过滤必排第一）
for slug, title, status, sold, best in [
    ("hot-a", "Hot A", 1, 500, 1),
    ("hot-b", "Hot B", 1, 300, 0),
    ("hot-c", "Hot C", 1, 100, 0),
    ("hot-e", "Hot E", 1, 50, 0),
    ("hot-f", "Hot F", 1, 40, 0),
    ("gone-d", "Gone D", 2, 9999, 1),
]:
    db.add(Product(slug=slug, title=title, category_id=1, status=status,
                   price_min=1999, price_max=1999, hero_image="/img.jpg",
                   sold_count=sold, is_best_seller=best))

# settings 与 seed 同口径（免邮门槛/运费/退货窗口）
for k, v in [("free_shipping_threshold", 3500), ("shipping_standard", 499),
             ("shipping_express", 1499), ("return_days", 30)]:
    db.add(Setting(key=k, value=v))

# FAQ：尺码/物流/退换 各一条（active=1）
for cat, q, a in [
    (1, "How do I find my nail size?", "Use the interactive sizer or printable chart."),
    (3, "When will my order ship?", "Packed within 24h, delivered in 3-6 business days (US)."),
    (4, "What's your return policy?", "30-day window on unopened sets."),
]:
    db.add(Faq(category=cat, question=q, answer_md=a, sort_order=1))

# 演示订单 + 运单（校验脱敏 tracking 尾号）
order = Order(order_no="NS2608AI0001", email="ai@glowmag.test",
              status=int(OrderStatus.SHIPPED), subtotal=1999, grand_total=2498,
              shipping_address={"city": "SF"})
db.add(order)
db.flush()
db.add(Shipment(shipment_no="SP2608AI01", order_id=order.id, carrier="usps",
                tracking_no="9400111899560000000042", status=2))
db.commit()
db.close()

client = TestClient(app)

# ---- chat 错误兜底 ----
r = client.post("/api/ai/chat", json={"message": ""})
j = r.json()
check("chat 空消息 200 且结构完整（intent/reply/suggestions）",
      r.status_code == 200 and {"intent", "reply", "suggestions"} <= set(j), r.text[:150])
check("空消息走 fallback 兜底话术（非通用 fallback 文案则失败）",
      j.get("intent") == "fallback" and j.get("reply"))

r = client.post("/api/ai/chat", json={"message": "   "})
check("chat 纯空白消息同空消息兜底",
      r.status_code == 200 and r.json()["intent"] == "fallback")

r = client.post("/api/ai/chat", json={"message": "a" * 5000})
check("chat 超长消息钳制（200 不 422/500）",
      r.status_code == 200 and r.json().get("reply"), r.status_code)

r = client.post("/api/ai/chat", json={"message": "<script>alert(1)</script> shipping cost"})
j = r.json()
check("chat 注入文本不回显原始标签",
      r.status_code == 200 and "<script>" not in j["reply"])

# ---- 主题命中（数据驱动增强） ----
r = client.post("/api/ai/chat", json={"message": "How much is shipping? is it free over 35?"})
j = r.json()
check("shipping 主题命中且含 $35.00 免邮门槛",
      j["intent"] == "shipping" and "$35.00" in j["reply"], j.get("reply", "")[:200])

r = client.post("/api/ai/chat", json={"message": "运费多少钱？多久能到"})
j = r.json()
check("中文运费主题命中门槛", j["intent"] == "shipping" and "$35.00" in j["reply"])

r = client.post("/api/ai/chat", json={"message": "How do I return an item?"})
j = r.json()
check("return 主题命中且含 30 天窗口与工单引导",
      j["intent"] == "return" and "30-day" in j["reply"] and "/contact" in j["reply"],
      j.get("reply", "")[:200])

r = client.post("/api/ai/chat", json={"message": "help me pick a size"})
j = r.json()
check("size 主题命中 FAQ（sizer 内容）",
      j["intent"] == "size" and "sizer" in j["reply"].lower())

# ---- 订单查询：脱敏 + 双因子（订单号+邮箱/登录）+ /track 引导 ----
r = client.post("/api/ai/chat", json={
    "message": "where is my order", "order_no": "NS2608AI0001",
    "email": "ai@glowmag.test"})
j = r.json()
check("order 命中（邮箱核验通过）且 data.tracking 只给尾号",
      j["intent"] == "order" and j["data"]["tracking"][0]["tracking_no_tail"] == "0042"
      and "9400111899560000000042" not in j["reply"])

r = client.post("/api/ai/chat", json={
    "message": "where is my order", "order_no": "NS2608AI0001"})
j = r.json()
check("仅订单号无邮箱 → 不回状态细节，引导 /track",
      j["intent"] == "order" and "/track" in j["reply"] and "data" not in j
      and "Shipped" not in j["reply"], j.get("reply", "")[:200])

r = client.post("/api/ai/chat", json={
    "message": "where is my order", "order_no": "NS2608AI0001",
    "email": "evil@glowmag.test"})
j = r.json()
check("订单号+错误邮箱 → 同样不回细节（防单号枚举）",
      j["intent"] == "order" and "/track" in j["reply"] and "data" not in j)

r = client.post("/api/ai/chat", json={"message": "track my order", "order_no": "<b>hack</b>"})
j = r.json()
check("order_no 非法自由文本不回显（引导到 /track）",
      j["intent"] == "order" and "<b>" not in j["reply"] and "/track" in j["reply"])

# ---- hot：size 钳制 + 下架过滤 + 排序 ----
r = client.get("/api/ai/hot", params={"size": 100})
check("hot size 超上限 422（le=20）", r.status_code == 422)

r = client.get("/api/ai/hot", params={"size": 2})
items = r.json()["items"]
check("hot 条数受 size 钳制", r.status_code == 200 and len(items) == 2)
check("hot 过滤下架商品（gone-d 不在结果）", all(i["slug"] != "gone-d" for i in items))
check("hot 排序 best 优先（hot-a 第一）", items and items[0]["slug"] == "hot-a")

# ---- recommend：超长 cart_ids 钳制回归 ----
r = client.get("/api/ai/recommend", params={
    "cart_ids": ",".join(["1", "2"] + [str(i) for i in range(10, 60)] + ["999"]), "size": 3})
items = r.json()["items"]
check("recommend 超长 cart_ids 正常返回且 ≤ size",
      r.status_code == 200 and len(items) == 3 and all(i["id"] not in (1, 2) for i in items))

# ---- /chat 域内限流 429 ----
from app.domains.ai import router as ai_router  # noqa: E402

_orig_limit = ai_router.CHAT_RATE_LIMIT
try:
    ai_router.CHAT_RATE_LIMIT = 2
    ai_router._rate_buckets.clear()
    c1 = client.post("/api/ai/chat", json={"message": "hi"})
    c2 = client.post("/api/ai/chat", json={"message": "hi"})
    c3 = client.post("/api/ai/chat", json={"message": "hi"})
    check("chat 限流：限值内 200、超出 429",
          c1.status_code == 200 and c2.status_code == 200 and c3.status_code == 429,
          f"{c1.status_code}/{c2.status_code}/{c3.status_code}")
    check("429 带 Retry-After 头且 detail=rate_limited",
          bool(c3.headers.get("retry-after")) and c3.json().get("detail") == "rate_limited")
finally:
    ai_router.CHAT_RATE_LIMIT = _orig_limit
    ai_router._rate_buckets.clear()

print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
