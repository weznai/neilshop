"""运营智能体 C 自测 —— worker 日报 daily_digest + 商品多语言 translations
（GM_DB=sqlite:///test_dg.sqlite 独立库；BigInteger 垫片抄 test_payments.py）"""

import logging
import os
import sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_dg.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient

from app.core.db import SessionLocal, init_db, utcnow
from app.core.enums import OrderStatus, PaymentStatus, RmaStatus
from app.core.security import create_token, hash_password
from app.main import app
from app.models import (
    Cart, Category, Exchange, Order, OrderItem, OutboxEvent, Payment, Product,
    ProductTranslation, Review, Rma, Setting, Ticket, UgcSubmission, User, Variant,
)
from app.services import emails
import worker

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


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


cap = _Capture()
for _name in ("glowmag.emails", "glowmag.worker"):
    _lg = logging.getLogger(_name)
    _lg.setLevel(logging.INFO)
    _lg.addHandler(cap)

ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US", "phone": "+14155550001"}

init_db()
s = SessionLocal()
now = utcnow()
yday = now - timedelta(days=1)
y_start = datetime(yday.year, yday.month, yday.day)
y_at = y_start + timedelta(hours=10)

cat = Category(slug="press-on-nails", name="Press-on Nails")
s.add(cat)
s.flush()
prods = {}
for slug, title, sub, price, stock, desc in [
    ("bare-gems", "Bare Gems", "Nude base with crystal accents", 1599, 50,
     "**Bare Gems** — english description"),
    ("french-kiss", "French Kiss", "The timeless french tip", 1499, 3,
     "**French Kiss** — english description"),
    ("venus", "Venus", "Pearl chrome masterpiece", 1999, 8,
     "**Venus** — english description"),
    ("ma-damn", "Ma Damn", "Classic red creme, instant icon", 1599, 20,
     "**Ma Damn** — english description"),
]:
    p = Product(slug=slug, title=title, subtitle=sub, description_md=desc,
                category_id=cat.id, status=1, hero_image=f"https://img/{slug}.jpg",
                price_min=price, price_max=price, published_at=now - timedelta(days=30))
    s.add(p)
    s.flush()
    prods[slug] = (p, Variant(product_id=p.id, sku=f"{slug[:3].upper()}-24",
                              option1_value="Short Almond", option2_value="24 pcs",
                              price=price, stock=stock, safety_stock=5))
    s.add(prods[slug][1])
s.flush()
vmap = {slug: v for slug, (p, v) in prods.items()}
pmap = {slug: p for slug, (p, v) in prods.items()}

admin = User(email="ops@glow.test", name="Ops", role=2, status=1,
             password_hash=hash_password("x"))
customer = User(email="cindy@glow.test", name="Cindy", role=0, status=1,
                password_hash=hash_password("x"))
newbie = User(email="new@glow.test", name="New", role=0, status=1,
              password_hash=hash_password("x"), created_at=y_at)
s.add_all([admin, customer, newbie])
s.flush()


def add_order(no, status, placed, paid, lines):
    total = sum(price * q for _, price, q in lines)
    o = Order(order_no=no, user_id=customer.id, email=customer.email, status=status,
              subtotal=total, grand_total=total, shipping_address=ADDR,
              placed_at=placed, paid_at=paid)
    s.add(o)
    s.flush()
    for slug, price, q in lines:
        s.add(OrderItem(order_id=o.id, variant_id=vmap[slug].id, product_slug=slug,
                        title_snapshot=f"{pmap[slug].title} · Short Almond", qty=q,
                        unit_price=price, subtotal=price * q))
    s.flush()
    return o


o1 = add_order("NSDG26080001", int(OrderStatus.PAID), y_at, y_at + timedelta(minutes=5),
               [("bare-gems", 1599, 2)])
o2 = add_order("NSDG26080002", int(OrderStatus.PAID), y_at, y_at + timedelta(minutes=6),
               [("french-kiss", 1499, 1), ("venus", 1999, 1)])
o3 = add_order("NSDG26080003", int(OrderStatus.REFUNDED),
               now - timedelta(days=3), now - timedelta(days=3), [("ma-damn", 1599, 1)])
s.add_all([
    Payment(order_id=o1.id, amount=3198, status=int(PaymentStatus.SUCCESS), created_at=y_at),
    Payment(order_id=o2.id, amount=3498, status=int(PaymentStatus.SUCCESS), created_at=y_at),
    Payment(order_id=o3.id, amount=1599, status=int(PaymentStatus.REFUNDED),
            refunded_amount=1599, created_at=now - timedelta(days=3)),
])
s.add(Rma(rma_no="RMA1", order_id=o3.id,
          order_item_id=s.query(OrderItem).filter(OrderItem.order_id == o3.id).first().id,
          qty=1, reason=3, status=int(RmaStatus.REFUNDED), refund_amount=1599,
          refunded_at=y_at + timedelta(hours=1)))
