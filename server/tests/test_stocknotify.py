"""智能体 B 自测 —— 到货通知（stock_notifications 影子表激活）+ 商品定时上架
（GM_DB=sqlite:///test_sn.sqlite + 垫片：BigInteger→INTEGER / worker 任务直调避开 GET_LOCK）"""

import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DBF = ROOT / "test_sn.sqlite"
for suffix in ("", "-wal", "-shm"):
    _f = Path(str(DBF) + suffix)
    if _f.exists():
        _f.unlink()
os.environ["GM_DB"] = "sqlite:///" + str(DBF).replace("\\", "/")
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


from app.core.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Category, OutboxEvent, Product, Setting, StockNotification, User, Variant,
)

import worker  # noqa: E402

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
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(cap)


def email_logs():
    return [m for m in cap.msgs if m.startswith("[EMAIL]")]


init_db()
db = SessionLocal()
now = utcnow()

cat = Category(slug="press-on-nails", name="Press-on Nails")
db.add(cat)
db.flush()

p_past = Product(slug="bare-gems", title="Bare Gems", category_id=cat.id, status=1,
                 price_min=1599, price_max=1799, hero_image="/img/bare.jpg",
                 published_at=now - timedelta(days=2))
p_none = Product(slug="ma-damn", title="Ma Damn", category_id=cat.id, status=1,
                 price_min=1599, price_max=1599, hero_image="/img/ma.jpg",
                 published_at=None)
p_cherry = Product(slug="cherry-bomb", title="Cherry Bomb", category_id=cat.id, status=1,
                   price_min=1399, price_max=1599, hero_image="/img/cherry.jpg",
                   published_at=now - timedelta(days=2))
p_velvet = Product(slug="velvet-nights", title="Velvet Nights", category_id=cat.id, status=1,
                   price_min=1699, price_max=1899, hero_image="/img/velvet.jpg",
                   published_at=now + timedelta(days=7))
db.add_all([p_past, p_none, p_cherry, p_velvet])
db.flush()
v_in = Variant(product_id=p_past.id, sku="BG-SA-24", option1_value="Short Almond",
               option2_value="24 pcs", price=1599, stock=120)
v_sold = Variant(product_id=p_cherry.id, sku="CB-SA-24", option1_value="Short Almond",
                 option2_value="24 pcs", price=1399, stock=0)
v_sold2 = Variant(product_id=p_cherry.id, sku="CB-MS-24", option1_value="Medium Square",
                  option2_value="24 pcs", price=1599, stock=0)
v_none = Variant(product_id=p_none.id, sku="MD-SA-24", option1_value="Short Almond",
                 option2_value="24 pcs", price=1599, stock=56)
v_velvet = Variant(product_id=p_velvet.id, sku="VN-SA-24", option1_value="Short Almond",
                   option2_value="24 pcs", price=1699, stock=60)
db.add_all([v_in, v_sold, v_sold2, v_none, v_velvet])

admin = User(email="ops@glowmag.test", name="Ops Admin", role=2, status=1,
             password_hash=hash_password("x"))
db.add(admin)
db.commit()
H = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}

