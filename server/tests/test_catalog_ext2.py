"""商品目录域回归自测（第二批）—— 修复项回归：
P0-1 变体改价后 price_min/max 重算正确（autoflush=False 需显式 flush）
P1-2 by-id 详情/变体兄弟：定时未到点商品不泄露
P1-4 slug/SKU check-then-insert 竞态 → IntegrityError 409（模拟预检失效）
P1-5 集合商品清单重复 product_id 去重 + 长度上限 422
P1-6 商品 PUT 不回写陈旧价格区间（有在售变体时忽略客户端值并重算）
P1-7 category_id 显式 null → 400 category_required
P1-8 单条 publish 与批量同口径（slug/分类校验）
P2-10 搜索/列表 q 长度上限 422
P2-11 变体初始库存写台账（StockMovement type=7 ref=create）
P2-12 媒体上传魔数校验（伪装图片 415）
P2-13 variant_referenced 购物车 LIKE 预筛（引用命中 409 / 未命中可删）
（GM_DB=sqlite:///test_catalog_ext2.sqlite + BigInteger→INTEGER 垫片）"""

import os
import sys
from datetime import timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DBF = ROOT / "test_catalog_ext2.sqlite"
for suffix in ("", "-wal", "-shm"):
    _f = Path(str(DBF) + suffix)
    if _f.exists():
        _f.unlink()
os.environ["GM_DB"] = "sqlite:///" + str(DBF).replace("\\", "/")
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, str(ROOT))

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
    Cart, Category, Collection, Product, StockMovement, User, Variant,
)
from app.domains.catalog import repository as repo  # noqa: E402

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
now = utcnow()

cat = Category(slug="reg-cat", name="Reg Cat")
db.add(cat)
db.flush()

# P0-1/P1-6 主商品：两在售变体
p_main = Product(slug="reg-main", title="Reg Main", category_id=cat.id, status=1,
                 price_min=1000, price_max=2000, hero_image="/img/m.jpg",
                 published_at=now - timedelta(days=1))
# P1-2 定时商品：status=1 但 published_at 在未来
p_future = Product(slug="reg-future", title="Reg Future", category_id=cat.id, status=1,
                   price_min=1500, price_max=1500, hero_image="/img/f.jpg",
                   published_at=now + timedelta(days=7))
# P1-8 单条 publish 校验用草稿：slug 为空 / 分类不存在
p_noslug = Product(slug="", title="No Slug", category_id=cat.id, status=0,
                   price_min=100, price_max=100)
p_nocat = Product(slug="reg-nocat", title="No Cat", category_id=999999, status=0,
                  price_min=100, price_max=100)
db.add_all([p_main, p_future, p_noslug, p_nocat])
db.flush()
v_a = Variant(product_id=p_main.id, sku="REG-MAIN-A", option1_value="Short Almond",
              option2_value="24 pcs", price=1000, stock=10)
v_b = Variant(product_id=p_main.id, sku="REG-MAIN-B", option1_value="Medium Square",
              option2_value="24 pcs", price=2000, stock=5)
v_f = Variant(product_id=p_future.id, sku="REG-FUTURE-A", option1_value="Short Almond",
              option2_value="24 pcs", price=1500, stock=3)
# v_free 挂草稿商品：仅供 P2-13 删除测试，不参与 p_main 价格区间
v_free = Variant(product_id=p_noslug.id, sku="REG-FREE-C", option1_value="Coffin",
                 option2_value="24 pcs", price=1200, stock=4)
db.add_all([v_a, v_b, v_f, v_free])

admin = User(email="reg@glowmag.test", name="Reg Admin", role=2, status=1,
             password_hash=hash_password("x"))
db.add(admin)
db.commit()
H = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}


