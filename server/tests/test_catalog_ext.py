"""商品目录域扩展自测 —— 价格区间/on_sale 筛选（GM_CACHE=1 验证新参数进缓存键不串）
+ 评价分布端点（仅 status=1）+ 磁吸睫毛种子幂等（老库补挂 + 子进程全量 seed 两轮）
（GM_DB=sqlite:///test_catalog_ext.sqlite + BigInteger→INTEGER 垫片）"""

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DBF = ROOT / "test_catalog_ext.sqlite"
for suffix in ("", "-wal", "-shm"):
    _f = Path(str(DBF) + suffix)
    if _f.exists():
        _f.unlink()
os.environ["GM_DB"] = "sqlite:///" + str(DBF).replace("\\", "/")
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
os.environ["GM_CACHE"] = "1"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


from app.core.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Product, Review, Variant  # noqa: E402
from app.services.cache import _cache  # noqa: E402

import seed  # noqa: E402

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

cat_nails = Category(slug="press-on-nails", name="Press-on Nails")
db.add(cat_nails)
db.flush()

# 三档价位商品：low [999,1099] compare<=price_min（假促销）；mid [1399,1599] compare>price_min（真促销）；high [1999,2199] 无 compare
p_low = Product(slug="price-low", title="Price Low", category_id=cat_nails.id, status=1,
                price_min=999, price_max=1099, compare_at_price=899, hero_image="/img/low.jpg",
                published_at=now - timedelta(days=3))
p_mid = Product(slug="price-mid", title="Price Mid", category_id=cat_nails.id, status=1,
                price_min=1399, price_max=1599, compare_at_price=1999, hero_image="/img/mid.jpg",
                published_at=now - timedelta(days=2))
p_high = Product(slug="price-high", title="Price High", category_id=cat_nails.id, status=1,
                 price_min=1999, price_max=2199, hero_image="/img/high.jpg",
                 published_at=now - timedelta(days=1))
db.add_all([p_low, p_mid, p_high])
db.flush()
for p, price in ((p_low, 999), (p_mid, 1399), (p_high, 1999)):
    db.add(Variant(product_id=p.id, sku=f"{p.slug.upper()}-SA", option1_value="Short Almond",
                   option2_value="24 pcs", price=price, stock=40))
# p_mid 补 Medium Square 变体（+200，siblings/shape=short 词测试用）
db.add(Variant(product_id=p_mid.id, sku=f"{p_mid.slug.upper()}-MS", option1_value="Medium Square",
               option2_value="24 pcs", price=1599, stock=25))
# p_low 补停用变体 Stiletto（is_active=0：shape 筛选与 siblings 均不应命中）
db.add(Variant(product_id=p_low.id, sku=f"{p_low.slug.upper()}-ST", option1_value="Stiletto",
               option2_value="24 pcs", price=1199, stock=10, is_active=0))
# 下架商品（status=2）：variants siblings → 404；列表/shape 均不可见
p_off = Product(slug="price-off", title="Price Off", category_id=cat_nails.id, status=2,
                price_min=1099, price_max=1299, hero_image="/img/off.jpg",
                published_at=now - timedelta(days=1))
db.add(p_off)
db.flush()
db.add(Variant(product_id=p_off.id, sku="PRICE-OFF-SA", option1_value="Short Almond",
               option2_value="24 pcs", price=1099, stock=30))

# 评价（mid 商品）：2×5★ + 1×4★ 已发布；3★ 待审（status=0）/ 1★ 拒绝（status=2）不计入
for i, (rating, status) in enumerate([(5, 1), (5, 1), (4, 1), (3, 0), (1, 2)]):
    db.add(Review(product_id=p_mid.id, user_id=1, order_item_id=9000 + i, rating=rating,
                  content=f"review {i}", status=status, created_at=now - timedelta(hours=i + 1)))
db.commit()

print("== 磁吸睫毛种子（老库补挂 + 幂等）==")
lash_slugs = [row[0] for row in seed.LASHES]
added = seed._seed_lashes(db)
n_lash = db.query(Product).filter(Product.slug.in_(lash_slugs)).count()
check("老库（有商品无睫毛）补挂 3 款", added == 3 and n_lash == 3, (added, n_lash))
cat_lash = db.query(Category).filter(Category.slug == "magnetic-lashes").first()
lash_pids = [p.id for p in db.query(Product).filter(Product.slug.in_(lash_slugs))]
n_var = db.query(Variant).filter(Variant.product_id.in_(lash_pids)).count()
check("睫毛分类 get-or-create 且每款 2 变体有库存",
      cat_lash is not None and n_var == 6
      and all(v.stock > 0 for v in db.query(Variant).filter(Variant.product_id.in_(lash_pids))),
      (cat_lash, n_var))