s.add(Rma(rma_no="RMA2", order_id=o3.id, order_item_id=0, qty=1, reason=1,
          status=int(RmaStatus.REQUESTED)))
s.add(Exchange(exchange_no="EX1", order_id=o3.id, order_item_id=0,
               old_variant_id=vmap["bare-gems"].id, new_variant_id=vmap["venus"].id,
               status=0))
s.add(Review(product_id=pmap["ma-damn"].id, user_id=customer.id, order_item_id=0,
             rating=5, content="nice", status=0))
s.add(UgcSubmission(user_id=customer.id, image_url="https://img/ugc.jpg", status=0))
s.add(Ticket(ticket_no="TK1", user_id=customer.id, email=customer.email,
             category=1, subject="where is my order", status=0))
s.add(Cart(session_id="tok-ab", email="ab@glow.test",
           items=[{"variantId": vmap["bare-gems"].id, "qty": 1}], updated_at=y_at))
s.add(Cart(session_id="tok-empty", email="e@glow.test", items=[], updated_at=y_at))
add_order("NSDG26080004", int(OrderStatus.PENDING), now, None, [("ma-damn", 1599, 1)])
s.commit()

target_date = (now - timedelta(days=1)).date().isoformat()


def email_logs():
    return [m for m in cap.msgs if m.startswith("[EMAIL]")]


# ===== daily_digest 单任务（直调函数） =====
worker.daily_digest(s)
s.expire_all()
digest_mails = [m for m in email_logs() if "GLOWMAG Daily Digest" in m]
check("日报发送：ops@glowmag.com 收到 1 封（默认收件人）subject=GLOWMAG Daily Digest — date",
      len(digest_mails) == 1 and f"to=ops@glowmag.com" in digest_mails[0]
      and f"GLOWMAG Daily Digest — {target_date}" in digest_mails[0], digest_mails)
check("日报不走 outbox（直接 deliver）",
      s.query(OutboxEvent).filter(OutboxEvent.event_type.like("%digest%")).count() == 0
      and s.query(OutboxEvent).count() == 0)
wm = s.get(Setting, "digest_last_date")
check("水位写回：settings.digest_last_date = 昨日",
      wm is not None and str(wm.value) == target_date, None if wm is None else wm.value)
check("日报内容：GMV $66.96（3198+3498 昨日 paid）",
      "$66.96" in digest_mails[0] and "$15.99" in digest_mails[0], "")
check("日报内容：退款 1 笔 + 新用户 1 + 弃购新增 1",
      ">1</td>" in digest_mails[0] and "New users" in digest_mails[0]
      and "New abandoned carts" in digest_mails[0], "")
check("日报内容：Top3 商品名（Bare Gems 2 sold / French Kiss / Venus）",
      "Bare Gems" in digest_mails[0] and "2 sold" in digest_mails[0]
      and "French Kiss" in digest_mails[0] and "Venus" in digest_mails[0], "")
check("日报内容：待办清单 6 行各计数 1（订单/RMA/换货/评价/UGC/工单）",
      all(name in digest_mails[0] for name in
          ("Pending orders", "RMA to review", "Exchanges to review",
           "Reviews to moderate", "UGC to moderate", "Open tickets"))
      and digest_mails[0].count("</tr>") >= 13, "")
check("日报内容：库存预警 stock≤8 计 2（french 3 / venus 8）+ 页脚 Unsubscribe",
      "Low stock alerts (stock &le; 8): <strong>2</strong>" in digest_mails[0]
      and "Unsubscribe" in digest_mails[0], "")
check("日志行 [daily-digest] date=/sent=1",
      any(f"[daily-digest] date={target_date} sent=1" in m for m in cap.msgs), "")

before = len(email_logs())
worker.daily_digest(s)
check("水位去重：二次跑不重复发送",
      len(email_logs()) == before
      and str(s.get(Setting, "digest_last_date").value) == target_date)

# ===== translations：前台读取 =====
for slug, zh_title in [("bare-gems", "裸钻"), ("french-kiss", "法式之吻"),
                       ("venus", "维纳斯猫眼睫毛")]:
    s.add(ProductTranslation(product_id=pmap[slug].id, locale="zh-CN", title=zh_title,
                             subtitle=f"{zh_title}副标题", description_md=f"**{zh_title}** 中文描述"))
s.commit()