with TestClient(app) as client:
    # ============================================================
    print("\n== 到货通知 API ==")
    r = client.post("/api/catalog/stock-notify", json={"variant_id": v_in.id, "email": "a@b.co"})
    check("在库变体订阅 → 409 in_stock", r.status_code == 409 and r.json().get("detail") == "in_stock", r.text)

    r = client.post("/api/catalog/stock-notify", json={"variant_id": v_sold.id, "email": "emma@glow.test"})
    check("售罄变体订阅 → 201 watching:true", r.status_code == 201 and r.json() == {"watching": True}, r.text)

    r = client.post("/api/catalog/stock-notify", json={"variant_id": v_sold.id, "email": "EMMA@glow.test"})
    rows = db.query(StockNotification).filter(StockNotification.variant_id == v_sold.id).all()
    check("uk(variant,email) 幂等：重复订阅 200 且表内仅 1 行（email 归一小写）",
          r.status_code == 200 and r.json() == {"watching": True} and len(rows) == 1
          and rows[0].email == "emma@glow.test", (r.status_code, len(rows)))

    r = client.get("/api/catalog/stock-notify",
                   params={"variant_id": v_sold.id, "email": "emma@glow.test"})
    check("GET watching=true", r.status_code == 200 and r.json() == {"watching": True}, r.text)

    r = client.post("/api/catalog/stock-notify", json={"variant_id": v_sold.id, "email": "not-an-email"})
    check("非法 email → 400", r.status_code == 400, r.text)
    r = client.post("/api/catalog/stock-notify", json={"variant_id": 999999, "email": "a@b.co"})
    check("未知变体 → 404", r.status_code == 404, r.text)

    r = client.delete("/api/catalog/stock-notify",
                      params={"variant_id": v_sold.id, "email": "emma@glow.test"})
    left = db.query(StockNotification).filter(StockNotification.variant_id == v_sold.id).count()
    check("DELETE 取消 → watching:false 且行删除",
          r.status_code == 200 and r.json() == {"watching": False} and left == 0, (r.text, left))
    r = client.get("/api/catalog/stock-notify",
                   params={"variant_id": v_sold.id, "email": "emma@glow.test"})
    check("取消后 GET watching=false", r.json() == {"watching": False}, r.text)

    # ============================================================
    print("\n== worker restock_notify ==")
    db.add(StockNotification(variant_id=v_sold.id, email="olivia@glow.test"))
    db.add(StockNotification(variant_id=v_sold.id, email="mia@glow.test"))
    db.add(StockNotification(variant_id=v_sold2.id, email="nora@glow.test"))  # 仍售罄 → 保持 pending
    db.commit()

    worker.restock_notify(db)
    db.expire_all()
    evs = db.query(OutboxEvent).filter(OutboxEvent.event_type == "stock.restocked").all()
    check("仍售罄时不出事件（pending 不触发）", len(evs) == 0, len(evs))

    db.get(Variant, v_sold.id).stock = 40  # 回补库存
    db.commit()
    worker.restock_notify(db)
    db.expire_all()
    evs = db.query(OutboxEvent).filter(OutboxEvent.event_type == "stock.restocked").all()
    want_keys = {"email", "variant_id", "sku", "product_title", "stock", "variant"}
    ok_payload = (len(evs) == 2 and all(e.aggregate_type == "stock"
                                        and want_keys <= set(e.payload)
                                        and e.payload["sku"] == "CB-SA-24"
                                        and e.payload["product_title"] == "Cherry Bomb"
                                        and e.payload["stock"] == 40 for e in evs))
    check("回补后 restock_notify → outbox stock.restocked ×2（payload 键齐 email/variant_id/sku/product_title/stock）",
          ok_payload, [(e.payload) for e in evs])
    sns = db.query(StockNotification).filter(StockNotification.variant_id == v_sold.id).all()
    check("notified_at 置位（防重复）", all(s.notified_at is not None for s in sns),
          [(s.email, s.notified_at) for s in sns])
    still = db.query(StockNotification).filter(StockNotification.variant_id == v_sold2.id).one()
    check("仍售罄变体的订阅保持 pending（notified_at=NULL）", still.notified_at is None, still.notified_at)
    check("[restock-notify] 日志含 pending/notified",
          any("[restock-notify] pending=" in m and "notified=" in m for m in cap.msgs))

    before = db.query(OutboxEvent).count()
    worker.restock_notify(db)
    db.expire_all()
    check("二次跑不重复（无新增事件）", db.query(OutboxEvent).count() == before)

    worker.consume_outbox(db)
    check("consume 渲染 restock_notify 邮件（日志含收件人与 Back in stock 主题）",
          any("to=olivia@glow.test" in m and "subject=Back in stock: Cherry Bomb" in m for m in email_logs())
          and any("to=mia@glow.test" in m for m in email_logs()),
          [m[:80] for m in email_logs()])
    db.expire_all()
    published = db.query(OutboxEvent).filter(OutboxEvent.event_type == "stock.restocked").all()
    check("restock 事件消费后 published=1", all(e.published == 1 for e in published))

    # ============================================================
    print("\n== 定时上架（查询时生效） ==")
    r = client.get("/api/catalog/products", params={"size": 100})
    d = r.json()
    check("前台列表不含未来商品（total=3，无 velvet-nights）",
          d["total"] == 3 and all(i["slug"] != "velvet-nights" for i in d["items"]),
          (d.get("total"), [i["slug"] for i in d["items"]]))
    check("前台详情 velvet-nights → 404",
          client.get("/api/catalog/products/velvet-nights").status_code == 404)
    r = client.get("/api/catalog/search", params={"q": "velvet"})
    check("前台搜索 velvet-nights 不命中", r.json()["products"] == [], r.json())
    check("过去/None published_at 正常可见（详情 200）",
          client.get("/api/catalog/products/bare-gems").status_code == 200
          and client.get("/api/catalog/products/ma-damn").status_code == 200)

    r = client.get("/api/admin/catalog/products", headers=H, params={"size": 100})
    items = {i["slug"]: i for i in r.json()["items"]}
    check("admin 列表含 velvet-nights 且 scheduled=true（未来可见运营侧）",
          "velvet-nights" in items and items["velvet-nights"]["scheduled"] is True,
          [s for s in items])
    check("admin 列表过去/None 商品 scheduled=false（纯加法布尔）",
          items["bare-gems"]["scheduled"] is False and items["ma-damn"]["scheduled"] is False)

    r = client.put(f"/api/admin/catalog/products/{p_past.id}", headers=H,
                   json={"published_at": (now + timedelta(days=3)).isoformat()})
    check("PUT published_at(ISO 字符串) 生效且返回 scheduled=true",
          r.status_code == 200 and r.json()["scheduled"] is True
          and r.json()["published_at"].startswith((now + timedelta(days=3)).isoformat()[:10]), r.text[:200])
    check("PUT 未来后前台详情 → 404", client.get("/api/catalog/products/bare-gems").status_code == 404)
    r = client.put(f"/api/admin/catalog/products/{p_past.id}", headers=H,
                   json={"published_at": None})
    check("PUT published_at=null → 前台恢复可见",
          r.status_code == 200 and r.json()["scheduled"] is False
          and client.get("/api/catalog/products/bare-gems").status_code == 200, r.text[:200])

    print("\n== worker publish_scheduled ==")
    worker.publish_scheduled(db)
    check("[publish-scheduled] 巡检日志含 upcoming（velvet 未来计数 1）",
          any("[publish-scheduled] upcoming=1" in m and "newly_visible=0" in m for m in cap.msgs),
          [m for m in cap.msgs if "publish-scheduled" in m])
    check("未来商品不发 product.published",
          db.query(OutboxEvent).filter(OutboxEvent.event_type == "product.published").count() == 0)

    wm = db.get(Setting, "last_publish_scan")
    wm.value = (utcnow() - timedelta(hours=1)).isoformat()  # 回拨水位模拟 velvet 到点
    db.commit()
    db.get(Product, p_velvet.id).published_at = utcnow() - timedelta(seconds=10)
    db.commit()
    worker.publish_scheduled(db)
    db.expire_all()
    pev = db.query(OutboxEvent).filter(OutboxEvent.event_type == "product.published").all()
    check("到点（published_at<=now 且过水位）→ outbox product.published（payload 含 slug/title）",
          len(pev) == 1 and pev[0].payload["slug"] == "velvet-nights"
          and pev[0].payload["title"] == "Velvet Nights", [e.payload for e in pev])
    before = db.query(OutboxEvent).filter(OutboxEvent.event_type == "product.published").count()
    worker.publish_scheduled(db)
    check("publish_scheduled 水位推进：二次跑不重复",
          db.query(OutboxEvent).filter(OutboxEvent.event_type == "product.published").count() == before)

db.close()
print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