check("二次补种幂等（不重复建）", seed._seed_lashes(db) == 0
      and db.query(Product).filter(Product.slug.in_(lash_slugs)).count() == 3)
lash_pub = db.query(Product).filter(Product.slug.in_(lash_slugs)).all()
check("睫毛 price_min 999-1599 档 + tags 含 cat-eye/lashes",
      {p.price_min for p in lash_pub} == {999, 1299, 1599}
      and all({"cat-eye", "lashes"} <= set(p.tags) for p in lash_pub),
      [(p.slug, p.price_min, p.tags) for p in lash_pub])

_cache.clear()

with TestClient(app) as client:
    def listing(params):
        r = client.get("/api/catalog/products", params=params)
        assert r.status_code == 200, r.text
        return r.json()

    print("\n== 价格区间筛选（交集语义）==")
    d = listing({"size": 50})
    check("基线 6 款可见（3 价位 + 3 睫毛）",
          d["total"] == 6 and {i["slug"] for i in d["items"]} ==
          {"price-low", "price-mid", "price-high", "venus-lash", "aurora-lash", "midnight-lash"},
          (d.get("total"), [i["slug"] for i in d["items"]]))
    check("卡片结构只增不改（price_min/compare_at_price/tags 键仍在）",
          {"price_min", "price_max", "compare_at_price", "tags"} <= set(d["items"][0]))

    d = listing({"min_price": 1200, "max_price": 1500, "size": 50})
    check("双侧区间交集（含跨界 venus-lash[1299,1499]）",
          d["total"] == 2 and {i["slug"] for i in d["items"]} == {"price-mid", "venus-lash"},
          [i["slug"] for i in d["items"]])
    d = listing({"min_price": 1500, "size": 50})
    check("仅 min_price 半开（price_max>=1500）",
          d["total"] == 3 and {i["slug"] for i in d["items"]} ==
          {"price-mid", "price-high", "midnight-lash"}, [i["slug"] for i in d["items"]])
    d = listing({"max_price": 1000, "size": 50})
    check("仅 max_price 半开（price_min<=1000）",
          d["total"] == 2 and {i["slug"] for i in d["items"]} == {"price-low", "aurora-lash"},
          [i["slug"] for i in d["items"]])
    d = listing({"min_price": 2199, "size": 50})
    check("闭区间边界（price_max==min_price 命中）",
          d["total"] == 1 and d["items"][0]["slug"] == "price-high", d.get("total"))
    d = listing({"max_price": 999, "size": 50})
    check("闭区间边界（price_min==max_price 命中）",
          d["total"] == 2 and {i["slug"] for i in d["items"]} == {"price-low", "aurora-lash"})
    r = client.get("/api/catalog/products", params={"min_price": -1})
    check("min_price 负数 422", r.status_code == 422)

    print("\n== on_sale 筛选与 WHERE 组合（AND）==")
    d = listing({"on_sale": "true", "size": 50})
    check("on_sale：compare 非空且 > price_min（假促销 price-low/无划线价排除）",
          d["total"] == 3 and {i["slug"] for i in d["items"]} ==
          {"price-mid", "venus-lash", "midnight-lash"}, [i["slug"] for i in d["items"]])
    d = listing({"on_sale": "true", "category": "press-on-nails", "size": 50})
    check("on_sale AND category 组合", d["total"] == 1 and d["items"][0]["slug"] == "price-mid")
    d = listing({"tag": "cat-eye", "min_price": 1500, "size": 50})
    check("tag AND min_price 组合", d["total"] == 1 and d["items"][0]["slug"] == "midnight-lash")
    check("不带新参数默认行为不变（total=6）", listing({"size": 50})["total"] == 6)

    print("\n== 缓存键覆盖新参数（GM_CACHE=1 不串缓存）==")
    st = _cache.stats()
    d_again = listing({"min_price": 1200, "max_price": 1500, "size": 50})
    check("同参重复命中缓存且结果一致",
          _cache.stats()["hits"] == st["hits"] + 1 and d_again["total"] == 2)
    check("各参数组合独立入缓存（键数随组合增长）", _cache.stats()["size"] >= 8, _cache.stats())

    print("\n== 评价分布端点 ==")
    r = client.get("/api/catalog/reviews/distribution", params={"product_id": p_mid.id})
    check("分布只统计已发布（rating_avg ×100 口径，待审/拒绝排除）",
          r.status_code == 200 and r.json() == {
              "product_id": p_mid.id, "rating_avg": 467, "rating_count": 3,
              "distribution": {"1": 0, "2": 0, "3": 0, "4": 1, "5": 2}}, r.json())
    r = client.get("/api/catalog/reviews/distribution", params={"product_id": p_low.id})
    check("无评价商品全 0 且 5 档键齐",
          r.json()["rating_avg"] == 0 and r.json()["rating_count"] == 0
          and r.json()["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}, r.json())
    r = client.get("/api/catalog/reviews", params={"product_id": p_mid.id})
    check("/reviews 原端点不受影响（total=3）", r.json()["total"] == 3)

    print("\n== 睫毛分类非空（前台导航不再空页）==")
    d = listing({"category": "magnetic-lashes", "size": 50})
    check("category=magnetic-lashes 返回 3 款", d["total"] == 3
          and {i["slug"] for i in d["items"]} == set(lash_slugs), d.get("total"))
    check("前台卡片 is_new/best 有分布", {i["is_new"] for i in d["items"]} <= {True, False}
          and any(i["is_best_seller"] for i in d["items"]))

    print("\n== shape 筛选（变体 EXISTS ilike，短词命中复合值）==")
    d = listing({"shape": "almond", "size": 50})
    check("shape=almond 命中 Short Almond 三价位款",
          d["total"] == 3 and {i["slug"] for i in d["items"]} ==
          {"price-low", "price-mid", "price-high"}, [i["slug"] for i in d["items"]])
    d = listing({"shape": "SQUARE", "size": 50})
    check("shape 大小写不敏感（SQUARE → price-mid）",
          d["total"] == 1 and d["items"][0]["slug"] == "price-mid", d.get("total"))
    d = listing({"shape": "cat", "size": 50})
    check("shape 短词部分匹配（cat → Natural Cat 睫毛 3 款）",
          d["total"] == 3 and {i["slug"] for i in d["items"]} == set(lash_slugs),
          [i["slug"] for i in d["items"]])
    d = listing({"shape": "stiletto", "size": 50})
    check("shape 命中停用变体不算（is_active=0 排除）且下架商品不可见", d["total"] == 0,
          d.get("total"))
    d = listing({"shape": "unknown-shape-xyz", "size": 50})
    check("未知 shape → 空集不 400", d["total"] == 0 and d["items"] == [], d.get("total"))
    d = listing({"shape": "almond", "tag": "cat-eye", "size": 50})
    check("shape AND tag 组合（交集空）", d["total"] == 0, d.get("total"))
    check("shape 空串 422（min_length=1）",
          client.get("/api/catalog/products", params={"shape": ""}).status_code == 422)
    check("shape 超长 422（max_length=50）",
          client.get("/api/catalog/products", params={"shape": "x" * 51}).status_code == 422)
    check("不带 shape 默认行为不变（total=6）", listing({"size": 50})["total"] == 6)

    print("\n== reviews rating 筛选（仅已发布）==")
    r = client.get("/api/catalog/reviews", params={"product_id": p_mid.id, "rating": 5})
    check("rating=5 → 仅已发布 5★（2 条）",
          r.status_code == 200 and r.json()["total"] == 2
          and all(i["rating"] == 5 for i in r.json()["items"]), r.json()["total"])
    r = client.get("/api/catalog/reviews", params={"product_id": p_mid.id, "rating": 4})
    check("rating=4 → 1 条", r.json()["total"] == 1, r.json()["total"])
    r = client.get("/api/catalog/reviews", params={"product_id": p_mid.id, "rating": 3})
    check("rating=3 → 0（待审 3★ 不计）", r.json()["total"] == 0, r.json()["total"])
    r = client.get("/api/catalog/reviews", params={"product_id": p_mid.id, "rating": 1})
    check("rating=1 → 0（拒绝 1★ 不计）", r.json()["total"] == 0, r.json()["total"])
    check("rating=0 / 6 → 422",
          client.get("/api/catalog/reviews",
                     params={"product_id": p_mid.id, "rating": 0}).status_code == 422
          and client.get("/api/catalog/reviews",
                         params={"product_id": p_mid.id, "rating": 6}).status_code == 422)
    check("不带 rating 原行为（total=3）",
          client.get("/api/catalog/reviews", params={"product_id": p_mid.id}).json()["total"] == 3)

    print("\n== 变体兄弟端点 GET /variants/{id}/siblings ==")
    v_mid = (db.query(Variant)
             .filter(Variant.product_id == p_mid.id,
                     Variant.option1_value == "Short Almond").first())
    v_off = db.query(Variant).filter(Variant.product_id == p_off.id).first()
    r = client.get(f"/api/catalog/variants/{v_mid.id}/siblings")
    d = r.json()
    check("200 且锚定信息齐全（variant_id/product_id/slug/title）",
          r.status_code == 200 and d["variant_id"] == v_mid.id
          and d["product_id"] == p_mid.id and d["slug"] == "price-mid"
          and d["title"] == "Price Mid", d)
    check("兄弟列表=同商品启用变体（SA+MS，停用 Stiletto 排除）且 _variant_out 结构",
          len(d["variants"]) == 2
          and {v["option1_value"] for v in d["variants"]} == {"Short Almond", "Medium Square"}
          and {"id", "sku", "price", "stock", "safety_stock", "option1_value",
               "option2_value", "stock_status", "images"} <= set(d["variants"][0]),
          [v["option1_value"] for v in d["variants"]])
    r = client.get("/api/catalog/variants/999999/siblings")
    check("变体不存在 → 404", r.status_code == 404, r.status_code)
    r = client.get(f"/api/catalog/variants/{v_off.id}/siblings")
    check("商品下架（status=2）→ 404", r.status_code == 404, r.status_code)

db.close()

print("\n== 全量 seed 幂等（子进程，独立 sqlite 两轮） ==")
SEED_DB = ROOT / "test_seed_ext.sqlite"
for suffix in ("", "-wal", "-shm"):
    _f = Path(str(SEED_DB) + suffix)
    if _f.exists():
        _f.unlink()


def run_seed(tag: str):
    env = {k: v for k, v in os.environ.items() if k != "GM_CACHE"}
    env["GM_DB"] = "sqlite:///" + str(SEED_DB).replace("\\", "/")
    env["PYTHONIOENCODING"] = "utf-8"
    root_s = str(ROOT).replace("\\", "/")
    lash_list = ",".join(f"'{sl}'" for sl in lash_slugs)
    probe = "\n".join([
        "import sys",
        f"sys.path.insert(0, r'{root_s}')",
        f"sys.path.insert(0, r'{root_s}/scripts')",
        "from sqlalchemy import BigInteger",
        "from sqlalchemy.ext.compiler import compiles",
        "def _shim(t, c, **kw):",
        "    return 'INTEGER'",
        "compiles(BigInteger, 'sqlite')(_shim)",
        "import seed",
        "seed.seed()",
        "from app.core.db import SessionLocal",
        "from app.models import Product, Variant, Referral, Setting",
        "s = SessionLocal()",
        f"lash = s.query(Product).filter(Product.slug.in_([{lash_list}])).count()",
        "prods = s.query(Product).count()",
        "vars_ = s.query(Variant).count()",
        "stile = s.query(Variant).filter(Variant.option1_value == 'Stiletto').count()",
        "coffin = s.query(Variant).filter(Variant.option1_value == 'Coffin').count()",
        "refs = s.query(Referral).count()",
        "site = s.get(Setting, 'site_url').value",
        f"print('{tag} lash=%d products=%d variants=%d stiletto=%d coffin=%d referrals=%d site=%s' "
        "% (lash, prods, vars_, stile, coffin, refs, site))",
        "s.close()",
    ])
    return subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))


EXPECT_SEED = ("lash=3 products=17 variants=59 stiletto=13 coffin=13 "
               "referrals=1 site=http://localhost:5173")
r1 = run_seed("SEED-FRESH")
check("空库首跑 seed done 且四型甲片/推荐/site_url 齐（" + EXPECT_SEED + "）",
      r1.returncode == 0 and "seed done" in r1.stdout
      and f"SEED-FRESH {EXPECT_SEED}" in r1.stdout,
      (r1.stdout[-400:] + r1.stderr[-400:]))
r2 = run_seed("SEED-RERUN")
check("重复执行总防重跳过（products exist, skip）且不重复建",
      r2.returncode == 0 and "products exist, skip" in r2.stdout
      and f"SEED-RERUN {EXPECT_SEED}" in r2.stdout,
      (r2.stdout[-400:] + r2.stderr[-400:]))

print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