def get_product(pid):
    r = client.get(f"/api/admin/catalog/products/{pid}", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


with TestClient(app) as client:

    print("== P0-1 变体改价 → price_min/max 重算（flush 后聚合可见）==")
    r = client.put(f"/api/admin/catalog/variants/{v_a.id}", headers=H,
                   json={"price": 3000})
    d = get_product(p_main.id)
    check("PUT 变体 1000→3000 后区间 (2000, 3000)",
          r.status_code == 200 and (d["price_min"], d["price_max"]) == (2000, 3000),
          (r.status_code, d.get("price_min"), d.get("price_max")))
    r = client.put(f"/api/admin/catalog/variants/{v_b.id}", headers=H,
                   json={"is_active": False})
    d = get_product(p_main.id)
    check("PUT 停用变体 B 后区间只算在售 (3000, 3000)",
          r.status_code == 200 and (d["price_min"], d["price_max"]) == (3000, 3000),
          (d.get("price_min"), d.get("price_max")))
    client.put(f"/api/admin/catalog/variants/{v_b.id}", headers=H,
               json={"is_active": True})

    print("== P1-6 商品 PUT 忽略客户端陈旧价格区间（有在售变体时重算）==")
    r = client.put(f"/api/admin/catalog/products/{p_main.id}", headers=H,
                   json={"price_min": 1, "price_max": 2, "title": "Reg Main v2"})
    d = r.json()
    check("PUT 带陈旧 price_min/max 被忽略并按在售变体重算",
          r.status_code == 200 and (d["price_min"], d["price_max"]) == (2000, 3000)
          and d["title"] == "Reg Main v2",
          (r.status_code, d.get("price_min"), d.get("price_max")))
    # 无在售变体商品：保留显式设置（test_a 契约）
    p_plain = Product(slug="reg-plain", title="Reg Plain", category_id=cat.id, status=1,
                      price_min=800, price_max=800, hero_image="/img/p.jpg",
                      published_at=now - timedelta(days=1))
    db.add(p_plain)
    db.commit()
    r = client.put(f"/api/admin/catalog/products/{p_plain.id}", headers=H,
                   json={"price_min": 850, "price_max": 880})
    check("无在售变体时 PUT 显式价格仍生效",
          r.status_code == 200 and (r.json()["price_min"], r.json()["price_max"]) == (850, 880),
          (r.status_code, r.json().get("price_min")))

    print("== P1-7 category_id 显式 null → 400 category_required ==")
    r = client.put(f"/api/admin/catalog/products/{p_main.id}", headers=H,
                   json={"category_id": None})
    check("PUT category_id=null → 400（不落 IntegrityError 500）",
          r.status_code == 400 and r.json().get("detail") == "category required",
          (r.status_code, r.text[:120]))

    print("== P1-2 定时商品 by-id / siblings 不泄露 ==")
    check("by-id 定时未到点 → 404",
          client.get(f"/api/catalog/products-by-id/{p_future.id}").status_code == 404)
    check("by-id 已到点 → 200",
          client.get(f"/api/catalog/products-by-id/{p_main.id}").status_code == 200)
    check("定时商品变体 siblings → 404",
          client.get(f"/api/catalog/variants/{v_f.id}/siblings").status_code == 404)
    check("在售商品变体 siblings → 200",
          client.get(f"/api/catalog/variants/{v_a.id}/siblings").status_code == 200)

    print("== P1-8 单条 publish 校验与批量同口径 ==")
    check("slug 为空 publish → 400 slug required",
          client.post(f"/api/admin/catalog/products/{p_noslug.id}/publish",
                      headers=H).status_code == 400)
    r = client.post(f"/api/admin/catalog/products/{p_nocat.id}/publish", headers=H)
    check("分类不存在 publish → 400 category not found",
          r.status_code == 400 and r.json().get("detail") == "category not found",
          (r.status_code, r.text[:120]))

    print("== P1-4 slug/SKU check-then-insert 竞态 → 409（预检失效模拟）==")
    _orig_slug_taken = repo.product_slug_taken
    repo.product_slug_taken = lambda d_, s: False  # 模拟并发窗口：预检全部放行
    try:
        body = {"slug": "reg-race", "title": "Race", "category_id": cat.id,
                "price_min": 100, "price_max": 100}
        r1 = client.post("/api/admin/catalog/products", headers=H, json=body)
        r2 = client.post("/api/admin/catalog/products", headers=H, json=body)
        check("并发撞 products.slug 唯一键 → 第二个 409 非 500",
              r1.status_code == 201 and r2.status_code == 409
              and r2.json().get("detail") == "slug already exists",
              (r1.status_code, r2.status_code, r2.text[:120]))
    finally:
        repo.product_slug_taken = _orig_slug_taken
    _orig_sku_taken = repo.variant_sku_taken
    repo.variant_sku_taken = lambda d_, s: False
    try:
        vbody = {"sku": "REG-RACE-SKU", "option1_value": "Almond",
                 "option2_value": "24 pcs", "price": 100, "stock": 3}
        r1 = client.post(f"/api/admin/catalog/products/{p_main.id}/variants",
                         headers=H, json=vbody)
        r2 = client.post(f"/api/admin/catalog/products/{p_main.id}/variants",
                         headers=H, json=vbody)
        check("并发撞 variants.sku 唯一键 → 第二个 409 非 500",
              r1.status_code == 201 and r2.status_code == 409
              and r2.json().get("detail") == "sku already exists",
              (r1.status_code, r2.status_code, r2.text[:120]))
    finally:
        repo.variant_sku_taken = _orig_sku_taken

    print("== P1-5 集合商品清单去重 + 长度上限 ==")
    r = client.post("/api/admin/catalog/collections", headers=H,
                    json={"slug": "reg-set", "title": "Reg Set", "rule_json": {}})
    cid = r.json()["id"]
    r = client.put(f"/api/admin/catalog/collections/{cid}/products", headers=H,
                   json={"products": [
                       {"product_id": p_main.id, "sort_order": 0},
                       {"product_id": p_plain.id, "sort_order": 1},
                       {"product_id": p_main.id, "sort_order": 2},
                   ]})
    check("重复 product_id 去重（保留首次）→ 200 且 count=2",
          r.status_code == 200 and r.json().get("count") == 2, r.text[:160])
    d = client.get(f"/api/admin/catalog/collections/{cid}/products", headers=H).json()
    check("清单落库 2 行且顺序保留（main 在前）",
          [i["product_id"] for i in d["items"]] == [p_main.id, p_plain.id],
          [i["product_id"] for i in d["items"]])
    big = {"products": [{"product_id": p_main.id, "sort_order": i} for i in range(201)]}
    check("products 超 200 条 → 422",
          client.put(f"/api/admin/catalog/collections/{cid}/products",
                     headers=H, json=big).status_code == 422)

    print("== P2-10 搜索/列表 q 长度上限 ==")
    check("/search q=100 字符 → 200",
          client.get("/api/catalog/search", params={"q": "x" * 100}).status_code == 200)
    check("/search q=101 字符 → 422",
          client.get("/api/catalog/search", params={"q": "x" * 101}).status_code == 422)
    check("/products q=101 字符 → 422",
          client.get("/api/catalog/products", params={"q": "x" * 101}).status_code == 422)

    print("== P2-11 变体初始库存写台账 ==")
    r = client.post(f"/api/admin/catalog/products/{p_plain.id}/variants", headers=H,
                    json={"sku": "REG-PLAIN-S1", "option1_value": "Almond",
                          "option2_value": "24 pcs", "price": 850, "stock": 7})
    vid_ledger = r.json()["id"]
    mv = db.query(StockMovement).filter(StockMovement.variant_id == vid_ledger).all()
    check("stock=7 创建 → 台账 1 行（change/stock_after=7, type=7 手工, ref=create）",
          len(mv) == 1 and mv[0].change == 7 and mv[0].stock_after == 7
          and mv[0].type == 7 and mv[0].ref_type == "create",
          [(m.change, m.stock_after, m.type, m.ref_type) for m in mv])
    r = client.post(f"/api/admin/catalog/products/{p_plain.id}/variants", headers=H,
                    json={"sku": "REG-PLAIN-S0", "option1_value": "Square",
                          "option2_value": "24 pcs", "price": 850, "stock": 0})
    n0 = db.query(StockMovement).filter(
        StockMovement.variant_id == r.json()["id"]).count()
    check("stock=0 创建 → 不写台账", n0 == 0, n0)

    print("== P2-13 variant_referenced 购物车预筛 ==")
    # 车 1 含 v_a（阻断删除 v_a）；车 2 只含无关变体（不应阻断删除 v_free）
    db.add(Cart(session_id="tok-reg", items=[{"variantId": v_a.id, "qty": 1}]))
    db.add(Cart(session_id="tok-reg2", items=[{"variantId": v_f.id, "qty": 2}]))
    db.commit()
    check("车含变体 A → DELETE A 409 in use",
          client.delete(f"/api/admin/catalog/variants/{v_a.id}",
                        headers=H).status_code == 409)
    r = client.delete(f"/api/admin/catalog/variants/{v_free.id}", headers=H)
    check("车不含变体 C → DELETE C 200（预筛排除无关车行）",
          r.status_code == 200 and r.json().get("ok") is True, r.text[:120])

    print("== P2-12 媒体上传魔数校验 ==")
    r = client.post("/api/admin/media/upload", headers=H,
                    files={"file": ("fake.png", b"not-a-png-at-all", "image/png")})
    check("伪装 png（扩展名/CT 合法，文件头非 PNG）→ 415",
          r.status_code == 415, (r.status_code, r.text[:120]))
    r = client.post("/api/admin/media/upload", headers=H,
                    files={"file": ("fake.webp", b"RIFFxxxxWAVP", "image/webp")})
    check("RIFF 但非 WEBP → 415", r.status_code == 415, (r.status_code, r.text[:120]))
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 16
    r = client.post("/api/admin/media/upload", headers=H,
                    files={"file": ("real.png", png_bytes, "image/png")})
    url = r.json().get("url") if r.status_code == 200 else None
    check("真 PNG 头 → 200 且返回 /static/uploads URL",
          r.status_code == 200 and url and url.startswith("/static/uploads/"),
          (r.status_code, r.text[:160]))
    if url:  # 清理测试落盘文件（月目录留予后续上传复用）
        try:
            os.remove(ROOT / url.lstrip("/"))
        except OSError:
            pass

db.close()

print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