with TestClient(app) as client:
    r = client.get("/api/catalog/products/bare-gems", params={"locale": "zh-CN"})
    d = r.json()
    check("详情 zh-CN：title/subtitle/description_md 替换 + locale 键 + 价格结构不变",
          r.status_code == 200 and d["title"] == "裸钻" and d["subtitle"] == "裸钻副标题"
          and d["description_md"] == "**裸钻** 中文描述" and d["locale"] == "zh-CN"
          and d["price_min"] == 1599 and d["price_max"] == 1599, d.get("title"))
    r = client.get("/api/catalog/products/ma-damn", params={"locale": "zh-CN"})
    d = r.json()
    check("无翻译回退英文 + locale=en-US",
          d["title"] == "Ma Damn" and d["description_md"].startswith("**Ma Damn**")
          and d["locale"] == "en-US", d.get("locale"))
    r = client.get("/api/catalog/products/bare-gems")
    d = r.json()
    check("不带 locale：响应结构零变化（无 locale 键，英文原文）",
          "locale" not in d and d["title"] == "Bare Gems", d.keys())
    r = client.get("/api/catalog/products", params={"locale": "zh-CN", "size": 100})
    items = {i["slug"]: i for i in r.json()["items"]}
    check("列表 zh-CN：有翻译卡片 title/subtitle 换、无翻译保持英文",
          items["bare-gems"]["title"] == "裸钻" and items["bare-gems"]["subtitle"] == "裸钻副标题"
          and items["venus"]["title"] == "维纳斯猫眼睫毛"
          and items["ma-damn"]["title"] == "Ma Damn"
          and items["ma-damn"]["subtitle"] == "Classic red creme, instant icon",
          (items["bare-gems"]["title"], items["ma-damn"]["title"]))

    # ===== translations：管理端点 =====
    atok = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}
    ctok = {"Authorization": f"Bearer {create_token(customer.id, customer.role)}"}
    md_id = pmap["ma-damn"].id
    check("PUT 守卫：未登录 401",
          client.put(f"/api/admin/catalog/products/{md_id}/translations",
                     json={"locale": "zh-CN", "title": "玛丹"}).status_code == 401)
    check("PUT 守卫：顾客 403",
          client.put(f"/api/admin/catalog/products/{md_id}/translations",
                     headers=ctok, json={"locale": "zh-CN", "title": "玛丹"}).status_code == 403)
    check("非法 locale（zh_cn / zh / 123）→ 422",
          client.put(f"/api/admin/catalog/products/{md_id}/translations",
                     headers=atok, json={"locale": "zh_cn", "title": "玛丹"}).status_code == 422
          and client.put(f"/api/admin/catalog/products/{md_id}/translations",
                         headers=atok, json={"locale": "zh", "title": "玛丹"}).status_code == 422
          and client.put(f"/api/admin/catalog/products/{md_id}/translations",
                         headers=atok, json={"locale": "123", "title": "玛丹"}).status_code == 422)

    r = client.put(f"/api/admin/catalog/products/{md_id}/translations",
                   headers=atok, json={"locale": "zh-CN", "title": "玛丹",
                                       "subtitle": "经典红哑光", "description_md": "**玛丹** 中文"})
    d = r.json()
    check("admin PUT upsert 新建 zh-CN",
          r.status_code == 200 and d["locale"] == "zh-CN" and d["title"] == "玛丹"
          and s.query(ProductTranslation).filter(
              ProductTranslation.product_id == md_id,
              ProductTranslation.locale == "zh-CN").count() == 1, d)
    r = client.put(f"/api/admin/catalog/products/{md_id}/translations",
                   headers=atok, json={"locale": "zh-CN", "title": "玛丹·红丝绒"})
    d = r.json()
    s.expire_all()
    row = s.query(ProductTranslation).filter(
        ProductTranslation.product_id == md_id, ProductTranslation.locale == "zh-CN").first()
    check("admin PUT 二次改：title 更新且仍 1 行（subtitle 未传保留）",
          d["title"] == "玛丹·红丝绒" and row.subtitle == "经典红哑光"
          and s.query(ProductTranslation).filter(
              ProductTranslation.product_id == md_id).count() == 1, d)
    r = client.get(f"/api/admin/catalog/products/{md_id}/translations", headers=atok)
    check("admin GET translations：该商品全部翻译",
          r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["locale"] == "zh-CN"
          and r.json()[0]["title"] == "玛丹·红丝绒", r.json())
    check("admin GET translations 守卫：顾客 403",
          client.get(f"/api/admin/catalog/products/{md_id}/translations",
                     headers=ctok).status_code == 403)
    r = client.get("/api/catalog/products/ma-damn", params={"locale": "zh-CN"})
    check("upsert 后前台详情读到新翻译",
          r.json()["title"] == "玛丹·红丝绒" and r.json()["locale"] == "zh-CN", r.json().get("title"))
    r = client.delete(f"/api/admin/catalog/products/{md_id}/translations/zh-CN",
                      headers=atok)
    check("admin DELETE → deleted=1 且前台回退 en-US",
          r.status_code == 200 and r.json()["deleted"] == 1
          and client.get("/api/catalog/products/ma-damn",
                         params={"locale": "zh-CN"}).json()["locale"] == "en-US", r.json())
    check("admin DELETE 不存在的 locale → deleted=0（幂等）",
          client.delete(f"/api/admin/catalog/products/{md_id}/translations/ja-JP",
                        headers=atok).json()["deleted"] == 0)
    check("admin 端点 404：未知商品",
          client.get("/api/admin/catalog/products/999999/translations",
                     headers=atok).status_code == 404)

s.close()
print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
